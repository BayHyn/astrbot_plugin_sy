import asyncio
from astrbot.api import logger
from astrbot.api.message_components import Plain, Video
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from .event_factory import EventFactory
from .utils import get_platform_type_from_origin


class CommandTrigger:
    """指令触发器，用于触发其他插件指令并转发结果"""
    
    def __init__(self, context, wechat_platforms, config=None):
        self.context = context
        self.wechat_platforms = wechat_platforms
        self.config = config or {}
        self.captured_messages = []  # 存储捕获到的消息
        self.original_send_method = None  # 保存原始的send方法
        self.target_event = None  # 目标事件对象
        self.event_factory = EventFactory(context)  # 事件工厂
        
    def _add_at_message(self, msg_chain, original_msg_origin, reminder):
        """添加@消息的helper函数"""
        platform_type = get_platform_type_from_origin(original_msg_origin, self.context)
        if platform_type == "aiocqhttp":
            from astrbot.api.message_components import At
            # QQ平台 - 优先使用昵称，回退到ID
            if "creator_name" in reminder and reminder["creator_name"]:
                msg_chain.chain.append(At(qq=reminder["creator_id"], name=reminder["creator_name"]))
            else:
                msg_chain.chain.append(At(qq=reminder["creator_id"]))
        elif platform_type in self.wechat_platforms:
            if "creator_name" in reminder and reminder["creator_name"]:
                msg_chain.chain.append(Plain(f"@{reminder['creator_name']} "))
            else:
                msg_chain.chain.append(Plain(f"@{reminder['creator_id']} "))
        else:
            msg_chain.chain.append(Plain(f"@{reminder['creator_id']} "))
    
    def setup_message_interceptor(self, target_event):
        """设置消息拦截器来捕获指令的响应"""
        self.target_event = target_event
        self.captured_messages = []
        
        # 保存原始的send方法
        if self.original_send_method is None:
            self.original_send_method = target_event.send
        
        # 保存原始的bot.api.call_action方法（如果存在）
        self.original_call_action = None
        if hasattr(target_event, 'bot') and hasattr(target_event.bot, 'api') and hasattr(target_event.bot.api, 'call_action'):
            self.original_call_action = target_event.bot.api.call_action
        
        # 创建拦截器包装函数
        async def intercepted_send(message_chain):
            # 捕获这条消息
            logger.info(f"捕获到指令响应消息，包含 {len(message_chain.chain)} 个组件")
            self.captured_messages.append(message_chain)
            
            # 设置已发送标记，但不实际发送到平台
            target_event._has_send_oper = True
            return True
        
        # 创建bot.api.call_action拦截器
        async def intercepted_call_action(action, **params):
            # 检查是否是发送消息的action
            if action in ["send_private_msg", "send_group_msg", "send_private_forward_msg", "send_group_forward_msg"]:
                logger.info(f"拦截到bot.api.call_action调用: {action}")
                
                # 从params中提取消息内容并转换为MessageChain
                if "message" in params:
                    from astrbot.core.message.message_event_result import MessageChain
                    from astrbot.api.message_components import Plain, At
                    
                    msg_chain = MessageChain()
                    message_data = params["message"]
                    
                    # 处理消息数据
                    if isinstance(message_data, list):
                        for seg in message_data:
                            if isinstance(seg, dict):
                                seg_type = seg.get("type", "")
                                seg_data = seg.get("data", {})
                                
                                if seg_type == "text":
                                    msg_chain.chain.append(Plain(seg_data.get("text", "")))
                                elif seg_type == "at":
                                    qq = seg_data.get("qq", "")
                                    msg_chain.chain.append(At(qq=qq))
                                # 可以根据需要添加更多消息类型的处理
                    
                    # 捕获转换后的消息
                    if msg_chain.chain:
                        logger.info(f"从bot.api.call_action捕获到消息，包含 {len(msg_chain.chain)} 个组件")
                        self.captured_messages.append(msg_chain)
                
                # 设置已发送标记，但不实际发送
                target_event._has_send_oper = True
                return {"message_id": 12345}  # 返回一个假的message_id
            else:
                # 对于非发送消息的action，调用原始方法
                if self.original_call_action:
                    return await self.original_call_action(action, **params)
                else:
                    return {}
        
        # 替换事件的send方法
        target_event.send = intercepted_send
        
        # 替换bot.api.call_action方法（如果存在）
        if self.original_call_action:
            target_event.bot.api.call_action = intercepted_call_action
        
        logger.info(f"已设置消息拦截器，监听事件: {target_event.unified_msg_origin}")
    
    def restore_message_sender(self):
        """恢复原始的消息发送器"""
        if self.original_send_method and self.target_event:
            self.target_event.send = self.original_send_method
            logger.info("已恢复原始消息发送器")
        
        # 恢复原始的bot.api.call_action方法
        if hasattr(self, 'original_call_action') and self.original_call_action and self.target_event:
            if hasattr(self.target_event, 'bot') and hasattr(self.target_event.bot, 'api'):
                self.target_event.bot.api.call_action = self.original_call_action
                logger.info("已恢复原始bot.api.call_action方法")
    
    def create_command_event(self, unified_msg_origin: str, command: str, creator_id: str, creator_name: str = None) -> AstrMessageEvent:
        """创建指令事件对象"""
        return self.event_factory.create_event(unified_msg_origin, command, creator_id, creator_name)
    
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
            max_wait_time = self.config.get('max_command_wait_time', 20.0)  # 从配置获取最大等待时间，默认20秒
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
        
        # 获取实际执行的命令
        actual_command = command
        if "commands" in reminder and isinstance(reminder["commands"], list) and len(reminder["commands"]) > 0:
            actual_command = reminder["commands"][0]  # 取第一个（也是唯一的）命令
        
        # 触发指令并捕获响应
        success, captured_messages = await self.trigger_and_capture_command(
            unified_msg_origin, actual_command, creator_id, creator_name
        )
        
        if success and captured_messages:
            logger.info(f"成功捕获到指令 {command} 的 {len(captured_messages)} 条响应，开始转发")
            
            # 转发捕获到的消息
            from .reminder_handlers import ReminderMessageHandler
            message_handler = ReminderMessageHandler(self.context, self.wechat_platforms, self.config)
            
            for i, captured_msg in enumerate(captured_messages):
                logger.info(f"转发第 {i+1} 条消息，包含 {len(captured_msg.chain)} 个组件")
                
                # 获取原始消息ID用于发送
                original_msg_origin = message_handler.get_original_session_id(unified_msg_origin)
                
                # 检查是否包含视频组件
                has_video = any(isinstance(comp, Video) for comp in captured_msg.chain)
                
                # 构建指令任务标识文本
                command_display = reminder.get("text", command)
                custom_identifier = reminder.get("custom_identifier")
                
                # 检查自定义标识的位置
                position = custom_identifier.get("position", "start") if custom_identifier else "start"
                
                # 构建标识文本
                if custom_identifier and custom_identifier.get("text"):
                    custom_text = custom_identifier["text"]
                    # 检查是否隐藏指令任务标识
                    if self.config.get("hide_command_identifier", False):
                        # 隐藏模式：只显示自定义文本
                        identifier_text = custom_text
                    else:
                        # 正常模式：显示完整格式
                        if position == "start":
                            identifier_text = f"[{custom_text}] {command_display}"
                        else:
                            # end位置：使用自定义标识替换"指令任务"
                            identifier_text = f"[{custom_text}] {command_display}"
                else:
                    # 没有自定义标识时，检查是否隐藏
                    if self.config.get("hide_command_identifier", False):
                        # 隐藏模式：不显示任何标识
                        identifier_text = ""
                    else:
                        # 正常模式：显示默认标识
                        identifier_text = f"[指令任务] {command_display}"
                
                # 如果包含视频且是QQ平台，需要分开发送
                platform_type = get_platform_type_from_origin(original_msg_origin, self.context)
                if has_video and platform_type == "aiocqhttp":
                    logger.info("检测到视频消息，QQ平台需要分开发送文字和视频")
                    
                    # 先发送文字标识（如果是start位置）
                    if identifier_text and position == "start":
                        text_msg = MessageChain()
                        
                        # 添加@消息（如果需要）
                        should_at = self.config.get("enable_command_at", False)
                        if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                            self._add_at_message(text_msg, original_msg_origin, reminder)
                        
                        text_msg.chain.append(Plain(identifier_text))
                        await self.context.send_message(original_msg_origin, text_msg)
                        await asyncio.sleep(0.3)  # 短暂间隔
                    
                    # 发送视频消息
                    video_msg = MessageChain()
                    
                    # 添加@消息（如果需要）
                    should_at = self.config.get("enable_command_at", False)
                    if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                        self._add_at_message(video_msg, original_msg_origin, reminder)
                    
                    # 只添加视频组件
                    for component in captured_msg.chain:
                        if isinstance(component, Video):
                            video_msg.chain.append(component)
                    
                    await self.context.send_message(original_msg_origin, video_msg)
                    
                    # 如果是end位置，在视频发送后再发送文字标识
                    if identifier_text and position == "end":
                        await asyncio.sleep(0.3)  # 短暂间隔
                        end_text_msg = MessageChain()
                        
                        # 添加@消息（如果需要）
                        should_at = self.config.get("enable_command_at", False)
                        if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                            self._add_at_message(end_text_msg, original_msg_origin, reminder)
                        
                        end_text_msg.chain.append(Plain(identifier_text))
                        await self.context.send_message(original_msg_origin, end_text_msg)
                    
                else:
                    # 其他情况，正常发送
                    forward_msg = MessageChain()
                    
                    # 添加@消息（如果需要）
                    should_at = self.config.get("enable_command_at", False)
                    if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                        self._add_at_message(forward_msg, original_msg_origin, reminder)
                    
                    # 如果是start位置，先添加标识再添加消息内容
                    if position == "start" and identifier_text:
                        forward_msg.chain.append(Plain(identifier_text + "\n"))
                    
                    # 添加捕获到的消息内容
                    for component in captured_msg.chain:
                        forward_msg.chain.append(component)
                    
                    # 发送转发消息
                    await self.context.send_message(original_msg_origin, forward_msg)
                    
                    # 如果是end位置，在消息发送后再发送标识
                    if position == "end" and identifier_text:
                        await asyncio.sleep(0.3)  # 短暂间隔
                        end_text_msg = MessageChain()
                        
                        # 添加@消息（如果需要）
                        should_at = self.config.get("enable_command_at", False)
                        if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                            self._add_at_message(end_text_msg, original_msg_origin, reminder)
                        
                        end_text_msg.chain.append(Plain(identifier_text))
                        await self.context.send_message(original_msg_origin, end_text_msg)
                
                # 如果有多条消息，添加间隔
                if len(captured_messages) > 1 and i < len(captured_messages) - 1:
                    await asyncio.sleep(0.5)
        else:
            logger.warning(f"未能捕获到指令 {command} 的响应，发送错误提示")
            
            # 发送执行失败的提示
            from .reminder_handlers import ReminderMessageHandler
            message_handler = ReminderMessageHandler(self.context, self.wechat_platforms, self.config)
            original_msg_origin = message_handler.get_original_session_id(unified_msg_origin)
            
            error_msg = MessageChain()
            
            # 添加@消息（如果需要）
            should_at = self.config.get("enable_command_at", False)
            if should_at and not message_handler.is_private_chat(unified_msg_origin) and "creator_id" in reminder and reminder["creator_id"]:
                self._add_at_message(error_msg, original_msg_origin, reminder)
            
            command_display = reminder.get("text", command)
            
            # 检查是否有自定义标识
            custom_identifier = reminder.get("custom_identifier")
            if custom_identifier and custom_identifier.get("text"):
                custom_text = custom_identifier["text"]
                position = custom_identifier.get("position", "start")
                
                if position == "start":
                    # 放在开头
                    error_msg.chain.append(Plain(f"[{custom_text}] {command_display} 执行失败，未收到响应"))
                else:
                    # 放在末尾
                    error_msg.chain.append(Plain(f"[指令任务] {command_display} 执行失败，未收到响应 [{custom_text}]"))
            else:
                # 默认标识
                error_msg.chain.append(Plain(f"[指令任务] {command_display} 执行失败，未收到响应"))
            
            await self.context.send_message(original_msg_origin, error_msg)