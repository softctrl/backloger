"""Management indicators derived from one validated canonical snapshot."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backloger.graph import analyze
from backloger.metrics import activity_history, burndown_history, completion_count
from backloger.models import Backlog, WorkItem, now

PRIORITIES = {"critical": "Crítica", "high": "Alta", "medium": "Média", "low": "Baixa"}
TYPES = {
    "epic": "Épico",
    "feature": "Funcionalidade",
    "story": "História",
    "task": "Tarefa",
    "bug": "Defeito",
    "maintenance": "Manutenção",
    "security": "Segurança",
    "documentation": "Documentação",
    "spike": "Investigação",
    "incident": "Incidente",
}
UNITS = {"hours": "horas", "days": "dias", "points": "pontos"}
RELATIONS = {
    "blocked_by": "Depende de",
    "blocks": "Bloqueia",
    "relates_to": "Relacionada a",
    "child_of": "Filha de",
}


def progress(items: list[WorkItem], categories: dict[str, str]) -> str:
    applicable = [item for item in items if categories[item.status] != "cancelled"]
    done = sum(categories[item.status] == "done" for item in applicable)
    return f"{done / len(applicable):.0%}" if applicable else "—"


@dataclass(frozen=True)
class ReportData:
    backlog: Backlog
    at: datetime
    analysis: dict[str, Any]
    categories: dict[str, str]
    statuses: dict[str, str]
    open_items: list[WorkItem]
    overdue: list[WorkItem]
    blocked: list[WorkItem]
    history: dict[str, Any]
    burndown: dict[str, Any]
    throughput: int

    @classmethod
    def build(
        cls, backlog: Backlog, events: list[dict[str, Any]] | None, at: datetime | None
    ) -> "ReportData":
        timestamp = (at or now()).astimezone(UTC)
        categories: dict[str, str] = {
            status.id: status.category for status in backlog.project.statuses
        }
        analysis = analyze(backlog)
        open_items = sorted(
            [i for i in backlog.work_items if categories[i.status] not in {"done", "cancelled"}],
            key=lambda i: (list(PRIORITIES).index(i.priority), str(i.due_date or "9999"), i.id),
        )
        return cls(
            backlog,
            timestamp,
            analysis,
            categories,
            {s.id: s.name for s in backlog.project.statuses},
            open_items,
            [i for i in open_items if i.due_date and i.due_date < timestamp.date()],
            [i for i in open_items if analysis["blockers"].get(i.id)],
            activity_history(backlog.project, events or [], timestamp),
            burndown_history(backlog, events or [], timestamp),
            completion_count(backlog.project, events or [], timestamp),
        )

    @property
    def counts(self) -> Counter[str]:
        return Counter(self.categories[i.status] for i in self.backlog.work_items)

    @property
    def assessment(self) -> str:
        if not self.backlog.work_items:
            return "Planejamento ainda não iniciado"
        if self.overdue or self.blocked or self.wip_exceeded:
            return "Atenção necessária"
        if not self.open_items:
            return "Escopo encerrado"
        return "Acompanhamento em curso"

    @property
    def wip_exceeded(self) -> list[str]:
        counts = Counter(i.status for i in self.backlog.work_items)
        return [
            s.name
            for s in self.backlog.project.statuses
            if s.wip_limit is not None and counts[s.id] > s.wip_limit
        ]

    def attention(self, item: WorkItem) -> str:
        reasons = []
        if item in self.overdue:
            reasons.append("Prazo vencido")
        blockers = self.analysis["blockers"].get(item.id, [])
        if blockers:
            reasons.append("Bloqueada por " + ", ".join(blockers))
        if self.categories[item.status] == "done":
            reasons.append("Concluída")
        elif self.categories[item.status] == "cancelled":
            reasons.append("Cancelada")
        elif not blockers:
            reasons.append("Sem bloqueio de dependência")
        return "; ".join(reasons)
