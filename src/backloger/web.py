"""A single-project FastAPI application backed by the shared service."""

import logging
import os
import secrets
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backloger import documents, exports
from backloger.errors import BacklogError, ReadOnlyError
from backloger.graph import analyze
from backloger.graph_export import GraphDocument, GraphExport
from backloger.models import Reference, SavedView
from backloger.repository import Repository
from backloger.security import LocalSecurity
from backloger.service import (
    BacklogService,
    CreateItem,
    IterationRequest,
    SaveViewRequest,
    UpdateItem,
)

ASSETS = Path(__file__).parent


def create_app(
    project: Path | str | None = None,
    *,
    read_only: bool | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    root = Path(project) if project is not None else Path(os.environ.get("BACKLOGER_PROJECT", "."))
    readonly = (
        read_only
        if read_only is not None
        else os.getenv("BACKLOGER_READ_ONLY", "false").lower() == "true"
    )
    service = BacklogService(Repository(root, read_only=readonly))
    token = secrets.token_urlsafe(32)
    app = FastAPI(title="Backloger", version="0.1.0", docs_url=None, redoc_url=None)
    app.add_middleware(LocalSecurity, token=token)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["localhost", "127.0.0.1", "[::1]"]
    )
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")
    templates = Jinja2Templates(directory=ASSETS / "templates")

    @app.exception_handler(BacklogError)
    async def domain_error(request: Request, exc: BacklogError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=exc.http_status)

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": "invalid_data",
                "message": "Dados do contrato inválidos",
                "fields": [
                    {"path": list(e["loc"]), "message": e["msg"]}
                    for e in exc.errors(include_input=False)
                ],
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        reference = uuid4().hex
        logging.getLogger("backloger").error(
            "request_failed reference=%s type=%s", reference, type(exc).__name__
        )
        return JSONResponse(
            {
                "error": "internal_error",
                "message": "Falha ao acessar os dados do projeto",
                "reference": reference,
            },
            status_code=500,
        )

    def mutation_revision(value: str | None) -> str:
        if readonly:
            raise ReadOnlyError("Projeto em modo somente leitura")
        if not value:
            from fastapi import HTTPException

            raise HTTPException(428, "Envie If-Match com a revisão retornada por /api/v1/state")
        return value.strip('"')

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        snapshot = service.snapshot()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "project": snapshot.backlog.project,
                "token": token,
                "read_only": readonly,
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        service.snapshot()
        return {"status": "ok"}

    @app.get("/api/docs", response_class=HTMLResponse, include_in_schema=False)
    def api_docs(request: Request) -> Response:
        return templates.TemplateResponse(request=request, name="api.html", context={})

    @app.get("/partials/history", response_class=HTMLResponse)
    def history(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request, name="history.html", context={"metrics": service.state()["metrics"]}
        )

    @app.get("/api/v1/state")
    def state(if_none_match: Annotated[str | None, Header()] = None) -> Response:
        data = service.state()
        etag = f'"{data["revision"]}"'
        if if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(data, headers={"ETag": etag})

    @app.post("/api/v1/items", status_code=201)
    def add_item(
        request: CreateItem, if_match: Annotated[str | None, Header()] = None
    ) -> JSONResponse:
        item, snapshot = service.add(request, mutation_revision(if_match))
        return JSONResponse(
            {"item": item.model_dump(mode="json"), "revision": snapshot.revision},
            status_code=201,
            headers={"ETag": f'"{snapshot.revision}"'},
        )

    @app.patch("/api/v1/items/{item_id}")
    def update_item(
        item_id: str, request: UpdateItem, if_match: Annotated[str | None, Header()] = None
    ) -> JSONResponse:
        item, snapshot = service.update(item_id, request, mutation_revision(if_match))
        return JSONResponse(
            {"item": item.model_dump(mode="json"), "revision": snapshot.revision},
            headers={"ETag": f'"{snapshot.revision}"'},
        )

    @app.put("/api/v1/views/{view_id}")
    def save_view(
        view_id: str, request: SaveViewRequest, if_match: Annotated[str | None, Header()] = None
    ) -> dict[str, str]:
        if request.id != view_id:
            raise BacklogError("ID da visualização diferente do caminho")
        saved = service.save_view(
            SavedView.model_validate(request.model_dump()), mutation_revision(if_match)
        )
        return {"revision": saved.revision}

    @app.post("/api/v1/iterations", status_code=201)
    def create_iteration(
        request: IterationRequest,
        if_match: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        iteration, snapshot = service.save_iteration(request, mutation_revision(if_match))
        return JSONResponse(
            {"iteration": iteration.model_dump(mode="json"), "revision": snapshot.revision},
            status_code=201,
            headers={"ETag": f'"{snapshot.revision}"'},
        )

    @app.put("/api/v1/iterations/{iteration_id}")
    def update_iteration(
        iteration_id: Reference,
        request: IterationRequest,
        if_match: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        iteration, snapshot = service.save_iteration(
            request,
            mutation_revision(if_match),
            iteration_id,
        )
        return JSONResponse(
            {"iteration": iteration.model_dump(mode="json"), "revision": snapshot.revision},
            headers={"ETag": f'"{snapshot.revision}"'},
        )

    @app.get("/api/v1/graph")
    def graph(item_id: str | None = None) -> dict[str, Any]:
        return analyze(service.snapshot().backlog, item_id, blocker_limit=100)

    @app.post("/api/v1/graph/export/{format}")
    def export_graph(
        format: str, request: GraphExport, if_match: Annotated[str | None, Header()] = None
    ) -> Response:
        if format not in {"svg", "pdf"}:
            raise BacklogError("Formato do grafo deve ser svg ou pdf")
        if not if_match:
            raise HTTPException(428, "Envie If-Match com a revisão da visão exportada")
        snapshot = service.snapshot(if_match.strip('"'))
        document = GraphDocument(snapshot.backlog, request)
        content = document.pdf() if format == "pdf" else document.svg().encode()
        return Response(
            content,
            media_type="application/pdf" if format == "pdf" else "image/svg+xml",
            headers={"Content-Disposition": f'attachment; filename="DEPENDENCIAS.{format}"'},
        )

    @app.get("/api/v1/document")
    def document_source() -> dict[str, Any]:
        snapshot, source = service.report()
        return {
            "markdown": source,
            "revision": snapshot.revision,
            "item_count": len(snapshot.backlog.work_items),
        }

    @app.get("/document", response_class=HTMLResponse, include_in_schema=False)
    def document_preview(standalone: bool = False) -> Response:
        snapshot, source = service.report()
        return HTMLResponse(
            documents.report_html(
                source,
                snapshot.backlog.project.name,
                standalone=standalone,
            )
        )

    @app.get("/api/v1/export/{format}")
    def export(format: str) -> Response:
        if format in {"markdown", "html", "pdf"}:
            snapshot, source = service.report()
            if format == "markdown":
                return Response(
                    source,
                    media_type="text/markdown",
                    headers={
                        "Content-Disposition": 'attachment; filename="BACKLOG.md"',
                    },
                )
        if format == "html":
            return HTMLResponse(
                documents.report_html(source, snapshot.backlog.project.name),
                headers={"Content-Disposition": 'attachment; filename="BACKLOG.html"'},
            )
        if format == "pdf":
            return Response(
                documents.pdf(snapshot.backlog, source=source),
                media_type="application/pdf",
                headers={"Content-Disposition": 'attachment; filename="BACKLOG.pdf"'},
            )
        formats = {
            "csv": (exports.csv_report, "text/csv", "csv"),
            "mermaid": (exports.mermaid, "text/plain", "mmd"),
            "svg": (exports.svg, "image/svg+xml", "svg"),
        }
        if format not in formats:
            raise BacklogError("Formato desconhecido")
        render, media, suffix = formats[format]
        return Response(
            render(service.snapshot().backlog),
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="backlog.{suffix}"'},
        )

    return app
