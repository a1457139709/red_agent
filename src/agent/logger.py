from langchain_core.messages import AIMessage, ToolMessage
step_counter = 0

def reset_steps():
    global step_counter
    step_counter = 0

def log_step(text: AIMessage | ToolMessage, tool_calls: list) -> None:

    global step_counter
    step_counter += 1

    ColoredOutput.print_step(step_counter)

    if text.content:
        # print(f"\x1b[37m{text.content}\x1b[0m")
        ColoredOutput.print_thinking(thought=text.content)

    for call in tool_calls:
        #print(f"\n\x1b[32m🔧工具调用: {call['name']}\x1b[0m \x1b[90m 参数: {call['args']}\x1b[0m")
        ColoredOutput.print_tool_call(call["name"],call["args"])
        
import sys
from colorama import init, Fore, Back, Style, just_fix_windows_console

# 初始化colorama（支持Windows）
just_fix_windows_console()
init(autoreset=True)

class ColoredOutput:
    """彩色输出格式化器"""
    
    # 定义颜色常量
    STEP = Fore.CYAN + Style.BRIGHT
    TOOL = Fore.YELLOW + Style.BRIGHT
    TOOL_ARGS = Fore.LIGHTYELLOW_EX
    OBSERVATION = Fore.MAGENTA
    FINAL = Fore.GREEN + Style.BRIGHT + Back.BLACK
    ERROR = Fore.RED + Style.BRIGHT
    INFO = Fore.BLUE
    RESET = Style.RESET_ALL
    
    # 定义图标
    ICONS = {
        'step': '🔹',
        'tool': '🔧',
        'observation': '📊',
        'final': '✨',
        'success': '✅',
        'error': '❌',
        'info': 'ℹ️',
        'arrow': '➜',
        'star': '⭐',
        'robot': '🤖',
        'thinking': '💭',
        'chain': '⛓️'
    }
    
    @classmethod
    def print_step(cls, step_num: int, total_steps: int = None):
        """打印步骤标题"""
        if total_steps:
            print(f"\n{cls.STEP}{cls.ICONS['step']} Step {step_num}/{total_steps} {cls.RESET}")
            print(f"{cls.STEP}{'─' * 50}{cls.RESET}")
        else:
            print(f"\n{cls.STEP}{cls.ICONS['step']} Step {step_num} {cls.RESET}")
            print(f"{cls.STEP}{'─' * 50}{cls.RESET}")
    
    @classmethod
    def print_tool_call(cls, tool_name: str, args: dict):
        """打印工具调用"""
        print(f"{cls.TOOL}{cls.ICONS['tool']} 工具调用: {tool_name} {cls.RESET}")
        
        # 格式化参数，每行一个
        for key, value in args.items():
            print(f"  {cls.TOOL_ARGS}{cls.ICONS['arrow']} {key}: {value}{cls.RESET}")
    
    @classmethod
    def print_observation(cls, observation: str, truncate: int = None):
        """打印观察结果"""
        if truncate and len(observation) > truncate:
            observation = observation[:truncate] + "..."
        
        # 分行显示长文本
        lines = observation.split('\n')
        print(f"{cls.OBSERVATION}{cls.ICONS['observation']} 观察结果:{cls.RESET}")
        for line in lines:
            print(f"{cls.OBSERVATION}  {line}{cls.RESET}")
    
    @classmethod
    def print_final_answer(cls, answer: str):
        """打印最终回答（突出显示）"""
        print(f"\n{cls.FINAL}{cls.ICONS['star']}{cls.ICONS['star']} 最终回答 {cls.ICONS['star']}{cls.ICONS['star']}{cls.RESET}")
        print(f"{cls.FINAL}{'═' * 60}{cls.RESET}")
        
        # 智能换行处理
        lines = answer.split('\n')
        for line in lines:
            print(f"{cls.FINAL}  {line}{cls.RESET}")
        
        print(f"{cls.FINAL}{'═' * 60}{cls.RESET}\n")
    
    @classmethod
    def print_error(cls, error_msg: str):
        """打印错误信息"""
        print(f"{cls.ERROR}{cls.ICONS['error']} 错误: {error_msg}{cls.RESET}")
    
    @classmethod
    def print_info(cls, info_msg: str):
        """打印普通信息"""
        print(f"{cls.INFO}{cls.ICONS['info']} {info_msg}{cls.RESET}")
    
    @classmethod
    def print_thinking(cls, thought: str):
        """打印思考过程"""
        print(f"{Fore.LIGHTBLACK_EX}{cls.ICONS['thinking']} {thought}{cls.RESET}")
    
    @classmethod
    def print_divider(cls, char: str = '─', length: int = 50, color=None):
        """打印分隔线"""
        if color:
            print(f"{color}{char * length}{cls.RESET}")
        else:
            print(f"{char * length}")
    
    @classmethod
    def print_success(cls, msg: str):
        """打印成功信息"""
        print(f"{Fore.GREEN}{cls.ICONS['success']} {msg}{cls.RESET}")
    
    @classmethod
    def print_header(cls, title: str):
        """打印标题头"""
        print(f"\n{Back.BLUE}{Fore.WHITE}{Style.BRIGHT} {cls.ICONS['robot']} {title} {cls.RESET}")
        print(f"{Fore.BLUE}{'━' * 60}{cls.RESET}")
