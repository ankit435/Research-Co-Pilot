import json
import logging
import asyncio
import os
import shutil
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import uuid
from phi.agent import Agent
from phi.model.groq import Groq
from phi.tools.duckduckgo import DuckDuckGo
#from phi.tools.yfinance import YFinanceTools
from rich.prompt import Prompt
import typer
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer
from dataclasses import dataclass, asdict, field
from abc import ABC, abstractmethod
from . import consumers
from . import pdfchatBot
from dotenv import load_dotenv



load_dotenv()


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UUIDEncoder(json.JSONEncoder):
    """Custom JSON encoder for UUID objects"""
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)

def serialize_uuid(obj: Any) -> Any:
    """Helper function to serialize UUIDs in dictionaries"""
    if isinstance(obj, dict):
        return {k: serialize_uuid(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_uuid(item) for item in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj

class MessageType(Enum):
    TEXT = 'TEXT'
    SYSTEM = 'SYSTEM'
    AI = 'AI'
    IMAGE = 'IMAGE'
    FILE = 'FILE'
    MULTIPLE = 'MULTIPLE'

class MessageStatus(Enum):
    SENT = 'SENT'
    DELIVERED = 'DELIVERED'
    READ = 'READ'
    FAILED = 'FAILED'

@dataclass
class Attachment:
    id: str
    file_type: str
    file_name: str
    file_path: str
    file_size: int
    created_at: str
    file: Optional[str] = None

    def to_dict(self) -> dict:
        return serialize_uuid(asdict(self))

@dataclass
class User:
    id: str
    username: str
    email: str
    profile_image: Optional[str] = None
    is_active: bool = True
    first_name: str = ''
    last_name: str = ''

    def to_dict(self) -> dict:
        return serialize_uuid(asdict(self))

@dataclass
class MessageReceipt:
    id: str
    user: Dict[str, Any]
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None

    def to_dict(self) -> dict:
        return serialize_uuid(asdict(self))

@dataclass
class ChatMessage:
    id: str
    sender: Dict[str, Any]
    text_content: str
    content: Dict[str, Any]
    message_type: str
    status: str
    created_at: str
    updated_at: str
    attachments: List[Dict] = field(default_factory=list)
    reply_to: Optional[str] = None
    reply_to_message: Optional[Dict] = None
    deleted_at: Optional[str] = None
    receipts: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return serialize_uuid(data)

@dataclass
class ChatSession:
    id: str
    type: str
    name: str
    avatar: str
    members: List[Dict[str, Any]]
    messages: List[Dict]
    last_message: str = ""
    time: str = ""
    unread: int = 0
    member_count: int = 2
    sender: Optional[str] = None
    profile_image: Optional[str] = None

    def to_dict(self) -> dict:
        return serialize_uuid(asdict(self))

class AIChatConsumer(AsyncWebsocketConsumer):
    active_chats: Dict[str, Dict[str, Any]] = {}
    chatbot_instances: Dict[str, Dict[str, pdfchatBot.PDFChatbot]] = {}
    channel_sessions: Dict[str, Dict[str, str]] = {}  # user_id -> {channel -> session_id}
    
    AI_ASSISTANT = {
        "id": str(uuid.uuid4()),
        "username": "AI Assistant",
        "email": "ai@assistant.com",
        "profile_image": None,
        "is_active": True,
        "first_name": "AI",
        "last_name": "Assistant"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_channel = None
        self.user = None
        
    async def connect(self):
        try:
            self.user = self.scope["user"]
            if not self.user.is_authenticated:
                logger.error("Unauthenticated user attempted to connect")
                await self.close()
                return
            
            # Create unique channel name
            unique_id = str(uuid.uuid4())
            self.user_channel = f'ai_chat_{self.user.id}_{unique_id}'
            
            user_id = str(self.user.id)
            if user_id not in self.channel_sessions:
                self.channel_sessions[user_id] = {}
            
            if user_id not in self.active_chats:
                self.active_chats[user_id] = {}
            
            await self.channel_layer.group_add(self.user_channel, self.channel_name)
            await self.accept()
            logger.info(f"User {self.user.id} connected to AI chat with channel {self.user_channel}")
            
        except Exception as e:
            logger.error(f"Error in AI chat connect: {str(e)}", exc_info=True)
            await self.close()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'user_channel') and hasattr(self, 'user'):
                user_id = str(self.user.id)
                
                # Clean up channel tracking
                if user_id in self.channel_sessions:
                    self.channel_sessions[user_id].pop(self.user_channel, None)
                    if not self.channel_sessions[user_id]:
                        del self.channel_sessions[user_id]
                
                await self.channel_layer.group_discard(
                    self.user_channel,
                    self.channel_name
                )
                
                logger.info(f"User {user_id} disconnected channel {self.user_channel}")
                
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}", exc_info=True)

    async def cleanup_on_logout(self, event):
        try:
            user_id = str(self.user.id)
            if user_id in self.chatbot_instances:
                for session_id, chatbot in self.chatbot_instances[user_id].items():
                    index_path = os.path.join(settings.BASE_DIR, f'FissIndex/faiss_index_{user_id}_{session_id}')
                    if os.path.exists(index_path):
                        shutil.rmtree(index_path)
                del self.chatbot_instances[user_id]
                
            if user_id in self.channel_sessions:
                del self.channel_sessions[user_id]
                
            if user_id in self.active_chats:
                del self.active_chats[user_id]
                
            logger.info(f"User {user_id} sessions and channels cleaned up on logout")
                
        except Exception as e:
            logger.error(f"Error in logout cleanup: {str(e)}", exc_info=True)

    def generate_session_id(self) -> str:
        return str(uuid.uuid4())

    async def create_new_session(self) -> ChatSession:
        session_id = self.generate_session_id()
        user_data = {
            "id": str(self.user.id),
            "username": self.user.username,
            "email": self.user.email,
            "profile_image": getattr(self.user, 'profile_image', None),
            "is_active": True,
            "first_name": getattr(self.user, 'first_name', ''),
            "last_name": getattr(self.user, 'last_name', '')
        }
        
        session = ChatSession(
            id=session_id,
            type="private",
            name="AI Assistant",
            avatar="AI",
            members=[user_data, self.AI_ASSISTANT],
            messages=[],
            sender=self.user.username,
            profile_image=user_data["profile_image"]
        )
        
        user_id = str(self.user.id)
        self.active_chats[user_id][session_id] = session.to_dict()
        
        # Associate channel with new session
        self.channel_sessions[user_id][self.user_channel] = session_id
        
        return session

    async def send(self, text_data=None, bytes_data=None):
        if text_data is not None:
            if isinstance(text_data, str):
                text_data = json.loads(text_data)
            await super().send(text_data=json.dumps(text_data, cls=UUIDEncoder))
        else:
            await super().send(bytes_data=bytes_data)

    async def send_message_to_channel(self, message_data: Dict):
        try:
            user_id = str(self.user.id)
            session_id = message_data.get('session_id')
            
            if (user_id in self.channel_sessions and 
                self.user_channel in self.channel_sessions[user_id] and
                self.channel_sessions[user_id][self.user_channel] == session_id):
                
                await self.channel_layer.group_send(
                    self.user_channel,
                    message_data
                )
            
        except Exception as e:
            logger.error(f"Error sending message to channel: {str(e)}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            session_id = data.get('session_id')
            message_type = data.get('message_type', MessageType.TEXT.value)

            if not consumers.validate_message_data(message_type, data):
                await self.send({
                    'type': 'error',
                    'message': 'Invalid message data'
                })
                return

            user_id = str(self.user.id)
            
            # Handle session management
            if session_id:
                # If session exists but channel mapping doesn't, establish new channel
                if user_id in self.active_chats and session_id in self.active_chats[user_id]:
                    if user_id not in self.channel_sessions:
                        self.channel_sessions[user_id] = {}
                    # Map current channel to this session
                    self.channel_sessions[user_id][self.user_channel] = session_id
                else:
                    # Create new session if doesn't exist
                    session = await self.create_new_session()
                    session_id = session.id
                    await self.send({
                        'type': 'chat_created',
                        'chat_id': session_id,
                        'message': 'New chat session created successfully'
                    })
            else:
                # No session_id provided, create new session
                session = await self.create_new_session()
                session_id = session.id
                await self.send({
                    'type': 'chat_created',
                    'chat_id': session_id,
                    'message': 'New chat session created successfully'
                })

            # Process new message if session is valid
            if (user_id in self.channel_sessions and 
                self.user_channel in self.channel_sessions[user_id] and
                self.channel_sessions[user_id][self.user_channel] == session_id):
                
                message = await self.save_message(data, session_id, is_ai=False)
                if message:
                    chat_session = self.active_chats[user_id][session_id]
                    chat_session["lastMessage"] = message["text_content"]
                    chat_session["time"] = datetime.now().strftime("%I:%M:%S %p")
                    
                    await self.send_message_to_channel({
                        'type': 'chat_message',
                        'session_id': session_id,
                        'message': message,
                        'is_ai': False
                    })

                    asyncio.create_task(
                        self.process_ai_response(message['text_content'], session_id, message, data)
                    )
            else:
                await self.send({
                    'type': 'error',
                    'message': 'Invalid session ID'
                })
                        
        except json.JSONDecodeError:
            logger.error("Invalid JSON in chat message")
            await self.send({
                'type': 'error',
                'message': 'Invalid message format'
            })
        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}", exc_info=True)
            await self.send({
                'type': 'error',
                'message': 'Internal server error'
            })
    
    
    
    async def save_message(self, data: Dict, session_id: str, is_ai: bool = False) -> Dict:
        try:
            chat_session = self.active_chats[str(self.user.id)][session_id]
            timestamp = datetime.now().isoformat()
            
            sender = self.AI_ASSISTANT if is_ai else chat_session["members"][0]
            message_id = str(uuid.uuid4())
            
            file_data = data.get('file', {})
            attachments = []
            if file_data:
                attachment = Attachment(
                    id=str(uuid.uuid4()),
                    file_type=file_data.get('type', ''),
                    file_name=file_data.get('name', ''),
                    file_path=file_data.get('path', ''),
                    file_size=file_data.get('size', 0),
                    created_at=timestamp
                )
                attachments = [attachment.to_dict()]

            receipt = MessageReceipt(
                id=str(uuid.uuid4()),
                user=self.AI_ASSISTANT if not is_ai else chat_session["members"][0]
            )

            message = ChatMessage(
                id=message_id,
                sender=sender,
                text_content=data.get('text', ''),
                content=data.get('content', {}),
                message_type=data.get('message_type', MessageType.TEXT.value),
                status=MessageStatus.SENT.value,
                created_at=timestamp,
                updated_at=timestamp,
                attachments=attachments,
                receipts=[receipt.to_dict()],
                metadata={}
            )
            
            message_dict = message.to_dict()
            chat_session["messages"].append(message_dict)
            return message_dict
            
        except Exception as e:
            logger.error(f"Error saving chat message: {str(e)}")
            return None

    async def initialize_chatbot(self, user_id: str, session_id: str):
        """Initialize a new PDFChatbot instance for a session."""
        if user_id not in self.chatbot_instances:
            self.chatbot_instances[user_id] = {}
        
        if session_id not in self.chatbot_instances[user_id]:
            groq_api_key = os.getenv('GROQ_API_KEY') 
            index_path = f'faiss_index_{user_id}_{session_id}'
            
            try:
                # Verify channel is still valid before initializing
                if (user_id not in self.channel_sessions or
                    self.user_channel not in self.channel_sessions[user_id] or
                    self.channel_sessions[user_id][self.user_channel] != session_id):
                    logger.info(f"Skipping chatbot initialization for inactive session {session_id}")
                    return
                    
                self.chatbot_instances[user_id][session_id] = await asyncio.to_thread(
                    pdfchatBot.PDFChatbot,
                    groq_api_key=groq_api_key,
                    index_path=index_path
                )
                logger.info(f"Initialized chatbot for user {user_id} session {session_id}")
                
            except Exception as e:
                logger.error(f"Error initializing chatbot for session {session_id}: {e}", exc_info=True)
                raise


    def suppress_output(func):
        with open(os.devnull, 'w') as fnull:
            with redirect_stdout(fnull):
                func()

    async def process_ai_response(self, user_message: str, session_id: str, message: Dict, data):
        try:
            if data["ai_agent"] == 'pdf_agent':
                user_id = str(self.user.id)
                chat_session = self.active_chats[user_id][session_id]

                # Initialize chatbot if not exists
                await self.initialize_chatbot(user_id, session_id)
                chatbot = self.chatbot_instances[user_id][session_id]

                print("sesssioID", session_id, chatbot.chat_history)

                # Handle file attachments (PDF processing)
                if message['attachments']:
                    file_path = message['attachments'][0]['file_path']
                    if file_path:
                        # Process PDF and get summary
                        summary = await asyncio.to_thread(chatbot.process_pdf, file_path)

                        # Save the summary as AI response
                        ai_message = await self.save_message({
                            'text': f"I've processed the PDF. Here's a summary:\n\n{summary}",
                            'message_type': MessageType.AI.value,
                            'content': {}
                        }, session_id, is_ai=True)

                        if ai_message:
                            chat_session["lastMessage"] = ai_message["text_content"]
                            chat_session["time"] = datetime.now().strftime("%I:%M:%S %p")
                            await self.channel_layer.group_send(
                                self.user_channel,
                                {
                                    'type': 'chat_message',
                                    'session_id': session_id,
                                    'message': ai_message,
                                    'is_ai': True
                                }
                            )
                        return
                # Handle regular text messages
                if user_message.strip():
                    # Get AI response using chatbot
                    ai_response, image, size = await asyncio.to_thread(chatbot.ask_question, user_message)
                    # Save and send AI response
                    if image and size:
                        ai_message = await self.save_message({
                            'text': ai_response,
                            'message_type': MessageType.MULTIPLE.value,
                            'content': {},
                            'file': {
                                "path": image,
                                "name": "AiChatBot.png",
                                "size": size,
                                "type": "IMAGE",
                            }
                        }, session_id, is_ai=True)
                    else:
                        ai_message = await self.save_message({
                            'text': ai_response,
                            'message_type': MessageType.AI.value,
                            'content': {}
                        }, session_id, is_ai=True)

                    if ai_message:
                        # Update chat session with latest message
                        chat_session["lastMessage"] = ai_message["text_content"]
                        chat_session["time"] = datetime.now().strftime("%I:%M:%S %p")

                        # Send message through channel layer to all connected clients
                        await self.channel_layer.group_send(
                            self.user_channel,
                            {
                                'type': 'chat_message',
                                'session_id': session_id,
                                'message': ai_message,
                                'is_ai': True
                            }
                        )
            elif data["ai_agent"] == 'web_agent':
                print("comming here: ", data)
                os.environ['GROQ_API_KEY'] =  "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" 
                user_id = str(self.user.id)
                chat_session = self.active_chats[user_id][session_id]

                # Initialize web agent
                web_agent = Agent(
                    name="Web Agent",
                    role="Search the web for information",
                    model=Groq(id="deepseek-r1-distill-llama-70b"),
                    tools=[DuckDuckGo()],
                    instructions=["Always include sources", "Use tables to display data"],
                    # groq_api_key=groq_api_key,
                    show_tool_calls=True,
                    markdown=True,
                    read_chat_history=True,
                )

                # Get response from web agent
                try:
                    response_text = await asyncio.to_thread(web_agent.run, user_message, stream=False)
                    
                    output_message = response_text.content
                    lines = output_message.split('\n')
                    output_message = '\n'.join(lines[4:]) 
                    print(output_message)

                    ai_message = await self.save_message({
                        'text': output_message,
                        'message_type': MessageType.AI.value,
                        'content': {}
                    }, session_id, is_ai=True)

                    if ai_message:
                        chat_session["lastMessage"] = ai_message["text_content"]
                        chat_session["time"] = datetime.now().strftime("%I:%M:%S %p")
                        
                        await self.channel_layer.group_send(
                            self.user_channel,
                            {
                                'type': 'chat_message',
                                'session_id': session_id,
                                'message': ai_message,
                                'is_ai': True
                            }
                        )
                except Exception as e:
                    logger.error(f"Error processing web agent response: {str(e)}", exc_info=True)
                    
                    error_message = await self.save_message({
                        'text': "I apologize, but I'm having trouble retrieving information from the web right now.",
                        'message_type': MessageType.SYSTEM.value,
                        'content': {}
                    }, session_id, is_ai=True)

                    if error_message:
                        await self.channel_layer.group_send(
                            self.user_channel,
                            {
                                'type': 'chat_message',
                                'session_id': session_id,
                                'message': error_message,
                                'is_ai': True
                            }
                        )
        except Exception as e:
            logger.error(f"Error processing AI response: {str(e)}", exc_info=True)
            error_message = await self.save_message({
                'text': "I apologize, but I'm having trouble processing your request right now.",
                'message_type': MessageType.SYSTEM.value,
                'content': {}
            }, session_id, is_ai=True)

            if error_message:
                await self.channel_layer.group_send(
                    self.user_channel,
                    {
                        'type': 'chat_message',
                        'session_id': session_id,
                        'message': error_message,
                        'is_ai': True
                    })

    async def chat_message(self, event):
        try:
            if event.get('is_ai', False):
                await asyncio.sleep(0.1)
            
            user_id = str(self.user.id)
            session_id = event['session_id']
            
            # Only send if this channel is still associated with the session
            if (user_id in self.channel_sessions and 
                self.user_channel in self.channel_sessions[user_id] and
                self.channel_sessions[user_id][self.user_channel] == session_id):
                
                message_data = {
                    'type': 'message',
                    'session_id': session_id,
                    'message': event['message']
                }
                
                message_data = serialize_uuid(message_data)
                await self.send(message_data)
            
        except Exception as e:
            logger.error(f"Error in chat_message handler: {str(e)}", exc_info=True)