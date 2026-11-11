import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backloger.graph import analyze
from backloger.repository import Repository

pytestmark = pytest.mark.integration
SCRIPT = Path("skills/backloger-adoption/scripts/stage_backlog.py").resolve()
PROPOSAL = Path("examples/migration/proposal.json")


def invoke(proposal: Path, output: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(proposal),
            "--output",
            str(output),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.mark.parametrize("storage", ["split", "single"])
def test_adoption_keeps_identity_content_provenance_and_original_files(
    tmp_path: Path, storage: str
) -> None:
    sources = [
        Path("examples/migration/legacy-backlog.md"),
        Path("examples/migration/legacy-status.csv"),
    ]
    before = {path: path.read_bytes() for path in [PROPOSAL, *sources]}
    output = tmp_path / "candidate"
    result = invoke(
        PROPOSAL,
        output,
        "--storage",
        storage,
        "--expected-count",
        "3",
        "--source",
        str(sources[0]),
        "--source",
        str(sources[1]),
    )
    assert result.returncode == 0, result.stderr
    snapshot = Repository(output, read_only=True).snapshot()
    assert snapshot.storage == storage
    assert len(snapshot.backlog.work_items) == 3
    items = {item.id: item for item in snapshot.backlog.work_items}
    assert items["MIG-002"].history[0].at.isoformat() == "2026-11-10T14:00:00-03:00"
    assert [criterion.done for criterion in items["MIG-002"].acceptance_criteria] == [True, False]
    assert items["MIG-003"].owner is None and items["MIG-003"].due_date is None
    metadata = items["MIG-003"].extensions["backloger.migration"]
    assert isinstance(metadata, dict)
    assert metadata["timestamp_basis"] == {"created_at": "import_time", "updated_at": "import_time"}
    assert items["MIG-003"].created_at.isoformat() == metadata["imported_at"]
    with sources[1].open(newline="") as stream:
        original_ids = {row["source_id"] for row in csv.DictReader(stream)}
    mapping = json.loads((output / "id-map.json").read_text())
    assert {row["original_id"] for row in mapping} == original_ids
    analysis = analyze(snapshot.backlog)
    assert {(edge["source"], edge["target"]) for edge in analysis["edges"]} == {
        ("MIG-001", "MIG-002"),
        ("MIG-001", "MIG-003"),
    }
    assert "credenciais inválidas verificadas" in (output / "BACKLOG.md").read_text()
    manifest = json.loads((output / "migration-manifest.json").read_text())
    assert manifest["revision"] == snapshot.revision
    assert manifest["by_status"] == {"done": 1, "in_progress": 1, "todo": 1}
    assert manifest["timestamp_basis_import_time"] == ["MIG-003"]
    assert manifest["proposal_sha256"] == hashlib.sha256(before[PROPOSAL]).hexdigest()
    assert not (output / ".backloger/.runtime").exists()
    assert all(path.read_bytes() == content for path, content in before.items())
    saved = {
        str(path.relative_to(output)): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    repeated = invoke(PROPOSAL, output)
    assert repeated.returncode == 1 and "destino deve ser novo" in repeated.stderr
    assert saved == {
        str(path.relative_to(output)): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("failure", ["reference", "cycle", "count", "partial_date", "metadata"])
def test_failed_adoption_does_not_publish_a_candidate(tmp_path: Path, failure: str) -> None:
    data = json.loads(PROPOSAL.read_text())
    if failure == "reference":
        data["work_items"][1]["dependencies"][0]["target_id"] = "MIG-999"
    elif failure == "cycle":
        data["work_items"][0]["dependencies"] = [{"target_id": "MIG-002", "relation": "blocked_by"}]
    elif failure == "partial_date":
        del data["work_items"][0]["created_at"]
    elif failure == "metadata":
        data["work_items"][0]["extensions"]["backloger.migration"] = "invalid"
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps(data))
    output = tmp_path / "candidate"
    result = invoke(proposal, output, "--expected-count", "99" if failure == "count" else "3")
    assert result.returncode == 1 and "Erro de migração" in result.stderr
    assert result.stdout == ""
    assert not output.exists()
    assert not list(tmp_path.glob(".backloger-candidate-*"))
    assert json.loads(proposal.read_text()) == data
