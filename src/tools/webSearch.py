# Example draft for a future web search tool.
# from langchain_community.tools.tavily_search import TavilySearchResults
# import os
# from dotenv import load_dotenv
# from .registry import register_tool
#
# load_dotenv()
#
# tool_schema = {
#     "type": "object",
#     "properties": {
#         "file_path": {
#             "type": "string",
#             "description": "File path relative to the current working directory"
#         },
#         "content": {
#             "type": "string",
#             "description": "Content to write"
#         }
#     },
#     "required": ["file_path", "content"]
# }
#
# @register_tool
# @tool(
#     "web_search_tool",
#     description="Write content to a file. Create the file if it does not exist, otherwise overwrite it completely.",
#     args_schema=tool_schema,
# )
# def web_search_tool(self,):
#     """Initialize a search tool with multiple provider options."""
#
#     # Prefer Tavily because it is optimized for AI-oriented search.
#     tavily_api_key = os.getenv("TAVILY_API_KEY")
#     if tavily_api_key:
#         print("Using Tavily search")
#         return TavilySearchResults(
#             api_key=tavily_api_key,
#             max_results=5,
#             include_raw_content=True,
#             search_depth="advanced",
#         )
#
#     # Fall back to DuckDuckGo if Tavily is not configured.
#     try:
#         from langchain_community.tools import DuckDuckGoSearchResults
#         print("Using DuckDuckGo search (no API key required)")
#         return DuckDuckGoSearchResults(max_results=5)
#     except ImportError:
#         raise ImportError(
#             "Error: install search dependencies with: pip install langchain-community duckduckgo-search"
#         )