import re
from typing import List, Tuple
from astrbot.api import logger


class CommandUtils:
    """命令工具类，用于处理多命令指令"""
    
    @staticmethod
    def parse_multi_command(command: str) -> Tuple[str, List[str]]:
        """
        解析命令字符串，处理包含 "--" 的完整指令
        
        Args:
            command: 原始命令字符串，如 "/rmd--ls" 或 "/rmd ls"
            
        Returns:
            Tuple[str, List[str]]: (显示命令, 执行命令列表)
            - 显示命令: 用于显示的命令字符串，保持原始格式
            - 执行命令列表: 处理后的命令列表，用于实际执行
        """
        # 检查是否包含 "--" 分隔符
        if "--" in command:
            # 使用 "--" 分割命令
            parts = command.split("--")
            # 过滤空字符串并去除首尾空格
            parts = [part.strip() for part in parts if part.strip()]
            
            if len(parts) == 0:
                return command, []
            elif len(parts) == 1:
                # 只有一个部分，直接返回
                return command, [parts[0]]
            else:
                # 多个部分，需要组合成完整指令
                # 第一个部分应该是主命令（如 /rmd），其余部分是子命令
                main_cmd = parts[0]
                sub_cmds = parts[1:]
                
                # 组合成完整的指令
                full_command = main_cmd + " " + " ".join(sub_cmds)
                
                # 显示命令保持原始格式（如 /rmd--ls），执行命令是组合后的完整指令（如 /rmd ls）
                return command, [full_command]
        else:
            # 没有 "--" 分隔符，这是单个命令
            return command, [command]
    
    @staticmethod
    def validate_commands(commands: List[str]) -> Tuple[bool, str]:
        """
        验证命令列表的有效性
        
        Args:
            commands: 命令列表
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        if not commands:
            return False, "没有有效的命令"
        
        for i, cmd in enumerate(commands):
            if not cmd.startswith('/'):
                return False, f"命令 {i+1} 格式错误，必须以 / 开头：{cmd}"
            
            # 检查命令长度
            if len(cmd) < 2:
                return False, f"命令 {i+1} 太短：{cmd}"
        
        return True, ""
    
    @staticmethod
    def format_command_display(display_command: str, commands: List[str]) -> str:
        """
        格式化命令显示信息
        
        Args:
            display_command: 原始显示命令
            commands: 执行命令列表
            
        Returns:
            str: 格式化后的显示信息
        """
        # 直接返回原始显示命令，保持用户输入的格式
        return display_command
    
    @staticmethod
    def get_command_description(commands: List[str]) -> str:
        """
        获取命令描述信息
        
        Args:
            commands: 命令列表
            
        Returns:
            str: 命令描述
        """
        if len(commands) == 1:
            return f"执行指令：{commands[0]}"
        else:
            return f"执行多个指令：{' '.join(commands)}" 