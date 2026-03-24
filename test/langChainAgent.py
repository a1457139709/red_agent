from langchain.agents import  create_agent

def get_weather(location: str) -> str:
    # 这里是一个模拟的天气查询函数，实际应用中可以调用真实的天气 API
    return f"{location} 的天气是晴朗，温度25摄氏度。"

weather_agent = create_agent(
    model="gpt-4",
    tools=["get_weather"],
    system_prompt="你是一个智能助手，能够根据用户提供的位置查询天气信息。"
)

weather_agent.invoke({"messages": [{"role": "user", "content": "请告诉我北京的天气如何？"}]})
