from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# 1. 初始化语言模型
llm = ChatOpenAI(
    model="qwen-plus",
    temperature=0.5,
    openai_api_key="sk-e3234b6c5ab14630b80f3eae4410f764", 
    openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

#2. 定义一个聊天提示模板
# MessagesPlaceholder 会在运行时被对话历史填充
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个信息安全技术专家，擅长深入分析网络安全技术，并给出原理性解释。"),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{concept}")
])

# 4. 构建链
chain = prompt | llm

# 5. 管理内存：创建一个字典来存储不同用户的历史记录
store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

# 6. 使用 RunnableWithMessageHistory 包装我们的链
with_message_history = RunnableWithMessageHistory(
    chain,
    get_session_history=get_session_history,
    input_messages_key="concept",
    history_messages_key="history"
)

# 7. 进入对话循环
print("--- 已进入聊天模式 (输入 'exit' 退出) ---")
session_config = {"configurable": {"session_id": "user_001"}} # 区分不同会话的 ID

# while True:
#     user_input = input("你: ")
#     if user_input.lower() in ["exit", "quit", "退出"]:
#         break
       
#     # 调用带记忆的链
#     response = with_message_history.invoke(
#         {"concept": user_input},
#         config=session_config
#     )
   
#     print(f"AI: {response.content}\n")
user_input = input("你: ")

    # 调用带记忆的链
response = with_message_history.invoke(
    {"concept": user_input},
    config=session_config
)
print(type(response))
print(response.content_blocks)
print(f"AI: {response.content}\n")