"""REST and SSE API routes for bibcanon local workbench."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from bibcanon.config import load_config, save_config
from bibcanon.server.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    CloudSecurityConfig,
    create_session_token,
    is_request_authenticated,
)
from bibcanon.core.bib_parser import (
    parse_bib_content,
    parse_bib_file,
    splice_bib_document,
    write_bib_with_backup,
)
from bibcanon.core.dedup import mark_duplicate_entries
from bibcanon.core.pipeline import (
    build_initial_audit_entries,
    merge_pasted_bibtex,
    run_verification_pipeline,
    verify_single_entry,
)
from bibcanon.models import (
    AppConfig,
    CacheClearResponse,
    CreateJobRequest,
    CreateJobResponse,
    EntryAuditResult,
    ExportRenderRequest,
    ExportRenderResponse,
    ExportWriteLocalRequest,
    ExportWriteLocalResponse,
    ParsedBibDocument,
    PasteMergeRequest,
    RetryEntryRequest,
)
from bibcanon.providers.base import RateLimitedHttpClient
from bibcanon.storage.cache import BibCache


MAX_BIB_CONTENT_BYTES = 5 * 1024 * 1024  # 5 MB upload ceiling
DEFAULT_MAX_RETAINED_JOBS = 50
DEFAULT_JOB_TTL_SEC = 7200.0  # 2 hours
MASKED_SECRET = "********"


class LoginRequest(BaseModel):
    username: str
    password: str


@dataclass
class JobState:
    """In-memory state for an active or completed .bib verification job."""

    job_id: str
    doc: ParsedBibDocument
    entries: list[EntryAuditResult]
    force_refresh: bool = False
    created_at: float = field(default_factory=time.time)
    completed_count: int = 0
    finished: bool = False
    cancelled: bool = False
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    event_history: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    subscribers: list[asyncio.Queue[tuple[str, dict[str, Any]]]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None


class JobManager:
    """Manages verification jobs, bounded memory eviction, and SSE event broadcasting."""

    def __init__(
        self,
        cache: BibCache | None = None,
        client_factory: Any = None,
        max_retained_jobs: int = DEFAULT_MAX_RETAINED_JOBS,
        job_ttl_sec: float = DEFAULT_JOB_TTL_SEC,
    ) -> None:
        self.jobs: dict[str, JobState] = {}
        self._cache = cache
        self._client_factory = client_factory
        self.max_retained_jobs = max_retained_jobs
        self.job_ttl_sec = job_ttl_sec

    def prune_old_jobs(self) -> None:
        """Evict expired or excess completed jobs so long-running cloud servers never leak RAM."""
        now = time.time()
        finished_jobs = [
            j for j in self.jobs.values() if j.finished and not j.subscribers
        ]
        for j in finished_jobs:
            if now - j.created_at > self.job_ttl_sec:
                self.jobs.pop(j.job_id, None)

        if len(self.jobs) > self.max_retained_jobs:
            removable = sorted(
                (j for j in self.jobs.values() if j.finished and not j.subscribers),
                key=lambda x: x.created_at,
            )
            excess = len(self.jobs) - self.max_retained_jobs
            for j in removable[:excess]:
                self.jobs.pop(j.job_id, None)

    def get_cache(self, config: AppConfig) -> BibCache:
        if self._cache is not None:
            return self._cache
        return BibCache(ttl_days=config.cache_ttl_days)

    def create_http_client(self, config: AppConfig) -> RateLimitedHttpClient:
        if self._client_factory is not None:
            return self._client_factory(config)
        return RateLimitedHttpClient(config=config)

    async def broadcast(self, job: JobState, event_name: str, data: dict[str, Any]) -> None:
        async with job.lock:
            job.event_history.append((event_name, data))
            for q in list(job.subscribers):
                q.put_nowait((event_name, data))
            if event_name in {"job_completed", "job_cancelled"}:
                job.finished = True

    async def run_job(self, job: JobState) -> None:
        cfg = load_config()
        cache = self.get_cache(cfg)
        client = self.create_http_client(cfg)

        async def _on_entry(entry: EntryAuditResult, completed: int, total: int) -> None:
            job.completed_count = completed
            await self.broadcast(
                job,
                "entry_updated",
                {
                    "job_id": job.job_id,
                    "completed": completed,
                    "total": total,
                    "entry": entry.model_dump(),
                },
            )

        try:
            final_entries = await run_verification_pipeline(
                job.doc,
                config=cfg,
                cache=cache,
                force_refresh=job.force_refresh,
                on_entry_updated=_on_entry,
                cancel_event=job.cancel_event,
                client=client,
            )
            if job.cancel_event.is_set():
                job.cancelled = True
                await self.broadcast(
                    job,
                    "job_cancelled",
                    {
                        "job_id": job.job_id,
                        "completed": job.completed_count,
                        "total": len(job.entries),
                    },
                )
                return

            job.entries = final_entries
            await self.broadcast(
                job,
                "job_completed",
                {
                    "job_id": job.job_id,
                    "completed": len(final_entries),
                    "total": len(final_entries),
                    "entries": [e.model_dump() for e in final_entries],
                },
            )
        except asyncio.CancelledError:
            job.cancelled = True
            await self.broadcast(
                job,
                "job_cancelled",
                {
                    "job_id": job.job_id,
                    "completed": job.completed_count,
                    "total": len(job.entries),
                },
            )
        finally:
            await client.aclose()


router = APIRouter(prefix="/api")


def _get_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


def _get_cloud_security(request: Request) -> CloudSecurityConfig:
    return getattr(request.app.state, "cloud_security", CloudSecurityConfig(enabled=False))


def _mask_config_for_client(cfg: AppConfig, cloud_mode: bool) -> AppConfig:
    if not cloud_mode:
        return cfg
    masked = cfg.model_copy(deep=True)
    if masked.openalex_api_key:
        masked.openalex_api_key = MASKED_SECRET
    if masked.semantic_scholar_api_key:
        masked.semantic_scholar_api_key = MASKED_SECRET
    return masked


def _get_job_or_404(manager: JobManager, job_id: str) -> JobState:
    job = manager.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未找到任务: {job_id}")
    return job


@router.get("/auth/status")
async def get_auth_status(request: Request) -> dict[str, Any]:
    """Public endpoint informing the SPA whether cloud login is required and active."""
    sec = _get_cloud_security(request)
    authed = is_request_authenticated(request, sec)
    return {
        "auth_required": sec.enabled,
        "authenticated": authed,
        "cloud_mode": sec.enabled,
        "username": sec.username if authed and sec.enabled else None,
    }


@router.post("/auth/login")
async def login_cloud(req: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    """Authenticate username/password and set a 30-day HttpOnly signed session cookie."""
    sec = _get_cloud_security(request)
    if not sec.enabled:
        return {"authenticated": True, "cloud_mode": False}

    user_ok = secrets.compare_digest(req.username.strip(), sec.username)
    pw_ok = secrets.compare_digest(req.password, sec.password)
    if not (user_ok and pw_ok):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_session_token(sec)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return {
        "authenticated": True,
        "cloud_mode": True,
        "username": sec.username,
    }


@router.post("/auth/logout")
async def logout_cloud(response: Response) -> dict[str, Any]:
    """Clear the cloud session cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"authenticated": False}


@router.get("/bootstrap")
async def get_bootstrap(request: Request) -> dict[str, Any]:
    """Return startup metadata (optional CLI bib_file path + current settings + cache stats)."""
    sec = _get_cloud_security(request)
    cfg = load_config()
    manager = _get_manager(request)
    cache_stats = manager.get_cache(cfg).get_stats()
    return {
        "initial_bib_path": None
        if sec.enabled
        else getattr(request.app.state, "initial_bib_path", None),
        "cloud_mode": sec.enabled,
        "username": sec.username if sec.enabled else None,
        "settings": _mask_config_for_client(cfg, sec.enabled).model_dump(),
        "cache_stats": cache_stats,
    }


@router.post("/jobs", response_model=CreateJobResponse)
async def create_job(req: CreateJobRequest, request: Request) -> CreateJobResponse:
    """Parse a single .bib input losslessly and launch background verification."""
    sec = _get_cloud_security(request)
    manager = _get_manager(request)
    manager.prune_old_jobs()

    if req.bib_path and req.bib_path.strip():
        if sec.enabled:
            raise HTTPException(
                status_code=403,
                detail="云端共享模式下已禁用读取服务器本地磁盘路径，请直接上传或粘贴 .bib 文件",
            )
        target = Path(req.bib_path.strip()).expanduser()
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=400, detail=f"本地 .bib 文件不存在: {target}")
        try:
            doc = parse_bib_file(target)
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"读取 UTF-8 .bib 文件失败: {exc}"
            ) from exc
    elif req.bib_content is not None and req.bib_content.strip():
        if len(req.bib_content.encode("utf-8")) > MAX_BIB_CONTENT_BYTES:
            raise HTTPException(status_code=413, detail="单个 .bib 内容不能超过 5 MB")
        doc = parse_bib_content(req.bib_content)
    else:
        raise HTTPException(
            status_code=400, detail="请粘贴或上传有效的 .bib 文件内容"
        )

    initial_entries = build_initial_audit_entries(doc)
    job_id = uuid.uuid4().hex[:12]
    manager = _get_manager(request)
    job = JobState(
        job_id=job_id,
        doc=doc,
        entries=initial_entries,
        force_refresh=req.force_refresh,
    )
    manager.jobs[job_id] = job
    job.task = asyncio.create_task(manager.run_job(job))

    return CreateJobResponse(
        job_id=job_id,
        total_entries=len(initial_entries),
        source_path=doc.source_path,
        entries=initial_entries,
    )


@router.get("/jobs/{job_id}", response_model=CreateJobResponse)
async def get_job(job_id: str, request: Request) -> CreateJobResponse:
    """Return current snapshot of a verification job."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, job_id)
    return CreateJobResponse(
        job_id=job.job_id,
        total_entries=len(job.entries),
        source_path=job.doc.source_path,
        entries=job.entries,
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request) -> StreamingResponse:
    """SSE stream pushing real-time `entry_updated` and final `job_completed` events."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, job_id)

    async def _event_generator():
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] | None = None
        async with job.lock:
            past_events = list(job.event_history)
            is_done = job.finished
            if not is_done:
                queue = asyncio.Queue()
                job.subscribers.append(queue)

        try:
            for ev_name, ev_data in past_events:
                payload = json.dumps(ev_data, ensure_ascii=False)
                yield f"event: {ev_name}\ndata: {payload}\n\n"

            if is_done or queue is None:
                return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev_name, ev_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    # SSE keep-alive comment heartbeat
                    yield ": heartbeat\n\n"
                    continue

                payload = json.dumps(ev_data, ensure_ascii=False)
                yield f"event: {ev_name}\ndata: {payload}\n\n"
                if ev_name in {"job_completed", "job_cancelled"}:
                    break
        finally:
            if queue is not None:
                async with job.lock:
                    if queue in job.subscribers:
                        job.subscribers.remove(queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    """Cancel a running verification job while preserving completed entry results."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, job_id)
    job.cancel_event.set()
    if job.task is not None and not job.task.done():
        job.task.cancel()
    return {
        "job_id": job.job_id,
        "status": "cancelled",
        "completed": job.completed_count,
    }


@router.post("/jobs/{job_id}/entries/{cite_key}/retry", response_model=EntryAuditResult)
async def retry_single_entry(
    job_id: str,
    cite_key: str,
    req: RetryEntryRequest,
    request: Request,
) -> EntryAuditResult:
    """Re-verify a single entry with optional overridden query title and cache bypass."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, job_id)

    target_idx: int | None = None
    for idx, ent in enumerate(job.entries):
        if ent.cite_key == cite_key:
            target_idx = idx
            break

    if target_idx is None:
        raise HTTPException(status_code=404, detail=f"未找到引用条目: {cite_key}")

    parsed_ent = job.doc.entries[target_idx]
    cfg = load_config()
    cache = manager.get_cache(cfg)

    async with manager.create_http_client(cfg) as client:
        refreshed = await verify_single_entry(
            parsed_ent,
            client,
            cache=cache,
            config=cfg,
            force_refresh=req.force_refresh,
            override_query_title=req.override_query_title,
        )

    job.entries[target_idx] = refreshed
    mark_duplicate_entries(job.entries, job.doc.entries)
    return job.entries[target_idx]


@router.post("/jobs/{job_id}/entries/{cite_key}/paste-merge", response_model=EntryAuditResult)
async def paste_merge_entry(
    job_id: str,
    cite_key: str,
    req: PasteMergeRequest,
    request: Request,
) -> EntryAuditResult:
    """Smart-merge user-pasted external BibTeX while locking original cite_key."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, job_id)

    target_idx: int | None = None
    for idx, ent in enumerate(job.entries):
        if ent.cite_key == cite_key:
            target_idx = idx
            break

    if target_idx is None:
        raise HTTPException(status_code=404, detail=f"未找到引用条目: {cite_key}")

    cfg = load_config()
    try:
        updated = merge_pasted_bibtex(job.entries[target_idx], req.pasted_bibtex, config=cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job.entries[target_idx] = updated
    mark_duplicate_entries(job.entries, job.doc.entries)
    return job.entries[target_idx]


@router.post("/export/render", response_model=ExportRenderResponse)
async def export_render(req: ExportRenderRequest, request: Request) -> ExportRenderResponse:
    """Losslessly render the full .bib document using character-span splicing."""
    manager = _get_manager(request)
    job = _get_job_or_404(manager, req.job_id)
    cfg = load_config()

    output_bibtex, stats = splice_bib_document(
        job.doc.raw_text,
        job.entries,
        style_mode=req.style_mode,
        protect_title_case=req.protect_title_case,
        decisions_override=req.decisions,
        noise_blacklist=cfg.noise_field_blacklist,
    )
    return ExportRenderResponse(output_bibtex=output_bibtex, stats=stats)


@router.post("/export/write-local", response_model=ExportWriteLocalResponse)
async def export_write_local(
    req: ExportWriteLocalRequest,
    request: Request,
) -> ExportWriteLocalResponse:
    """Create a timestamped .bak backup and write spliced UTF-8 .bib to local disk."""
    sec = _get_cloud_security(request)
    if sec.enabled:
        raise HTTPException(
            status_code=403,
            detail="云端共享模式下已禁用写入服务器磁盘，请使用复制或下载 .bib 功能",
        )
    manager = _get_manager(request)
    job = _get_job_or_404(manager, req.job_id)
    cfg = load_config()

    if not req.target_bib_path.strip():
        raise HTTPException(status_code=400, detail="未指定目标本地 .bib 路径")

    output_bibtex, stats = splice_bib_document(
        job.doc.raw_text,
        job.entries,
        style_mode=req.style_mode,
        protect_title_case=req.protect_title_case,
        decisions_override=req.decisions,
        noise_blacklist=cfg.noise_field_blacklist,
    )

    try:
        target_resolved = Path(req.target_bib_path.strip()).expanduser().resolve()
        bak_path = write_bib_with_backup(target_resolved, output_bibtex)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"写回本地文件失败: {exc}") from exc

    return ExportWriteLocalResponse(
        output_bibtex=output_bibtex,
        backup_path=str(bak_path),
        target_bib_path=str(target_resolved),
        stats=stats,
    )


@router.get("/settings", response_model=AppConfig)
async def get_settings(request: Request) -> AppConfig:
    """Load global AppConfig from ~/.bibcanon/config.json."""
    sec = _get_cloud_security(request)
    return _mask_config_for_client(load_config(), sec.enabled)


@router.put("/settings", response_model=AppConfig)
async def update_settings(cfg: AppConfig, request: Request) -> AppConfig:
    """Save global AppConfig to ~/.bibcanon/config.json."""
    sec = _get_cloud_security(request)
    if sec.enabled:
        existing = load_config()
        if cfg.openalex_api_key == MASKED_SECRET:
            cfg.openalex_api_key = existing.openalex_api_key
        if cfg.semantic_scholar_api_key == MASKED_SECRET:
            cfg.semantic_scholar_api_key = existing.semantic_scholar_api_key
    saved = save_config(cfg)
    return _mask_config_for_client(saved, sec.enabled)


@router.get("/cache/stats")
async def get_cache_stats(request: Request) -> dict[str, Any]:
    """Return local SQLite cache statistics."""
    cfg = load_config()
    manager = _get_manager(request)
    return manager.get_cache(cfg).get_stats()


@router.delete("/cache", response_model=CacheClearResponse)
async def clear_cache(
    request: Request,
    scope: Literal["all", "queries"] = Query(default="all"),
) -> CacheClearResponse:
    """Clear SQLite cache entries for the requested scope."""
    cfg = load_config()
    manager = _get_manager(request)
    deleted = manager.get_cache(cfg).clear(scope=scope)
    return CacheClearResponse(scope=scope, deleted_entries=deleted)
