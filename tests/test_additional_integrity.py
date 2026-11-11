import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from backloger import transactions
from backloger.cli import app
from backloger.errors import BacklogError
from backloger.exports import csv_report
from backloger.filesystem import digest, encode
from backloger.service import BacklogService, CreateItem, UpdateItem

pytestmark = [pytest.mark.integration, pytest.mark.security]


def test_export_cannot_overwrite_canonical_data(service: BacklogService) -> None:
    snapshot = service.snapshot()
    destination = service.repository.root / (
        "backlog.json" if snapshot.storage == "single" else ".backloger/project.json"
    )
    before = destination.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(service.repository.root),
            "export",
            "markdown",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 1
    assert destination.read_bytes() == before


def test_add_file_fields_and_invalid_top_level(service: BacklogService, tmp_path: Path) -> None:
    path = tmp_path / "fields.json"
    path.write_text(json.dumps({"priority": "critical", "owner": "my-team", "type": "feature"}))
    runner = CliRunner()
    prefix = ["--project", str(service.repository.root), "--json"]
    result = runner.invoke(app, [*prefix, "add", "--title", "JSON fields", "--file", str(path)])
    assert result.exit_code == 0, result.output
    item = json.loads(result.stdout)["item"]
    assert (item["priority"], item["owner"], item["type"]) == ("critical", "my-team", "feature")
    path.write_text("[]")
    assert runner.invoke(app, [*prefix, "update", item["id"], "--file", str(path)]).exit_code == 1


def test_recovery_validates_journal_payload(
    service: BacklogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _ = service.add(CreateItem(title="Safe"))

    def fail(*args: object) -> None:
        raise OSError("Crash")

    with monkeypatch.context() as patch:
        patch.setattr(transactions, "_finalize", fail)
        with pytest.raises(OSError):
            service.update(item.id, UpdateItem(expected_version=1, title="Committed"))
    journal = transactions.pending(service.repository.root)[0]
    record = json.loads(journal.read_text())
    content = json.loads(base64.b64decode(record["after"]))
    if service.snapshot().storage == "single":
        content["work_items"][0]["status"] = "invalid"
    else:
        content["status"] = "invalid"
    after = encode(content)
    record.update(after=base64.b64encode(after).decode(), after_hash=digest(after))
    # Keep the actual target as the legitimate before hash so validation, rather
    # than a hash mismatch, must reject this corrupted recovery intent.
    current = service.repository.root / record["target"]
    record["before_hash"] = digest(current.read_bytes())
    journal.write_bytes(encode(record))
    with pytest.raises((BacklogError, ValidationError)):
        service.repository.recover()
    assert service.snapshot().backlog.work_items[0].title == "Committed"
    assert journal.exists()


def test_csv_formula_escaping(service: BacklogService) -> None:
    service.add(CreateItem(title='=HYPERLINK("https://example.invalid")', owner="@SUM(1)"))
    report = csv_report(service.snapshot().backlog)
    assert "'=HYPERLINK" in report
    assert "'@SUM(1)" in report


def test_corrupt_backup_returns_cli_error_without_changing_data(service: BacklogService) -> None:
    item, _ = service.add(CreateItem(title="Before"))
    service.update(item.id, UpdateItem(expected_version=1, title="After"))
    backup = next((service.repository.root / ".backloger/.runtime/backups").glob("*.json"))
    backup.write_text("{}")
    result = CliRunner().invoke(
        app,
        [
            "--project",
            str(service.repository.root),
            "restore",
            item.id,
            "--backup",
            backup.stem,
            "--version",
            "2",
        ],
    )
    assert result.exit_code == 1
    assert service.snapshot().backlog.work_items[0].title == "After"
