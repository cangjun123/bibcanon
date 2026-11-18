"""FastAPI application factory and static frontend hosting."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bibcanon import __version__
from bibcanon.server.auth import CloudSecurityConfig, is_request_authenticated
from bibcanon.server.routes import JobManager, router
from bibcanon.storage.cache import BibCache

# Initialize mimetypes first so Windows Registry (`HKCR\.js = text/plain`) is loaded,
# then override standard web asset MIME types so ES module scripts always execute.
mimetypes.init()
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("application/wasm", ".wasm")


def get_static_dir() -> Path:
    """Return the bundled static frontend directory (`src/bibcanon/static`)."""
    return Path(__file__).resolve().parent.parent / "static"


def create_app(
    *,
    initial_bib_path: str | None = None,
    cache: BibCache | None = None,
    client_factory: Any = None,
    cloud_security: CloudSecurityConfig | None = None,
    max_retained_jobs: int = 50,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="bibcanon Local & Cloud Workbench",
        version=__version__,
        description="Academic BibTeX verifier, preprint upgrader, and canonical publisher formatter",
    )

    sec = cloud_security or CloudSecurityConfig(enabled=False)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def cloud_auth_middleware(request: Request, call_next):
        if sec.enabled and request.url.path.startswith("/api/"):
            public_paths = {"/api/auth/status", "/api/auth/login", "/api/auth/logout"}
            if request.url.path not in public_paths and not is_request_authenticated(request, sec):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "请先登录工作台 (Unauthorized)"},
                )
        return await call_next(request)

    app.state.initial_bib_path = initial_bib_path
    app.state.cloud_security = sec
    app.state.job_manager = JobManager(
        cache=cache,
        client_factory=client_factory,
        max_retained_jobs=max_retained_jobs,
    )

    app.include_router(router)

    static_dir = get_static_dir()
    assets_dir = static_dir / "assets"
    mimetypes.init()
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("application/javascript", ".mjs")
    mimetypes.add_type("text/css", ".css")
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;padding:2rem;'>"
            "<h2>bibcanon API Server is running</h2>"
            "<p>Static frontend bundle not yet built in <code>src/bibcanon/static/</code>.</p>"
            "</body></html>"
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa_fallback(full_path: str):
        candidate = (static_dir / full_path).resolve()
        if (
            static_dir.exists()
            and str(candidate).startswith(str(static_dir.resolve()))
            and candidate.is_file()
        ):
            return FileResponse(str(candidate))
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse(status_code=404, content="Not Found")

    return app


app = create_app()
