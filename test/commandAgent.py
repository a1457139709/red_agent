import random

# 1. 定义工具
def tool_get_weather():
    """模拟获取天气信息的工具"""
    weathers = ["晴朗","多云","小雨","小雪"]
    temperature = random.randint(-5,25)
    return {"weather": random.choice(weathers), "temperature": temperature}

def tool_calculate(a,b, operator):
    """模拟一个简单的计算工具"""
    if operator == "+":
        return a + b
    elif operator == "-":
        return a - b
    elif operator == "*":
        return a * b
    elif operator == "/":
        return a / b if b != 0 else "除数不能为零"
    else:
        return "不支持的运算符"
    
# 2. 记忆存储
history_memory = []

# 3. 定义Agent

class CommandAgent:
    def __init__(self):
        #self.decision = ""
        pass

    def make_decision(self, user_input):
        """
        根据感知信息做出简单决策。
        这是一个基于规则的示例，实际中通常由复杂的AI模型完成。
        """
        print(f"[决策模块] 正在分析信息：'{user_input}'")
    
        if "天气" in user_input:
            decision = "get_weather"
        elif "计算" in user_input:
            decision = "calculate"
        elif user_input in ["退出","exit","quit"]:
            decision = "exit"
        else:
            decision = "pass"
    
        print(f"[决策模块] 决策结果：{decision}")
        return decision

    def execute_action(self,decision, user_input):
        if decision == "get_weather":
            result = tool_get_weather()
            return f"[执行模块] 天气信息：{result}"
        elif decision == "calculate":
            # 解析用户输入中的数字和运算符
            if "1+1" in user_input:
                response = tool_calculate(1, 1, '+')
            elif "10-5" in user_input:
                 response = tool_calculate(10, 5, '-')
            else:
                response = "请尝试输入'计算1+1'或'计算10-5'。"
            #result = tool_calculate(a, b, operator)
            return f"[执行模块] 计算结果：{response}"
        elif decision == "exit":
            print("[执行模块] Agent已退出。")
            exit()

    def run(self):
        print("欢迎使用命令Agent！")

        while True:
            # 感知
            print("请输入命令")
            user_input = input(">> ")
            history_memory.append("用户输入: " + user_input)
            # 决策
            decision = self.make_decision(user_input)
                
            # 行动
            res = self.execute_action(decision, user_input)
            print(res)
            # 记忆
            history_memory.append("执行结果: " + res)

# 4. 启动Agent
if __name__ == "__main__":
    ca = CommandAgent()
    ca.run()