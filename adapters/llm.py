from langchain_openai import ChatOpenAI
from config import LMSTUDIO_BASE_URL, LMSTUDIO_API_KEY, LMSTUDIO_MODEL

_llm: ChatOpenAI | None = None

def get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            base_url=LMSTUDIO_BASE_URL,
            api_key=LMSTUDIO_API_KEY,
            model=LMSTUDIO_MODEL,
            temperature=0.3
        )
    return _llm