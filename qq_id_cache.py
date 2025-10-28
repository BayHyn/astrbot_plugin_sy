"""
QQ号缓存工具模块
用于获取并缓存真实的QQ机器人ID，避免重复API调用
"""
import asyncio
from typing import Optional, Dict
from astrbot.api import logger

class QQIdCache:
    """QQ号缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, str] = {}  # platform_id -> qq_id
        self._lock = asyncio.Lock()
    
    async def get_qq_id(self, platform_id: str, platform_instance) -> str:
        """
        获取QQ号，优先从缓存获取，如果没有则从平台实例获取并缓存
        
        Args:
            platform_id: 平台ID
            platform_instance: 平台实例
            
        Returns:
            QQ号字符串，如果获取失败返回默认值
        """
        # 先检查缓存
        if platform_id in self._cache:
            logger.info(f"从缓存获取QQ号: {self._cache[platform_id]}")
            return self._cache[platform_id]
        
        # 缓存中没有，尝试获取真实QQ号
        async with self._lock:
            # 双重检查，防止并发时重复获取
            if platform_id in self._cache:
                return self._cache[platform_id]
            
            qq_id = await self._fetch_real_qq_id(platform_instance)
            self._cache[platform_id] = qq_id
            # logger.info(f"获取并缓存QQ号: {platform_id} -> {qq_id}")
            return qq_id
    
    async def _fetch_real_qq_id(self, platform_instance) -> str:
        """
        从平台实例获取真实的QQ号
        
        Args:
            platform_instance: 平台实例
            
        Returns:
            QQ号字符串
        """
        try:
            if not platform_instance:
                logger.warning("平台实例为空，使用默认QQ号")
                return "123456789"
            
            # 检查是否是aiocqhttp平台
            if hasattr(platform_instance, 'bot') and platform_instance.bot:
                bot = platform_instance.bot
                
                # 尝试调用get_login_info获取真实QQ号
                try:
                    login_info = await bot.get_login_info()
                    if login_info and 'user_id' in login_info:
                        qq_id = str(login_info['user_id'])
                        logger.info(f"成功获取真实QQ号: {qq_id}")
                        return qq_id
                except Exception as e:
                    logger.warning(f"调用get_login_info失败: {e}")
            
            # 尝试从平台实例的缓存属性获取
            for attr in ['_cached_self_id', 'cached_self_id', 'self_id', 'bot_id', 'user_id']:
                if hasattr(platform_instance, attr):
                    value = getattr(platform_instance, attr)
                    if value and not callable(value) and str(value) != "123456789":
                        logger.info(f"从平台实例属性 {attr} 获取QQ号: {value}")
                        return str(value)
            
        except Exception as e:
            logger.error(f"获取真实QQ号时发生错误: {e}")
        
        # 所有方法都失败，返回默认值
        logger.warning("无法获取真实QQ号，使用默认值")
        return "123456789"
    
    def set_qq_id(self, platform_id: str, qq_id: str):
        """
        手动设置QQ号缓存
        
        Args:
            platform_id: 平台ID
            qq_id: QQ号
        """
        self._cache[platform_id] = qq_id
        logger.info(f"手动设置QQ号缓存: {platform_id} -> {qq_id}")
    
    def clear_cache(self, platform_id: Optional[str] = None):
        """
        清除缓存
        
        Args:
            platform_id: 如果指定则只清除该平台的缓存，否则清除所有缓存
        """
        if platform_id:
            if platform_id in self._cache:
                del self._cache[platform_id]
                logger.info(f"清除平台 {platform_id} 的QQ号缓存")
        else:
            self._cache.clear()
            logger.info("清除所有QQ号缓存")

# 全局缓存实例
_qq_cache = QQIdCache()

async def get_cached_qq_id(platform_id: str, platform_instance) -> str:
    """
    获取缓存的QQ号的便捷函数
    
    Args:
        platform_id: 平台ID
        platform_instance: 平台实例
        
    Returns:
        QQ号字符串
    """
    return await _qq_cache.get_qq_id(platform_id, platform_instance)

def set_cached_qq_id(platform_id: str, qq_id: str):
    """
    设置缓存QQ号的便捷函数
    
    Args:
        platform_id: 平台ID
        qq_id: QQ号
    """
    _qq_cache.set_qq_id(platform_id, qq_id)

def clear_qq_cache(platform_id: Optional[str] = None):
    """
    清除QQ号缓存的便捷函数
    
    Args:
        platform_id: 如果指定则只清除该平台的缓存，否则清除所有缓存
    """
    _qq_cache.clear_cache(platform_id)

def init_qq_id_cache(context):
    """初始化QQ号缓存"""
    try:
        # 检查是否有平台管理器和平台实例
        if not hasattr(context, 'platform_manager') or not context.platform_manager:
            logger.warning("未找到平台管理器，跳过QQ号缓存初始化")
            return
            
        platform_insts = context.platform_manager.platform_insts
        if not platform_insts:
            logger.warning("未找到平台实例，跳过QQ号缓存初始化")
            return
        
        # 异步初始化所有平台的QQ号
        asyncio.create_task(_init_platform_qq_id(platform_insts))
        logger.info(f"QQ号缓存初始化任务已启动，共 {len(platform_insts)} 个平台实例")
        
    except Exception as e:
        logger.error(f"初始化QQ号缓存失败: {e}")


async def _init_platform_qq_id(platform_insts):
    """异步初始化平台QQ号"""
    try:
        for platform in platform_insts:
            try:
                # 获取平台信息
                platform_id = getattr(platform, 'platform_id', 'unknown')
                platform_type = getattr(platform, 'platform_type', 'unknown')
                
                # 获取并缓存QQ号
                qq_id = await _qq_cache.get_qq_id(platform_id, platform)
                
                if qq_id and qq_id != "123456789":
                    logger.debug(f"成功缓存平台 {platform_type}({platform_id}) 的QQ号: {qq_id}")
                else:
                    logger.warning(f"平台 {platform_type}({platform_id}) 未能获取有效QQ号，使用默认值")
            except Exception as e:
                platform_id = getattr(platform, 'platform_id', 'unknown')
                platform_type = getattr(platform, 'platform_type', 'unknown')
                logger.error(f"初始化平台 {platform_type}({platform_id}) QQ号失败: {e}")
    except Exception as e:
        logger.error(f"批量初始化平台QQ号失败: {e}")