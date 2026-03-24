from utils.safety import *
from tools import bash
from utils.confirm import confirm_from_user
from agent import *
from tools.readFile import read_file
from tools.editFile import edit_file
from tools.writeFile import write_file
import dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from langchain_openai import ChatOpenAI
from agent.provider import create_model
import os
from tools import get_tools
from langchain.tools import tool

def testImport():
    print("Testing imports...")
    
def test_file_ope():
    print(bash.execute_command("whoami"))
    #print(confirm_from_user("rm -rf /"))
    safe_path = resolve_safe_path("test.txt")

    print(safe_path.as_posix())

    print(is_sensitive_path(safe_path.as_posix()))

    print(read_file("test.txt"))
    #print(write_file("test.txt", "Hello, World!"))
    print(edit_file("test.txt", "World", "Universe"))
    print(read_file("test.txt"))

def test_dotenv():
    dotenv.load_dotenv()
    print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
    print("OPENAI_API_BASE:", os.getenv("OPENAI_API_BASE"))
    print("OPENAI_MODEL:", os.getenv("OPENAI_MODEL"))

def test_agent_loop():
    dotenv.load_dotenv()
    model = create_model()
    agent = create_agent(
        model=model,
        system_prompt=SystemMessage(content="你是一个聊天机器人。"),
    )
    messages = []
    messages.extend([])
    messages.append(HumanMessage(content="介绍一下你自己"))
    system_msg = SystemMessage("You are a helpful assistant.")
    human_msg = HumanMessage("Hello, how are you?")
    messages = [system_msg, human_msg]
    #print(messages)
    
    res = agent.invoke(
        
        {"messages":messages}
    )
    print(res)
    print(type(res))
    ai_message =res["messages"][-1]
    print(ai_message.tool_calls)

tool_schema = {
    "type": "object",
    "properties": {
        "city": {
            "type": "string",
            "description":"要查询的城市"
        },
    },
    "required": ["city"]
}
@tool
def get_weather(city: str)->str:
    """获取天气"""
    return "今天天气有雨，redAndWhite"

def test_model_loop():
    dotenv.load_dotenv()
    model = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL"),
        temperature=0.2,
        openai_api_key=os.getenv("OPENAI_API_KEY"), 
        openai_api_base=os.getenv("OPENAI_API_BASE"),
        
    )
    print(get_weather.name)
    model_with_tools  = model.bind_tools([get_weather])

    messages = HumanMessage(content="查看上海天气")
    
    res = model_with_tools.invoke(
        [{"role": "user", "content": "查看上海天气"}]
    )
    print(res)
    #print(type(res))

def test_tools():
    
    tools = get_tools()
    tool_invoke = {
        t.name: t for t in tools
    }
    tool_call = {
        "name": "read_file",
        "args": {
            "file_path": "test.txt"
        }
    }
    tool = tool_invoke[tool_call["name"]]
    tool_result = tool.invoke(tool_call["args"])
    tool_message =ToolMessage(
                content=tool_result
            )
    print(tool_message)

if __name__ == "__main__":
    test_tools()
    