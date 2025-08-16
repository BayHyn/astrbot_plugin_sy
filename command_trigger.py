import asyncio
from astrbot.api import logger
from astrbot.api.message_components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent as CoreAstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.message.message_event_result import MessageChain


class CommandTrigger:
    """指令触发器，用于触发其他插件指令并转发结果"""
    
    def __init__(self, context, wechat_platforms):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.captured_messages = []  # 存储捕获到的消息
        self.original_send_method = None  # 保存原始的send方法
        self.target_event = None  # 目标事件对象
        
    def setup_message_interceptor(self, target_event):
        """设置消息拦截器来捕获指令的响应"""
        self.target_event = target_event
        self.captured_messages = []
        
        # 保存原始的send方法
        if self.original_send_method is None:
            self.original_send_method = target_event.send
        
        # 创建拦截器包装函数
        async def intercepted_send(message_chain):
            # 捕获这条消息
            logger.info(f"捕获到指令响应消息，包含 {len(message_chain.chain)} 个组件")
            self.captured_messages.append(message_chain)
            
            # 设置已发送标记，但不实际发送到平台
            target_event._has_send_oper = True
            return True
        
        # 替换事件的send方法
        target_event.send = intercepted_send
        logger.info(f"已设置消息拦截器，监听事件: {target_event.unified_msg_origin}")
    
    def restore_message_sender(self):
        """恢复原始的消息发送器"""
        if self.original_send_method and self.target_event:
            self.target_event.send = self.original_send_method
            logger.info("已恢复原始消息发送器")
    
    def create_command_event(self, unified_msg_origin: str, command: str, creator_id: str, creator_name: str = None) -> CoreAstrMessageEvent:
        """创建指令事件对象"""
        
        # 解析平台信息
        platform_name = "unknown"
        session_id = "unknown"
        message_type = MessageType.FRIEND_MESSAGE
        
        if ":" in unified_msg_origin:
            parts = unified_msg_origin.split(":")
            if len(parts) >= 3:
                platform_name = parts[0]
                msg_type_str = parts[1]
                session_id = ":".join(parts[2:])  # 可能包含多个冒号
                
                if "GroupMessage" in msg_type_str:
                    message_type = MessageType.GROUP_MESSAGE
                elif "FriendMessage" in msg_type_str:
                    message_type = MessageType.FRIEND_MESSAGE
        
        # 创建消息对象
        msg = AstrBotMessage()
        msg.message_str = command
        msg.session_id = session_id
        msg.type = message_type
        msg.self_id = "astrbot_command_trigger"
        
        # 设置发送者信息
        from astrbot.api.platform import MessageMember
        msg.sender = MessageMember(creator_id, creator_name or "用户")
        
        # 设置群组ID（如果是群聊）
        if message_type == MessageType.GROUP_MESSAGE:
            # 从session_id中提取群组ID
            if "_" in session_id:
                # 处理会话隔离格式
                group_id = session_id.split("_")[0]
            else:
                group_id = session_id
            msg.group_id = group_id
        
        # 设置消息链
        from astrbot.core.message.components import Plain as CorePlain
        msg.message = [CorePlain(command)]
        
        # 创建平台元数据
        meta = PlatformMetadata(platform_name, "command_trigger")
        
        # 创建新的事件对象
        fake_event = CoreAstrMessageEvent(
            message_str=command,
            message_obj=msg,
            platform_meta=meta,
            session_id=session_id
        )
        
        # 设置必要属性
        fake_event.unified_msg_origin = unified_msg_origin
        fake_event.is_wake = True  # 标记为唤醒状态
        fake_event.is_at_or_wake_command = True  # 标记为指令
        
        return fake_event
    
    async def trigger_and_capture_command(self, unified_msg_origin: str, command: str, creator_id: str, creator_name: str = None):
        """触发指令并捕获响应"""
        try:
            logger.info(f"开始触发指令: {command}")
            
            # 创建指令事件
            fake_event = self.create_command_event(unified_msg_origin, command, creator_id, creator_name)
            
            # 设置消息拦截器
            self.setup_message_interceptor(fake_event)
            
            # 提交事件到事件队列
            event_queue = self.context.get_event_queue()
            event_queue.put_nowait(fake_event)
            
            logger.info(f"已将指令事件 {command} 提交到事件队列")
            
            # 等待指令执行并捕获响应
            max_wait_time = 5.0  # 最大等待5秒
            wait_interval = 0.1   # 每100毫秒检查一次
            waited_time = 0.0
            
            while waited_time < max_wait_time:
                await asyncio.sleep(wait_interval)
                waited_time += wait_interval
                
                # 检查是否捕获到了消息
                if self.captured_messages:
                    logger.info(f"成功捕获到 {len(self.captured_messages)} 条响应消息")
                    break
            
            # 恢复原始消息发送器
            self.restore_message_sender()
            
            if self.captured_messages:
                return True, self.captured_messages
            else:
                logger.warning(f"等待 {max_wait_time} 秒后未捕获到指令 {command} 的响应消息")
                return False, []
            
        except Exception as e:
            logger.error(f"触发指令失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 确保恢复原始消息发送器
            self.restore_message_sender()
            return False, []
    
    async def trigger_and_forward_command(self, unified_msg_origin: str, reminder: dict, command: str):
        """触发指令并转发结果（用于定时任务）"""
        creator_id = reminder.get("creator_id", "unknown")
        creator_name = reminder.get("creator_name")
        
        # 触发指令并捕获响应
        success, captured_messages = await self.trigger_and_capture_command(
            unified_msg_origin, command, creator_id, creator_name
        )
        
        if success and captured_messages:
            logger.info(f"成功捕获到指令 {command} 的 {len(captured_messages)} 条响应，开始转发")
            
            # 转发捕获到的消息
            from .reminder_handlers import ReminderMessageHandler
            message_handler = ReminderMessageHandler(self.context, self.wechat_platforms)
            
            for i, captured_msg in enumerate(captured_messages):
                logger.info(f"转发第 {i+1} 条消息，包含 {len(captured_msg.chain)} 个组件")
                
                # 获取原始消息ID用于发送
                original_msg_origin = message_handler.get_original_session_id(unified_msg_origin)
                
                # 构建转发消息
                forward_msg = MessageChain()
                
                # 添加@消息（如果需要）
                if not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                    if original_msg_origin.startswith("aiocqhttp"):
                        from astrbot.api.message_components import At
                        forward_msg.chain.append(At(qq=reminder["creator_id"]))
                    elif any(original_msg_origin.startswith(platform) for platform in self.wechat_platforms):
                        if "creator_name" in reminder and reminder["creator_name"]:
                            forward_msg.chain.append(Plain(f"@{reminder['creator_name']} "))
                        else:
                            forward_msg.chain.append(Plain(f"@{reminder['creator_id']} "))
                    else:
                        forward_msg.chain.append(Plain(f"@{reminder['creator_id']} "))
                
                # 添加指令任务标识和结果
                forward_msg.chain.append(Plain(f"[指令任务] /{command}\n"))
                
                # 添加捕获到的消息内容
                for component in captured_msg.chain:
                    forward_msg.chain.append(component)
                
                # 发送转发消息
                await self.context.send_message(original_msg_origin, forward_msg)
                
                # 如果有多条消息，添加间隔
                if len(captured_messages) > 1 and i < len(captured_messages) - 1:
                    await asyncio.sleep(0.5)
        else:
            logger.warning(f"未能捕获到指令 {command} 的响应，发送错误提示")
            
            # 发送执行失败的提示
            from .reminder_handlers import ReminderMessageHandler
            message_handler = ReminderMessageHandler(self.context, self.wechat_platforms)
            original_msg_origin = message_handler.get_original_session_id(unified_msg_origin)
            
            error_msg = MessageChain()
            
            # 添加@消息（如果需要）
            if not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                if original_msg_origin.startswith("aiocqhttp"):
                    from astrbot.api.message_components import At
                    error_msg.chain.append(At(qq=reminder["creator_id"]))
                elif any(original_msg_origin.startswith(platform) for platform in self.wechat_platforms):
                    if "creator_name" in reminder and reminder["creator_name"]:
                        error_msg.chain.append(Plain(f"@{reminder['creator_name']} "))
                    else:
                        error_msg.chain.append(Plain(f"@{reminder['creator_id']} "))
                else:
                    error_msg.chain.append(Plain(f"@{reminder['creator_id']} "))
            
            error_msg.chain.append(Plain(f"[指令任务] /{command} 执行失败，未收到响应"))
            
            await self.context.send_message(original_msg_origin, error_msg)