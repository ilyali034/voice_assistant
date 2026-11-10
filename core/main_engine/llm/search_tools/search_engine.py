from langchain_community.tools import DuckDuckGoSearchRun

class LangchainOllamaSearchEngine: 
    def __init__(self):
        self.search_tool = DuckDuckGoSearchRun()

    async def standart_search(self, request: str): 
        response = await self.search_tool.ainvoke(request)
        return response