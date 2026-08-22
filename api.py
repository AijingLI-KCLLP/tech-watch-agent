from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.agent_service import ask_question, watch_topic

app = FastAPI(
    title="Tech Watch Agent API",
    version="0.1.0",
)


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
