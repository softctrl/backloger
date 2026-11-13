import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from backloger.models import Project
from backloger.repository import Repository
from backloger.service import BacklogService, CreateItem
from backloger.web import create_app

pytestmark = pytest.mark.e2e


def test_browser_kanban_external_edit_graph_and_readonly(tmp_path: Path) -> None:
    root = tmp_path / "browser-project"
    repo = Repository(root)
    repo.initialize(Project(name="Sistema de teste", key="SYS"))
    service = BacklogService(repo)
    service.add(CreateItem(title="Primeira entrega", labels=["backend"]))

    def loop_factory():
        loop = asyncio.new_event_loop()

        def tick():
            loop.call_later(0.02, tick)

        loop.call_soon(tick)
        return loop

    client = TestClient(create_app(root), backend_options={"loop_factory": loop_factory})
    with sync_playwright() as p, ThreadPoolExecutor(max_workers=1) as executor:
        browser = p.chromium.launch(
            executable_path=os.getenv("CHROMIUM_EXECUTABLE_PATH"),
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route_request(route):
            request = route.request
            response = executor.submit(
                client.request,
                request.method,
                request.url,
                content=request.post_data_buffer,
                headers=request.headers,
            ).result(timeout=15)
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={
                    k: v
                    for k, v in response.headers.items()
                    if k not in {"content-length", "content-encoding"}
                },
            )

        page.route("http://127.0.0.1:8765/**", route_request)
        page.goto("http://127.0.0.1:8765/")
        expect(page.locator("#completion-chart svg")).to_be_visible()
        page.locator('[data-history-days="7"]').click()
        expect(page.locator("#activity-chart .activity-day")).to_have_count(7)
        page.locator('[data-view="kanban"]').click()
        expect(page.locator('.card[data-id="SYS-001"]')).to_be_visible()
        page.get_by_role("button", name="＋ Nova atividade", exact=True).click()
        page.get_by_label("Título", exact=True).fill("Segunda entrega")
        page.get_by_label("Bloqueada por", exact=False).fill("SYS-001")
        page.get_by_role("button", name="Salvar atividade", exact=True).click()
        expect(page.locator("#editor")).not_to_be_visible()
        expect(page.locator('.card[data-id="SYS-002"]')).to_be_visible()
        page.locator('.card[data-id="SYS-001"]').drag_to(
            page.locator('.column[data-status="in_progress"]')
        )
        expect(
            page.locator('.column[data-status="in_progress"] .card[data-id="SYS-001"]')
        ).to_be_visible()
        page.locator('.card[data-id="SYS-001"]').click()
        page.get_by_label("Título", exact=True).fill("Minha edição ainda aberta")
        path = root / ".backloger/work-items/SYS-001.json"
        data = json.loads(path.read_text())
        data["title"] = "Edição externa sem mudar version"
        data["external_field"] = {"preserved": True}
        path.write_text(json.dumps(data))
        page.get_by_role("button", name="Salvar atividade", exact=True).click()
        expect(page.locator("#editor-conflict")).to_be_visible()
        expect(page.get_by_label("Título", exact=True)).to_have_value("Minha edição ainda aberta")
        assert json.loads(path.read_text())["title"] == data["title"]
        page.get_by_role("button", name="Fechar editor", exact=True).click()
        expect(page.locator('.card[data-id="SYS-001"]')).to_contain_text(data["title"])
        page.locator('[data-view="sprints"]').click()
        page.locator("#sprint-create").click()
        page.get_by_label("Nome da sprint", exact=True).fill("Sprint de entrega")
        today = datetime.now(UTC).date()
        page.get_by_label("Início da sprint", exact=True).fill(today.isoformat())
        page.get_by_label("Fim da sprint", exact=True).fill(
            (today + timedelta(days=13)).isoformat()
        )
        page.locator("#sprint-save").click()
        expect(page.locator("#sprint-editor")).not_to_be_visible()
        expect(page.locator("#sprint-name")).to_have_text("Sprint de entrega")
        page.locator("#sprint-add").click()
        for item_id in ("SYS-001", "SYS-002"):
            page.locator("#sprint-backlog-search").fill(item_id)
            button = page.get_by_role("button", name=f"Adicionar {item_id} à sprint", exact=True)
            button.click()
            expect(button).to_have_count(0)
        page.locator("#sprint-planner-close").click()
        expect(page.locator('#sprint-board [data-category="active"] .card')).to_have_count(1)
        expect(page.locator('#sprint-board [data-category="pending"] .card')).to_have_count(1)
        page.locator('#sprint-board .card[data-id="SYS-002"]').click()
        expect(page.locator("#editor")).to_be_visible()
        page.locator('#editor select[name="status"]').select_option("done")
        page.locator("#save-item").click()
        expect(page.locator("#sprint-progress-label")).to_contain_text("50%")
        screenshot = os.getenv("BACKLOGER_SPRINT_SCREENSHOT")
        if screenshot:
            page.screenshot(path=screenshot, full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Dependências", exact=False).click()
        page.locator("#graph-scope").select_option("project")
        page.wait_for_function(
            "() => typeof graph !== 'undefined' && graph && graph.nodes().length === 2"
        )
        assert page.evaluate("graph.edges().length") == 1
        expect(page.locator("#critical-path")).to_contain_text("sem estimativa")
        page.locator("#graph-fullscreen").click()
        expect(page.locator("#graph-panel")).to_have_attribute("aria-modal", "true")
        page.locator("#graph-search").fill("SYS-002")
        page.locator("#graph-search").press("Enter")
        expect(page.locator("#graph-detail h3")).to_contain_text("Segunda entrega")
        with page.expect_download() as download:
            page.locator("#graph-export-svg").click()
        assert download.value.suggested_filename == "SYS-DEPENDENCIAS.svg"
        with page.expect_download() as download:
            page.locator("#graph-export-pdf").click()
        assert download.value.suggested_filename == "SYS-DEPENDENCIAS.pdf"
        page.locator("#graph-fullscreen").click()
        expect(page.locator("#graph-fullscreen")).to_have_attribute("aria-pressed", "false")
        page.get_by_role("button", name="Tabela", exact=False).click()
        expect(page.locator("#item-table tr")).to_have_count(2)
        page.get_by_role("button", name="Roadmap", exact=False).click()
        expect(page.locator("#roadmap")).to_contain_text("Sem milestone")
        page.get_by_role("button", name="Dashboard", exact=False).click()
        expect(page.locator(".history-note")).to_contain_text("Throughput")
        page.locator('[data-view="document"]').click()
        expect(page.frame_locator("#document-frame").locator("h1")).to_contain_text("Backlog")
        page.locator('[data-document-mode="source"]').click()
        expect(page.locator("#document-source")).to_contain_text(data["title"])
        with page.expect_download() as download:
            page.locator("#document-view [data-export-pdf]").click()
        assert download.value.suggested_filename == "SYS-BACKLOG.pdf"
        page.locator('[data-view="dashboard"]').click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        screenshot = os.getenv("BACKLOGER_SCREENSHOT")
        if screenshot:
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.get_by_role("button", name="Kanban", exact=False).click()
            page.screenshot(path=screenshot, full_page=True)
        assert errors == []
        browser.close()
