import io
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader
from test_api_cli import client_for

from backloger import documents, exports
from backloger.documents import PDFUnavailable
from backloger.metrics import activity_history, burndown_history
from backloger.models import Backlog, Iteration, Project, WorkItem
from backloger.pdf_worker import deny_resource
from backloger.service import BacklogService, CreateItem, UpdateItem

pytestmark = pytest.mark.integration


@pytest.mark.unit
def test_history_uses_utc_days_and_deduplicates_completions() -> None:
    events = [
        {
            "item_id": "SYS-001",
            "at": "2026-11-10T23:30:00-03:00",
            "action": "create",
            "status": "todo",
        },
        {
            "item_id": "SYS-001",
            "at": "2026-11-11T04:00:00Z",
            "action": "update",
            "status": "done",
            "previous_status": "review",
        },
        {
            "item_id": "SYS-001",
            "at": "2026-11-11T05:00:00Z",
            "action": "update",
            "status": "done",
            "previous_status": "review",
        },
        {
            "item_id": "SYS-002",
            "at": "2026-11-10T14:00:00Z",
            "action": "update",
            "status": "done",
            "previous_status": "done",
        },
        {"item_id": "SYS-999", "at": "2026-11-12T00:00:00Z", "action": "create", "status": "todo"},
        {"item_id": "SYS-099", "at": "bad", "action": "create"},
    ]
    history = activity_history(
        Project(name="P", key="SYS"), events, datetime(2026, 11, 11, 12, tzinfo=UTC)
    )
    assert len(history["days"]) == 30
    assert history["days"][-1] == {"date": "2026-11-11", "created": 1, "completed": 1}
    assert history["days"][-2]["completed"] == 0
    assert history["timezone"] == "UTC"
    assert history["observed_since"] == "2026-11-10T14:00:00+00:00"


def test_history_does_not_invent_events_for_external_files(service: BacklogService) -> None:
    assert all(
        day["created"] == day["completed"] == 0 for day in service.state()["history"]["days"]
    )
    item, _ = service.add(CreateItem(title="Observed"))
    service.update(item.id, UpdateItem(expected_version=1, status="done"))
    history = service.state()["history"]
    assert history["days"][-1]["created"] == 1
    assert history["days"][-1]["completed"] == 1


@pytest.mark.security
def test_document_preview_source_and_pdf_share_the_canonical_markdown(
    service: BacklogService,
) -> None:
    service.add(CreateItem(title="Autenticação — revisão", description="Descrição"))
    service.add(
        CreateItem(
            title='<img src="file:///etc/passwd" onerror="alert(1)"> [link](https://example.invalid)'
        )
    )
    before = service.snapshot()
    client, _ = client_for(service, read_only=True)
    source = client.get("/api/v1/document")
    assert source.json()["markdown"] == exports.markdown(
        before.backlog, events=service.repository.events()
    )
    assert source.json()["revision"] == before.revision
    preview = client.get("/document")
    assert preview.status_code == 200
    assert '<table class="report-table' in preview.text
    assert preview.text.count('<figure class="report-chart">') == 4
    assert "<img" not in preview.text
    assert '<a href="https://example.invalid' not in preview.text
    assert "frame-ancestors 'self'" in preview.headers["content-security-policy"]
    standalone = client.get("/document?standalone=true")
    assert "print-document" in standalone.text and "/static/report.js" in standalone.text
    assert "/static/report.js" not in preview.text
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
    response = client.get("/api/v1/export/pdf")
    assert response.status_code == 200, (
        response.text if not response.content.startswith(b"%PDF") else ""
    )
    assert response.headers["content-type"] == "application/pdf"
    pdf = PdfReader(io.BytesIO(response.content))
    text = " ".join(page.extract_text() for page in pdf.pages)
    assert "Autenticação" in text
    assert "SYS-001" in text and "SYS-002" in text
    assert before.raw == service.snapshot().raw


@pytest.mark.security
def test_pdf_forbids_resource_fetching() -> None:
    for url in ("https://example.invalid/x.png", "file:///etc/passwd", "data:text/plain,hello"):
        with pytest.raises(ValueError):
            deny_resource(url)


def test_pdf_has_a_hard_timeout_and_releases_its_slot(
    service: BacklogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("pdf", 30)

    monkeypatch.setattr(documents.subprocess, "run", timeout)
    for _ in range(2):
        with pytest.raises(PDFUnavailable, match="30 segundos"):
            documents.pdf(service.snapshot().backlog)


def test_pdf_cli_writes_a_real_file(service: BacklogService, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from backloger.cli import app

    service.add(CreateItem(title="Relatório PDF"))
    path = tmp_path / "BACKLOG.pdf"
    result = CliRunner().invoke(
        app, ["--project", str(service.repository.root), "export", "pdf", "--output", str(path)]
    )
    assert result.exit_code == 0, result.output
    assert path.read_bytes().startswith(b"%PDF-")


@pytest.mark.unit
def test_burndown_preserves_unknown_dates_and_builds_an_ideal_from_a_real_baseline() -> None:
    backlog = Backlog(
        project=Project(name="P", key="SYS"),
        iterations=[
            Iteration(id="I1", name="Sprint 1", start_date="2026-11-09", due_date="2026-11-13")
        ],
        work_items=[
            WorkItem(id="SYS-001", title="One", iteration_id="I1"),
            WorkItem(id="SYS-002", title="Two", iteration_id="I1"),
            WorkItem(id="SYS-003", title="Other"),
        ],
    )
    events = [
        {
            "at": "2026-11-09T12:00:00Z",
            "burn": {
                "remaining": 4,
                "total": 4,
                "iterations": {"I1": {"remaining": 3, "total": 3}},
            },
        },
        {
            "at": "2026-11-10T12:00:00Z",
            "burn": {
                "remaining": 3,
                "total": 4,
                "iterations": {"I1": {"remaining": 2, "total": 3}},
            },
        },
    ]
    data = burndown_history(backlog, events, datetime(2026, 11, 11, 12, tzinfo=UTC))
    project, iteration = data["scopes"]
    assert project["points"][-4]["remaining"] is None
    assert [point["remaining"] for point in project["points"][-3:]] == [4, 3, 3]
    assert all(point["ideal"] is None for point in project["points"])
    assert iteration["id"] == "iteration:I1"
    assert iteration["baseline_date"] == "2026-11-09"
    assert iteration["points"][-1]["remaining"] == 2
    assert iteration["points"][-1]["ideal"] == 1.5


def test_writes_record_burndown_checkpoints_without_backfilling_the_past(
    service: BacklogService,
) -> None:
    item, _ = service.add(CreateItem(title="Scope"))
    service.update(item.id, UpdateItem(expected_version=1, status="done"))
    events = service.repository.events()
    assert sorted(event["burn"]["remaining"] for event in events) == [0, 1]
    points = service.state()["burndown"]["scopes"][0]["points"]
    assert points[-1]["remaining"] == 0
    assert all(point["remaining"] is None for point in points[:-1])
