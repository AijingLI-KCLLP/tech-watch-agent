from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adapters.store import delete_article, get_article_detail, init_db, list_articles, update_article
from core.models import Category, OriginalType, SourceVerificationStatus
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


class SourceDetailResponse(BaseModel):
    id: str
    name: str
    url: str
    type: str
    credibility_score: float | None
    source_summary: str | None


class InputAssetResponse(BaseModel):
    id: str
    article_id: str | None
    original_type: OriginalType
    mime_type: str
    input_filename: str | None
    storage_path: str | None
    sha256: str
    raw_text: str | None
    extracted_text: str | None
    provided_source_url: str | None
    source_verification_status: SourceVerificationStatus
    source_verification_reason: str | None
    source_verification_confidence: float | None
    verified_source_id: str | None
    created_at: str


class ArticleDetailResponse(BaseModel):
    id: str
    title: str
    url: str | None
    content: str
    fetched_at: str
    category: Category
    n_tags: int
    summary: str | None
    original_type: str | None
    source: SourceDetailResponse | None
    tags: list[str]
    input_assets: list[InputAssetResponse]


class ArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=5_000)
    category: Category | None = None
    tags: list[str] | None = Field(default=None, max_length=30)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/articles", response_model=list[ArticleListItemResponse])
def articles() -> list[ArticleListItemResponse]:
    init_db()
    return list_articles()


@app.get("/articles/{article_id}", response_model=ArticleDetailResponse)
def article_detail(article_id: str) -> ArticleDetailResponse:
    init_db()
    article = get_article_detail(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article


@app.patch("/articles/{article_id}", response_model=ArticleDetailResponse)
def edit_article(article_id: str, request: ArticleUpdateRequest) -> ArticleDetailResponse:
    updates = request.model_dump(exclude_unset=True, mode="json")
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    for field in ("title", "category"):
        if field in updates and updates[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null.")

    init_db()
    article = update_article(article_id, **updates)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article


@app.delete("/articles/{article_id}", status_code=204)
def remove_article(article_id: str) -> Response:
    init_db()
    if not delete_article(article_id):
        raise HTTPException(status_code=404, detail="Article not found.")
    return Response(status_code=204)


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
