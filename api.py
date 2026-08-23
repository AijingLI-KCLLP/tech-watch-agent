from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from adapters.content import ContentExtractionError
from adapters.store import (
    delete_article,
    count_articles,
    get_article_detail,
    get_input_asset_file,
    init_db,
    list_articles,
    update_article,
)
from config import MAX_UPLOAD_BYTES, ROOT, UPLOADS_DIR
from core.models import Category, OriginalType, SourceVerificationStatus
from services.agent_service import add_pasted_text, add_uploaded_file, ask_question, watch_topic

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


class PasteTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    title: str | None = Field(default=None, max_length=500)
    provided_source_url: HttpUrl | None = None


class AddContentResponse(BaseModel):
    article: ArticleResponse
    input_asset_id: str
    chunk_count: int


class ArticleListItemResponse(BaseModel):
    id: str
    title: str
    url: str | None
    fetched_at: str
    category: str
    n_tags: int
    source_name: str | None
    raw_file_url: str | None


class ArticlePageResponse(BaseModel):
    items: list[ArticleListItemResponse]
    total: int
    limit: int
    offset: int


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


@app.post("/content/text", response_model=AddContentResponse)
def add_text_content(request: PasteTextRequest) -> AddContentResponse:
    try:
        return add_pasted_text(
            text=request.text,
            title=request.title,
            provided_source_url=(
                str(request.provided_source_url)
                if request.provided_source_url is not None
                else None
            ),
        )
    except ContentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Content ingest failed. Check LM Studio and the application logs.",
        ) from exc


@app.post("/content/file", response_model=AddContentResponse)
async def add_file_content(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    provided_source_url: HttpUrl | None = Form(default=None),
) -> AddContentResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds the 25 MB limit.")

    try:
        return add_uploaded_file(
            content=content,
            filename=file.filename or "upload",
            mime_type=file.content_type,
            title=title,
            provided_source_url=(
                str(provided_source_url) if provided_source_url is not None else None
            ),
        )
    except (ContentExtractionError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Content ingest failed. Check LM Studio and the application logs.",
        ) from exc


@app.get("/articles", response_model=ArticlePageResponse)
def articles(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ArticlePageResponse:
    init_db()
    items = [
        {
            **article,
            "raw_file_url": (
                f"/input-assets/{article['input_asset_id']}/file"
                if article["input_asset_original_type"] == OriginalType.IMAGE.value
                else None
            ),
        }
        for article in list_articles(limit=limit, offset=offset)
    ]
    return {"items": items, "total": count_articles(), "limit": limit, "offset": offset}


@app.get("/input-assets/{asset_id}/file", include_in_schema=False)
def input_asset_file(asset_id: str) -> FileResponse:
    """Serve a retained upload only when it is inside the managed uploads directory."""
    init_db()
    asset = get_input_asset_file(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Raw uploaded file not found.")

    file_path = (ROOT / asset["storage_path"]).resolve()
    uploads_path = UPLOADS_DIR.resolve()
    try:
        file_path.relative_to(uploads_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Raw uploaded file not found.") from exc
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Raw uploaded file not found.")

    return FileResponse(
        file_path,
        media_type=asset["mime_type"],
        filename=asset["input_filename"],
        content_disposition_type="inline",
    )


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
