# # 加载环境变量
# from langchain_community.tools.tavily_search import TavilySearchResults
# import os
# from dotenv import load_dotenv
# from .registry import register_tool

# load_dotenv()

# tool_schema = {
#     "type": "object",
#     "properties": {
#         "file_path": {
#             "type": "string",
#             "description":"文件路径（相对于当前工作目录）"
#         },
#         "content": {
#             "type": "string",
#             "description":"要写入的内容"
#         }
#     },
#     "required": ["file_path", "content"]
# }

# @register_tool
# @tool("web_search_tool", description="将内容写入文件。文件不存在则创建，已存在则完整覆盖。局部修改请用 edit_file，避免不必要的全量重写",args_schema=tool_schema)
# def web_search_tool(self,):
#         """初始化搜索工具（支持多种搜索引擎）"""
        
#         # 使用Tavily搜索（推荐，专为AI优化）
#         tavily_api_key = os.getenv("TAVILY_API_KEY")
#         if tavily_api_key:
#             print("使用Tavily搜索引擎")
#             return TavilySearchResults(
#                 api_key=tavily_api_key,
#                 max_results=5,  # 返回5条结果
#                 include_raw_content=True,  # 包含原始内容
#                 search_depth="advanced"  # 高级搜索深度
#             )
        
#         # 如果没有配置Tavily，尝试使用DuckDuckGo（无需API密钥）
#         try:
#             from langchain_community.tools import DuckDuckGoSearchResults
#             print("使用DuckDuckGo搜索引擎（无需API密钥）")
#             return DuckDuckGoSearchResults(max_results=5)
#         except ImportError:
#             raise ImportError("Error: 请安装搜索工具依赖：pip install langchain-community duckduckgo-search")
    