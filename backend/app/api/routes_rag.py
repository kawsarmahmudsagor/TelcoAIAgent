import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.models.rag import EmbeddingJob, RagSource
from app.rag.config import MAX_UPLOAD_BYTES, RAG_SOURCE_ID_KEY, collection_for
from app.rag.retrieval import retrieve_scored
from app.repositories import agent_config_repo
from app.schemas.rag import (
    CreateSourceResponse,
    EmbeddingJobOut,
    LinkSourceCreate,
    RagSearchHit,
    RagSearchRequest,
    RagSearchResponse,
    RagSourceDetail,
    RagSourceList,
    RagSourceOut,
    ReindexAllResponse,
    TextSourceCreate,
)
from app.services import agent_config_service, rag_service
from app.services.rag_service import ConflictError, NotFoundError, RagServiceError

logger = logging.getLogger("api.rag")

router = APIRouter(prefix="/api/rag", tags=["knowledge-base"], dependencies=[Depends(get_current_admin)])


def _http_error(exc: RagServiceError) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


def _source_out(source: RagSource, job: EmbeddingJob | None) -> RagSourceOut:
    out = RagSourceOut.model_validate(source)
    out.latest_job = EmbeddingJobOut.model_validate(job) if job else None
    return out


def _created(source: RagSource, job: EmbeddingJob) -> CreateSourceResponse:
    return CreateSourceResponse(
        source=_source_out(source, job), job=EmbeddingJobOut.model_validate(job)
    )


@router.get("/sources", response_model=RagSourceList)
def list_sources(
    db: Session = Depends(get_db),
    source_type: str | None = None,
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> RagSourceList:
    rows, total = rag_service.list_sources(
        db, source_type=source_type, status=status_, limit=limit, offset=offset
    )
    jobs = rag_service.latest_jobs(db, [row.id for row in rows])
    return RagSourceList(items=[_source_out(row, jobs.get(row.id)) for row in rows], total=total)


@router.post(
    "/sources/documents", response_model=CreateSourceResponse, status_code=status.HTTP_201_CREATED
)
def create_document_source(
    file: UploadFile = File(...),
    name: str | None = Form(default=None, max_length=255),
    db: Session = Depends(get_db),
) -> CreateSourceResponse:
    # Read one byte past the limit, so an oversized upload is caught without
    # holding more than that in memory.
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File too large: max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    try:
        source, job = rag_service.create_document_source(
            db,
            name=name,
            filename=file.filename or "upload",
            content=content,
            content_type=file.content_type,
        )
    except RagServiceError as exc:
        raise _http_error(exc) from exc
    return _created(source, job)


@router.post("/sources/links", response_model=CreateSourceResponse, status_code=status.HTTP_201_CREATED)
def create_link_source(payload: LinkSourceCreate, db: Session = Depends(get_db)) -> CreateSourceResponse:
    try:
        source, job = rag_service.create_link_source(
            db,
            name=payload.name,
            url=payload.url,
            max_depth=payload.max_depth,
            max_pages=payload.max_pages,
            allowed_domains=payload.allowed_domains,
        )
    except RagServiceError as exc:
        raise _http_error(exc) from exc
    return _created(source, job)


@router.post("/sources/text", response_model=CreateSourceResponse, status_code=status.HTTP_201_CREATED)
def create_text_source(payload: TextSourceCreate, db: Session = Depends(get_db)) -> CreateSourceResponse:
    try:
        source, job = rag_service.create_text_source(db, name=payload.name, text=payload.text)
    except RagServiceError as exc:
        raise _http_error(exc) from exc
    return _created(source, job)


@router.get("/sources/{source_id}", response_model=RagSourceDetail)
def get_source(source_id: uuid.UUID, db: Session = Depends(get_db)) -> RagSourceDetail:
    try:
        source = rag_service.get_source(db, source_id, with_pages=True)
    except RagServiceError as exc:
        raise _http_error(exc) from exc
    jobs = rag_service.list_jobs(db, rag_source_id=source.id, limit=10)
    detail = RagSourceDetail.model_validate(source)
    detail.latest_job = EmbeddingJobOut.model_validate(jobs[0]) if jobs else None
    detail.jobs = [EmbeddingJobOut.model_validate(job) for job in jobs]
    return detail


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    try:
        rag_service.delete_source(db, source_id)
    except RagServiceError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/sources/{source_id}/reindex",
    response_model=CreateSourceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_source(source_id: uuid.UUID, db: Session = Depends(get_db)) -> CreateSourceResponse:
    try:
        source, job = rag_service.reindex_source(db, source_id)
    except RagServiceError as exc:
        raise _http_error(exc) from exc
    return _created(source, job)


@router.post("/reindex-all", response_model=ReindexAllResponse, status_code=status.HTTP_202_ACCEPTED)
def reindex_all(db: Session = Depends(get_db)) -> ReindexAllResponse:
    """Re-embeds every source with the current model and chunk settings (e.g.
    after changing chunk size, which marks sources stale)."""
    return ReindexAllResponse(queued=rag_service.reindex_all(db))


@router.get("/jobs", response_model=list[EmbeddingJobOut])
def list_jobs(
    db: Session = Depends(get_db),
    source_id: uuid.UUID | None = None,
    status_: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EmbeddingJobOut]:
    jobs = rag_service.list_jobs(db, rag_source_id=source_id, status=status_, limit=limit)
    return [EmbeddingJobOut.model_validate(job) for job in jobs]


@router.post("/jobs/{job_id}/retry", response_model=EmbeddingJobOut)
def retry_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> EmbeddingJobOut:
    try:
        return EmbeddingJobOut.model_validate(rag_service.retry_job(db, job_id))
    except RagServiceError as exc:
        raise _http_error(exc) from exc


@router.post("/search", response_model=RagSearchResponse)
def search(payload: RagSearchRequest, db: Session = Depends(get_db)) -> RagSearchResponse:
    """The retrieval tester: what search_knowledge_base would return, with scores."""
    config = agent_config_service.resolve(agent_config_repo.get(db))
    api_key = agent_config_service.embedding_api_key(config)
    if not api_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No OpenRouter API key for embeddings: set OPENROUTER_API_KEY or save an OpenRouter key",
        )
    top_k = payload.top_k or config.rag_top_k
    threshold = config.rag_similarity_threshold if payload.threshold is None else payload.threshold
    scope = (
        [str(value) for value in payload.source_ids]
        if payload.source_ids is not None
        else config.rag_source_ids
    )
    source_ids = rag_service.searchable_source_ids(db, scope)
    try:
        chunks = retrieve_scored(
            payload.query,
            collection=collection_for(config.embedding_model),
            embedding_model=config.embedding_model,
            api_key=api_key,
            top_k=top_k,
            threshold=threshold,
            source_ids=source_ids,
        )
    except Exception as exc:
        logger.exception("knowledge base search failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Search failed: {exc}") from exc
    return RagSearchResponse(
        embedding_model=config.embedding_model,
        top_k=top_k,
        threshold=threshold,
        results=[
            RagSearchHit(
                text=chunk["text"],
                score=chunk["score"],
                rag_source_id=chunk["metadata"].get(RAG_SOURCE_ID_KEY),
                rag_source_name=chunk["metadata"].get("rag_source_name"),
                metadata=chunk["metadata"],
            )
            for chunk in chunks
        ],
    )
