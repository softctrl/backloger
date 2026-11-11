"""A durable intent journal makes interrupted writes explicitly recoverable."""

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backloger.errors import BacklogError, ConflictError
from backloger.filesystem import (
    atomic_write,
    decode,
    digest,
    encode,
    read_bytes,
    safe_path,
    sync_directory,
)


class BackupRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=256)
    content: str
    event: dict[str, JsonValue]


class JournalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=256)
    before_hash: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    after_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    after: str
    event: dict[str, JsonValue]


def runtime(root: Path) -> Path:
    for name in (
        ".backloger",
        ".backloger/.runtime",
        ".backloger/.runtime/journal",
        ".backloger/.runtime/backups",
        ".backloger/.runtime/audit",
    ):
        safe_path(root, name).mkdir(exist_ok=True)
    return root / ".backloger/.runtime"


def pending(root: Path) -> list[Path]:
    directory = safe_path(root, ".backloger/.runtime/journal")
    return sorted(directory.glob("*.json")) if directory.exists() else []


def _finalize(root: Path, journal: Path, record: dict[str, Any]) -> None:
    event = record["event"]
    audit = safe_path(root, f".backloger/.runtime/audit/{journal.name}")
    atomic_write(audit, encode(event))
    journal.unlink()
    sync_directory(journal.parent)


def transact(
    root: Path, target: str, before: bytes | None, after: bytes, event: dict[str, Any]
) -> None:
    transaction = uuid4().hex
    event = {**event, "transaction": transaction}
    record = {
        "target": target,
        "before_hash": digest(before) if before is not None else None,
        "after_hash": digest(after),
        "after": base64.b64encode(after).decode(),
        "event": event,
    }
    base = runtime(root)
    if before is not None:
        backup = {"target": target, "content": base64.b64encode(before).decode(), "event": event}
        atomic_write(
            safe_path(root, f".backloger/.runtime/backups/{transaction}.json"), encode(backup)
        )
    journal = base / "journal" / f"{transaction}.json"
    atomic_write(journal, encode(record))
    # Recheck immediately before replacement: editors must use the same lock for a
    # strict guarantee. A non-cooperating writer can still race this last check.
    path = safe_path(root, target)
    actual = read_bytes(path) if path.exists() else None
    if actual != before:
        journal.unlink()
        sync_directory(journal.parent)
        raise ConflictError("Arquivo modificado durante a gravação; recarregue os dados")
    atomic_write(path, after)
    _finalize(root, journal, record)


def recover(root: Path, validate: Callable[[str, bytes], None]) -> int:
    """Replay intents only if the target still equals the before or after hash."""
    recovered = 0
    for journal in pending(root):
        record = JournalRecord.model_validate(
            decode(read_bytes(safe_path(root, str(journal.relative_to(root))), 16 * 1024 * 1024))
        ).model_dump()
        target = record["target"]
        allowed = (
            target == "backlog.json"
            or target == ".backloger/views.json"
            or (target.startswith(".backloger/work-items/") and target.endswith(".json"))
        )
        if not allowed:
            raise BacklogError("Destino inválido no diário de recuperação")
        path = safe_path(root, target)
        actual = digest(read_bytes(path)) if path.exists() else None
        if actual not in {record["before_hash"], record["after_hash"]}:
            raise ConflictError(
                "Recuperação encontrou edição externa; preserve o diário e resolva manualmente"
            )
        after = base64.b64decode(record["after"], validate=True)
        if digest(after) != record["after_hash"]:
            raise BacklogError("Diário de recuperação corrompido")
        validate(target, after)
        if actual != record["after_hash"]:
            atomic_write(path, after)
        _finalize(root, journal, record)
        recovered += 1
    return recovered
