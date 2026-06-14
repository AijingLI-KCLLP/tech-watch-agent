from openai import OpenAI
from config import LMSTUDIO_API_KEY, LMSTUDIO_BASE_URL, LMSTUDIO_EMBEDDING_MODEL

_client: OpenAI | None = None

def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key=LMSTUDIO_API_KEY)
    return _client

def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    res = _openai().embeddings.create(
        model=LMSTUDIO_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in res.data]
