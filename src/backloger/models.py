"""Versioned, extensible JSON contract. Unknown stored fields survive edits."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
Identifier = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9]{1,15}-[0-9]{3,9}$")]
Reference = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
StatusId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
ItemType = Literal[
    "epic",
    "feature",
    "story",
    "task",
    "bug",
    "maintenance",
    "security",
    "documentation",
    "spike",
    "incident",
]
Priority = Literal["critical", "high", "medium", "low"]
Category = Literal["pending", "active", "done", "cancelled"]
HistoryKind = Literal["created", "updated", "comment", "restored"]


def now() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class Estimate(Contract):
    unit: Literal["hours", "days", "points"]
    value: Annotated[float, Field(ge=0, le=1_000_000)]


class Dependency(Contract):
    target_id: Identifier
    relation: Literal["blocked_by", "blocks", "relates_to", "child_of"] = "blocked_by"


class AcceptanceCriterion(Contract):
    id: Reference
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    done: bool = False


class HistoryEntry(Contract):
    id: Reference
    at: AwareDatetime
    kind: HistoryKind
    text: Annotated[str, Field(min_length=1, max_length=4000)]
    version: Annotated[int, Field(ge=1, strict=True)]
    changed_fields: Annotated[list[str], Field(max_length=30)] = Field(default_factory=list)


class WorkItem(Contract):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    id: Identifier
    title: Annotated[str, Field(min_length=1, max_length=300)]
    description: Annotated[str, Field(max_length=50_000)] = ""
    type: ItemType = "task"
    status: StatusId = "todo"
    priority: Priority = "medium"
    component: Annotated[str, Field(max_length=100)] | None = None
    owner: Annotated[str, Field(max_length=100)] | None = None
    labels: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=60)]], Field(max_length=50)
    ] = Field(default_factory=list)
    milestone_id: Reference | None = None
    iteration_id: Reference | None = None
    due_date: date | None = None
    estimate: Estimate | None = None
    dependencies: Annotated[list[Dependency], Field(max_length=100)] = Field(default_factory=list)
    acceptance_criteria: Annotated[list[AcceptanceCriterion], Field(max_length=100)] = Field(
        default_factory=list
    )
    created_at: AwareDatetime = Field(default_factory=now)
    updated_at: AwareDatetime = Field(default_factory=now)
    version: Annotated[int, Field(ge=1, strict=True)] = 1
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    history: Annotated[list[HistoryEntry], Field(max_length=1000)] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at deve ser posterior a created_at")
        if len({entry.id for entry in self.history}) != len(self.history):
            raise ValueError("IDs de histórico duplicados")
        if len({c.id for c in self.acceptance_criteria}) != len(self.acceptance_criteria):
            raise ValueError("IDs de critérios de aceite duplicados")
        relations = [(d.target_id, d.relation) for d in self.dependencies]
        if len(set(relations)) != len(relations):
            raise ValueError("Dependências duplicadas")
        if any(d.target_id == self.id for d in self.dependencies):
            raise ValueError("Uma atividade não pode depender de si mesma")
        return self


class Status(Contract):
    id: StatusId
    name: Annotated[str, Field(min_length=1, max_length=80)]
    category: Category
    wip_limit: Annotated[int, Field(ge=1, le=2000)] | None = None


def default_statuses() -> list[Status]:
    return [
        Status(id="todo", name="A fazer", category="pending"),
        Status(id="in_progress", name="Em andamento", category="active"),
        Status(id="review", name="Em revisão", category="active"),
        Status(id="done", name="Concluído", category="done"),
        Status(id="cancelled", name="Cancelado", category="cancelled"),
    ]


class Project(Contract):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    name: Annotated[str, Field(min_length=1, max_length=120)]
    key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$")]
    statuses: Annotated[list[Status], Field(min_length=1, max_length=20)] = Field(
        default_factory=default_statuses
    )
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_statuses(self) -> Self:
        if len({s.id for s in self.statuses}) != len(self.statuses):
            raise ValueError("Estados duplicados")
        if not any(s.category == "pending" for s in self.statuses):
            raise ValueError("Configure ao menos um estado de categoria pending")
        return self


class Milestone(Contract):
    id: Reference
    name: Annotated[str, Field(min_length=1, max_length=120)]
    due_date: date | None = None


class Iteration(Milestone):
    start_date: date | None = None

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("O fim da sprint deve ser igual ou posterior ao início")
        return self


class SavedView(Contract):
    id: Reference
    name: Annotated[str, Field(min_length=1, max_length=80)]
    filters: dict[str, Annotated[str, Field(max_length=300)]] = Field(default_factory=dict)


class Backlog(Contract):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    project: Project
    work_items: Annotated[list[WorkItem], Field(max_length=2000)] = Field(default_factory=list)
    milestones: Annotated[list[Milestone], Field(max_length=200)] = Field(default_factory=list)
    iterations: Annotated[list[Iteration], Field(max_length=200)] = Field(default_factory=list)
    views: Annotated[list[SavedView], Field(max_length=100)] = Field(default_factory=list)
