from datetime import date

import pytest
from pydantic import ValidationError
from test_api_cli import client_for

from backloger.errors import ReadOnlyError
from backloger.graph import analyze
from backloger.models import Backlog, Iteration, Project, Status, WorkItem
from backloger.service import BacklogService, CreateItem, IterationRequest
from backloger.sprints import overview


@pytest.mark.unit
def test_sprint_summary_respects_custom_states_cancelled_and_external_blockers() -> None:
    project = Project(
        name="Sprints",
        key="SYS",
        statuses=[
            Status(id="waiting", name="Fila", category="pending"),
            Status(id="testing", name="Homologação", category="active"),
            Status(id="released", name="Publicado", category="done"),
            Status(id="discarded", name="Descartado", category="cancelled"),
        ],
    )
    backlog = Backlog(
        project=project,
        iterations=[
            Iteration(id="S1", name="Ciclo atual", start_date="2026-11-01", due_date="2026-11-20"),
            Iteration(id="S2", name="Planejada", start_date="2026-12-01", due_date="2026-12-14"),
            Iteration(id="S3", name="Anterior", due_date="2026-10-31"),
            Iteration(id="S4", name="Sem datas"),
        ],
        work_items=[
            WorkItem(id="SYS-001", title="Pré-requisito fora da sprint", status="waiting"),
            WorkItem(
                id="SYS-002",
                title="Pendente",
                status="waiting",
                iteration_id="S1",
                estimate={"unit": "hours", "value": 3},
                dependencies=[{"target_id": "SYS-001"}],
                due_date="2026-11-10",
            ),
            WorkItem(
                id="SYS-003",
                title="Em testes",
                status="testing",
                iteration_id="S1",
                estimate={"unit": "points", "value": 5},
            ),
            WorkItem(id="SYS-004", title="Entregue", status="released", iteration_id="S1"),
            WorkItem(
                id="SYS-005",
                title="Cancelado",
                status="discarded",
                iteration_id="S1",
                due_date="2026-10-01",
            ),
        ],
    )
    result = overview(backlog, analyze(backlog), date(2026, 11, 13))
    current = result["iterations"][0]
    assert current["total"] == 4 and current["remaining"] == 2
    assert current["pending"] == current["active"] == current["done"] == current["cancelled"] == 1
    assert current["progress"] == 33.3
    assert current["blocked"] == 1 and current["overdue"] == 1
    assert current["open_estimates"] == {"hours": 3, "points": 5}
    assert [s["phase"] for s in result["iterations"]] == ["current", "upcoming", "past", "undated"]
    assert result["unassigned"]["total"] == 1
    assert result["iterations"][1]["progress"] is None
    backlog.work_items = [backlog.work_items[-1]]
    assert (
        overview(backlog, analyze(backlog), date(2026, 11, 13))["iterations"][0]["progress"] is None
    )


@pytest.mark.integration
def test_create_update_and_assign_sprint_preserves_data_and_revisions(
    service: BacklogService,
) -> None:
    first, saved = service.save_iteration(
        IterationRequest(name="Sprint inicial", start_date="2026-11-01", due_date="2026-11-14")
    )
    assert first.id == "SPR-001"
    second, _ = service.save_iteration(IterationRequest(name="Próximo ciclo"), saved.revision)
    assert second.id == "SPR-002"
    item, _ = service.add(CreateItem(title="Entrega", iteration_id=first.id))
    snapshot = service.snapshot()
    model = snapshot.backlog.model_copy(deep=True)
    model.iterations[0] = Iteration.model_validate(
        {**first.model_dump(mode="json"), "external_field": {"preserve": True}}
    )
    service.repository.commit(
        snapshot, model, item_id=None, action="external_fixture", collection="iterations"
    )
    before = service.snapshot()
    client, headers = client_for(service)
    updated = client.put(
        f"/api/v1/iterations/{first.id}",
        json={"name": "Sprint revisada", "start_date": "2026-11-02", "due_date": "2026-11-15"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["iteration"]["external_field"] == {"preserve": True}
    assert service.snapshot().backlog.work_items[0] == before.backlog.work_items[0]
    assert service.snapshot().backlog.views == before.backlog.views
    assert (
        client.put(
            f"/api/v1/iterations/{first.id}", json={"name": "Sobrescrever"}, headers=headers
        ).status_code
        == 409
    )
    state = client.get("/api/v1/state").json()
    assert state["sprint_overview"]["iterations"][0]["remaining"] == 1
    moved = client.patch(
        f"/api/v1/items/{item.id}",
        json={"expected_version": item.version, "status": "in_progress"},
        headers={**headers, "If-Match": f'"{state["revision"]}"'},
    )
    assert moved.status_code == 200
    assert client.get("/api/v1/state").json()["sprint_overview"]["iterations"][0]["active"] == 1
    assert any(event["action"] == "create_iteration" for event in service.repository.events())


@pytest.mark.integration
@pytest.mark.security
def test_sprint_api_validates_dates_csrf_readonly_and_stale_snapshots(
    service: BacklogService,
) -> None:
    client, headers = client_for(service)
    before = service.snapshot()
    assert client.post("/api/v1/iterations", json={"name": "Sem token"}).status_code == 403
    for payload in [
        {"name": "   "},
        {"name": "Inválida", "start_date": "2026-11-20", "due_date": "2026-11-01"},
        {"name": "Campos extras", "id": "BAD-ID"},
    ]:
        assert client.post("/api/v1/iterations", json=payload, headers=headers).status_code == 422
    assert service.snapshot().raw == before.raw
    response = client.post("/api/v1/iterations", json={"name": "Sprint 1"}, headers=headers)
    assert response.status_code == 201
    assert (
        client.post("/api/v1/iterations", json={"name": "Sprint 2"}, headers=headers).status_code
        == 409
    )
    readonly, ro_headers = client_for(service, read_only=True)
    assert (
        readonly.post(
            "/api/v1/iterations", json={"name": "Proibida"}, headers=ro_headers
        ).status_code
        == 403
    )
    assert (
        readonly.put(
            "/api/v1/iterations/SPR-001", json={"name": "Proibida"}, headers=ro_headers
        ).status_code
        == 403
    )
    with pytest.raises(ReadOnlyError):
        BacklogService(
            type(service.repository)(service.repository.root, read_only=True)
        ).save_iteration(IterationRequest(name="Proibida"))
    fresh = service.snapshot()
    assert (
        client.put(
            "/api/v1/iterations/UNKNOWN",
            json={"name": "Ausente"},
            headers={**headers, "If-Match": f'"{fresh.revision}"'},
        ).status_code
        == 404
    )


@pytest.mark.unit
def test_iteration_period_rejects_inverted_dates_but_allows_same_day() -> None:
    with pytest.raises(ValidationError, match="fim da sprint"):
        Iteration(id="I1", name="Inválida", start_date="2026-11-20", due_date="2026-11-19")
    Iteration(id="I1", name="Um dia", start_date="2026-11-20", due_date="2026-11-20")
