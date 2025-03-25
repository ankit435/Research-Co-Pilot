import asyncio
import json
import logging
import os
import shutil
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db.models import Prefetch
from django.db.models import Q
from typing import Dict, List, Optional, Any
import uuid
from django.conf import settings
from .models import (
    
    Chat, 
    GroupChat, 
    Message, 
    MessageReceipt, 
    GroupMembership,
    MessageType,
    MessageStatus,
    MessageAttachment
    
)
from .serializers import (
    MessageSerializer,
    ChatSerializer,
    GroupChatSerializer,
    User
)
from django.db import models
from . import middleware
from . import pdfchatBot
from datetime import datetime, timedelta
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()



logger = logging.getLogger(__name__)



class ConnectionTracker:
    """Tracks user connections to chats and groups"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.chat_connections = defaultdict(set)  # {chat_id: {user_ids}}
            cls._instance.group_connections = defaultdict(set)  # {group_id: {user_ids}}
        return cls._instance
    
    def add_connection(self, chat_or_group_id, user_id, is_group=False):
        """Track new connection"""
        if is_group:
            self.group_connections[chat_or_group_id].add(user_id)
        else:
            self.chat_connections[chat_or_group_id].add(user_id)
            
    def remove_connection(self, chat_or_group_id, user_id, is_group=False):
        """Remove tracked connection"""
        if is_group:
            self.group_connections[chat_or_group_id].discard(user_id)
            if not self.group_connections[chat_or_group_id]:
                del self.group_connections[chat_or_group_id]
        else:
            self.chat_connections[chat_or_group_id].discard(user_id)
            if not self.chat_connections[chat_or_group_id]:
                del self.chat_connections[chat_or_group_id]
                
    def is_connected(self, chat_or_group_id, user_id, is_group=False):
        """Check if user is connected to chat/group"""
        if is_group:
            return user_id in self.group_connections.get(chat_or_group_id, set())
        return user_id in self.chat_connections.get(chat_or_group_id, set())

class ChatbotCacheManager:
    """Manages chatbot instances with automatic cleanup"""
    def __init__(self, cleanup_interval=300, max_inactive_time=1800):  # 5 min cleanup, 30 min max inactive
        self.chatbots = {}  # {group_id: {'bot': chatbot, 'last_accessed': timestamp}}
        self.cleanup_interval = cleanup_interval
        self.max_inactive_time = max_inactive_time
        self.cleanup_task = None

    def get(self, group_id):
        """Get chatbot instance and update last access time"""
        if group_id in self.chatbots:
            self.chatbots[group_id]['last_accessed'] = datetime.now()
            return self.chatbots[group_id]['bot']
        return None

    def set(self, group_id, chatbot):
        """Set chatbot instance with current timestamp"""
        self.chatbots[group_id] = {
            'bot': chatbot,
            'last_accessed': datetime.now()
        }
        
    def remove(self, group_id):
        """Remove chatbot instance"""
        if group_id in self.chatbots:
            del self.chatbots[group_id]

    async def start_cleanup(self):
        """Start the cleanup task"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_loop())
            
    async def stop_cleanup(self):
        """Stop the cleanup task"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None

    async def _cleanup_loop(self):
        """Periodically clean up inactive chatbot instances"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                self._cleanup_inactive()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {str(e)}")
                await asyncio.sleep(self.cleanup_interval)

    def _cleanup_inactive(self):
        """Remove inactive chatbot instances"""
        current_time = datetime.now()
        inactive_groups = [
            group_id for group_id, data in self.chatbots.items()
            if (current_time - data['last_accessed']).total_seconds() > self.max_inactive_time
        ]
        
        for group_id in inactive_groups:
            logger.info(f"Cleaning up inactive chatbot for group {group_id}")
            self.remove(group_id)

class BaseChatConsumer(AsyncWebsocketConsumer):
    """Base consumer for shared functionality"""
    
    async def connect(self):
        """Handle connection"""
        if not self.scope['user'].is_authenticated:
            logger.error("Unauthenticated connection attempt")
            await self.close()
            return False
            
        self.user = self.scope['user']
        logger.info(f"Base connection established for user: {self.user.id}")
        return True

    @database_sync_to_async
    def get_message_data(self, message):
        """Get serialized message data"""
        try:
            return MessageSerializer(message).data
        except Exception as e:
            logger.error(f"Error serializing message: {str(e)}")
            return None
        
class GroupChatConsumer(BaseChatConsumer):
    """Consumer for group chats"""
    connection_tracker = ConnectionTracker()
    _cache_manager = ChatbotCacheManager()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def connect(self):
        """Handle connection and start cleanup if needed"""
        if not await super().connect():
            return
            
        try:
            self.group_id = self.scope['url_route']['kwargs']['group_id']
            logger.info(f"Connecting to group chat: {self.group_id}")
            
            # Start cleanup task if not already running
            await self._cache_manager.start_cleanup()
            
            is_member = await self.verify_membership()
            if not is_member:
                logger.error(f"User not member of group: {self.group_id}")
                await self.close()
                return
                
            self.chat_group = f'group_{self.group_id}'
            await self.channel_layer.group_add(
                self.chat_group,
                self.channel_name
            )
            
            await self.accept()
            self.connection_tracker.add_connection(self.group_id, self.user.id, is_group=True)
            logger.info(f"Connected to group chat: {self.group_id}")
            
        except Exception as e:
            logger.error(f"Error in group chat connect: {str(e)}", exc_info=True)
            await self.close()


    async def get_or_create_chatbot(self, group_id):
        """Get existing chatbot instance or create a new one."""
        chatbot = self._cache_manager.get(group_id)
        groq_api_key = os.getenv('GROQ_API_KEY')  # Make sure to set this in your environment
        
        if not chatbot:
            # Offload blocking PDFChatbot initialization to a thread
            chatbot = await asyncio.to_thread(
                pdfchatBot.PDFChatbot,
                groq_api_key=groq_api_key,
                index_path=f"faiss_index_group_{group_id}"
            )
            self._cache_manager.set(group_id, chatbot)
            
            # Load chat history (if any)
            try:
                await self.load_chat_history(group_id)
            except Exception as e:
                logger.error(f"Error loading chat history for group {group_id}: {e}", exc_info=True)
        
        return chatbot

    async def notify_offline_users(self, message_data):
        """Notify only offline users through ChatManagement"""
        try:
            if await self.verify_membership():
                for member in message_data.get('receipts', []):
                    user_id = member['user']['id']
                    # Skip sender and connected users
                    if (user_id == self.user.id or 
                        self.connection_tracker.is_connected(self.group_id, user_id, is_group=True)):
                        continue
                        
                    # Send only to offline users via management channel
                    await self.channel_layer.group_send(
                        f'user_{user_id}_management',
                        {
                            'type': 'chat_notification',
                            'message': {
                                'type': 'new_message',
                                'chat_type': 'group',
                                'chat_id': self.group_id,
                                'message': message_data
                            }
                        }
                    )
        except Exception as e:
            logger.error(f"Error notifying offline users: {str(e)}", exc_info=True)


    @database_sync_to_async
    def load_chat_history(self, group_id):
        """Load chat history from existing messages"""
        try:
            chatbot = self._cache_manager.get(group_id)
            if not chatbot:
                return
                
            messages = Message.objects.filter(
                group_chat_id=group_id
            ).filter(
                Q(text_content__istartswith='@bot') |
                Q(sender__email='bot@gmail.com')
            ).order_by('-created_at')[:50]
            print(messages)
            
            for msg in reversed(messages):
                question_text = msg.text_content
                if msg.sender.email != 'bot@gmail.com' and question_text:
                    question_text = question_text.lstrip('@bot').strip()
                
                chatbot.chat_history.append(
                    pdfchatBot.ChatHistory(
                        question=question_text if msg.sender.email != 'bot@gmail.com' else "",
                        answer=msg.text_content if msg.sender.email == 'bot@gmail.com' else ""
                    )
                )
        except Exception as e:
            logger.error(f"Error loading chat history: {str(e)}")

    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'chat_group'):
            self.connection_tracker.remove_connection(self.group_id, self.user.id, is_group=True)
            await self.channel_layer.group_discard(
                self.chat_group,
                self.channel_name
            )
            
        logger.info(f"Disconnected from group chat: {self.group_id}")

    async def receive(self, text_data):
        """Handle received messages"""
        try:
            data = json.loads(text_data)
            
            # Verify user is still an active member
            is_member = await self.verify_membership()
            if not is_member:
                logger.warning(f"User no longer member of group: {self.group_id}")
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'You are no longer a member of this group'
                }))
                return
            
            message_type = data.get('message_type', MessageType.TEXT)
            if not validate_message_data(message_type, data):
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Invalid message data'
                }))
                return

            message = await self.save_message(data)
            message_data = None
            
            if message:
                message_data = await self.get_message_data(message)
                await self.channel_layer.group_send(
                    self.chat_group,
                    {
                        'type': 'chat_message',
                        'message': message_data
                    }
                )
            await self.notify_offline_users(message_data)
            mention = data.get('mention', [])
            if mention and any(d.get('name', '').lower() == 'bot' for d in mention):
                asyncio.create_task(self.handle_ai_response(data, message_data, self.group_id))
                
    
                
            
                
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON in group message")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error handling group message: {str(e)}", exc_info=True)
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))

    @database_sync_to_async
    def processAIResponse(self, lastMessage, content, group_id,attachment=None):
        
        bot=middleware.User.objects.get(email='bot@gmail.com')
        if not bot:
            return None

        message = Message.objects.create(
                sender=bot,
                group_chat_id=group_id,
                text_content=lastMessage,
                content=content or {},
                message_type=MessageType.MULTIPLE if attachment else  MessageType.TEXT
            )
        if attachment:
            attachment = MessageAttachment.objects.create(
                file_path=attachment.get('path'),
                file_name=attachment.get('name'),
                file_size=attachment.get('size', 0),
                file_type=attachment.get('type')
            )
            message.attachments.add(attachment)
            message.save()
        message.save()
        active_members = message.group_chat.members.exclude(
                id=bot.id
            ).filter(
                groupmembership__is_active=True,
                groupmembership__left_at__isnull=True
            ).distinct()
            # Bulk create receipts
        receipts = [
                MessageReceipt(
                    message=message,
                    user=member
                ) for member in active_members
            ]
        MessageReceipt.objects.bulk_create(receipts)
            
        return message


    async def handle_ai_response(self, lastMessage, message_data, group_id):
        try: 
            chatbot = await self.get_or_create_chatbot(group_id)
            if not chatbot:
                return
            text_content = message_data['text_content'].lstrip('@bot').strip() 
            
            if message_data['attachments']:
                    file_path = message_data['attachments'][0]['file_path']
                    if file_path:
                        # Process PDF and get summary
                        print("Processing PDF...",file_path)
                        summary = await asyncio.to_thread(chatbot.process_pdf, file_path)
                        if summary:
                            message = await self.processAIResponse(
                                group_id=group_id,
                                content={},
                                lastMessage=summary)
                            if message:
                                message_data = await self.get_message_data(message)
                                print("calling one time")
                                await self.channel_layer.group_send(
                                    self.chat_group,
                                    {
                                        'type': 'chat_message',
                                        'message': message_data
                                    }
                                )

                    
            if text_content and len(text_content)>0:
                response,image,Size = await asyncio.to_thread(chatbot.ask_question, message_data['text_content'].lstrip('@bot').strip(),True)
                if response:
                    message = await self.processAIResponse(
                        group_id=group_id,
                        content={},
                        lastMessage=response,
                        attachment= {
                                        "path": image,
                                        "name": "AiChatBot.png",
                                        "size": Size,
                                        "type": "IMAGE",
                                } if image and Size else None
                        
                        )
                    
                    if message:
                        message_data = await self.get_message_data(message)
                        await self.channel_layer.group_send(
                            self.chat_group,
                            {
                                'type': 'chat_message',
                                'message': message_data
                            }
                        )

        except Exception as e:
            logger.error(f"Error in AI response: {str(e)}", exc_info=True)
            message = await self.processAIResponse(
                group_id=group_id,
                content={},
                lastMessage="Sorry, I encountered an error processing your request.")
            if message:
                message_data = await self.get_message_data(message)
                await self.channel_layer.group_send(
                    self.chat_group,
                    {
                        'type': 'chat_message',
                        'message': message_data
                    }
                )
            
        
        



      
    @database_sync_to_async
    def verify_membership(self):
        """Verify user is an active member of the group"""
        try:
            group = GroupChat.objects.get(id=self.group_id)
            return (group.is_active and 
                   GroupMembership.objects.filter(
                       group_id=self.group_id,
                       user=self.user,
                       is_active=True,
                       left_at__isnull=True
                   ).exists())
        except GroupChat.DoesNotExist:
            logger.error(f"Group not found: {self.group_id}")
            return False
        except Exception as e:
            logger.error(f"Error verifying group membership: {str(e)}")
            return False

    @database_sync_to_async
    def save_message(self, data):
        """Save message to database"""
        try:


            # Create the message
            message_type = data.get('message_type', MessageType.TEXT)
            content = data.get('content', {})
            message = Message.objects.create(
                
                sender=self.user,
                group_chat_id=self.group_id,
                text_content=data.get('text'),
                content=content,
                message_type=data.get('message_type', MessageType.TEXT)
            )
            
           
            # Handle different message types
            if message_type == MessageType.TEXT:
                message.text_content = data.get('text')
                
            elif message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.AUDIO, MessageType.DOCUMENT]:
                # Handle file attachments
                file_data = data.get('file', {})
                attachment = MessageAttachment.objects.create(
                        file_path=file_data.get('path'),
                        file_name=file_data.get('name'),
                        file_size=file_data.get('size', 0),
                        file_type=file_data.get('type')
                )
                message.save()  # Save message first to get ID
                message.attachments.add(attachment)
                
            elif message_type == MessageType.MULTIPLE:
                # Handle file attachments
                message.text_content = data.get('text', '')
                file_data = data.get('file', [])
                if file_data:
                    message.save()  # Save message first to get ID
                for fileresult in file_data:
                    file=fileresult.get('result')
                    attachment = MessageAttachment.objects.create(
                        file_path=file.get('path'),
                        file_name=file.get('name'),
                        file_size=file.get('size', 0),
                        file_type=file.get('type')
                    )
                    message.attachments.add(attachment)
                    
            elif message_type == MessageType.LOCATION:
                message.content = {
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'address': data.get('address', '')
                }

            elif message_type == MessageType.CONTACT:
                message.content = {
                    'name': data.get('contact_name'),
                    'phone': data.get('contact_phone'),
                    'email': data.get('contact_email', ''),
                    'additional_info': data.get('additional_info', {})
                }

            elif message_type == MessageType.STICKER:
                message.content = {
                    'sticker_id': data.get('sticker_id'),
                    'pack_id': data.get('pack_id', ''),
                    'sticker_metadata': data.get('sticker_metadata', {})
                }

            elif message_type == MessageType.SYSTEM:
                message.content = {
                    'action': data.get('action'),
                    'metadata': data.get('metadata', {})
                }

            # Save the message
            message.save()
           
            active_members = message.group_chat.members.exclude(
                id=self.user.id
            ).filter(
                groupmembership__is_active=True,
                groupmembership__left_at__isnull=True
            ).distinct()

            
            # Bulk create receipts
            receipts = [
                MessageReceipt(
                    message=message,
                    user=member
                ) for member in active_members
            ]
            MessageReceipt.objects.bulk_create(receipts)
            
            return message
        except Exception as e:
            logger.error(f"Error saving group message: {str(e)}")
            return None

    async def chat_message(self, event):
        """Handle chat messages"""
        await self.send(json.dumps({
            'type': 'message',
            'message': event['message']
        }))

    async def group_update(self, event):
        """Handle group update notifications"""
        await self.send(json.dumps({
            'type': 'group_update',
            'group_id': event['group_id'],
            'update_type': event['update_type'],
            'data': event.get('data', {})
        }))


class ChatManagementConsumer(AsyncWebsocketConsumer):
    """Consumer for managing chat and group creation/deletion"""
    
    async def connect(self):
        """Handle connection"""
        if not self.scope['user'].is_authenticated:
            logger.error("Unauthenticated management connection attempt")
            await self.close()
            return
            
        self.user = self.scope['user']
        
        # Create a personal channel for the user
        self.user_channel = f'user_{self.user.id}_management'
        await self.channel_layer.group_add(
            self.user_channel,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Management connection established for user: {self.user.id}")
        
    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'user_channel'):
            await self.channel_layer.group_discard(
                self.user_channel,
                self.channel_name
            )
        logger.info(f"Management connection closed for user: {self.user.id}")

    async def receive(self, text_data):
        """Handle management commands"""
        try:
            data = json.loads(text_data)
            command = data.get('command')
            logger.info(f"Received management command: {command}")
            
            if command == 'create_chat':
                chat = await self.create_chat(data)
                if chat:
                    # Notify all participants about the new chat
                    for participant in chat['participants']:
                        await self.channel_layer.group_send(
                            f'user_{participant["id"]}_management',
                            {
                                'type': 'chat_notification',
                                'message': {
                                    'type': 'chat_created',
                                    'chat': chat
                                }
                            }
                        )
                else:
                    await self.send_error('Failed to create chat')
                    
            elif command == 'get_all_chats':
                try:
                    chats = await self.get_all_chats()
                    await self.send(json.dumps({
                        'type': 'chats_list',
                        'chats': chats
                    }))
                except Exception as e:
                    logger.error(f"Error fetching chats: {str(e)}")
                    await self.send_error('Failed to fetch chats')
                    
            elif command == 'create_group':
                group = await self.create_group(data)
                print(group)
                if group:
                    # Notify all group members about the new group
                    for member in group['members']:
                        await self.channel_layer.group_send(
                            f'user_{member["user"]["id"]}_management',
                            {
                                'type': 'chat_notification',
                                'message': {
                                    'type': 'group_created',
                                    'group': group
                                }
                            }
                        )
                else:
                    await self.send_error('Failed to create group')
                    
            elif command == 'delete_chat':
                chat_data = await self.delete_chat(data.get('chat_id'))
                if chat_data:
                    # Notify all participants about chat deletion
                    for participant in chat_data['participants']:
                        await self.channel_layer.group_send(
                            f'user_{participant["id"]}_management',
                            {
                                'type': 'chat_notification',
                                'message': {
                                    'type': 'chat_deleted',
                                    'chat_id': data.get('chat_id')
                                }
                            }
                        )
                else:
                    await self.send_error('Failed to delete chat')
                    
            elif command == 'delete_group':
                group_data = await self.delete_group(data.get('group_id'))
                if group_data:
                    # Notify all members about group deletion
                    asyncio.create_task(self.delete_group_files(data.get('group_id')))
                    for member in group_data['members']:
                        await self.channel_layer.group_send(
                            f'user_{member["user"]["id"]}_management',
                            {
                                'type': 'chat_notification',
                                'message': {
                                    'type': 'group_deleted',
                                    'group_id': data.get('group_id')
                                }
                            }
                        )

                else:
                    await self.send_error('Failed to delete group')
                    
            elif command == 'add_members':
                try:
                    success, group = await self.add_group_members(
                        data.get('group_id'),
                        data.get('member_ids', [])
                    )
                    if success:
                        # Notify all members (including new ones) about the update
                        for member in group['members']:
                            await self.channel_layer.group_send(
                                f'user_{member["id"]}_management',
                                {
                                    'type': 'chat_notification',
                                    'message': {
                                        'type': 'members_added',
                                        'group_id': data.get('group_id'),
                                        'member_ids': data.get('member_ids', []),
                                        'group': group
                                    }
                                }
                            )
                    else:
                        await self.send_error('Failed to add members')
                except Exception as e:
                    logger.error(f"Error adding members: {str(e)}")
                    await self.send_error('Failed to add members')
                    
            elif command == 'remove_members':
                try:
                    success, group = await self.remove_group_members(
                        data.get('group_id'),
                        data.get('member_ids', [])
                    )
                    if success:
                        # Get list of removed member IDs for notification
                        removed_member_ids = data.get('member_ids', [])
                        
                        # Notify both remaining and removed members
                        all_affected_users = (
                            [{'id': mid} for mid in removed_member_ids] + 
                            group['members']
                        )
                        
                        for member in all_affected_users:
                            await self.channel_layer.group_send(
                                f'user_{member["id"]}_management',
                                {
                                    'type': 'chat_notification',
                                    'message': {
                                        'type': 'members_removed',
                                        'group_id': data.get('group_id'),
                                        'member_ids': removed_member_ids,
                                        'group': group
                                    }
                                }
                            )
                    else:
                        await self.send_error('Failed to remove members')
                except Exception as e:
                    logger.error(f"Error removing members: {str(e)}")
                    await self.send_error('Failed to remove members')
                    
            else:
                await self.send_error(f'Unknown command: {command}')
                    
        except json.JSONDecodeError:
            logger.error("Invalid JSON in management command")
            await self.send_error('Invalid command format')
        except Exception as e:
            logger.error(f"Error handling management command: {str(e)}", exc_info=True)
            await self.send_error('Internal server error')

    async def chat_notification(self, event):
        try:
            print("test")
            message = event['message']
            
            # For new messages from chats/groups user isn't connected to
            if message['type'] == 'new_message':
                await self.send(json.dumps({
                    'type': 'new_message_notification',
                    'chat_type': message['chat_type'],
                    'chat_id': message['chat_id'],
                    'message': message['message']
                }))
            else:
                await self.send(json.dumps(message))
                
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")


    async def delete_group_files(self, group_id):
        """Delete all files associated with a group"""
        try:
            

            index_path=os.path.join(settings.BASE_DIR, f'FissIndex/faiss_index_group_{group_id}_text')
            if os.path.exists(index_path):
                shutil.rmtree(index_path)
            index_path=os.path.join(settings.BASE_DIR, f'FissIndex/faiss_index_group_{group_id}_table')
            if os.path.exists(index_path):
                shutil.rmtree(index_path)
            
        except GroupChat.DoesNotExist:
            logger.error(f"Group not found for file deletion: {group_id}")
        except Exception as e:
            logger.error(f"Error deleting group files: {str(e)}")

    async def send_error(self, message):
        """Helper method to send error messages"""
        try:
            await self.send(json.dumps({
                'type': 'error',
                'message': message
            }))
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    @database_sync_to_async
    def get_all_chats(self):
        """Get all private and group chats for the user with latest 20 messages each"""
        try:
            # Get messages subquery
            message_queryset = Message.objects.filter(
                deleted_at__isnull=True
            ).order_by('-created_at')

            # Get private chats
            private_chats = Chat.objects.filter(
                participants=self.user,
                is_active=True
            ).prefetch_related(
                'participants',
                Prefetch(
                    'messages',
                    queryset=message_queryset,
                    to_attr='recent_messages'
                )
            ).order_by('-last_message_at')

            # Get group chats
            group_chats = GroupChat.objects.filter(
                members=self.user,
                is_active=True,
                groupmembership__is_active=True
            ).prefetch_related(
                'members',
                'admins',
                Prefetch(
                    'messages',
                    queryset=message_queryset,
                    to_attr='recent_messages'
                )
            ).order_by('-last_message_at')

            # Serialize the chats
            private_chat_data = ChatSerializer(
                private_chats,
                many=True,
                context={'user': self.user}
            ).data
            group_chat_data = GroupChatSerializer(
                group_chats,
                many=True,
                context={'user': self.user}
            ).data

            # Combine and sort all chats
            all_chats = []
            for chat in private_chat_data:
                messages = chat.get('messages', [])[:20][::-1]
                all_chats.append({
                    'id': chat['id'],
                    'type': 'private',
                    'participants': chat['participants'],
                    'last_message': chat['last_message'],
                    'last_message_at': chat['last_message_at'],
                    'unread_count': chat['unread_count'],
                    'messages': messages
                })
            
            for chat in group_chat_data:
                messages = chat.get('messages', [])[:20][::-1]
                all_chats.append({
                    'id': chat['id'],
                    'type': 'group',
                    'name': chat['name'],
                    'image': chat['image'],
                    'last_message': chat['last_message'],
                    'last_message_at': chat['last_message_at'],
                    'unread_count': chat['unread_count'],
                    'members': chat['members'],
                    'messages': messages
                })

            # Sort by last_message_at
            sorted_chats = sorted(
                all_chats,
                key=lambda x: (x['last_message_at'] is None, x['last_message_at'] or ''),
                reverse=True
            )

            return sorted_chats

        except Exception as e:
            logger.error(f"Error fetching chats: {str(e)}")
            raise

    @database_sync_to_async
    def create_chat(self, data):
        """Create a new private chat"""
        try:
            participant_ids = data.get('participant_ids', [])
            
            if not participant_ids or len(participant_ids) > 2 or len([p for p in participant_ids if p != self.user.id]) != 1:
                logger.error("Invalid participant count for chat creation")
                return None

            if self.user.id not in participant_ids:
                participant_ids.append(self.user.id)

            # Check existing chat
            existing_chat = Chat.objects.filter(
                participants__id__in=participant_ids
            ).annotate(
                participant_count=models.Count('participants')
            ).filter(
                participant_count=len(participant_ids)
            ).first()
           
            if existing_chat:
                logger.info("Chat already exists between the participants")
                return None
               
            # Create new chat
            chat = Chat.objects.create()
            chat.participants.set(participant_ids)

            if not chat.id:
                logger.error("Failed to create chat")
                return None
            
            logger.info(f"New chat created between user {self.user.id} and participants {participant_ids}")
            return ChatSerializer(chat, context={'user': self.user}).data
            
        except Exception as e:
            logger.error(f"Error creating chat: {str(e)}")
            return None

    @database_sync_to_async
    def create_group(self, data):
        """Create a new group chat"""
        try:
            if not data.get('name'):
                logger.error("Group name not provided")
                return None
          
            group = GroupChat.objects.create(
                name=data.get('name'),
                description=data.get('description', ''),
                creator=self.user
            )
            
            # Add creator as admin and member
            group.admins.add(self.user)
            GroupMembership.objects.create(
                user=self.user,
                group=group,
                is_active=True
            )

            # Add other members
            member_ids = data.get('member_ids', [])
            try:
                BOT = User.objects.get(email='bot@gmail.com')
                GroupMembership.objects.create(
                    user=BOT,
                    group=group,
                    is_active=True
                )
            except User.DoesNotExist:
                print("User with email 'bot@gmail.com' does not exist.")
            for member_id in member_ids:
                if member_id != self.user.id:
                    GroupMembership.objects.create(
                        user_id=member_id,
                        group=group,
                        is_active=True
                    )
            
            return GroupChatSerializer(group, context={'user': self.user}).data
        except Exception as e:
            logger.error(f"Error creating group: {str(e)}")
            return None

    @database_sync_to_async
    def delete_chat(self, chat_id):
        """Delete a chat and return participant data for notifications"""
        try:
            chat = Chat.objects.get(id=chat_id)
            if chat.participants.filter(id=self.user.id).exists():
                chat_data = ChatSerializer(chat, context={'user': self.user}).data
                chat.hard_delete()
                return chat_data

            logger.warning(f"Unauthorized chat deletion attempt: {chat_id}")
            return None
        except Chat.DoesNotExist:
            logger.error(f"Chat not found for deletion: {chat_id}")
            return None
        except Exception as e:
            logger.error(f"Error deleting chat: {str(e)}")
            return None

    @database_sync_to_async
    def delete_group(self, group_id):
        """Delete a group and return member data for notifications"""
        try:
            print(group_id)
            group = GroupChat.objects.get(id=group_id)
            if self.user == group.creator or group.admins.filter(id=self.user.id).exists():
                group_data = GroupChatSerializer(group, context={'user': self.user}).data
                # group.is_active = False
                # group.save()
                group.hard_delete()
                return group_data
            logger.warning(f"Unauthorized group deletion attempt: {group_id}")
            return None
        except GroupChat.DoesNotExist:
            logger.error(f"Group not found for deletion: {group_id}")
            return None
        except Exception as e:
            logger.error(f"Error deleting group: {str(e)}")
            return None

    @database_sync_to_async
    def add_group_members(self, group_id, member_ids):
        """Add members to a group"""
        try:
            group = GroupChat.objects.get(id=group_id)
            if self.user == group.creator or group.admins.filter(id=self.user.id).exists():
                # Add new members
                members_added = False
                for member_id in member_ids:
                    membership, created = GroupMembership.objects.get_or_create(
                        user_id=member_id,
                        group=group,
                        defaults={'is_active': True}
                    )
                    
                    # If membership existed but was inactive, reactivate it
                    if not created and not membership.is_active:
                        membership.is_active = True
                        membership.save()
                        members_added = True
                    elif created:
                        members_added = True

                # Only return success if at least one member was added or reactivated
                if members_added:
                    # Refresh group data after adding members
                    group = GroupChat.objects.get(id=group_id)
                    return True, GroupChatSerializer(group, context={'user': self.user}).data
                else:
                    logger.info(f"No new members added to group: {group_id}")
                    return False, GroupChatSerializer(group, context={'user': self.user}).data
            
            logger.warning(f"Unauthorized member addition attempt: {group_id}")
            return False, None
            
        except GroupChat.DoesNotExist:
            logger.error(f"Group not found for adding members: {group_id}")
            return False, None
        except Exception as e:
            logger.error(f"Error adding members to group: {str(e)}")
            return False, None

    @database_sync_to_async
    def remove_group_members(self, group_id, member_ids):
        """Remove members from a group"""
        try:
            group = GroupChat.objects.get(id=group_id)
            if self.user == group.creator or group.admins.filter(id=self.user.id).exists():
                # Store original members for notification
                original_members = list(group.members.all())
                
                # Remove members
                current_time = timezone.now()
                affected_rows = GroupMembership.objects.filter(
                    user_id__in=member_ids,
                    group=group,
                    is_active=True  # Only affect active memberships
                ).update(
                    is_active=False,
                    left_at=current_time
                )
                
                if affected_rows > 0:
                    # Refresh group data after removing members
                    group = GroupChat.objects.get(id=group_id)
                    group_data = GroupChatSerializer(group, context={'user': self.user}).data
                    
                    # Add removed members to the notification list
                    removed_members = User.objects.filter(id__in=member_ids)
                    all_affected_members = set(original_members) | set(removed_members)
                    
                    return True, {
                        **group_data,
                        'removed_members': [{'id': member.id} for member in removed_members]
                    }
                else:
                    logger.info(f"No members were removed from group: {group_id}")
                    return False, GroupChatSerializer(group, context={'user': self.user}).data
                    
            logger.warning(f"Unauthorized member removal attempt: {group_id}")
            return False, None
            
        except GroupChat.DoesNotExist:
            logger.error(f"Group not found for removing members: {group_id}")
            return False, None
        except Exception as e:
            logger.error(f"Error removing members from group: {str(e)}")
            return False, None

class ChatConsumer(BaseChatConsumer):
    """Consumer for private chats"""

    connection_tracker = ConnectionTracker()
    
    async def connect(self):
        """Handle private chat connection"""
        if not await super().connect():
            return
        
        try:
            self.chat_id = self.scope['url_route']['kwargs']['chat_id']
            logger.info(f"Connecting to private chat: {self.chat_id}")
            
            chat = await self.get_chat()

            if not chat or not chat.is_active:
                logger.error(f"Chat not found or inactive: {self.chat_id}")
                await self.close()
                return
            
            self.connection_tracker.add_connection(self.chat_id, self.user.id)
            self.chat_group = f'chat_{self.chat_id}'
            await self.channel_layer.group_add(
                self.chat_group,
                self.channel_name
            )

            
            await self.accept()
            logger.info(f"Connected to private chat: {self.chat_id}")
            
        except Exception as e:
            logger.error(f"Error in private chat connect: {str(e)}", exc_info=True)
            
            await self.close()

    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'chat_group'):
            self.connection_tracker.remove_connection(self.chat_id, self.user.id)
            await self.channel_layer.group_discard(
                self.chat_group,
                self.channel_name
            )
        logger.info(f"Disconnected from private chat: {self.chat_id}")

    async def receive(self, text_data):
        """Handle received messages"""
        try:
            data = json.loads(text_data)
            
            # Validate required fields based on message type
            message_type = data.get('message_type', MessageType.TEXT)
            print(data)
            if not validate_message_data(message_type, data):
                await self.send(json.dumps({
                    'type': 'error',
                    'message': 'Invalid message data'
                }))
                return

            message = await self.save_message(data)
            
            if message:
                message_data = await self.get_message_data(message)
                await self.channel_layer.group_send(
                    self.chat_group,
                    {
                        'type': 'chat_message',
                        'message': message_data
                    }
                )
            await self.notify_offline_users(message_data)
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON in chat message")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error handling chat message: {str(e)}", exc_info=True)
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))

    async def notify_offline_users(self, message_data):
        try:
            print(message_data)
            participants=message_data.get('receipts', [])
            for participant in participants:
                user_id = participant['user']['id']
                # Skip sender and connected users
                if (user_id == self.user.id or 
                    self.connection_tracker.is_connected(self.chat_id, user_id)):
                    continue
                    
                # Send only to offline users via management channel
                await self.channel_layer.group_send(
                    f'user_{user_id}_management',
                    {
                        'type': 'chat_notification',
                        'message': {
                            'type': 'new_message',
                            'chat_type': 'private',
                            'chat_id': self.chat_id,
                            'message': message_data
                        }
                    }
                )
        except Exception as e:
            logger.error(f"Error notifying offline users: {str(e)}", exc_info=True)


    @database_sync_to_async
    def get_chat(self):
        """Get chat and verify user is participant"""
        try:
           
            chat = Chat.objects.get(id=self.chat_id)
            if chat.participants.filter(id=self.user.id).exists():
                return chat
            return None
        except Chat.DoesNotExist:

            return None
        except Exception as e:
            logger.error(f"Error getting chat: {str(e)}")
            print(e)    
            return None

    @database_sync_to_async
    def save_message(self, data):
        """Save message to database with support for all message types"""
        try:
            message_type = data.get('message_type', MessageType.TEXT)
            content = data.get('content', {})
            
            # Create base message object
            message = Message(
                sender=self.user,
                chat_id=self.chat_id,
                message_type=message_type,
                content=content
            )

            # Handle different message types
            if message_type == MessageType.TEXT:
                message.text_content = data.get('text')
                
            elif message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.AUDIO, MessageType.DOCUMENT]:
                # Handle file attachments
                file_data = data.get('file', [])
                attachment = MessageAttachment.objects.create(
                        file_path=file_data.get('path'),
                        file_name=file_data.get('name'),
                        file_size=file_data.get('size', 0),
                        file_type=file_data.get('type')
                    )
                message.save()  # Save message first to get ID
                message.attachments.add(attachment)
            elif message_type == MessageType.MULTIPLE:
                # Handle file attachments
                message.text_content = data.get('text', '')
                file_data = data.get('file', [])
                if file_data:
                    message.save()  # Save message first to get ID
                for fileresult in file_data:
                    file=fileresult.get('result')
                    attachment = MessageAttachment.objects.create(
                        file_path=file.get('path'),
                        file_name=file.get('name'),
                        file_size=file.get('size', 0),
                        file_type=file.get('type')
                    )
                    message.attachments.add(attachment)

            elif message_type == MessageType.LOCATION:
                message.content = {
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'address': data.get('address', '')
                }

            elif message_type == MessageType.CONTACT:
                message.content = {
                    'name': data.get('contact_name'),
                    'phone': data.get('contact_phone'),
                    'email': data.get('contact_email', ''),
                    'additional_info': data.get('additional_info', {})
                }

            elif message_type == MessageType.STICKER:
                message.content = {
                    'sticker_id': data.get('sticker_id'),
                    'pack_id': data.get('pack_id', ''),
                    'sticker_metadata': data.get('sticker_metadata', {})
                }

            elif message_type == MessageType.SYSTEM:
                message.content = {
                    'action': data.get('action'),
                    'metadata': data.get('metadata', {})
                }

            # Save the message
            message.save()

            # Create receipts for other participants
            participants = message.chat.participants.exclude(id=self.user.id)
            MessageReceipt.objects.bulk_create([
                MessageReceipt(message=message, user=participant)
                for participant in participants
            ])

            return message

        except Exception as e:
            logger.error(f"Error saving chat message: {str(e)}", exc_info=True)
            return None

    async def chat_message(self, event):
        """Handle chat messages"""
        await self.send(json.dumps({
            'type': 'message',
            'message': event['message']
        }))


class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for handling user notifications"""
    
    async def connect(self):
        """Handle connection"""
        if not self.scope['user'].is_authenticated:
            logger.error("Unauthenticated notification connection attempt")
            await self.close()
            return
            
        self.user = self.scope['user']
        self.notification_group = f'notifications_{self.user.id}'
        
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Notification connection established for user: {self.user.id}")

    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'notification_group'):
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )
        logger.info(f"Notification connection closed for user: {self.user.id}")

    async def receive(self, text_data):
        """Handle received commands"""
        try:
            data = json.loads(text_data)
            command = data.get('command')
            
            if command == 'mark_read':
                # Handle marking notifications as read
                pass
            else:
                logger.warning(f"Unknown notification command: {command}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON in notification command")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Invalid command format'
            }))
        except Exception as e:
            logger.error(f"Error handling notification command: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': 'Internal server error'
            }))

    async def notify(self, event):
        """Send notification to user"""
        await self.send(json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))

def validate_message_data( message_type, data):
     
        try:
            if message_type == MessageType.TEXT:
                return bool(data.get('text'))
                
            elif message_type in [MessageType.IMAGE, MessageType.VIDEO, MessageType.AUDIO, MessageType.DOCUMENT]:
                file_data = data.get('file', {})
                return all([
                    file_data.get('path'),
                    file_data.get('name'),
                    file_data.get('type')
                ])
                
            elif message_type == MessageType.LOCATION:
                return all([
                    data.get('latitude') is not None,
                    data.get('longitude') is not None
                ])
                
            elif message_type == MessageType.CONTACT:
                return all([
                    data.get('contact_name'),
                    data.get('contact_phone')
                ])
                
            elif message_type == MessageType.STICKER:
                return bool(data.get('sticker_id'))
                
            elif message_type == MessageType.SYSTEM:
                return bool(data.get('action'))
            
            elif message_type== MessageType.MULTIPLE:
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error validating message data: {str(e)}")
            return False
        
class DiffChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = "chat_room"  # Single room for now
        self.room_group_name = f"chat_{self.room_name}"

        # Join the room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave the room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get("message", "")

        # Send message to the room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
            },
        )

    async def chat_message(self, event):
        message = event["message"]

        # Echo the message back to WebSocket
        await self.send(text_data=json.dumps({"message": message}))