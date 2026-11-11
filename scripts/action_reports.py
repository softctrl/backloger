"""Runner for the reusable action. Inputs stay in environment variables, never shell code."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def workspace_path(workspace: Path, value: str) -> Path:
    if any(ord(char) < 32 for char in value):
        raise ValueError("Diretório contém caracteres de controle")
    path = (workspace / value).resolve()
    if not path.is_relative_to(workspace):
        raise ValueError("Diretório fora do workspace autorizado")
    return path


def configure() -> tuple[Path, Path, list[str], bool]:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    project = workspace_path(workspace, os.environ.get("BACKLOGER_INPUT_PROJECT", "."))
    output = workspace_path(
        workspace, os.environ.get("BACKLOGER_INPUT_OUTPUT", "backloger-reports")
    )
    if any(
        part in {".backloger", ".git", ".github", ".aws", ".codex", ".agents"}
        for part in output.relative_to(workspace).parts
    ):
        raise ValueError("Relatórios não podem ser escritos em diretórios de dados ou configuração")
    formats = list(
        dict.fromkeys(
            value.strip().lower()
            for value in os.environ.get("BACKLOGER_INPUT_FORMATS", "markdown").split(",")
        )
    )
    if not formats or any(value not in {"markdown", "html", "pdf"} for value in formats):
        raise ValueError("Formatos aceitos: markdown,html,pdf; solicite ao menos um")
    strict = os.environ.get("BACKLOGER_INPUT_STRICT", "true").strip().lower()
    if strict not in {"true", "false"}:
        raise ValueError("strict deve ser true ou false")
    if not project.is_dir():
        raise ValueError("Diretório do projeto não existe")
    return project, output, formats, strict == "true"


def github_outputs(values: dict[str, str]) -> None:
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")


def generate() -> dict[str, str]:
    from backloger import documents, exports
    from backloger.filesystem import atomic_write, encode
    from backloger.repository import Repository
    from backloger.schema import reject_unknown

    project, output, formats, strict = configure()
    repository = Repository(project, read_only=True)
    snapshot = repository.snapshot()
    if strict:
        reject_unknown(snapshot.backlog)
    source = exports.markdown(snapshot.backlog, events=repository.events())
    output.mkdir(parents=True, exist_ok=True)
    values = {"directory": str(output), "markdown": "", "html": "", "pdf": ""}
    hashes = {}
    for format in formats:
        if format == "markdown":
            filename, content = "BACKLOG.md", source.encode()
        elif format == "html":
            filename, content = (
                "BACKLOG.html",
                documents.report_html(source, snapshot.backlog.project.name).encode(),
            )
        else:
            filename, content = "BACKLOG.pdf", documents.pdf(snapshot.backlog, source=source)
        path = output / filename
        if path.is_symlink():
            raise ValueError("Destino de relatório não pode ser um link simbólico")
        atomic_write(path, content)
        values[format] = str(path)
        hashes[filename] = hashlib.sha256(content).hexdigest()
    manifest = output / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("Manifesto não pode ser um link simbólico")
    atomic_write(
        manifest,
        encode(
            {
                "project_key": snapshot.backlog.project.key,
                "revision": snapshot.revision,
                "item_count": len(snapshot.backlog.work_items),
                "formats": formats,
                "sha256": hashes,
            }
        ),
    )
    values["manifest"] = str(manifest)
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        _, output, formats, _ = configure()
        github_outputs({"directory": str(output), "needs-pdf": str("pdf" in formats).lower()})
    else:
        values = generate()
        github_outputs(values)
        print(json.dumps(values, ensure_ascii=False))


if __name__ == "__main__":
    main()
