import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_api_cli import client_for

from backloger.errors import ConflictError
from backloger.service import BacklogService, CreateItem, UpdateItem

pytestmark = pytest.mark.integration


def test_card_notes_changes_and_conflicts_are_preserved(service: BacklogService) -> None:
    item, snapshot = service.add(CreateItem(title="History", history_note="Contexto inicial"))
    assert [entry.kind for entry in item.history] == ["created", "comment"]
    changed, saved = service.update(
        item.id,
        UpdateItem(expected_version=1, status="review", history_note="Revisão iniciada"),
        snapshot.revision,
    )
    assert [entry.kind for entry in changed.history] == ["created", "comment", "updated", "comment"]
    assert changed.history[-1].text == "Revisão iniciada"
    assert changed.history[-2].changed_fields == ["status"]
    with pytest.raises(ConflictError):
        service.update(
            item.id, UpdateItem(expected_version=1, history_note="Stale"), snapshot.revision
        )
    assert service.snapshot().raw == saved.raw
    client, headers = client_for(service)
    response = client.patch(
        f"/api/v1/items/{item.id}",
        json={"expected_version": 2, "history_note": "<img src=x onerror=alert(1)>"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["item"]["history"][-1]["text"].startswith("<img")
    report = client.get("/document").text
    assert "<img" not in report and "Histórico das atividades" in report


def test_restore_keeps_notes_that_were_added_after_the_backup(service: BacklogService) -> None:
    item, _ = service.add(CreateItem(title="Before", history_note="Keep this"))
    service.update(
        item.id, UpdateItem(expected_version=1, title="After", history_note="Also keep this")
    )
    backup = next((service.repository.root / ".backloger/.runtime/backups").glob("*.json"))
    restored, _ = service.restore(item.id, backup.stem, 2)
    assert restored.title == "Before"
    assert [e.text for e in restored.history if e.kind == "comment"] == [
        "Keep this",
        "Also keep this",
    ]
    assert restored.history[-1].kind == "restored"


def run_action(tmp_path: Path, formats: str, **extra: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "project"
    if not source.exists():
        shutil.copytree("examples/demo", source)
    env = {
        **os.environ,
        "GITHUB_WORKSPACE": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "BACKLOGER_INPUT_PROJECT": "project",
        "BACKLOGER_INPUT_FORMATS": formats,
        "BACKLOGER_INPUT_OUTPUT": "reports",
        **extra,
    }
    return subprocess.run(
        [sys.executable, "scripts/action_reports.py"],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )


def test_action_generates_only_selected_formats_and_does_not_modify_the_backlog(
    tmp_path: Path,
) -> None:
    result = run_action(tmp_path, "markdown,html,pdf")
    assert result.returncode == 0, result.stderr
    directory = tmp_path / "reports"
    assert {p.name for p in directory.iterdir()} == {
        "BACKLOG.md",
        "BACKLOG.html",
        "BACKLOG.pdf",
        "manifest.json",
    }
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    assert (directory / "BACKLOG.pdf").read_bytes().startswith(b"%PDF-")
    for source in Path("examples/demo").rglob("*.json"):
        assert (
            source.read_bytes()
            == (tmp_path / "project" / source.relative_to("examples/demo")).read_bytes()
        )
    assert not (tmp_path / "project/.backloger/.runtime").exists()


def test_action_defaults_to_markdown_and_keeps_html_pdf_optional(tmp_path: Path) -> None:
    assert run_action(tmp_path, "markdown").returncode == 0
    assert {p.name for p in (tmp_path / "reports").iterdir()} == {"BACKLOG.md", "manifest.json"}


@pytest.mark.security
@pytest.mark.parametrize(
    "extra",
    [
        {"BACKLOGER_INPUT_FORMATS": "markdown;touch injected"},
        {"BACKLOGER_INPUT_PROJECT": "../outside"},
        {"BACKLOGER_INPUT_OUTPUT": ".backloger"},
        {"BACKLOGER_INPUT_OUTPUT": "reports\ninjected=x"},
    ],
)
def test_action_rejects_unsafe_inputs(tmp_path: Path, extra: dict[str, str]) -> None:
    assert run_action(tmp_path, "markdown", **extra).returncode != 0
    assert not (tmp_path / "injected").exists()


def test_composite_action_has_pinned_dependencies_and_never_uploads_the_workspace() -> None:
    action = yaml.safe_load(Path("action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    steps = action["runs"]["steps"]
    for step in steps:
        if "uses" in step:
            assert len(step["uses"].split("@")[-1]) == 40
        if "run" in step:
            assert "${{ inputs." not in step["run"]
    upload = steps[-1]["with"]["path"]
    assert "outputs.directory" not in upload
    assert all(f"outputs.{name}" in upload for name in ("markdown", "html", "pdf", "manifest"))
