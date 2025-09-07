import time
from typing import Optional
from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.message.components import Plain
from .utils import get_platform_type_from_origin


class EventFactory:
    """事件工厂类，用于创建不同平台类型的事件对象"""
    
    def __init__(self, context):
        self.context = context
    
    def _get_platform_instance(self, platform_type: str):
        """获取平台实例的兼容性方法"""
        try:
            # 首先尝试使用 get_platform (v3兼容)
            if hasattr(self.context, 'get_platform'):
                return self.context.get_platform(platform_type)
        except Exception as e:
            logger.warning(f"使用get_platform获取平台实例失败: {e}")
        
        # 如果上面失败，尝试通过平台管理器遍历查找
        try:
            if hasattr(self.context, 'platform_manager') and hasattr(self.context.platform_manager, 'platform_insts'):
                for platform_inst in self.context.platform_manager.platform_insts:
                    if hasattr(platform_inst, 'meta') and platform_inst.meta().name == platform_type:
                        return platform_inst
        except Exception as e:
            logger.warning(f"通过platform_manager获取平台实例失败: {e}")
        
        return None
    
    def create_event(self, unified_msg_origin: str, command: str, creator_id: str, creator_name: str = None) -> AstrMessageEvent:
        """创建事件对象，根据平台类型自动选择正确的事件类"""
        
        # 解析平台信息
        platform_name = "unknown"
        session_id = "unknown"
        message_type = MessageType.FRIEND_MESSAGE
        
        if ":" in unified_msg_origin:
            parts = unified_msg_origin.split(":")
            if len(parts) >= 3:
                # 使用兼容性工具提取平台类型，而不是直接使用第一部分
                platform_name = get_platform_type_from_origin(unified_msg_origin)
                msg_type_str = parts[1]
                session_id = ":".join(parts[2:])  # 可能包含多个冒号
                
                if "GroupMessage" in msg_type_str:
                    message_type = MessageType.GROUP_MESSAGE
                elif "FriendMessage" in msg_type_str:
                    message_type = MessageType.FRIEND_MESSAGE
        
        # 创建基础消息对象
        msg = self._create_message_object(command, session_id, message_type, creator_id, creator_name)
        
        # 创建平台元数据
        meta = PlatformMetadata(platform_name, "command_trigger")
        
        # 根据平台类型创建正确的事件对象
        return self._create_platform_specific_event(platform_name, command, msg, meta, session_id)
    
    def _create_message_object(self, command: str, session_id: str, message_type: MessageType, 
                              creator_id: str, creator_name: str = None) -> AstrBotMessage:
        """创建消息对象"""
        msg = AstrBotMessage()
        msg.message_str = command
        msg.session_id = session_id
        msg.type = message_type
        msg.self_id = "astrbot_command_trigger"
        msg.message_id = "command_trigger_" + str(int(time.time()))
        
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
        msg.message = [Plain(command)]
        
        # 设置raw_message属性（模拟原始消息对象）
        msg.raw_message = {
            "message": command,
            "message_type": message_type.value,
            "sender": {"user_id": creator_id, "nickname": creator_name or "用户"},
            "self_id": "astrbot_command_trigger"
        }
        
        return msg
    
    def _create_platform_specific_event(self, platform_name: str, command: str, msg: AstrBotMessage, 
                                       meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """根据平台类型创建特定的事件对象"""
        
        if platform_name == "aiocqhttp":
            return self._create_aiocqhttp_event(command, msg, meta, session_id)
        elif platform_name == "qq_official":
            return self._create_qq_official_event(command, msg, meta, session_id)
        elif platform_name == "telegram":
            return self._create_telegram_event(command, msg, meta, session_id)
        elif platform_name == "discord":
            return self._create_discord_event(command, msg, meta, session_id)
        elif platform_name == "slack":
            return self._create_slack_event(command, msg, meta, session_id)
        elif platform_name == "lark":
            return self._create_lark_event(command, msg, meta, session_id)
        elif platform_name == "wechatpadpro":
            return self._create_wechatpadpro_event(command, msg, meta, session_id)
        elif platform_name == "webchat":
            return self._create_webchat_event(command, msg, meta, session_id)
        elif platform_name == "dingtalk":
            return self._create_dingtalk_event(command, msg, meta, session_id)
        else:
            # 默认使用基础事件对象
            return self._create_base_event(command, msg, meta, session_id)
    
    def _create_aiocqhttp_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 aiocqhttp 平台事件"""
        try:
            platform = self._get_platform_instance("aiocqhttp")
            if platform and hasattr(platform, 'bot'):
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                event = AiocqhttpMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.bot
                )
                logger.info("成功创建 AiocqhttpMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 AiocqhttpMessageEvent 失败: {e}")
        
        # 回退到基础事件
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_qq_official_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 QQ 官方平台事件"""
        try:
            platform = self._get_platform_instance("qq_official")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
                event = QQOfficialMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.client
                )
                logger.info("成功创建 QQOfficialMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 QQOfficialMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_telegram_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Telegram 平台事件"""
        try:
            platform = self._get_platform_instance("telegram")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                event = TelegramPlatformEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 TelegramPlatformEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 TelegramPlatformEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_discord_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Discord 平台事件"""
        try:
            platform = self._get_platform_instance("discord")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.discord.discord_platform_event import DiscordPlatformEvent
                event = DiscordPlatformEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 DiscordPlatformEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 DiscordPlatformEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_slack_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Slack 平台事件"""
        try:
            platform = self._get_platform_instance("slack")
            if platform and hasattr(platform, 'web_client'):
                from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
                event = SlackMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    web_client=platform.web_client
                )
                logger.info("成功创建 SlackMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 SlackMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_lark_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 Lark 平台事件"""
        try:
            platform = self._get_platform_instance("lark")
            if platform and hasattr(platform, 'bot'):
                from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
                event = LarkMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    bot=platform.bot
                )
                logger.info("成功创建 LarkMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 LarkMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_wechatpadpro_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 WeChatPadPro 平台事件"""
        try:
            platform = self._get_platform_instance("wechatpadpro")
            if platform:
                from astrbot.core.platform.sources.wechatpadpro.wechatpadpro_message_event import WeChatPadProMessageEvent
                event = WeChatPadProMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    adapter=platform
                )
                logger.info("成功创建 WeChatPadProMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 WeChatPadProMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_webchat_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建 WebChat 平台事件"""
        try:
            from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
            event = WebChatMessageEvent(
                message_str=command,
                message_obj=msg,
                platform_meta=meta,
                session_id=session_id
            )
            logger.info("成功创建 WebChatMessageEvent")
            return event
        except Exception as e:
            logger.warning(f"创建 WebChatMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_dingtalk_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建钉钉平台事件"""
        try:
            platform = self._get_platform_instance("dingtalk")
            if platform and hasattr(platform, 'client'):
                from astrbot.core.platform.sources.dingtalk.dingtalk_event import DingtalkMessageEvent
                event = DingtalkMessageEvent(
                    message_str=command,
                    message_obj=msg,
                    platform_meta=meta,
                    session_id=session_id,
                    client=platform.client
                )
                logger.info("成功创建 DingtalkMessageEvent")
                return event
        except Exception as e:
            logger.warning(f"创建 DingtalkMessageEvent 失败: {e}")
        
        return self._create_base_event(command, msg, meta, session_id)
    
    def _create_base_event(self, command: str, msg: AstrBotMessage, meta: PlatformMetadata, session_id: str) -> AstrMessageEvent:
        """创建基础事件对象（作为回退方案）"""
        from astrbot.core.platform.astr_message_event import AstrMessageEvent as CoreAstrMessageEvent
        
        event = CoreAstrMessageEvent(
            message_str=command,
            message_obj=msg,
            platform_meta=meta,
            session_id=session_id
        )
        
        # 设置必要属性
        event.unified_msg_origin = f"{meta.name}:{msg.type.value}:{session_id}"
        event.is_wake = True  # 标记为唤醒状态
        event.is_at_or_wake_command = True  # 标记为指令
        
        logger.info("使用基础 AstrMessageEvent")
        return event