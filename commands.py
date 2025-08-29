import datetime
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.api import logger
from apscheduler.schedulers.base import JobLookupError
from .utils import parse_datetime, save_reminder_data
from .command_utils import CommandUtils

class ReminderCommands:
    def __init__(self, star_instance):
        self.star = star_instance
        self.context = star_instance.context
        self.reminder_data = star_instance.reminder_data
        self.data_file = star_instance.data_file
        self.scheduler_manager = star_instance.scheduler_manager
        self.unique_session = star_instance.unique_session
        self.tools = star_instance.tools

    async def list_reminders(self, event: AstrMessageEvent):
        '''列出所有提醒和任务'''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取会话ID
        raw_msg_origin = event.unified_msg_origin
        if self.unique_session:
            # 使用会话隔离
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
        else:
            msg_origin = raw_msg_origin
            
        reminders = self.reminder_data.get(msg_origin, [])
        if not reminders:
            yield event.plain_result("当前没有设置任何提醒或任务。")
            return
            
        provider = self.context.get_using_provider()
        if provider:
            try:
                # 分离提醒、任务和指令任务
                reminder_items = []
                task_items = []
                command_task_items = []
                
                for r in reminders:
                    if r.get("is_command_task", False):
                        # 指令任务，显示完整指令
                        command_text = r['text']
                        command_task_items.append(f"- {command_text} (时间: {r['datetime']})")
                    elif r.get("is_task", False):
                        # 普通任务
                        task_items.append(f"- {r['text']} (时间: {r['datetime']})")
                    else:
                        # 提醒
                        reminder_items.append(f"- {r['text']} (时间: {r['datetime']})")
                
                # 构建提示
                prompt = "请帮我整理并展示以下提醒和任务列表，用自然的语言表达：\n"
                
                if reminder_items:
                    prompt += f"\n提醒列表：\n" + "\n".join(reminder_items)
                
                if task_items:
                    prompt += f"\n\n任务列表：\n" + "\n".join(task_items)
                
                if command_task_items:
                    prompt += f"\n\n指令任务列表：\n" + "\n".join(command_task_items)
                
                prompt += "\n\n同时告诉用户可以使用/rmd rm <序号>删除提醒、任务或指令任务，或者直接命令你来删除。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
                
                response = await provider.text_chat(
                    prompt=prompt,
                    session_id=event.session_id,
                    contexts=[]  # 确保contexts是一个空列表而不是None
                )
                yield event.plain_result(response.completion_text)
            except Exception as e:
                logger.error(f"在list_reminders中调用LLM时出错: {str(e)}")
                # 如果LLM调用失败，回退到基本显示
                reminder_str = "当前的提醒和任务：\n"
                
                # 分类显示
                reminders_list = [r for r in reminders if not r.get("is_task", False)]
                tasks_list = [r for r in reminders if r.get("is_task", False) and not r.get("is_command_task", False)]
                command_tasks_list = [r for r in reminders if r.get("is_command_task", False)]
                
                if reminders_list:
                    reminder_str += "\n提醒：\n"
                    for i, reminder in enumerate(reminders_list):
                        reminder_str += f"{i+1}. {reminder['text']} - {reminder['datetime']}\n"
                
                if tasks_list:
                    reminder_str += "\n任务：\n"
                    for i, task in enumerate(tasks_list):
                        reminder_str += f"{len(reminders_list)+i+1}. {task['text']} - {task['datetime']}\n"
                
                if command_tasks_list:
                    reminder_str += "\n指令任务：\n"
                    current_index = len(reminders_list) + len(tasks_list)
                    for i, cmd_task in enumerate(command_tasks_list):
                        reminder_str += f"{current_index+i+1}. /{cmd_task['text']} - {cmd_task['datetime']}\n"
                
                reminder_str += "\n使用 /rmd rm <序号> 删除提醒、任务或指令任务"
                yield event.plain_result(reminder_str)
        else:
            reminder_str = "当前的提醒和任务：\n"
            
            # 分类显示
            reminders_list = [r for r in reminders if not r.get("is_task", False)]
            tasks_list = [r for r in reminders if r.get("is_task", False) and not r.get("is_command_task", False)]
            command_tasks_list = [r for r in reminders if r.get("is_command_task", False)]
            
            if reminders_list:
                reminder_str += "\n提醒：\n"
                for i, reminder in enumerate(reminders_list):
                    reminder_str += f"{i+1}. {reminder['text']} - {reminder['datetime']}\n"
            
            if tasks_list:
                reminder_str += "\n任务：\n"
                for i, task in enumerate(tasks_list):
                    reminder_str += f"{len(reminders_list)+i+1}. {task['text']} - {task['datetime']}\n"
            
            if command_tasks_list:
                reminder_str += "\n指令任务：\n"
                current_index = len(reminders_list) + len(tasks_list)
                for i, cmd_task in enumerate(command_tasks_list):
                    reminder_str += f"{current_index+i+1}. /{cmd_task['text']} - {cmd_task['datetime']}\n"
            
            reminder_str += "\n使用 /rmd rm <序号> 删除提醒、任务或指令任务"
            yield event.plain_result(reminder_str)

    async def remove_reminder(self, event: AstrMessageEvent, index: int):
        '''删除提醒、任务或指令任务
        
        Args:
            index(int): 提醒、任务或指令任务的序号
        '''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取会话ID
        raw_msg_origin = event.unified_msg_origin
        if self.unique_session:
            # 使用会话隔离
            msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
        else:
            msg_origin = raw_msg_origin
            
        reminders = self.reminder_data.get(msg_origin, [])
        if not reminders:
            yield event.plain_result("没有设置任何提醒或任务。")
            return
            
        if index < 1 or index > len(reminders):
            yield event.plain_result("序号无效。")
            return
            
        # 获取要删除的提醒或任务
        # 由于任务ID包含时间戳，我们需要通过遍历所有任务来找到匹配的
        removed = reminders[index - 1]
        
        # 尝试删除调度任务 - 通过遍历所有任务找到匹配的
        job_found = False
        for job in self.scheduler_manager.scheduler.get_jobs(): 
            if job.id.startswith(f"reminder_{msg_origin}_{index-1}_"):
                try:
                    self.scheduler_manager.remove_job(job.id)
                    logger.info(f"Successfully removed job: {job.id}")
                    job_found = True
                    break
                except JobLookupError:
                    logger.error(f"Job not found: {job.id}")
        
        if not job_found:
            logger.warning(f"No job found for reminder_{msg_origin}_{index-1}")
            
        # 从列表中移除任务
        removed = reminders.pop(index - 1)
        await save_reminder_data(self.data_file, self.reminder_data)
        
        is_command_task = removed.get("is_command_task", False)
        is_task = removed.get("is_task", False)
        
        if is_command_task:
            item_type = "指令任务"
            display_text = f"/{removed['text']}"
        elif is_task:
            item_type = "任务"
            display_text = removed['text']
        else:
            item_type = "提醒"
            display_text = removed['text']
        
        provider = self.context.get_using_provider()
        if provider:
            prompt = f"用户删除了一个{item_type}，内容是'{display_text}'。请用自然的语言确认删除操作。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.session_id,
                contexts=[]  # 确保contexts是一个空列表而不是None
            )
            yield event.plain_result(response.completion_text)
        else:
            yield event.plain_result(f"已删除{item_type}：{display_text}")

    async def add_reminder(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加提醒
        
        Args:
            text(string): 提醒内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            # 解析时间
            try:
                datetime_str = parse_datetime(time_str)
            except ValueError as e:
                yield event.plain_result(str(e))
                return

            # 验证星期格式
            week_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                'fri': 4, 'sat': 5, 'sun': 6
            }
            
            # 改进的参数处理逻辑：尝试调整星期和重复类型参数
            if week and week.lower() not in week_map:
                # 星期格式错误，尝试将其作为repeat处理
                if week.lower() in ["daily", "weekly", "monthly", "yearly"] or week.lower() in ["workday", "holiday"]:
                    # week参数实际上可能是repeat参数
                    if repeat:
                        # 如果repeat也存在，则将week和repeat作为组合
                        holiday_type = repeat  # 将原来的repeat视为holiday_type
                        repeat = week  # 将原来的week视为repeat
                    else:
                        repeat = week  # 将原来的week视为repeat
                    week = None  # 清空week，使用默认值（今天）
                    logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
                else:
                    yield event.plain_result("星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun")
                    return

            # 特殊处理: 检查repeat是否包含节假日类型信息
            if repeat:
                parts = repeat.split()
                if len(parts) == 2 and parts[1] in ["workday", "holiday"]:
                    # 如果repeat参数包含两部分，且第二部分是workday或holiday
                    repeat = parts[0]  # 提取重复类型
                    holiday_type = parts[1]  # 提取节假日类型

            # 验证重复类型
            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat and repeat.lower() not in repeat_types:
                yield event.plain_result("重复类型错误，可选值：daily,weekly,monthly,yearly")
                return
                
            # 验证节假日类型
            holiday_types = ["workday", "holiday"]
            if holiday_type and holiday_type.lower() not in holiday_types:
                yield event.plain_result("节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)")
                return

            # 获取用户ID，用于会话隔离
            creator_id = event.get_sender_id()
            
            # 获取会话ID
            raw_msg_origin = event.unified_msg_origin
            if self.unique_session:
                # 使用会话隔离
                msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
            else:
                msg_origin = raw_msg_origin
                
            # 获取创建者昵称
            creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果指定了星期，调整到下一个符合的日期
            if week:
                target_weekday = week_map[week.lower()]
                current_weekday = dt.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:  # 如果目标星期已过，调整到下周
                    days_ahead += 7
                dt += datetime.timedelta(days=days_ahead)
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat.lower() if repeat else "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
            
            item = {
                "text": text,
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "user_name": creator_id,
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": False  # 明确标记为提醒，不是任务
            }
            
            self.reminder_data[msg_origin].append(item)
            
            # 设置定时任务
            self.scheduler_manager.add_job(msg_origin, item, dt)
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 生成提示信息
            week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            start_str = f"从{week_names[dt.weekday()]}开始，" if week else ""
            
            # 根据重复类型和节假日类型生成文本说明
            repeat_str = "一次性"
            if repeat == "daily" and not holiday_type:
                repeat_str = "每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "每年的这一天重复，但仅法定节假日触发"
            
            yield event.plain_result(f"已设置提醒:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            
        except Exception as e:
            yield event.plain_result(f"设置提醒时出错：{str(e)}")

    async def add_task(self, event: AstrMessageEvent, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''手动添加任务
        
        Args:
            text(string): 任务内容
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly或带节假日类型的组合（如daily workday）
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            # 解析时间
            try:
                datetime_str = parse_datetime(time_str)
            except ValueError as e:
                yield event.plain_result(str(e))
                return

            # 验证星期格式
            week_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                'fri': 4, 'sat': 5, 'sun': 6
            }
            
            # 改进的参数处理逻辑：尝试调整星期和重复类型参数
            if week and week.lower() not in week_map:
                # 星期格式错误，尝试将其作为repeat处理
                if week.lower() in ["daily", "weekly", "monthly", "yearly"] or week.lower() in ["workday", "holiday"]:
                    # week参数实际上可能是repeat参数
                    if repeat:
                        # 如果repeat也存在，则将week和repeat作为组合
                        holiday_type = repeat  # 将原来的repeat视为holiday_type
                        repeat = week  # 将原来的week视为repeat
                    else:
                        repeat = week  # 将原来的week视为repeat
                    week = None  # 清空week，使用默认值（今天）
                    logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
                else:
                    yield event.plain_result("星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun")
                    return

            # 特殊处理: 检查repeat是否包含节假日类型信息
            if repeat:
                parts = repeat.split()
                if len(parts) == 2 and parts[1] in ["workday", "holiday"]:
                    # 如果repeat参数包含两部分，且第二部分是workday或holiday
                    repeat = parts[0]  # 提取重复类型
                    holiday_type = parts[1]  # 提取节假日类型

            # 验证重复类型
            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat and repeat.lower() not in repeat_types:
                yield event.plain_result("重复类型错误，可选值：daily,weekly,monthly,yearly")
                return
                
            # 验证节假日类型
            holiday_types = ["workday", "holiday"]
            if holiday_type and holiday_type.lower() not in holiday_types:
                yield event.plain_result("节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)")
                return

            # 获取用户ID，用于会话隔离
            creator_id = event.get_sender_id()
            
            # 获取会话ID
            raw_msg_origin = event.unified_msg_origin
            if self.unique_session:
                # 使用会话隔离
                msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
            else:
                msg_origin = raw_msg_origin
                
            # 获取创建者昵称
            creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果指定了星期，调整到下一个符合的日期
            if week:
                target_weekday = week_map[week.lower()]
                current_weekday = dt.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:  # 如果目标星期已过，调整到下周
                    days_ahead += 7
                dt += datetime.timedelta(days=days_ahead)
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat.lower() if repeat else "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
            
            item = {
                "text": text,
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "user_name": "用户",  # 任务模式下不需要特别指定用户名
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,  # 添加创建者昵称
                "is_task": True  # 明确标记为任务
            }
            
            self.reminder_data[msg_origin].append(item)
            
            # 设置定时任务
            self.scheduler_manager.add_job(msg_origin, item, dt)
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 生成提示信息
            week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            start_str = f"从{week_names[dt.weekday()]}开始，" if week else ""
            
            # 根据重复类型和节假日类型生成文本说明
            repeat_str = "一次性"
            if repeat == "daily" and not holiday_type:
                repeat_str = "每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "每年的这一天重复，但仅法定节假日触发"
            
            yield event.plain_result(f"已设置任务:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            
        except Exception as e:
            yield event.plain_result(f"设置任务时出错：{str(e)}")

    async def show_help(self, event: AstrMessageEvent):
        '''显示帮助信息'''
        help_text = """提醒与任务功能指令说明：

【提醒】：到时间后会提醒你做某事
【任务】：到时间后AI会自动执行指定的操作
【指令任务】：到时间后直接执行指定的指令并转发结果

1. 添加提醒：
   /rmd add <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmd add 写周报 8:05
   - /rmd add 吃饭 8:05 sun daily (从周日开始每天)
   - /rmd add 开会 8:05 mon weekly (每周一)
   - /rmd add 交房租 8:05 fri monthly (从周五开始每月)
   - /rmd add 上班打卡 8:30 daily workday (每个工作日，法定节假日不触发)
   - /rmd add 休息提醒 9:00 daily holiday (每个法定节假日触发)

2. 添加任务：
   /rmd task <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmd task 发送天气预报 8:00
   - /rmd task 汇总今日新闻 18:00 daily
   - /rmd task 推送工作安排 9:00 mon weekly workday (每周一工作日推送)

2.5. 添加指令任务：
   /rmd command <指令> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmd command /memory_config 8:00
   - /rmd command /weather 9:00 daily
   - /rmd command /news 18:00 mon weekly (每周一推送)
   - /rmd command /rmd--ls 8:00 daily (使用--避免指令被错误分割)
   - /rmd command /rmd--ls----before--每日提醒 8:00 daily (自定义标识放在开头)
   - /rmd command /rmd--ls----after--执行完成 8:00 daily (自定义标识放在末尾)

3. 查看提醒和任务：
   /rmd ls - 列出所有提醒和任务

4. 删除提醒或任务：
   /rmd rm <序号> - 删除指定提醒或任务，注意任务序号是提醒序号继承，比如提醒有两个，任务1的序号就是3（llm会自动重编号）

5. 星期可选值：
   - mon: 周一
   - tue: 周二
   - wed: 周三
   - thu: 周四
   - fri: 周五
   - sat: 周六
   - sun: 周日

6. 重复类型：
   - daily: 每天重复
   - weekly: 每周重复
   - monthly: 每月重复
   - yearly: 每年重复

7. 节假日类型：
   - workday: 仅工作日触发（法定节假日不触发）
   - holiday: 仅法定节假日触发

8. AI智能提醒与任务
   正常对话即可，AI会自己设置提醒或任务，但需要AI支持LLM

9. 会话隔离功能
   {session_isolation_status}
   - 关闭状态：群聊中所有成员共享同一组提醒和任务
   - 开启状态：群聊中每个成员都有自己独立的提醒和任务
   
   可以通过管理面板的插件配置开启或关闭此功能

注：时间格式为 HH:MM 或 HHMM，如 8:05 或 0805

指令任务自定义标识说明：
- 使用 ---- 分隔符可以自定义指令任务的标识文字
- 格式：指令----位置--自定义文字
- 位置可选：before(开头)、after(末尾)、start(开头)、end(末尾)
- 示例：/rmd--ls----before--每日提醒 或 /rmd--ls----after--执行完成
- 如果不使用 ---- 分隔符，默认显示 [指令任务]

法定节假日数据来源：http://timor.tech/api/holiday""".format(
           session_isolation_status="当前已开启会话隔离" if self.unique_session else "当前未开启会话隔离"
        )
        yield event.plain_result(help_text)

    async def add_command_task(self, event: AstrMessageEvent, command: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''设置指令任务
        
        Args:
            command(string): 要执行的指令，如"/memory_config"或"/rmd--ls"（多个指令用--分隔）
            time_str(string): 时间，格式为 HH:MM 或 HHMM
            week(string): 可选，开始星期：mon,tue,wed,thu,fri,sat,sun
            repeat(string): 可选，重复类型：daily,weekly,monthly,yearly
            holiday_type(string): 可选，节假日类型：workday(仅工作日执行)，holiday(仅法定节假日执行)
        '''
        try:
            # 解析多命令指令
            display_command, commands, custom_identifier = CommandUtils.parse_multi_command(command)
            
            # 验证命令列表
            is_valid, error_msg = CommandUtils.validate_commands(commands)
            if not is_valid:
                yield event.plain_result(f"指令格式错误：{error_msg}")
                return
            
            # 格式化显示命令
            clean_display_command = CommandUtils.format_command_display(display_command, commands)
            
            # 解析时间
            try:
                datetime_str = parse_datetime(time_str)
            except ValueError as e:
                yield event.plain_result(str(e))
                return

            # 验证星期格式
            week_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                'fri': 4, 'sat': 5, 'sun': 6
            }
            
            # 参数处理逻辑（复用现有逻辑）
            if week and week.lower() not in week_map:
                if week.lower() in ["daily", "weekly", "monthly", "yearly"] or week.lower() in ["workday", "holiday"]:
                    if repeat:
                        holiday_type = repeat
                        repeat = week
                    else:
                        repeat = week
                    week = None
                    logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
                else:
                    yield event.plain_result("星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun")
                    return

            # 特殊处理: 检查repeat是否包含节假日类型信息
            if repeat:
                parts = repeat.split()
                if len(parts) == 2 and parts[1] in ["workday", "holiday"]:
                    repeat = parts[0]
                    holiday_type = parts[1]

            # 验证重复类型
            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat and repeat.lower() not in repeat_types:
                yield event.plain_result("重复类型错误，可选值：daily,weekly,monthly,yearly")
                return
                
            # 验证节假日类型
            holiday_types = ["workday", "holiday"]
            if holiday_type and holiday_type.lower() not in holiday_types:
                yield event.plain_result("节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)")
                return

            # 获取用户ID，用于会话隔离
            creator_id = event.get_sender_id()
            
            # 获取会话ID
            raw_msg_origin = event.unified_msg_origin
            if self.unique_session:
                # 使用会话隔离
                msg_origin = self.tools.get_session_id(raw_msg_origin, creator_id)
            else:
                msg_origin = raw_msg_origin
                
            # 获取创建者昵称
            creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果指定了星期，调整到下一个符合的日期
            if week:
                target_weekday = week_map[week.lower()]
                current_weekday = dt.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:  # 如果目标星期已过，调整到下周
                    days_ahead += 7
                dt += datetime.timedelta(days=days_ahead)
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat.lower() if repeat else "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
            
            item = {
                "text": clean_display_command,  # 存储格式化后的显示命令
                "commands": commands,  # 存储完整的命令列表用于执行
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "user_name": "指令任务",  # 指令任务标识
                "repeat": final_repeat,
                "creator_id": creator_id,
                "creator_name": creator_name,
                "is_task": True,  # 标记为任务
                "is_command_task": True,  # 特殊标记：指令任务
                "custom_identifier": custom_identifier  # 存储自定义标识信息
            }
            
            self.reminder_data[msg_origin].append(item)
            
            # 设置定时任务
            self.scheduler_manager.add_job(msg_origin, item, dt)
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 生成提示信息
            week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            start_str = f"从{week_names[dt.weekday()]}开始，" if week else ""
            
            # 根据重复类型和节假日类型生成文本说明
            repeat_str = "一次性"
            if repeat == "daily" and not holiday_type:
                repeat_str = "每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "每年的这一天重复，但仅法定节假日触发"
            
            # 获取命令描述
            command_desc = CommandUtils.get_command_description(commands)
            
            yield event.plain_result(f"已设置指令任务:\n{command_desc}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            
        except Exception as e:
            yield event.plain_result(f"设置指令任务时出错：{str(e)}")

    async def _add_remote_item(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None, is_task: bool = False, is_command_task: bool = False, commands: list = None, custom_identifier: dict = None):
        '''通用的远程群聊添加方法
        
        Args:
            event: 消息事件
            group_id: 群聊ID
            text: 内容
            time_str: 时间字符串
            week: 星期
            repeat: 重复类型
            holiday_type: 节假日类型
            is_task: 是否为任务
            is_command_task: 是否为指令任务
            commands: 指令列表（仅指令任务使用）
            custom_identifier: 自定义标识信息（仅指令任务使用）
        '''
        try:
            # 解析时间
            try:
                datetime_str = parse_datetime(time_str)
            except ValueError as e:
                yield event.plain_result(str(e))
                return

            # 验证星期格式
            week_map = {
                'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 
                'fri': 4, 'sat': 5, 'sun': 6
            }
            
            # 改进的参数处理逻辑：尝试调整星期和重复类型参数
            if week and week.lower() not in week_map:
                # 星期格式错误，尝试将其作为repeat处理
                if week.lower() in ["daily", "weekly", "monthly", "yearly"] or week.lower() in ["workday", "holiday"]:
                    # week参数实际上可能是repeat参数
                    if repeat:
                        # 如果repeat也存在，则将week和repeat作为组合
                        holiday_type = repeat  # 将原来的repeat视为holiday_type
                        repeat = week  # 将原来的week视为repeat
                    else:
                        repeat = week  # 将原来的week视为repeat
                    week = None  # 清空week，使用默认值（今天）
                    logger.info(f"已将'{week}'识别为重复类型，默认使用今天作为开始日期")
                else:
                    yield event.plain_result("星期格式错误，可选值：mon,tue,wed,thu,fri,sat,sun")
                    return

            # 特殊处理: 检查repeat是否包含节假日类型信息
            if repeat:
                parts = repeat.split()
                if len(parts) == 2 and parts[1] in ["workday", "holiday"]:
                    # 如果repeat参数包含两部分，且第二部分是workday或holiday
                    repeat = parts[0]  # 提取重复类型
                    holiday_type = parts[1]  # 提取节假日类型

            # 验证重复类型
            repeat_types = ["daily", "weekly", "monthly", "yearly"]
            if repeat and repeat.lower() not in repeat_types:
                yield event.plain_result("重复类型错误，可选值：daily,weekly,monthly,yearly")
                return
                
            # 验证节假日类型
            holiday_types = ["workday", "holiday"]
            if holiday_type and holiday_type.lower() not in holiday_types:
                yield event.plain_result("节假日类型错误，可选值：workday(仅工作日执行)，holiday(仅法定节假日执行)")
                return

            # 获取用户ID，用于会话隔离
            creator_id = event.get_sender_id()
            
            # 获取平台名称
            platform_name = event.get_platform_name()
            
            # 构建远程群聊的会话ID
            if self.unique_session:
                # 使用会话隔离
                msg_origin = f"{platform_name}:GroupMessage:{group_id}_{creator_id}"
            else:
                msg_origin = f"{platform_name}:GroupMessage:{group_id}"
                
            # 获取创建者昵称
            creator_name = event.message_obj.sender.nickname if hasattr(event.message_obj, 'sender') and hasattr(event.message_obj.sender, 'nickname') else None
            
            if msg_origin not in self.reminder_data:
                self.reminder_data[msg_origin] = []
            
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果指定了星期，调整到下一个符合的日期
            if week:
                target_weekday = week_map[week.lower()]
                current_weekday = dt.weekday()
                days_ahead = target_weekday - current_weekday
                if days_ahead <= 0:  # 如果目标星期已过，调整到下周
                    days_ahead += 7
                dt += datetime.timedelta(days=days_ahead)
            
            # 处理重复类型和节假日类型的组合
            final_repeat = repeat.lower() if repeat else "none"
            if repeat and holiday_type:
                final_repeat = f"{repeat.lower()}_{holiday_type.lower()}"
            
            # 根据类型构建item
            if is_command_task:
                item = {
                    "text": text,  # 存储格式化后的显示命令
                    "commands": commands,  # 存储完整的命令列表用于执行
                    "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                    "user_name": "指令任务",  # 指令任务标识
                    "repeat": final_repeat,
                    "creator_id": creator_id,
                    "creator_name": creator_name,
                    "is_task": True,  # 标记为任务
                    "is_command_task": True,  # 特殊标记：指令任务
                    "custom_identifier": custom_identifier  # 存储自定义标识信息
                }
            else:
                item = {
                    "text": text,
                    "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                    "user_name": creator_id if not is_task else "用户",
                    "repeat": final_repeat,
                    "creator_id": creator_id,
                    "creator_name": creator_name,
                    "is_task": is_task
                }
            
            self.reminder_data[msg_origin].append(item)
            
            # 设置定时任务
            self.scheduler_manager.add_job(msg_origin, item, dt)
            
            await save_reminder_data(self.data_file, self.reminder_data)
            
            # 生成提示信息
            week_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            start_str = f"从{week_names[dt.weekday()]}开始，" if week else ""
            
            # 根据重复类型和节假日类型生成文本说明
            repeat_str = "一次性"
            if repeat == "daily" and not holiday_type:
                repeat_str = "每天重复"
            elif repeat == "daily" and holiday_type == "workday":
                repeat_str = "每个工作日重复（法定节假日不触发）"
            elif repeat == "daily" and holiday_type == "holiday":
                repeat_str = "每个法定节假日重复"
            elif repeat == "weekly" and not holiday_type:
                repeat_str = "每周重复"
            elif repeat == "weekly" and holiday_type == "workday":
                repeat_str = "每周的这一天重复，但仅工作日触发"
            elif repeat == "weekly" and holiday_type == "holiday":
                repeat_str = "每周的这一天重复，但仅法定节假日触发"
            elif repeat == "monthly" and not holiday_type:
                repeat_str = "每月重复"
            elif repeat == "monthly" and holiday_type == "workday":
                repeat_str = "每月的这一天重复，但仅工作日触发"
            elif repeat == "monthly" and holiday_type == "holiday":
                repeat_str = "每月的这一天重复，但仅法定节假日触发"
            elif repeat == "yearly" and not holiday_type:
                repeat_str = "每年重复"
            elif repeat == "yearly" and holiday_type == "workday":
                repeat_str = "每年的这一天重复，但仅工作日触发"
            elif repeat == "yearly" and holiday_type == "holiday":
                repeat_str = "每年的这一天重复，但仅法定节假日触发"
            
            # 根据类型生成不同的成功消息
            if is_command_task:
                # 获取命令描述
                command_desc = CommandUtils.get_command_description(commands)
                yield event.plain_result(f"已在群聊 {group_id} 设置指令任务:\n{command_desc}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            elif is_task:
                yield event.plain_result(f"已在群聊 {group_id} 设置任务:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            else:
                yield event.plain_result(f"已在群聊 {group_id} 设置提醒:\n内容: {text}\n时间: {dt.strftime('%Y-%m-%d %H:%M')}\n{start_str}{repeat_str}\n\n使用 /rmd ls 查看所有提醒和任务")
            
        except Exception as e:
            yield event.plain_result(f"设置{'指令任务' if is_command_task else '任务' if is_task else '提醒'}时出错：{str(e)}")

    async def add_remote_reminder(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''在指定群聊中手动添加提醒'''
        async for result in self._add_remote_item(event, group_id, text, time_str, week, repeat, holiday_type, is_task=False, is_command_task=False):
            yield result

    async def add_remote_task(self, event: AstrMessageEvent, group_id: str, text: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''在指定群聊中手动添加任务'''
        async for result in self._add_remote_item(event, group_id, text, time_str, week, repeat, holiday_type, is_task=True, is_command_task=False):
            yield result

    async def add_remote_command_task(self, event: AstrMessageEvent, group_id: str, command: str, time_str: str, week: str = None, repeat: str = None, holiday_type: str = None):
        '''在指定群聊中设置指令任务'''
        try:
            # 解析多命令指令
            display_command, commands, custom_identifier = CommandUtils.parse_multi_command(command)
            
            # 验证命令列表
            is_valid, error_msg = CommandUtils.validate_commands(commands)
            if not is_valid:
                yield event.plain_result(f"指令格式错误：{error_msg}")
                return
            
            # 格式化显示命令
            clean_display_command = CommandUtils.format_command_display(display_command, commands)
            
            async for result in self._add_remote_item(event, group_id, clean_display_command, time_str, week, repeat, holiday_type, is_task=True, is_command_task=True, commands=commands, custom_identifier=custom_identifier):
                yield result
                
        except Exception as e:
            yield event.plain_result(f"设置指令任务时出错：{str(e)}")

    async def show_remote_help(self, event: AstrMessageEvent):
        '''显示远程群聊帮助信息'''
        help_text = """远程群聊提醒与任务功能指令说明：

【功能】：在指定的群聊中设置、查看和管理提醒、任务或指令任务

1. 在指定群聊中添加提醒：
   /rmdg add <群聊ID> <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg add 1001914995 写周报 8:05
   - /rmdg add 1001914995 吃饭 8:05 sun daily (从周日开始每天)
   - /rmdg add 1001914995 开会 8:05 mon weekly (每周一)
   - /rmdg add 1001914995 交房租 8:05 fri monthly (从周五开始每月)
   - /rmdg add 1001914995 上班打卡 8:30 daily workday (每个工作日，法定节假日不触发)

2. 在指定群聊中添加任务：
   /rmdg task <群聊ID> <内容> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg task 1001914995 发送天气预报 8:00
   - /rmdg task 1001914995 汇总今日新闻 18:00 daily
   - /rmdg task 1001914995 推送工作安排 9:00 mon weekly workday (每周一工作日推送)

3. 在指定群聊中添加指令任务：
   /rmdg command <群聊ID> <指令> <时间> [开始星期] [重复类型] [--holiday_type=...]
   例如：
   - /rmdg command 1001914995 /memory_config 8:00
   - /rmdg command 1001914995 /weather 9:00 daily
   - /rmdg command 1001914995 /news 18:00 mon weekly (每周一推送)
   - /rmdg command 1001914995 /rmd--ls----before--每日提醒 8:00 daily (自定义标识放在开头)
   - /rmdg command 1001914995 /rmd--ls----after--执行完成 8:00 daily (自定义标识放在末尾)

4. 查看指定群聊的提醒和任务：
   /rmdg ls <群聊ID>
   例如：
   - /rmdg ls 1001914995

5. 删除指定群聊中的提醒或任务：
   /rmdg rm <群聊ID> <序号>
   例如：
   - /rmdg rm 1001914995 1 (删除序号为1的提醒或任务)

6. 群聊ID获取方法：
   - QQ群：群号，如 1001914995
   - 微信群：群聊的wxid，如 wxid_hbjtu1j2gf5x22
   - 其他平台：对应的群聊标识符

7. 星期可选值：
   - mon: 周一
   - tue: 周二
   - wed: 周三
   - thu: 周四
   - fri: 周五
   - sat: 周六
   - sun: 周日

8. 重复类型：
   - daily: 每天重复
   - weekly: 每周重复
   - monthly: 每月重复
   - yearly: 每年重复

9. 节假日类型：
   - workday: 仅工作日触发（法定节假日不触发）
   - holiday: 仅法定节假日触发

注：时间格式为 HH:MM 或 HHMM，如 8:05 或 0805

指令任务自定义标识说明：
- 使用 ---- 分隔符可以自定义指令任务的标识文字
- 格式：指令----位置--自定义文字
- 位置可选：before(开头)、after(末尾)、start(开头)、end(末尾)
- 示例：/rmd--ls----before--每日提醒 或 /rmd--ls----after--执行完成
- 如果不使用 ---- 分隔符，默认显示 [指令任务]

法定节假日数据来源：http://timor.tech/api/holiday"""
        yield event.plain_result(help_text)

    async def list_remote_reminders(self, event: AstrMessageEvent, group_id: str):
        '''列出指定群聊中的所有提醒和任务'''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取平台名称
        platform_name = event.get_platform_name()
        
        # 构建远程群聊的会话ID
        if self.unique_session:
            # 使用会话隔离
            msg_origin = f"{platform_name}:GroupMessage:{group_id}_{creator_id}"
        else:
            msg_origin = f"{platform_name}:GroupMessage:{group_id}"
            
        reminders = self.reminder_data.get(msg_origin, [])
        if not reminders:
            yield event.plain_result(f"群聊 {group_id} 中没有设置任何提醒或任务。")
            return
            
        provider = self.context.get_using_provider()
        if provider:
            try:
                # 分离提醒、任务和指令任务
                reminder_items = []
                task_items = []
                command_task_items = []
                
                for r in reminders:
                    if r.get("is_command_task", False):
                        # 指令任务，显示完整指令
                        command_text = r['text']
                        command_task_items.append(f"- {command_text} (时间: {r['datetime']})")
                    elif r.get("is_task", False):
                        # 普通任务
                        task_items.append(f"- {r['text']} (时间: {r['datetime']})")
                    else:
                        # 提醒
                        reminder_items.append(f"- {r['text']} (时间: {r['datetime']})")
                
                # 构建提示
                prompt = f"请帮我整理并展示群聊 {group_id} 的以下提醒和任务列表，用自然的语言表达：\n"
                
                if reminder_items:
                    prompt += f"\n提醒列表：\n" + "\n".join(reminder_items)
                
                if task_items:
                    prompt += f"\n\n任务列表：\n" + "\n".join(task_items)
                
                if command_task_items:
                    prompt += f"\n\n指令任务列表：\n" + "\n".join(command_task_items)
                
                prompt += f"\n\n同时告诉用户可以使用/rmdg rm {group_id} <序号>删除提醒、任务或指令任务，或者直接命令你来删除。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
                
                response = await provider.text_chat(
                    prompt=prompt,
                    session_id=event.session_id,
                    contexts=[]  # 确保contexts是一个空列表而不是None
                )
                yield event.plain_result(response.completion_text)
            except Exception as e:
                logger.error(f"在list_remote_reminders中调用LLM时出错: {str(e)}")
                # 如果LLM调用失败，回退到基本显示
                reminder_str = f"群聊 {group_id} 的提醒和任务：\n"
                
                # 分类显示
                reminders_list = [r for r in reminders if not r.get("is_task", False)]
                tasks_list = [r for r in reminders if r.get("is_task", False) and not r.get("is_command_task", False)]
                command_tasks_list = [r for r in reminders if r.get("is_command_task", False)]
                
                if reminders_list:
                    reminder_str += "\n提醒：\n"
                    for i, reminder in enumerate(reminders_list):
                        reminder_str += f"{i+1}. {reminder['text']} - {reminder['datetime']}\n"
                
                if tasks_list:
                    reminder_str += "\n任务：\n"
                    for i, task in enumerate(tasks_list):
                        reminder_str += f"{len(reminders_list)+i+1}. {task['text']} - {task['datetime']}\n"
                
                if command_tasks_list:
                    reminder_str += "\n指令任务：\n"
                    current_index = len(reminders_list) + len(tasks_list)
                    for i, cmd_task in enumerate(command_tasks_list):
                        reminder_str += f"{current_index+i+1}. /{cmd_task['text']} - {cmd_task['datetime']}\n"
                
                reminder_str += f"\n使用 /rmdg rm {group_id} <序号> 删除提醒、任务或指令任务"
                yield event.plain_result(reminder_str)
        else:
            reminder_str = f"群聊 {group_id} 的提醒和任务：\n"
            
            # 分类显示
            reminders_list = [r for r in reminders if not r.get("is_task", False)]
            tasks_list = [r for r in reminders if r.get("is_task", False) and not r.get("is_command_task", False)]
            command_tasks_list = [r for r in reminders if r.get("is_command_task", False)]
            
            if reminders_list:
                reminder_str += "\n提醒：\n"
                for i, reminder in enumerate(reminders_list):
                    reminder_str += f"{i+1}. {reminder['text']} - {reminder['datetime']}\n"
            
            if tasks_list:
                reminder_str += "\n任务：\n"
                for i, task in enumerate(tasks_list):
                    reminder_str += f"{len(reminders_list)+i+1}. {task['text']} - {task['datetime']}\n"
            
            if command_tasks_list:
                reminder_str += "\n指令任务：\n"
                current_index = len(reminders_list) + len(tasks_list)
                for i, cmd_task in enumerate(command_tasks_list):
                    reminder_str += f"{current_index+i+1}. /{cmd_task['text']} - {cmd_task['datetime']}\n"
            
            reminder_str += f"\n使用 /rmdg rm {group_id} <序号> 删除提醒、任务或指令任务"
            yield event.plain_result(reminder_str)

    async def remove_remote_reminder(self, event: AstrMessageEvent, group_id: str, index: int):
        '''删除指定群聊中的提醒、任务或指令任务
        
        Args:
            group_id(string): 群聊ID
            index(int): 提醒、任务或指令任务的序号
        '''
        # 获取用户ID，用于会话隔离
        creator_id = event.get_sender_id()
        
        # 获取平台名称
        platform_name = event.get_platform_name()
        
        # 构建远程群聊的会话ID
        if self.unique_session:
            # 使用会话隔离
            msg_origin = f"{platform_name}:GroupMessage:{group_id}_{creator_id}"
        else:
            msg_origin = f"{platform_name}:GroupMessage:{group_id}"
            
        reminders = self.reminder_data.get(msg_origin, [])
        if not reminders:
            yield event.plain_result(f"群聊 {group_id} 中没有设置任何提醒或任务。")
            return
            
        if index < 1 or index > len(reminders):
            yield event.plain_result(f"序号无效。群聊 {group_id} 中只有 {len(reminders)} 个提醒或任务。")
            return
            
        # 获取要删除的提醒或任务
        job_id = f"reminder_{msg_origin}_{index-1}"
        
        # 尝试删除调度任务
        try:
            self.scheduler_manager.remove_job(job_id)
            logger.info(f"Successfully removed job: {job_id}")
        except JobLookupError:
            logger.error(f"Job not found: {job_id}")
            
        removed = reminders.pop(index - 1)
        await save_reminder_data(self.data_file, self.reminder_data)
        
        is_command_task = removed.get("is_command_task", False)
        is_task = removed.get("is_task", False)
        
        if is_command_task:
            item_type = "指令任务"
            display_text = f"/{removed['text']}"
        elif is_task:
            item_type = "任务"
            display_text = removed['text']
        else:
            item_type = "提醒"
            display_text = removed['text']
        
        provider = self.context.get_using_provider()
        if provider:
            prompt = f"用户删除了群聊 {group_id} 中的一个{item_type}，内容是'{display_text}'。请用自然的语言确认删除操作。直接发出对话内容，就是你说的话，不要有其他的背景描述。"
            response = await provider.text_chat(
                prompt=prompt,
                session_id=event.session_id,
                contexts=[]  # 确保contexts是一个空列表而不是None
            )
            yield event.plain_result(response.completion_text)
        else:
            yield event.plain_result(f"已删除群聊 {group_id} 中的{item_type}：{display_text}")