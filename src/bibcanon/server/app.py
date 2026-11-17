"""FastAPI application factory and static frontend hosting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from bibcanon import __version__
from bibcanon.server.routes import JobManager, router
from bibcanon.storage.cache import BibCache


def get_static_dir() -> Path:
    """Return the bundled static frontend directory (`src/bibcanon/static`)."""
    return Path(__file__).resolve().parent.parent / "static"


def create_app(
    *,
    initial_bib_path: str | None = None,
    cache: BibCache | None = None,
    client_factory: Any = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="bibcanon Local Workbench",
        version=__version__,
        description="Academic BibTeX verifier, preprint upgrader, and canonical publisher formatter",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.initial_bib_path = initial_bib_path
    app.state.job_manager = JobManager(cache=cache, client_factory=client_factory)

    app.include_router(router)

    static_dir = get_static_dir()
    assets_dir = static_dir / "assets"
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
