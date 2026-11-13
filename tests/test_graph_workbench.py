import io
import random
import xml.etree.ElementTree as ET

import networkx as nx
import pytest
from pydantic import ValidationError
from pypdf import PdfReader
from test_api_cli import client_for

from backloger.errors import BacklogError
from backloger.graph import analyze, dependency_graph
from backloger.graph_export import GraphDocument, GraphExport
from backloger.models import Backlog, Project, WorkItem
from backloger.service import BacklogService, CreateItem


def item(
    number: int, hours: float | None, parents: tuple[int, ...] = (), **fields: object
) -> WorkItem:
    data = {
        "id": f"SYS-{number:03}",
        "title": f"Atividade {number}",
        "dependencies": [{"target_id": f"SYS-{parent:03}"} for parent in parents],
        **fields,
    }
    if hours is not None:
        data["estimate"] = {"unit": "hours", "value": hours}
    return WorkItem.model_validate(data)


@pytest.mark.unit
def test_cpm_highlights_parallel_critical_routes_and_reports_slack() -> None:
    backlog = Backlog(
        project=Project(name="Rotas", key="SYS"),
        work_items=[
            item(1, 2),
            item(2, 3, (1,)),
            item(3, 3, (1,)),
            item(4, 4, (2, 3)),
            item(5, 1),
        ],
    )
    result = analyze(backlog)["critical_paths"]["remaining"]
    assert result["method"] == "estimate" and result["duration"] == 9
    assert result["path"] == ["SYS-001", "SYS-002", "SYS-004"]
    assert result["nodes"] == ["SYS-001", "SYS-002", "SYS-003", "SYS-004"]
    assert len(result["edges"]) == 4
    assert result["timings"]["SYS-005"]["slack"] == 8
    assert result["timings"]["SYS-004"]["start"] == 5


@pytest.mark.unit
def test_remaining_schedule_ignores_closed_estimates_and_handles_zero_and_fractional_work() -> None:
    backlog = Backlog(
        project=Project(name="Restante", key="SYS"),
        work_items=[
            item(1, None, status="done"),
            item(2, 0.1, (1,)),
            item(3, 0.2, (2,)),
            item(4, None, status="cancelled"),
        ],
    )
    result = analyze(backlog)
    assert result["critical_paths"]["project"]["method"] == "structure"
    remaining = result["critical_paths"]["remaining"]
    assert remaining["duration"] == pytest.approx(0.3)
    assert remaining["path"] == ["SYS-002", "SYS-003"]
    assert all(row["slack"] == 0 for row in remaining["timings"].values())
    backlog.work_items = [item(1, 0), item(2, 0, (1,))]
    zero = analyze(backlog)["critical_paths"]["remaining"]
    assert zero["duration"] == 0 and zero["path"] == ["SYS-001", "SYS-002"]
    for activity in backlog.work_items:
        activity.status = "done"
    assert analyze(backlog)["critical_paths"]["remaining"]["method"] == "empty"


@pytest.mark.unit
def test_missing_or_incompatible_estimates_produce_an_explicit_structural_chain() -> None:
    backlog = Backlog(
        project=Project(name="Sem duração", key="SYS"),
        work_items=[
            item(1, None),
            item(2, 3, (1,)),
            item(3, None, (2,)),
        ],
    )
    schedule = analyze(backlog)["critical_paths"]["remaining"]
    assert schedule["method"] == "structure" and schedule["duration"] is None
    assert schedule["path"] == ["SYS-001", "SYS-002", "SYS-003"]
    assert schedule["length"] == 3
    assert schedule["missing_estimates"] == ["SYS-001", "SYS-003"]
    backlog.work_items[0] = item(1, None, estimate={"unit": "points", "value": 5})
    schedule = analyze(backlog)["critical_paths"]["remaining"]
    assert schedule["units"] == ["hours", "points"]
    assert "unidades diferentes" in schedule["reason"]


@pytest.mark.unit
def test_bitset_analysis_matches_networkx_and_truncated_blockers_keep_exact_counts() -> None:
    randomizer = random.Random(42)
    activities = []
    for number in range(1, 75):
        parents = tuple(
            parent for parent in range(max(1, number - 10), number) if randomizer.random() < 0.5
        )
        activities.append(item(number, 1, parents, status="done" if number % 7 == 0 else "todo"))
    backlog = Backlog(project=Project(name="DAG", key="SYS"), work_items=activities)
    graph = dependency_graph(backlog)
    actual = analyze(backlog, "SYS-050", blocker_limit=3)
    unfinished = {activity.id for activity in activities if activity.status != "done"}
    assert actual["selected"]["prerequisites"] == sorted(nx.ancestors(graph, "SYS-050"))
    assert actual["selected"]["affected"] == sorted(nx.descendants(graph, "SYS-050"))
    for key in unfinished:
        expected = sorted(nx.ancestors(graph, key) & unfinished)
        assert actual["blockers"][key] == expected[:3]
        assert actual["blocker_counts"][key] == len(expected)
    assert actual["blockers_truncated"] is True
    assert actual["ready"] == sorted(key for key in unfinished if not actual["blocker_counts"][key])


@pytest.mark.integration
@pytest.mark.security
def test_graph_exports_use_canonical_text_and_work_readonly_without_writes(
    service: BacklogService,
) -> None:
    first, _ = service.add(
        CreateItem(
            title="Autenticação <script>alert(1)</script>", estimate={"unit": "hours", "value": 2}
        )
    )
    service.add(
        CreateItem(
            title="Revisão de segurança",
            estimate={"unit": "hours", "value": 3},
            dependencies=[{"target_id": first.id}],
        )
    )
    before = service.snapshot()
    client, headers = client_for(service, read_only=True)
    payload = {
        "positions": {"SYS-001": {"x": 120, "y": 90}, "SYS-002": {"x": 420, "y": 90}},
        "scope": "remaining",
        "highlight_critical": True,
    }
    response = client.post("/api/v1/graph/export/svg", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    root = ET.fromstring(response.content)
    assert not root.findall(".//{*}script") and not root.findall(".//{*}image")
    assert "Autenticação" in "".join(root.itertext())
    response = client.post("/api/v1/graph/export/pdf", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    pdf = PdfReader(io.BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Dependências" in text and "SYS-001" in text and "Revisão de segurança" in text
    assert "Caminho crítico" in text
    assert "5 horas" in text
    assert before.raw == service.snapshot().raw
    assert client.post("/api/v1/graph/export/svg", json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/graph/export/svg", json=payload, headers={**headers, "If-Match": '"stale"'}
        ).status_code
        == 409
    )
    invalid = {**payload, "positions": {"SYS-999": {"x": 1, "y": 2}}}
    assert client.post("/api/v1/graph/export/svg", json=invalid, headers=headers).status_code == 422


@pytest.mark.unit
@pytest.mark.security
def test_graph_geometry_is_bounded_and_extreme_pdf_views_are_rejected() -> None:
    for value in [float("inf"), float("nan"), 10_000_001]:
        with pytest.raises(ValidationError):
            GraphExport.model_validate({"positions": {"SYS-001": {"x": value, "y": 0}}})
    backlog = Backlog(
        project=Project(name="Distante", key="SYS"), work_items=[item(1, 1), item(2, 2)]
    )
    request = GraphExport.model_validate(
        {
            "positions": {
                "SYS-001": {"x": 0, "y": 0},
                "SYS-002": {"x": 1_000_000, "y": 1_000_000},
            }
        }
    )
    with pytest.raises(BacklogError, match="36 páginas"):
        GraphDocument(backlog, request).pdf()


@pytest.mark.integration
def test_large_graph_pdf_has_overview_readable_tiles_and_full_inventory() -> None:
    backlog = Backlog(
        project=Project(name="Projeto grande", key="SYS"),
        work_items=[item(1, 2), item(2, 3, (1,)), item(3, 4, (2,))],
    )
    request = GraphExport.model_validate(
        {
            "positions": {
                "SYS-002": {"x": 500, "y": 0},
                "SYS-003": {"x": 1800, "y": 0},
            },
            "highlight_critical": True,
        }
    )
    content = GraphDocument(backlog, request).pdf()
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() for page in reader.pages]
    assert len(pages) == 4, pages
    assert "Panorama" in pages[0] and "9 horas" in pages[0]
    assert "Região 1, 1" in pages[1] and "Atividade 2" in pages[1]
    assert "Região 1, 2" in pages[2] and "Atividade 3" in pages[2]
    assert "Atividades da visão exportada" in pages[3]
    assert "SYS-001 (fora da visão)" in pages[3]
    assert "SYS-002" in pages[3] and "Atividade 3" in pages[3]
