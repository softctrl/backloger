"""Validate a normalized migration proposal and create a new, separate candidate."""

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backloger.errors import BacklogError
from backloger.exports import markdown
from backloger.filesystem import atomic_write, decode, encode, read_bytes
from backloger.graph import dependency_graph
from backloger.models import Backlog
from backloger.repository import Repository
from backloger.schema import reject_unknown

NAMESPACE = "backloger.migration"


def normalize_dates(data: dict[str, Any]) -> list[str]:
    """Absent source dates are explicitly import-time dates, never invented history."""
    imported = datetime.now(UTC).isoformat()
    assigned = []
    for item in data.get("work_items", []):
        if not isinstance(item, dict):
            raise ValueError("Cada atividade deve ser um objeto JSON")
        supplied = [bool(item.get(field)) for field in ("created_at", "updated_at")]
        if any(supplied) and not all(supplied):
            raise ValueError(
                f"{item.get('id')}: datas parciais; resolva e documente a origem das duas datas"
            )
        if not any(supplied):
            extensions = item.setdefault("extensions", {})
            if not isinstance(extensions, dict):
                raise ValueError("extensions deve ser um objeto")
            metadata = extensions.setdefault(NAMESPACE, {})
            if not isinstance(metadata, dict):
                raise ValueError(f"extensions.{NAMESPACE} deve ser um objeto")
            metadata["imported_at"] = imported
            metadata["timestamp_basis"] = {"created_at": "import_time", "updated_at": "import_time"}
            item["created_at"] = item["updated_at"] = imported
            assigned.append(str(item.get("id", "")))
    return assigned


def stage(
    proposal: Path, output: Path, storage: str, sources: list[Path], expected_count: int | None
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("O destino deve ser novo; nenhuma migração existente será sobrescrita")
    raw = read_bytes(proposal)
    data = decode(raw)
    if not isinstance(data, dict) or not isinstance(data.get("work_items", []), list):
        raise ValueError("A proposta deve ser um objeto Backlog com work_items em lista")
    assigned = normalize_dates(data)
    backlog = Backlog.model_validate(data)
    reject_unknown(backlog)
    dependency_graph(backlog)
    if expected_count is not None and len(backlog.work_items) != expected_count:
        raise ValueError(
            f"Contagem divergente: esperado {expected_count}, recebido {len(backlog.work_items)}"
        )
    fingerprints = []
    for source in sources:
        content = read_bytes(source)
        fingerprints.append(
            {
                "name": source.name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".backloger-candidate-", dir=output.parent
    ) as directory:
        candidate = Path(directory)
        if storage == "single":
            atomic_write(candidate / "backlog.json", encode(backlog.model_dump(mode="json")))
        else:
            canonical = candidate / ".backloger"
            canonical.mkdir()
            (canonical / "work-items").mkdir()
            atomic_write(
                canonical / "project.json", encode(backlog.project.model_dump(mode="json"))
            )
            for name in ("milestones", "iterations", "views"):
                atomic_write(
                    canonical / f"{name}.json",
                    encode([value.model_dump(mode="json") for value in getattr(backlog, name)]),
                )
            for item in backlog.work_items:
                atomic_write(
                    canonical / "work-items" / f"{item.id}.json",
                    encode(item.model_dump(mode="json")),
                )
        snapshot = Repository(candidate, read_only=True).snapshot()
        mapping = []
        for item in backlog.work_items:
            metadata = item.extensions.get(NAMESPACE, {})
            if not isinstance(metadata, dict):
                raise ValueError(f"{item.id}: metadados de migração devem ser um objeto")
            mapping.append(
                {
                    "id": item.id,
                    "original_id": metadata.get("original_id"),
                    "source_refs": metadata.get("source_refs", []),
                }
            )
        summary = {
            "project_key": backlog.project.key,
            "storage": storage,
            "item_count": len(backlog.work_items),
            "revision": snapshot.revision,
            "by_status": dict(Counter(item.status for item in backlog.work_items)),
            "proposal_sha256": hashlib.sha256(raw).hexdigest(),
            "sources": fingerprints,
            "timestamp_basis_import_time": assigned,
            "note": "Candidato separado; nenhuma origem ou projeto ativo foi alterado. "
            "Não reconstrói auditoria/burndown retroativo.",
        }
        atomic_write(candidate / "migration-manifest.json", encode(summary))
        atomic_write(candidate / "id-map.json", encode(mapping))
        atomic_write(candidate / "BACKLOG.md", markdown(snapshot.backlog).encode())
        # copytree claims a new destination and refuses an existing directory,
        # including a destination created concurrently after the initial check.
        shutil.copytree(candidate, output)
    return {**summary, "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preparar uma migração Backloger em diretório novo."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Proposta no contrato Backlog JSON."
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Diretório novo, separado do projeto."
    )
    parser.add_argument("--storage", choices=["split", "single"], default="split")
    parser.add_argument(
        "--source", action="append", type=Path, default=[], help="Origem para hash; repetível."
    )
    parser.add_argument(
        "--expected-count", type=int, help="Contagem reconciliada de atividades esperadas."
    )
    args = parser.parse_args()
    try:
        result = stage(args.input, args.output, args.storage, args.source, args.expected_count)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, BacklogError) as exc:
        message = str(exc)
        if isinstance(exc, ValidationError):
            message = "; ".join(f"{e['loc']}: {e['msg']}" for e in exc.errors(include_input=False))
        print(f"Erro de migração: {message}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
