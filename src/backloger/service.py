"""Use cases shared by CLI, API and future integrations."""

import base64
import re
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backloger import item_history
from backloger.errors import BacklogError, ConflictError, NotFoundError
from backloger.filesystem import decode, read_bytes, safe_path
from backloger.graph import analyze
from backloger.metrics import activity_history, burndown_history, completion_count
from backloger.models import (
    AcceptanceCriterion,
    Backlog,
    Dependency,
    Estimate,
    ItemType,
    Priority,
    SavedView,
    WorkItem,
    now,
)
from backloger.report_markdown import markdown
from backloger.repository import Repository, Snapshot
from backloger.transactions import BackupRecord


class CreateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    history_note: Annotated[str, Field(max_length=4000)] | None = None
    description: str = ""
    type: ItemType = "task"
    status: str | None = None
    priority: Priority = "medium"
    owner: str | None = None
    component: str | None = None
    labels: list[str] = []
    milestone_id: str | None = None
    iteration_id: str | None = None
    due_date: date | None = None
    estimate: Estimate | None = None
    dependencies: list[Dependency] = []
    acceptance_criteria: list[AcceptanceCriterion] = []
    extensions: dict[str, JsonValue] = {}


class UpdateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int
    history_note: Annotated[str, Field(max_length=4000)] | None = None
    title: str | None = None
    description: str | None = None
    type: ItemType | None = None
    status: str | None = None
    priority: Priority | None = None
    owner: str | None = None
    component: str | None = None
    labels: list[str] | None = None
    milestone_id: str | None = None
    iteration_id: str | None = None
    due_date: date | None = None
    estimate: Estimate | None = None
    dependencies: list[Dependency] | None = None
    acceptance_criteria: list[AcceptanceCriterion] | None = None
    extensions: dict[str, JsonValue] | None = None


class SaveViewRequest(SavedView):
    model_config = ConfigDict(extra="forbid")


class BacklogService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def snapshot(self, expected_revision: str | None = None) -> Snapshot:
        snapshot = self.repository.snapshot()
        if expected_revision is not None and snapshot.revision != expected_revision:
            raise ConflictError("Os dados mudaram; recarregue e reaplique sua alteração")
        return snapshot

    @staticmethod
    def item(snapshot: Snapshot, item_id: str) -> WorkItem:
        for item in snapshot.backlog.work_items:
            if item.id == item_id:
                return item
        raise NotFoundError(f"Atividade inexistente: {item_id}")

    @staticmethod
    def _wip(snapshot: Snapshot, status_id: str, old_status: str | None = None) -> None:
        if status_id == old_status:
            return
        status = next((s for s in snapshot.backlog.project.statuses if s.id == status_id), None)
        if status is None:
            raise BacklogError(f"Estado desconhecido: {status_id}")
        count = sum(i.status == status_id for i in snapshot.backlog.work_items)
        if status.wip_limit and count >= status.wip_limit:
            raise ConflictError(f"Limite WIP atingido em {status.name}")

    def add(
        self, request: CreateItem, expected_revision: str | None = None
    ) -> tuple[WorkItem, Snapshot]:
        snapshot = self.snapshot(expected_revision)
        if len(snapshot.backlog.work_items) >= 2000:
            raise BacklogError("Limite de 2000 atividades excedido")
        number = (
            max((int(i.id.rsplit("-", 1)[1]) for i in snapshot.backlog.work_items), default=0) + 1
        )
        data = request.model_dump(mode="json")
        data.pop("history_note", None)
        data["history"] = [
            e.model_dump(mode="json")
            for e in [
                item_history.entry("created", "Atividade criada.", 1),
                *item_history.comment(request.history_note, 1),
            ]
        ]
        data["status"] = request.status or next(
            s.id for s in snapshot.backlog.project.statuses if s.category == "pending"
        )
        item = WorkItem.model_validate(
            {**data, "id": f"{snapshot.backlog.project.key}-{number:03}"}
        )
        self._wip(snapshot, item.status)
        updated = snapshot.backlog.model_copy(deep=True)
        updated.work_items.append(item)
        return item, self.repository.commit(snapshot, updated, item_id=item.id, action="create")

    def update(
        self, item_id: str, request: UpdateItem, expected_revision: str | None = None
    ) -> tuple[WorkItem, Snapshot]:
        snapshot = self.snapshot(expected_revision)
        old = self.item(snapshot, item_id)
        if request.expected_version != old.version:
            raise ConflictError(f"Versão desatualizada de {item_id}; atual: {old.version}")
        changes = request.model_dump(
            mode="json", exclude_unset=True, exclude={"expected_version", "history_note"}
        )
        data = {
            **old.model_dump(mode="json"),
            **changes,
            "version": old.version + 1,
            "updated_at": max(now(), old.updated_at).isoformat(),
        }
        item = WorkItem.model_validate(data)
        data["history"] = [
            e.model_dump(mode="json")
            for e in item_history.updated(old, item, snapshot.backlog.project, request.history_note)
        ]
        item = WorkItem.model_validate(data)
        self._wip(snapshot, item.status, old.status)
        updated = snapshot.backlog.model_copy(deep=True)
        updated.work_items = [item if i.id == item_id else i for i in updated.work_items]
        return item, self.repository.commit(
            snapshot, updated, item_id=item_id, action="update", previous_status=old.status
        )

    def save_view(self, view: SavedView, expected_revision: str | None = None) -> Snapshot:
        snapshot = self.snapshot(expected_revision)
        updated = snapshot.backlog.model_copy(deep=True)
        updated.views = [v for v in updated.views if v.id != view.id] + [view]
        if len(updated.views) > 100:
            raise BacklogError("Limite de 100 visualizações excedido")
        return self.repository.commit(snapshot, updated, item_id=None, action="save_view")

    def restore(
        self,
        item_id: str,
        backup_id: str,
        expected_version: int,
        expected_revision: str | None = None,
    ) -> tuple[WorkItem, Snapshot]:
        if not re.fullmatch(r"[a-f0-9]{32}", backup_id):
            raise BacklogError("Identificador de backup inválido")
        snapshot = self.snapshot(expected_revision)
        old = self.item(snapshot, item_id)
        if old.version != expected_version:
            raise ConflictError("Versão desatualizada")
        path = safe_path(self.repository.root, f".backloger/.runtime/backups/{backup_id}.json")
        backup = BackupRecord.model_validate(decode(read_bytes(path, 16 * 1024 * 1024)))
        payload = decode(base64.b64decode(backup.content, validate=True))
        content = None
        if backup.target == "backlog.json":
            stored = Backlog.model_validate(payload)
            content = next(
                (i.model_dump(mode="json") for i in stored.work_items if i.id == item_id), None
            )
        elif backup.target != f".backloger/work-items/{item_id}.json":
            raise BacklogError("Backup não pertence à atividade")
        else:
            content = WorkItem.model_validate(payload).model_dump(mode="json")
        if content is None or content.get("id") != item_id:
            raise BacklogError("Atividade ausente no backup")
        content.update(version=old.version + 1, updated_at=max(now(), old.updated_at).isoformat())
        content["history"] = [
            e.model_dump(mode="json")
            for e in [
                *old.history,
                item_history.entry(
                    "restored", f"Conteúdo restaurado do backup {backup_id[:8]}.", old.version + 1
                ),
            ]
        ]
        item = WorkItem.model_validate(content)
        self._wip(snapshot, item.status, old.status)
        updated = snapshot.backlog.model_copy(deep=True)
        updated.work_items = [item if i.id == item_id else i for i in updated.work_items]
        return item, self.repository.commit(
            snapshot, updated, item_id=item_id, action="restore", previous_status=old.status
        )

    def report(self) -> tuple[Snapshot, str]:
        snapshot = self.snapshot()
        return snapshot, markdown(snapshot.backlog, events=self.repository.events())

    def state(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        backlog = snapshot.backlog
        analysis = analyze(backlog)
        categories = {s.id: s.category for s in backlog.project.statuses}
        events = self.repository.events()
        return {
            **backlog.model_dump(mode="json"),
            "revision": snapshot.revision,
            "read_only": self.repository.read_only,
            "storage": snapshot.storage,
            "analysis": analysis,
            "history": activity_history(backlog.project, events, now()),
            "burndown": burndown_history(backlog, events, now()),
            "metrics": {
                "total": len(backlog.work_items),
                "done": sum(categories[i.status] == "done" for i in backlog.work_items),
                "blocked": analysis["blocked_count"],
                "overdue": sum(
                    i.due_date is not None
                    and i.due_date < now().date()
                    and categories[i.status] not in {"done", "cancelled"}
                    for i in backlog.work_items
                ),
                "by_status": {
                    s.id: sum(i.status == s.id for i in backlog.work_items)
                    for s in backlog.project.statuses
                },
                "throughput_7d": completion_count(backlog.project, events, now()),
                "history_note": (
                    "Throughput: atividades concluídas via Backloger nos últimos "
                    "7 dias; edições externas não geram histórico."
                ),
            },
        }
