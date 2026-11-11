import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from backloger.cli import app
from backloger.service import BacklogService, CreateItem, UpdateItem
from backloger.web import create_app

pytestmark = pytest.mark.integration


def client_for(service: BacklogService, read_only: bool = False) -> tuple[TestClient, dict]:
    # A periodic wakeup also supports sandboxes that restrict loop self-pipes.
    def loop_factory():
        loop = asyncio.new_event_loop()

        def tick():
            loop.call_later(0.02, tick)

        loop.call_soon(tick)
        return loop

    client = TestClient(
        create_app(service.repository.root, read_only=read_only, allowed_hosts=["testserver"]),
        backend_options={"loop_factory": loop_factory},
    )
    page = client.get("/")
    token = re.search(r'name="backloger-token" content="([^"]+)"', page.text)[1]
    revision = client.get("/api/v1/state").headers["etag"]
    return client, {"X-Backloger-Token": token, "If-Match": revision}


def test_api_crud_etag_and_stale_version(service: BacklogService) -> None:
    client, headers = client_for(service)
    assert (
        client.get("/api/v1/state", headers={"If-None-Match": headers["If-Match"]}).status_code
        == 304
    )
    response = client.post("/api/v1/items", json={"title": "Nova"}, headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["item"]["id"] == "SYS-001"
    assert (
        client.patch(
            "/api/v1/items/SYS-001", json={"expected_version": 1, "status": "done"}, headers=headers
        ).status_code
        == 409
    )
    headers["If-Match"] = response.headers["etag"]
    response = client.patch(
        "/api/v1/items/SYS-001", json={"expected_version": 1, "status": "done"}, headers=headers
    )
    assert response.status_code == 200
    state = client.get("/api/v1/state").json()
    assert state["metrics"]["throughput_7d"] == 1
    assert client.get("/api/v1/export/svg").headers["content-type"].startswith("image/svg+xml")
    assert client.get("/api/v1/export/markdown").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    documentation = client.get("/api/docs")
    assert documentation.status_code == 200
    assert "/api/v1/items" in documentation.text
    assert "cdn" not in documentation.text
    assert client.get("/openapi.json").json()["info"]["title"] == "Backloger"


@pytest.mark.security
def test_http_boundary(service: BacklogService) -> None:
    client, headers = client_for(service)
    for extra in ({}, {"X-Backloger-Token": "wrong"}):
        assert (
            client.post("/api/v1/items", json={"title": "Denied"}, headers=extra).status_code == 403
        )
    assert (
        client.post(
            "/api/v1/items",
            json={"title": "Denied"},
            headers={**headers, "Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/state", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/v1/state", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert (
        client.post(
            "/api/v1/items",
            json={"title": "Denied"},
            headers={"X-Backloger-Token": headers["X-Backloger-Token"]},
        ).status_code
        == 428
    )
    assert client.post("/api/v1/items", content=b"x" * 300_000, headers=headers).status_code == 413
    response = client.post(
        "/api/v1/items", json={"title": "x", "id": "../../outside"}, headers=headers
    )
    assert response.status_code == 422
    assert not service.snapshot().backlog.work_items


@pytest.mark.security
def test_readonly_and_escaping(service: BacklogService) -> None:
    service.add(CreateItem(title='<script>alert("x")</script>'))
    client, headers = client_for(service, read_only=True)
    assert (
        client.post("/api/v1/items", json={"title": "Denied"}, headers=headers).status_code == 403
    )
    page = client.get("/")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    markdown = client.get("/api/v1/export/markdown").text
    assert "<script>" not in markdown
    svg = client.get("/api/v1/export/svg").text
    assert "<script>" not in svg


@pytest.mark.parametrize("storage", ["split", "single"])
def test_cli_full_flow_and_exit_codes(tmp_path: Path, storage: str) -> None:
    runner = CliRunner()
    prefix = ["--project", str(tmp_path), "--json"]

    def run(*args: str, code: int = 0):
        result = runner.invoke(app, [*prefix, *args])
        assert result.exit_code == code, result.output
        return result

    run("init", "--name", "Meu projeto", "--key", "SYS", "--storage", storage)
    run("init", "--name", "Duplicate", "--key", "SYS", code=3)
    run("add", "--type", "feature", "--title", "Fundação")
    run("add", "--title", "Implementar")
    run("link", "SYS-002", "--blocked-by", "SYS-001")
    run("link", "SYS-001", "--blocked-by", "SYS-002", code=1)
    assert len(json.loads(run("list", "--blocked").stdout)) == 1
    run("move", "SYS-001", "--to", "done")
    run("move", "SYS-001", "--to", "review", "--version", "1", code=3)
    run("validate", "--strict")
    run("analyze", "SYS-001")
    run("export", "markdown", "--output", str(tmp_path / "docs/BACKLOG.md"))
    run("graph", "--format", "svg", "--output", str(tmp_path / "docs/graph.svg"))
    run("doctor")
    run("recover")
    result = runner.invoke(app, [*prefix, "--read-only", "add", "--title", "Denied"])
    assert result.exit_code == 4
    assert (tmp_path / "docs/BACKLOG.md").read_text().startswith("# Backlog")
    assert run("show", "SYS-999", code=1).stdout == ""


def test_saved_views(service: BacklogService) -> None:
    client, headers = client_for(service)
    assert (
        client.put(
            "/api/v1/views/mine",
            json={"id": "mine", "name": "Invalid", "arbitrary": True},
            headers=headers,
        ).status_code
        == 422
    )
    response = client.put(
        "/api/v1/views/mine",
        json={"id": "mine", "name": "Meu trabalho", "filters": {"filter-owner": "me"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert client.get("/api/v1/state").json()["views"][0]["name"] == "Meu trabalho"


def test_metrics_reopening_and_completion(service: BacklogService) -> None:
    item, _ = service.add(CreateItem(title="Count once"))
    for version, status in [(1, "done"), (2, "review"), (3, "done")]:
        service.update(item.id, UpdateItem(expected_version=version, status=status))
    assert service.state()["metrics"]["throughput_7d"] == 1
