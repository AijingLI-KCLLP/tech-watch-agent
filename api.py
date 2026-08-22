from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adapters.store import init_db, list_articles
from services.agent_service import ask_question, watch_topic

app = FastAPI(
    title="Tech Watch Agent API",
    version="0.1.0",
)

WEB_DIR = Path(__file__).parent / "web"


class WatchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)


class ArticleResponse(BaseModel):
    id: str
    title: str
    url: str | None


class WatchResponse(BaseModel):
    topic: str
    article_count: int
    chunk_count: int
    articles: list[ArticleResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class AskResponse(BaseModel):
    question: str
    answer: str


class ArticleListItemResponse(BaseModel):
    id: str
    title: str
    url: str | None
    fetched_at: str
    category: str
    n_tags: int
    source_name: str | None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/articles", response_model=list[ArticleListItemResponse])
def articles() -> list[ArticleListItemResponse]:
    init_db()
    return list_articles()


@app.post("/watch", response_model=WatchResponse)
def watch(request: WatchRequest) -> WatchResponse:
    try:
        return watch_topic(request.topic)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Watch failed. Check Tavily, LM Studio, and the application logs.",
        ) from exc


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    try:
        return ask_question(request.question)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Question failed. Check LM Studio and the application logs.",
        ) from exc


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
