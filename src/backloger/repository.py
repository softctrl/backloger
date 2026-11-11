"""JSON repositories. No derived database is authoritative."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import portalocker

from backloger import transactions
from backloger.errors import BacklogError, ConflictError, NotFoundError, ReadOnlyError
from backloger.filesystem import (
    MAX_PROJECT_BYTES,
    atomic_create,
    atomic_write,
    decode,
    encode,
    read_bytes,
    revision,
    safe_path,
    sync_directory,
)
from backloger.graph import dependency_graph
from backloger.models import Backlog, Project, WorkItem, now


@dataclass(frozen=True)
class Snapshot:
    backlog: Backlog
    revision: str
    raw: dict[str, bytes]
    storage: Literal["split", "single"]


def deserialize(raw: dict[str, bytes], storage: Literal["split", "single"]) -> Backlog:
    if storage == "single":
        return Backlog.model_validate(decode(raw["backlog.json"]))
    data = {
        n: decode(raw[f".backloger/{n}.json"])
        for n in ("project", "milestones", "iterations", "views")
    }
    data["work_items"] = []
    for name, value in raw.items():
        if name.startswith(".backloger/work-items/"):
            item = decode(value)
            if not isinstance(item, dict) or Path(name).stem != item.get("id"):
                raise BacklogError("Nome de arquivo diferente do ID da atividade")
            data["work_items"].append(item)
    return Backlog.model_validate(data)


def find_project(path: Path) -> Path:
    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "backlog.json").exists() or (
            candidate / ".backloger/project.json"
        ).exists():
            return candidate
    return resolved


class Repository:
    def __init__(self, root: Path, *, read_only: bool = False):
        self.root = root.resolve()
        self.read_only = read_only

    def writable(self) -> None:
        if self.read_only:
            raise ReadOnlyError("Projeto em modo somente leitura")

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.writable()
        transactions.runtime(self.root)
        path = safe_path(self.root, ".backloger/.runtime/project.lock")
        try:
            with portalocker.Lock(path, timeout=5):
                yield
        except portalocker.exceptions.LockException as exc:
            raise ConflictError("Projeto ocupado; tente novamente") from exc

    def initialize(
        self, project: Project, storage: Literal["split", "single"] = "split"
    ) -> Snapshot:
        self.writable()
        self.root.mkdir(parents=True, exist_ok=True)
        if (
            safe_path(self.root, ".backloger").exists()
            or safe_path(self.root, "backlog.json").exists()
        ):
            raise ConflictError("Projeto já contém .backloger ou backlog.json")
        if storage == "single":
            atomic_create(
                self.root / "backlog.json", encode(Backlog(project=project).model_dump(mode="json"))
            )
        else:
            staging = Path(tempfile.mkdtemp(prefix=".backloger-init-", dir=self.root))
            try:
                (staging / "work-items").mkdir()
                for name in ("milestones", "iterations", "views"):
                    atomic_write(staging / f"{name}.json", encode([]))
                atomic_write(staging / "project.json", encode(project.model_dump(mode="json")))
                staging.rename(self.root / ".backloger")
                sync_directory(self.root)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        return self.snapshot()

    def _read_raw(self) -> tuple[dict[str, bytes], Literal["split", "single"]]:
        single = safe_path(self.root, "backlog.json")
        project = safe_path(self.root, ".backloger/project.json")
        if single.exists() and project.exists():
            raise BacklogError("Dois modelos de armazenamento encontrados; escolha um")
        if single.exists():
            return {"backlog.json": read_bytes(single)}, "single"
        if not project.exists():
            raise NotFoundError("Projeto não inicializado; execute backloger init")
        directory = safe_path(self.root, ".backloger/work-items")
        paths = [project] + [
            safe_path(self.root, f".backloger/{n}.json")
            for n in ("milestones", "iterations", "views")
        ]
        for item in directory.iterdir():
            if item.suffix != ".json":
                continue
            paths.append(safe_path(self.root, str(item.relative_to(self.root))))
            if len(paths) > 2004:
                raise BacklogError("Limite de 2000 atividades excedido")
        raw: dict[str, bytes] = {}
        total = 0
        for path in sorted(paths):
            data = read_bytes(path)
            total += len(data)
            if total > MAX_PROJECT_BYTES:
                raise BacklogError("Projeto maior que 32 MiB")
            raw[str(path.relative_to(self.root))] = data
        return raw, "split"

    def snapshot(self, *, validate: bool = True) -> Snapshot:
        for _ in range(3):
            raw, storage = self._read_raw()
            backlog = deserialize(raw, storage)
            if self._read_raw()[0] == raw:
                if validate:
                    dependency_graph(backlog)
                return Snapshot(backlog, revision(raw), raw, storage)
        raise ConflictError("Arquivos mudando durante a leitura; tente novamente")

    def commit(
        self,
        snapshot: Snapshot,
        backlog: Backlog,
        *,
        item_id: str | None,
        action: str,
        previous_status: str | None = None,
    ) -> Snapshot:
        self.writable()
        dependency_graph(backlog)
        if snapshot.storage == "single":
            target = "backlog.json"
            after = encode(backlog.model_dump(mode="json"))
        elif item_id:
            item = next(i for i in backlog.work_items if i.id == item_id)
            target = f".backloger/work-items/{item_id}.json"
            safe_path(self.root, target)
            after = encode(item.model_dump(mode="json"))
        else:
            target = ".backloger/views.json"
            after = encode([v.model_dump(mode="json") for v in backlog.views])
        if len(after) > 8 * 1024 * 1024:
            raise BacklogError("Arquivo resultante excede 8 MiB")
        if (
            sum(map(len, snapshot.raw.values())) - len(snapshot.raw.get(target, b"")) + len(after)
            > MAX_PROJECT_BYTES
        ):
            raise BacklogError("Projeto resultante excede 32 MiB")
        event: dict[str, Any] = {"at": now().isoformat(), "action": action, "item_id": item_id}
        categories = {status.id: status.category for status in backlog.project.statuses}

        def remaining(items: list[WorkItem]) -> dict[str, int]:
            return {
                "total": len(items),
                "remaining": sum(categories[i.status] not in {"done", "cancelled"} for i in items),
            }

        previous = next((i for i in snapshot.backlog.work_items if i.id == item_id), None)
        current = next((i for i in backlog.work_items if i.id == item_id), None)
        iteration_ids = {i.iteration_id for i in (previous, current) if i and i.iteration_id}
        event["burn"] = {
            **remaining(backlog.work_items),
            "iterations": {
                iteration: remaining([i for i in backlog.work_items if i.iteration_id == iteration])
                for iteration in iteration_ids
            },
        }
        if item_id:
            item = next(i for i in backlog.work_items if i.id == item_id)
            event.update(version=item.version, status=item.status, previous_status=previous_status)
        with self.lock():
            if transactions.pending(self.root):
                raise ConflictError("Gravação interrompida; execute backloger recover")
            if self._read_raw()[0] != snapshot.raw:
                raise ConflictError("Projeto alterado externamente; recarregue antes de salvar")
            transactions.transact(self.root, target, snapshot.raw.get(target), after, event)
        return self.snapshot()

    def recover(self) -> int:
        def validate(target: str, after: bytes) -> None:
            raw, storage = self._read_raw()
            raw[target] = after
            if len(after) > 8 * 1024 * 1024 or sum(map(len, raw.values())) > MAX_PROJECT_BYTES:
                raise BacklogError("Recuperação excede limites de tamanho")
            dependency_graph(deserialize(raw, storage))

        with self.lock():
            count = transactions.recover(self.root, validate)
        self.snapshot()
        return count

    def events(self) -> list[dict[str, Any]]:
        path = safe_path(self.root, ".backloger/.runtime/audit")
        if not path.exists():
            return []
        files = sorted(path.glob("*.json"))
        if len(files) > 20_000:
            raise BacklogError("Mais de 20000 eventos; arquive a auditoria antiga")
        return [
            decode(read_bytes(safe_path(self.root, str(p.relative_to(self.root))))) for p in files
        ]
