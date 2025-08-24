import datetime
import json
import os
import aiohttp
from astrbot.api import logger

def parse_datetime(datetime_str: str) -> str:
    '''解析时间字符串，支持简单时间格式，可选择星期'''
    try:
        today = datetime.datetime.now()
        
        # 处理输入字符串，去除多余空格
        datetime_str = datetime_str.strip()
        
        # 解析时间
        try:
            hour, minute = map(int, datetime_str.split(':'))
        except ValueError:
            try:
                # 尝试处理无冒号格式 (如 "0805")
                if len(datetime_str) == 4:
                    hour = int(datetime_str[:2])
                    minute = int(datetime_str[2:])
                else:
                    raise ValueError()
            except:
                raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）或 HHMM 格式（如 0805）")
        
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间超出范围")
            
        # 设置时间
        dt = today.replace(hour=hour, minute=minute)
        if dt < today:  # 如果时间已过，设置为明天
            dt += datetime.timedelta(days=1)
        
        return dt.strftime("%Y-%m-%d %H:%M")
        
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError("时间格式错误，请使用 HH:MM 格式（如 8:05）或 HHMM 格式（如 0805）")

def is_outdated(reminder: dict) -> bool:
    '''检查提醒是否过期'''
    if "datetime" in reminder and reminder["datetime"]:  # 确保datetime存在且不为空
        try:
            return datetime.datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M") < datetime.datetime.now()
        except ValueError:
            # 如果日期格式不正确，记录错误并返回False
            logger.error(f"提醒的日期时间格式错误: {reminder.get('datetime', '')}")
            return False
    return False

def load_reminder_data(data_file: str) -> dict:
    '''加载提醒数据'''
    if not os.path.exists(data_file):
        with open(data_file, "w", encoding='utf-8') as f:
            f.write("{}")
    with open(data_file, "r", encoding='utf-8') as f:
        return json.load(f)

async def save_reminder_data(data_file: str, reminder_data: dict):
    '''保存提醒数据'''
    # 在保存前清理过期的一次性任务和无效数据
    for group in list(reminder_data.keys()):
        reminder_data[group] = [
            r for r in reminder_data[group] 
            if "datetime" in r and r["datetime"] and  # 确保datetime字段存在且不为空
               not (r.get("repeat", "none") == "none" and is_outdated(r))
        ]
        # 如果群组没有任何提醒了，删除这个群组的条目
        if not reminder_data[group]:
            del reminder_data[group]
            
    with open(data_file, "w", encoding='utf-8') as f:
        json.dump(reminder_data, f, ensure_ascii=False)

# 法定节假日相关功能
class HolidayManager:
    def __init__(self):
        # 数据文件路径处理 - 符合框架规范并保持向后兼容
        old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
        old_holiday_file = os.path.join(old_data_dir, "holiday_data", "holiday_cache.json")
        
        try:
            from astrbot.api.star import StarTools
            plugin_data_dir = StarTools.get_data_dir("ai_reminder")
            new_holiday_file = plugin_data_dir / "holiday_cache.json"
            
            # 检查旧位置是否存在节假日缓存文件
            if os.path.exists(old_holiday_file):
                # 旧位置有数据，执行数据迁移
                logger.info(f"检测到旧节假日缓存文件，开始数据迁移...")
                logger.info(f"旧位置: {old_holiday_file}")
                logger.info(f"新位置: {new_holiday_file}")
                
                # 确保新目录存在
                plugin_data_dir.mkdir(parents=True, exist_ok=True)
                
                # 迁移节假日缓存文件
                import shutil
                try:
                    # 复制文件到新位置
                    shutil.copy2(old_holiday_file, new_holiday_file)
                    logger.info(f"节假日缓存迁移成功: {old_holiday_file} -> {new_holiday_file}")
                    
                    # 删除旧文件
                    os.remove(old_holiday_file)
                    logger.info(f"旧节假日缓存文件已删除: {old_holiday_file}")
                    
                    # 使用新位置
                    self.holiday_cache_file = new_holiday_file
                    logger.info(f"使用新的框架规范节假日缓存目录: {self.holiday_cache_file}")
                    
                except Exception as e:
                    logger.error(f"节假日缓存迁移失败: {e}")
                    # 迁移失败，继续使用旧位置
                    self.holiday_cache_file = old_holiday_file
                    logger.info(f"迁移失败，继续使用旧节假日缓存目录: {self.holiday_cache_file}")
            else:
                # 旧位置没有数据，直接使用新位置
                self.holiday_cache_file = new_holiday_file
                logger.info(f"使用框架规范节假日缓存目录: {self.holiday_cache_file}")
                
        except Exception as e:
            # 如果框架方法失败，回退到旧的数据目录
            os.makedirs(os.path.join(old_data_dir, "holiday_data"), exist_ok=True)
            self.holiday_cache_file = old_holiday_file
            logger.info(f"回退到兼容节假日缓存目录: {self.holiday_cache_file}")
            logger.warning(f"框架数据目录获取失败: {e}")
        
        self.holiday_data = self._load_holiday_data()
        
    def _load_holiday_data(self) -> dict:
        """加载节假日数据缓存"""
        if not os.path.exists(self.holiday_cache_file):
            return {}
        
        try:
            with open(self.holiday_cache_file, "r", encoding='utf-8') as f:
                data = json.load(f)
                
            # 检查数据是否过期（缓存超过30天更新一次）
            if "last_update" in data:
                last_update = datetime.datetime.fromisoformat(data["last_update"])
                now = datetime.datetime.now()
                if (now - last_update).days > 30:
                    logger.info("节假日数据缓存已过期，需要更新")
                    return {}
                    
            return data
        except Exception as e:
            logger.error(f"加载节假日数据缓存失败: {e}")
            return {}
    
    async def _save_holiday_data(self):
        """保存节假日数据缓存"""
        try:
            # 添加最后更新时间
            self.holiday_data["last_update"] = datetime.datetime.now().isoformat()
            
            with open(self.holiday_cache_file, "w", encoding='utf-8') as f:
                json.dump(self.holiday_data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存节假日数据缓存失败: {e}")
            
    async def fetch_holiday_data(self, year: int = None) -> dict:
        """获取指定年份的节假日数据
        
        Args:
            year: 年份，默认为当前年份
            
        Returns:
            dict: 节假日数据，格式为 {日期字符串: 布尔值}
                  布尔值说明: True-法定节假日, False-调休工作日（需要补班的周末）
        """
        if year is None:
            year = datetime.datetime.now().year
            
        # 如果缓存中已有数据则直接返回
        year_key = str(year)
        if year_key in self.holiday_data and "data" in self.holiday_data[year_key]:
            return self.holiday_data[year_key]["data"]
            
        # 否则从API获取
        try:
            # 使用 http://timor.tech/api/holiday/year/{year} 接口获取数据
            url = f"http://timor.tech/api/holiday/year/{year}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"获取节假日数据失败，状态码: {response.status}")
                        return {}
                        
                    json_data = await response.json()
                    
                    if json_data.get("code") != 0:
                        logger.error(f"获取节假日数据失败: {json_data.get('msg')}")
                        return {}
                    
                    holiday_data = {}
                    for date_str, info in json_data.get("holiday", {}).items():
                        holiday_data[date_str] = info.get("holiday")
                    
                    # 缓存数据
                    if year_key not in self.holiday_data:
                        self.holiday_data[year_key] = {}
                    self.holiday_data[year_key]["data"] = holiday_data
                    await self._save_holiday_data()
                    
                    return holiday_data
        except Exception as e:
            logger.error(f"获取节假日数据出错: {e}")
            return {}
    
    async def is_holiday(self, date: datetime.datetime = None) -> bool:
        """判断指定日期是否为法定节假日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为法定节假日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为True，表示法定节假日
            is_holiday = holiday_data[short_date_str] == True
            return is_holiday
            
        # 如果不在特殊日期列表中，则根据是否为周末判断
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return True
            
        return False
    
    async def is_workday(self, date: datetime.datetime = None) -> bool:
        """判断指定日期是否为工作日
        
        Args:
            date: 日期，默认为当天
            
        Returns:
            bool: 是否为工作日
        """
        if date is None:
            date = datetime.datetime.now()
            
        year = date.year
        # 获取完整日期和不含年份的日期
        full_date_str = date.strftime("%Y-%m-%d")
        short_date_str = date.strftime("%m-%d")
        
        # 获取该年份的节假日数据
        holiday_data = await self.fetch_holiday_data(year)
        
        # 判断是否在节假日数据中，使用不含年份的短日期格式
        if short_date_str in holiday_data:
            # 如果值为False，表示调休工作日（需要补班的周末）
            # 如果值为True，表示法定节假日
            is_workday = holiday_data[short_date_str] == False
            return is_workday
            
        # 如果是周末且不在节假日数据中，则不是工作日
        if date.weekday() >= 5:  # 5和6分别是周六和周日
            return False
            
        return True 