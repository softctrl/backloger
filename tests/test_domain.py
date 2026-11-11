import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from backloger.errors import BacklogError
from backloger.graph import analyze
from backloger.models import Backlog, Estimate, Project, WorkItem
from backloger.schema import generate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": "2.0.0"},
        {"id": "../SYS-001"},
        {"title": ""},
        {"version": 0},
        {"version": True},
        {"created_at": "2026-11-11T09:00:00"},
        {"estimate": {"unit": "hours", "value": -1}},
        {"dependencies": [{"target_id": "SYS-001", "relation": "blocked_by"}]},
        {"acceptance_criteria": [{"id": "AC-1", "text": "a"}, {"id": "AC-1", "text": "b"}]},
    ],
)
def test_reject_invalid_contract(patch: dict) -> None:
    with pytest.raises(ValidationError):
        WorkItem.model_validate({"id": "SYS-001", "title": "Tarefa", **patch})


def test_graph_direction_transitive_blockers_and_critical_path() -> None:
    backlog = Backlog.model_validate(
        {
            "project": {"name": "Teste", "key": "SYS"},
            "work_items": [
                {"id": "SYS-001", "title": "A", "estimate": {"unit": "hours", "value": 2}},
                {
                    "id": "SYS-002",
                    "title": "B",
                    "estimate": {"unit": "hours", "value": 3},
                    "dependencies": [{"target_id": "SYS-001"}],
                },
                {
                    "id": "SYS-003",
                    "title": "C",
                    "estimate": {"unit": "hours", "value": 7},
                    "dependencies": [{"target_id": "SYS-002"}],
                },
                {"id": "SYS-004", "title": "Livre", "estimate": {"unit": "hours", "value": 1}},
            ],
        }
    )
    result = analyze(backlog, "SYS-002")
    assert result["edges"] == [
        {"source": "SYS-001", "target": "SYS-002"},
        {"source": "SYS-002", "target": "SYS-003"},
    ]
    assert result["blockers"]["SYS-003"] == ["SYS-001", "SYS-002"]
    assert result["selected"]["affected"] == ["SYS-003"]
    assert result["isolated"] == ["SYS-004"]
    assert result["critical_path"] == {
        "path": ["SYS-001", "SYS-002", "SYS-003"],
        "duration": 12,
        "unit": "hours",
    }
    backlog.work_items[0].status = "done"
    assert analyze(backlog)["blockers"]["SYS-003"] == ["SYS-002"]
    backlog.work_items[0].estimate = Estimate(unit="points", value=2)
    assert analyze(backlog)["critical_path"]["duration"] is None


@pytest.mark.parametrize(
    "items",
    [
        [{"id": "SYS-001", "title": "a", "dependencies": [{"target_id": "SYS-099"}]}],
        [{"id": "SYS-001", "title": "a", "status": "unknown"}],
        [{"id": "SYS-001", "title": "a", "milestone_id": "missing"}],
        [{"id": "SYS-001", "title": "a"}, {"id": "SYS-001", "title": "dup"}],
        [
            {"id": "SYS-001", "title": "a", "dependencies": [{"target_id": "SYS-002"}]},
            {"id": "SYS-002", "title": "b", "dependencies": [{"target_id": "SYS-001"}]},
        ],
    ],
)
def test_reject_invalid_graph(items: list) -> None:
    with pytest.raises(BacklogError):
        analyze(
            Backlog.model_validate({"project": {"name": "P", "key": "SYS"}, "work_items": items})
        )


def test_schema_matches_models_and_checked_in_files(tmp_path: Path) -> None:
    generate(tmp_path)
    for path in tmp_path.glob("*.json"):
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema == json.loads((Path("schemas/1.0.0") / path.name).read_text())
    data = WorkItem(id="SYS-001", title="Teste").model_dump(mode="json")
    Draft202012Validator(json.loads((tmp_path / "work-item.schema.json").read_text())).validate(
        data
    )
    assert Project(name="P", key="SYS").statuses[0].category == "pending"
