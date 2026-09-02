from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from adapters.content import ContentExtractionError
from adapters.discovery import discover_topics
from adapters.store import (
    delete_article,
    count_articles,
    count_drafts,
    get_conversation_detail,
    get_draft_detail,
    get_article_detail,
    get_input_asset_file,
    init_db,
    list_articles,
    list_drafts,
    list_conversations,
)
from config import MAX_UPLOAD_BYTES, ROOT, UPLOADS_DIR
from core.models import Category, DraftFormat, DraftStatus, OriginalType, SourceVerificationStatus
from services.agent_service import (
    add_article_by_url,
    add_pasted_text,
    add_podcast_episode,
    add_uploaded_file,
    add_youtube_video,
    ask_question,
    watch_topic,
)
from services.article_review_service import edit_article as update_article
from services.publish_service import create_draft, regenerate_draft
from adapters.store import update_draft
from services.conversation_service import ask_in_conversation, create_conversation

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


class DiscoveredTopicResponse(BaseModel):
    category: Category
    topic: str
    description: str
    source_url: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class AskResponse(BaseModel):
    question: str
    answer: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


class ConversationDetailResponse(ConversationResponse):
    messages: list[ConversationMessageResponse]


class ConversationListItemResponse(ConversationResponse):
    message_count: int


class ConversationAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class PasteTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    title: str | None = Field(default=None, max_length=500)
    provided_source_url: HttpUrl | None = None
    provided_source_reference: str | None = Field(default=None, max_length=1_000)


class AddArticleUrlRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=500)


class AddPodcastRequest(BaseModel):
    url: HttpUrl
    transcript: str | None = Field(default=None, min_length=1, max_length=500_000)
    transcript_url: HttpUrl | None = None
    title: str | None = Field(default=None, max_length=500)


class AddContentResponse(BaseModel):
    article: ArticleResponse
    input_asset_id: str
    chunk_count: int
    source_verification_status: SourceVerificationStatus


class ArticleListItemResponse(BaseModel):
    id: str
    title: str
    url: str | None
    fetched_at: str
    category: str
    n_tags: int
    tags: list[str]
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
    credibility_reason: str | None
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
    provided_source_reference: str | None
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
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    summary: str | None = Field(default=None, max_length=5_000)
    category: Category | None = None
    tags: list[str] | None = Field(default=None, max_length=30)


class DraftCreateRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=2_000)
    format: DraftFormat
    platform: str = Field(default="none", min_length=1, max_length=80)
    language: str = Field(min_length=1, max_length=80)
    audience: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=300)
    tone: str = Field(min_length=1, max_length=300)
    personal_angle: str = Field(min_length=1, max_length=2_000)
    enrich_with_web: bool = True


class DraftUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    intent: str | None = Field(default=None, min_length=1, max_length=2_000)
    platform: str | None = Field(default=None, min_length=1, max_length=80)
    language: str | None = Field(default=None, min_length=1, max_length=80)
    audience: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = Field(default=None, min_length=1, max_length=300)
    tone: str | None = Field(default=None, min_length=1, max_length=300)
    personal_angle: str | None = Field(default=None, min_length=1, max_length=2_000)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)
    status: DraftStatus | None = None


class DraftArticleResponse(BaseModel):
    id: str
    title: str
    url: str | None
    category: str
    summary: str | None
    position: int


class DraftResponse(BaseModel):
    id: str
    title: str
    intent: str
    format: DraftFormat
    platform: str
    language: str
    audience: str
    objective: str
    tone: str
    personal_angle: str
    source_summary: str
    generated_content: str
    content: str
    status: DraftStatus
    created_at: str
    updated_at: str
    articles: list[DraftArticleResponse]


class DraftListItemResponse(BaseModel):
    id: str
    title: str
    intent: str
    format: DraftFormat
    platform: str
    language: str
    audience: str
    objective: str
    tone: str
    personal_angle: str
    status: DraftStatus
    created_at: str
    updated_at: str
    article_count: int


class DraftPageResponse(BaseModel):
    items: list[DraftListItemResponse]
    total: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/content/text", response_model=AddContentResponse)
def add_text_content(request: PasteTextRequest) -> AddContentResponse:
    try:
        kwargs = {
            "text": request.text,
            "title": request.title,
            "provided_source_url": (
                str(request.provided_source_url)
                if request.provided_source_url is not None
                else None
            ),
        }
        if request.provided_source_reference:
            kwargs["provided_source_reference"] = request.provided_source_reference
        return add_pasted_text(**kwargs)
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
    provided_source_reference: str | None = Form(default=None),
) -> AddContentResponse:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds the 25 MB limit.")

    try:
        kwargs = {
            "content": content,
            "filename": file.filename or "upload",
            "mime_type": file.content_type,
            "title": title,
            "provided_source_url": (
                str(provided_source_url) if provided_source_url is not None else None
            ),
        }
        if provided_source_reference:
            kwargs["provided_source_reference"] = provided_source_reference
        return add_uploaded_file(**kwargs)
    except (ContentExtractionError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Content ingest failed. Check LM Studio and the application logs.",
        ) from exc


@app.post("/content/url", response_model=AddContentResponse)
def add_url_content(request: AddArticleUrlRequest) -> AddContentResponse:
    try:
        return add_article_by_url(
            url=str(request.url),
            title=request.title,
        )
    except ContentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="URL ingest failed. Check the URL, OCR setup, and application logs.",
        ) from exc


@app.post("/content/youtube", response_model=AddContentResponse)
def add_youtube_content(request: AddArticleUrlRequest) -> AddContentResponse:
    try:
        return add_youtube_video(url=str(request.url), title=request.title)
    except ContentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="YouTube ingest failed. Check captions and the application logs.",
        ) from exc


@app.post("/content/podcast", response_model=AddContentResponse)
def add_podcast_content(request: AddPodcastRequest) -> AddContentResponse:
    try:
        return add_podcast_episode(
            url=str(request.url),
            transcript=request.transcript,
            transcript_url=(str(request.transcript_url) if request.transcript_url else None),
            title=request.title,
        )
    except ContentExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Podcast ingest failed. Check the transcript and application logs.",
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
    for field in ("title", "content", "category"):
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


@app.get("/drafts", response_model=DraftPageResponse)
def drafts() -> DraftPageResponse:
    init_db()
    return {"items": list_drafts(), "total": count_drafts()}


@app.post("/drafts", response_model=DraftResponse, status_code=201)
def add_draft(request: DraftCreateRequest) -> DraftResponse:
    init_db()
    try:
        return create_draft(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Draft generation failed: {exc}",
        ) from exc


@app.get("/drafts/{draft_id}", response_model=DraftResponse)
def draft_detail(draft_id: str) -> DraftResponse:
    init_db()
    draft = get_draft_detail(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft


@app.patch("/drafts/{draft_id}", response_model=DraftResponse)
def edit_draft(draft_id: str, request: DraftUpdateRequest) -> DraftResponse:
    updates = request.model_dump(exclude_unset=True, mode="json")
    if not updates:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    if any(value is None for value in updates.values()):
        raise HTTPException(status_code=422, detail="Draft fields cannot be null.")
    init_db()
    draft = update_draft(draft_id, **updates)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft


@app.post("/drafts/{draft_id}/regenerate", response_model=DraftResponse)
def regenerate_saved_draft(draft_id: str) -> DraftResponse:
    init_db()
    try:
        draft = regenerate_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Draft regeneration failed: {exc}",
        ) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft


@app.post("/watch", response_model=WatchResponse)
def watch(request: WatchRequest) -> WatchResponse:
    try:
        return watch_topic(request.topic)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Watch failed. Check Tavily, LM Studio, and the application logs.",
        ) from exc


@app.get("/discover/topics", response_model=list[DiscoveredTopicResponse])
def discover_recent_topics(
    categories: list[Category] = Query(
        default=[Category.TECH_CODE, Category.AI_AUTOMATION]
    ),
) -> list[DiscoveredTopicResponse]:
    try:
        return discover_topics(categories)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Topic discovery failed. Check Tavily and the application logs.",
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


@app.get("/conversations", response_model=list[ConversationListItemResponse])
def conversations() -> list[ConversationListItemResponse]:
    init_db()
    return list_conversations()


@app.post("/conversations", response_model=ConversationDetailResponse, status_code=201)
def add_conversation() -> ConversationDetailResponse:
    init_db()
    return create_conversation()


@app.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def conversation_detail(conversation_id: str) -> ConversationDetailResponse:
    init_db()
    conversation = get_conversation_detail(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@app.post(
    "/conversations/{conversation_id}/ask",
    response_model=ConversationDetailResponse,
)
def ask_conversation(
    conversation_id: str, request: ConversationAskRequest
) -> ConversationDetailResponse:
    init_db()
    try:
        conversation = ask_in_conversation(conversation_id, request.question)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Conversation answer failed: {exc}",
        ) from exc
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
