import React from 'react';
import { List, Avatar, Typography, Button, Badge ,theme} from 'antd';
import { UsergroupAddOutlined, TeamOutlined,CloseOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { useToken } = theme;


const ChatList = ({onClose, chats, onSelectChat, onCreateGroup }) => {


  const { token } = useToken();
  
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column',}}>
    
      <div className='custom-scroll' style={{ flex: 1, overflowY: 'auto' }}>
      <style>
                        {`
                          .custom-scroll::-webkit-scrollbar {
                            width: 1px;
                            background-color: transparent;
                          }
                          .custom-scroll::-webkit-scrollbar-thumb {
                            background-color: ${token.colorTextQuaternary};
                            border-radius: 20px;
                          }
                          .custom-scroll::-webkit-scrollbar-track {
                            background-color: ${token.colorBgContainer};
                          }
                          .custom-scroll:hover::-webkit-scrollbar-thumb {
                            background-color: ${token.colorTextTertiary};
                          }
                          .custom-scroll {
                            scrollbar-width: thin;
                            scrollbar-color: ${token.colorTextQuaternary} transparent;
                          }
                          .custom-scroll:hover {
                            scrollbar-color: ${token.colorTextTertiary} transparent;
                          }
                          .custom-scroll::-webkit-scrollbar-thumb {
                            transition: background-color 0.2s;
                          }
                          

                          
                        `}
                      </style>

        <List
          dataSource={chats}
          renderItem={chat => (
            <div
              onClick={() => onSelectChat(chat)}
              style={{
                padding: '16px 16px',
                borderBottom: '1px solid #1f1f1f',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center'
              }}
            >
              <Badge count={chat.unread}>
                <Avatar 
                  style={{ 
                    backgroundColor: '#1677ff',
                    marginRight: 12 
                  }}
                  icon={chat.type === 'group' ? <TeamOutlined /> : null}
                >
                  {chat.avatar}
                </Avatar>
              </Badge>
              <div style={{ flex: 1 }}>
                <Text style={{ color: '#ffffff', display: 'block' }}>
                  {chat.name}
                </Text>
                <Text style={{ color: '#8c8c8c', fontSize: 12 }}>
                  {chat.lastMessage?chat.lastMessage.length>20?chat.lastMessage.subs    :"":'No messages'}
                </Text>
              </div>
              <Text style={{ color: '#8c8c8c', fontSize: 12 }}>
                {chat.time}
              </Text>
            </div>
          )}
        />
      </div>
    </div>
  );
};

export default ChatList;