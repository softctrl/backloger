import io
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from html.parser import HTMLParser

import pytest

from backloger import documents, exports
from backloger.models import Backlog, Project
from backloger.report_charts import Chart, Series, chart_markdown, render_chart
from backloger.report_data import ReportData

pytestmark = pytest.mark.unit
AT = datetime(2026, 11, 11, 18, tzinfo=UTC)


@pytest.fixture
def management_backlog() -> Backlog:
    return Backlog.model_validate(
        {
            "project": {
                "name": "Modernização da API",
                "key": "SYS",
                "statuses": [
                    {"id": "planned", "name": "Planejado", "category": "pending"},
                    {"id": "doing", "name": "Em validação", "category": "active", "wip_limit": 1},
                    {"id": "finished", "name": "Entregue", "category": "done"},
                    {"id": "dropped", "name": "Descartado", "category": "cancelled"},
                ],
            },
            "milestones": [{"id": "M1", "name": "Entrega principal", "due_date": "2026-11-10"}],
            "iterations": [
                {
                    "id": "I1",
                    "name": "Sprint de entrega",
                    "start_date": "2026-11-09",
                    "due_date": "2026-11-13",
                }
            ],
            "work_items": [
                {
                    "id": "SYS-001",
                    "title": "Contrato da API",
                    "status": "finished",
                    "description": "Publicar o contrato validado.",
                    "owner": "Ana",
                    "due_date": "2026-11-05",
                    "milestone_id": "M1",
                },
                {
                    "id": "SYS-002",
                    "title": "Autenticação",
                    "status": "doing",
                    "priority": "critical",
                    "description": "Validar as credenciais da API.\n\n"
                    "Registrar tentativas e expiração de sessão.",
                    "owner": "Ana",
                    "due_date": "2026-11-10",
                    "component": "Segurança",
                    "estimate": {"unit": "hours", "value": 8},
                    "milestone_id": "M1",
                    "iteration_id": "I1",
                    "labels": ["backend", "segurança"],
                    "version": 2,
                    "created_at": "2026-11-09T09:00:00-03:00",
                    "updated_at": "2026-11-10T10:00:00-03:00",
                    "dependencies": [{"target_id": "SYS-003", "relation": "blocked_by"}],
                    "acceptance_criteria": [
                        {"id": "AC-1", "text": "Rejeitar credenciais inválidas", "done": True},
                        {"id": "AC-2", "text": "Expirar a sessão", "done": False},
                    ],
                    "history": [
                        {
                            "id": "H-1",
                            "at": "2026-11-10T10:00:00Z",
                            "kind": "comment",
                            "version": 2,
                            "text": "Aguardando provisionamento da infraestrutura.",
                        }
                    ],
                },
                {
                    "id": "SYS-003",
                    "title": "Infraestrutura",
                    "status": "planned",
                    "priority": "high",
                    "description": "Provisionar ambiente de validação.",
                    "owner": "Operações",
                    "due_date": "2026-11-14",
                    "iteration_id": "I1",
                },
                {
                    "id": "SYS-004",
                    "title": "Solução antiga",
                    "status": "dropped",
                    "due_date": "2026-11-01",
                },
                {"id": "SYS-005", "title": "Documentar decisões", "status": "planned"},
            ],
        }
    )


@pytest.fixture
def observations() -> list[dict[str, object]]:
    return [
        {
            "at": "2026-11-09T12:00:00Z",
            "burn": {
                "remaining": 4,
                "total": 5,
                "iterations": {"I1": {"remaining": 3, "total": 3}},
            },
        },
        {
            "at": "2026-11-10T12:00:00Z",
            "item_id": "SYS-001",
            "status": "finished",
            "previous_status": "doing",
            "burn": {
                "remaining": 3,
                "total": 5,
                "iterations": {"I1": {"remaining": 2, "total": 3}},
            },
        },
        {
            "at": "2026-11-11T12:00:00Z",
            "item_id": "SYS-001",
            "status": "finished",
            "previous_status": "doing",
        },
        {
            "at": "2026-11-12T12:00:00Z",
            "item_id": "SYS-999",
            "status": "finished",
            "previous_status": "doing",
        },
    ]


def test_management_indicators_follow_categories_and_observed_history(
    management_backlog: Backlog,
    observations: list[dict[str, object]],
) -> None:
    data = ReportData.build(management_backlog, observations, AT)
    assert data.counts == {"done": 1, "active": 1, "pending": 2, "cancelled": 1}
    assert [i.id for i in data.overdue] == ["SYS-002"]
    assert [i.id for i in data.blocked] == ["SYS-002"]
    assert data.throughput == 1  # one item re-completed twice, plus a future event
    source = exports.markdown(management_backlog, events=observations, at=AT)
    assert "| Conclusão do escopo | 25% |" in source
    assert "| Prazos vencidos | 1 |" in source
    assert "| Entregas nos últimos 7 dias | 1 |" in source
    assert "Vencido com pendências" in source
    assert "Atenção necessária" in source
    assert "Prazo vencido; Bloqueada por SYS-003" in source
    assert "Linha de base observada: 2026-11-09. Prazo: 2026-11-13." in source
    assert "Referência ideal" in source
    assert source.count("```mermaid") == 6


def test_full_activity_scope_acceptance_and_tracking_are_included(
    management_backlog: Backlog,
) -> None:
    source = exports.markdown(management_backlog, at=AT)
    assert "### SYS-002 — Autenticação" in source
    assert (
        "> Validar as credenciais da API.\n> \n> Registrar tentativas e expiração de sessão."
        in source
    )
    assert "- [x] AC-1 · Rejeitar credenciais inválidas" in source
    assert "- [ ] AC-2 · Expirar a sessão" in source
    assert "Depende de **SYS-003** · Infraestrutura" in source
    assert "Aguardando provisionamento da infraestrutura." in source
    assert "2026-11-09 12:00" in source  # normalized UTC
    assert "| Entregas nos últimos 7 dias | Não disponível |" in source
    preview = documents.report_html(source, management_backlog.project.name)
    assert preview.count('<article class="report-work-item">') == 5
    assert preview.count("</article>") == 5
    assert preview.count('<figure class="report-chart">') == 5
    assert '<table class="report-table inventory-table">' in preview
    assert "✓ AC-1" in preview and "○ AC-2" in preview
    assert "language-mermaid" not in preview


def test_empty_report_explains_absent_data_instead_of_claiming_delivery() -> None:
    source = exports.markdown(Backlog(project=Project(name="Novo projeto", key="SYS")), at=AT)
    assert "Planejamento ainda não iniciado" in source
    assert "Nenhuma atividade cadastrada" in source
    assert "| Conclusão do escopo | — |" in source
    assert "Não há auditoria operacional disponível" in source
    assert "| Entregas nos últimos 7 dias | Não disponível |" in source
    assert "Não há previsão de término" in source


def test_native_chart_does_not_bridge_unknown_dates() -> None:
    chart = Chart(
        kind="line",
        title="Saldo",
        labels=["11-09", "11-10", "11-11"],
        series=[Series(name="Restantes", values=[3, None, 1])],
    )
    source = chart_markdown(chart)
    assert 'x-axis ["11-09", "11-11"]' in source
    assert "line [3, 1]" in source
    rendered = render_chart(source.split("\n", 1)[1])
    assert rendered
    root = ET.fromstring(rendered[rendered.index("<svg") : rendered.index("</svg>") + 6])
    assert len(root.findall(".//{*}circle")) == 2
    assert all("L" not in path.attrib["d"] for path in root.findall(".//{*}path"))


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


@pytest.mark.security
def test_descriptions_and_chart_labels_cannot_inject_report_markup(
    management_backlog: Backlog,
) -> None:
    payload = '</text><script>alert(1)</script><img src="file:///etc/passwd" onerror="alert(1)">'
    management_backlog.work_items[0].description = (
        payload + '\n\n## Forged section\n```mermaid\n%% backloger-chart-v1 {"kind":"line"}\n```'
    )
    management_backlog.project.statuses[0].name = '<svg onload="alert(1)"> & "status"'
    source = exports.markdown(management_backlog, at=AT)
    rendered = documents.report_html(source, payload)
    parser = Tags()
    parser.feed(rendered)
    assert not any(
        tag in {"img", "script", "iframe", "foreignobject"} for tag, _ in parser.elements
    )
    assert not any(
        key.startswith("on") or key in {"src", "href"}
        for _, attrs in parser.elements
        for key in attrs
    )
    assert sum(tag == "h2" for tag, _ in parser.elements) == 9
    assert sum(tag == "svg" for tag, _ in parser.elements) == 5


@pytest.mark.security
@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"kind":"line","title":"X","labels":["a"],"series":[]}',
        '{"kind":"line","title":"X","labels":["a"],"series":[{"name":"X","values":[1,2]}]}',
        '{"kind":"line","title":"X","labels":["a"],"series":[{"name":"X","values":[1]}],'
        '"colors":["url(file:///etc/passwd)"]}',
    ],
)
def test_malformed_chart_metadata_remains_inert_code(payload: str) -> None:
    assert render_chart("%% backloger-chart-v1 " + payload) is None
    rendered = documents.render_markdown("```mermaid\n%% backloger-chart-v1 " + payload + "\n```")
    assert "<pre>" in rendered and "<svg" not in rendered


@pytest.mark.integration
def test_management_pdf_includes_graphs_and_full_activity_details(
    management_backlog: Backlog,
) -> None:
    from pypdf import PdfReader

    source = exports.markdown(management_backlog, at=AT)
    document = PdfReader(io.BytesIO(documents.pdf(management_backlog, source=source)))
    text = " ".join(page.extract_text() for page in document.pages)
    for expected in (
        "Resumo executivo",
        "25%",
        "Autenticação",
        "Rejeitar credenciais inválidas",
        "Registrar tentativas",
        "Aguardando provisionamento",
        "Restantes",
        "Concluídas",
    ):
        assert expected in text
    assert all(item.id in text for item in management_backlog.work_items)
