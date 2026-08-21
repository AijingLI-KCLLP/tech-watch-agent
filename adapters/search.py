from urllib.parse import urlparse
from tavily import TavilyClient

from config import TAVILY_API_KEY
from core.models import Article, Source, SourceType

def _domain(url:str) -> str:
    return urlparse(url).netloc

def search(topic:str, max_results:int=5 ) -> list[tuple[Source, Article]]:
    client = TavilyClient(api_key=TAVILY_API_KEY)
    res = client.search(
        query=topic,
        include_raw_content=True,
        max_results=max_results,
    )

    sources: dict[str, Source] = {}
    pairs: list[tuple[Source, Article]] = []

    for r in res["results"]:
        url = r["url"]
        domain = _domain(url)

        if domain not in sources:
            sources[domain] = Source(
                name=domain,
                url=f"https://{domain}",
                type=SourceType.ARTICLE,
            )
        source = sources[domain]

        body = r.get("raw_content") or r.get("content") or ""
        if not body:
            continue

        article = Article(
            source_id=source.id,
            url=url,
            title=r.get("title") or url,
            content=body,
            n_tags=1,
        )

        pairs.append((source, article))

    return pairs
