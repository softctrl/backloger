"""Bounded UTF-8 reads and durable atomic replacements on local filesystems."""

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from backloger.errors import BacklogError

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PROJECT_BYTES = 32 * 1024 * 1024


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise BacklogError("Caminho fora do projeto")
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise BacklogError("Links simbólicos não são permitidos nos dados do backlog")
    return path


def read_bytes(path: Path, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise BacklogError("Arquivo inválido ou acima do limite de tamanho")
        value = stream.read(max_bytes + 1)
        if len(value) > max_bytes:
            raise BacklogError("Arquivo acima do limite de tamanho")
        return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise BacklogError(f"Chave JSON duplicada: {key}")
        value[key] = item
    return value


def decode(value: bytes) -> Any:
    def invalid_constant(_: str) -> None:
        raise BacklogError("JSON não aceita NaN ou Infinity")

    try:
        return json.loads(value, object_pairs_hook=_pairs, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BacklogError("JSON inválido; corrija o arquivo antes de continuar") from exc


def encode(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def revision(raw: dict[str, bytes]) -> str:
    return digest(encode({name: digest(value) for name, value in sorted(raw.items())}))


def atomic_write(path: Path, value: bytes) -> None:
    """Flush contents and directory; temp and target live on the same filesystem."""
    fd, temporary = tempfile.mkstemp(prefix=".backloger-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_create(path: Path, value: bytes) -> None:
    """Publish a complete new file without replacing an existing destination."""
    fd, temporary = tempfile.mkstemp(prefix=".backloger-init-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)
