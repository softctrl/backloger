"""Public Typer interface. Options shared by commands precede the subcommand."""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from backloger import __version__, documents, exports
from backloger.errors import BacklogError
from backloger.filesystem import atomic_write, decode, read_bytes, safe_path
from backloger.graph import analyze
from backloger.models import Backlog, Dependency, Project
from backloger.repository import Repository, find_project
from backloger.service import BacklogService, CreateItem, UpdateItem
from backloger.transactions import BackupRecord

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help=(
        "Backlogs locais em JSON. Códigos: 0 sucesso, 1 dados/IO, 2 uso, "
        "3 conflito, 4 somente leitura."
    ),
)
export_app = typer.Typer(help="Exportar dados canônicos.")
docker_app = typer.Typer(help="Executar Compose a partir de uma instalação do código-fonte.")
app.add_typer(export_app, name="export")
app.add_typer(docker_app, name="docker")


@app.callback()
def main(
    ctx: typer.Context,
    project: Annotated[
        Path, typer.Option("--project", "-p", help="Raiz do projeto (ou subdiretório).")
    ] = Path("."),
    json_output: Annotated[
        bool, typer.Option("--json", help="Saída JSON para automações.")
    ] = False,
    read_only: Annotated[bool, typer.Option("--read-only")] = False,
    version: Annotated[bool, typer.Option("--version", is_eager=True)] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    ctx.obj = {
        "root": find_project(project),
        "explicit": project.resolve(),
        "json": json_output,
        "read_only": read_only or os.getenv("BACKLOGER_READ_ONLY", "false").lower() == "true",
    }


@contextmanager
def operation(ctx: typer.Context) -> Iterator[BacklogService]:
    try:
        yield BacklogService(Repository(ctx.obj["root"], read_only=ctx.obj["read_only"]))
    except (BacklogError, ValidationError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, BacklogError) else "invalid_data"
        message = (
            str(exc)
            if not isinstance(exc, ValidationError)
            else "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                for e in exc.errors(include_input=False)
            )
        )
        if ctx.obj["json"]:
            typer.echo(
                json.dumps({"error": code, "message": message}, ensure_ascii=False), err=True
            )
        else:
            typer.echo(f"Erro: {message}", err=True)
        raise typer.Exit(exc.exit_code if isinstance(exc, BacklogError) else 1) from exc


def emit(ctx: typer.Context, data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def output_file(ctx: typer.Context, content: str, output: Path | None) -> None:
    if output:
        if output.name == "backlog.json" or ".backloger" in output.resolve().parts:
            raise BacklogError("Exportação não pode substituir dados canônicos ou de recuperação")
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(output, content.encode())
        emit(ctx, {"output": str(output)})
    else:
        typer.echo(content, nl=False)


def read_object(path: Path) -> dict[str, Any]:
    data = decode(read_bytes(path))
    if not isinstance(data, dict):
        raise BacklogError("O arquivo deve conter um objeto JSON")
    return data


@app.command()
def init(
    ctx: typer.Context,
    name: Annotated[str, typer.Option()],
    key: Annotated[str, typer.Option()],
    storage: Annotated[Literal["split", "single"], typer.Option()] = "split",
) -> None:
    """Inicializar sem substituir dados existentes."""
    with operation(ctx):
        repository = Repository(ctx.obj["explicit"], read_only=ctx.obj["read_only"])
        snapshot = repository.initialize(Project(name=name, key=key), storage)
        emit(ctx, {"project": snapshot.backlog.project.model_dump(mode="json"), "storage": storage})


@app.command(name="list")
def list_items(
    ctx: typer.Context,
    status: str | None = None,
    owner: str | None = None,
    priority: str | None = None,
    label: str | None = None,
    blocked: bool = False,
) -> None:
    """Consultar atividades; filtros são combinados."""
    with operation(ctx) as service:
        snapshot = service.snapshot()
        analysis = analyze(snapshot.backlog)
        items = [
            i
            for i in snapshot.backlog.work_items
            if (not status or i.status == status)
            and (not owner or i.owner == owner)
            and (not priority or i.priority == priority)
            and (not label or label in i.labels)
            and (not blocked or analysis["blockers"].get(i.id))
        ]
        if ctx.obj["json"]:
            emit(ctx, [i.model_dump(mode="json") for i in items])
        else:
            table = Table("ID", "Atividade", "Estado", "Prioridade", "Responsável")
            for item in items:
                table.add_row(item.id, item.title, item.status, item.priority, item.owner or "—")
            Console(markup=False, highlight=False).print(table)


@app.command()
def show(ctx: typer.Context, item_id: str) -> None:
    with operation(ctx) as service:
        snapshot = service.snapshot()
        emit(
            ctx,
            {
                "item": service.item(snapshot, item_id).model_dump(mode="json"),
                "revision": snapshot.revision,
            },
        )


@app.command()
def add(
    ctx: typer.Context,
    title: Annotated[str, typer.Option()],
    item_type: Annotated[str | None, typer.Option("--type")] = None,
    description: str | None = None,
    priority: str | None = None,
    owner: str | None = None,
    file: Annotated[Path | None, typer.Option(help="JSON com campos adicionais.")] = None,
) -> None:
    with operation(ctx) as service:
        data = read_object(file) if file else {}
        data["title"] = title
        data.update(
            {
                key: value
                for key, value in {
                    "type": item_type,
                    "description": description,
                    "priority": priority,
                    "owner": owner,
                }.items()
                if value is not None
            }
        )
        item, snapshot = service.add(CreateItem.model_validate(data))
        emit(ctx, {"item": item.model_dump(mode="json"), "revision": snapshot.revision})


@app.command()
def update(
    ctx: typer.Context,
    item_id: str,
    file: Annotated[Path, typer.Option(help="JSON parcial de campos editáveis.")],
    version: Annotated[int | None, typer.Option(min=1)] = None,
    revision: str | None = None,
) -> None:
    with operation(ctx) as service:
        snapshot = service.snapshot(revision)
        old = service.item(snapshot, item_id)
        data = read_object(file)
        data["expected_version"] = version or old.version
        item, saved = service.update(item_id, UpdateItem.model_validate(data), snapshot.revision)
        emit(ctx, {"item": item.model_dump(mode="json"), "revision": saved.revision})


@app.command()
def move(
    ctx: typer.Context,
    item_id: str,
    to: Annotated[str, typer.Option("--to")],
    version: Annotated[int | None, typer.Option(min=1)] = None,
    revision: str | None = None,
) -> None:
    with operation(ctx) as service:
        snapshot = service.snapshot(revision)
        old = service.item(snapshot, item_id)
        item, saved = service.update(
            item_id,
            UpdateItem(expected_version=version or old.version, status=to),
            snapshot.revision,
        )
        emit(ctx, {"item": item.model_dump(mode="json"), "revision": saved.revision})


@app.command()
def link(
    ctx: typer.Context, item_id: str, blocked_by: Annotated[str, typer.Option("--blocked-by")]
) -> None:
    with operation(ctx) as service:
        snapshot = service.snapshot()
        old = service.item(snapshot, item_id)
        deps = [*old.dependencies, Dependency(target_id=blocked_by)]
        item, saved = service.update(
            item_id, UpdateItem(expected_version=old.version, dependencies=deps), snapshot.revision
        )
        emit(ctx, {"item": item.model_dump(mode="json"), "revision": saved.revision})


@app.command()
def validate(ctx: typer.Context, strict: bool = False) -> None:
    """Validar contrato e referências. --strict rejeita campos fora do contrato."""
    with operation(ctx) as service:
        snapshot = service.snapshot()
        if strict:
            from backloger.schema import reject_unknown

            reject_unknown(snapshot.backlog)
        emit(
            ctx,
            {
                "valid": True,
                "items": len(snapshot.backlog.work_items),
                "revision": snapshot.revision,
            },
        )


@app.command(name="analyze")
def analyze_command(
    ctx: typer.Context, item_id: Annotated[str | None, typer.Argument()] = None
) -> None:
    with operation(ctx) as service:
        emit(ctx, analyze(service.snapshot().backlog, item_id))


@export_app.command("markdown")
def export_markdown(ctx: typer.Context, output: Path | None = None) -> None:
    with operation(ctx) as service:
        _, source = service.report()
        output_file(ctx, source, output)


@export_app.command("csv")
def export_csv(ctx: typer.Context, output: Path | None = None) -> None:
    with operation(ctx) as service:
        output_file(ctx, exports.csv_report(service.snapshot().backlog), output)


@export_app.command("html")
def export_html(ctx: typer.Context, output: Path | None = None) -> None:
    with operation(ctx) as service:
        snapshot, source = service.report()
        output_file(ctx, documents.report_html(source, snapshot.backlog.project.name), output)


@export_app.command("pdf")
def export_pdf(ctx: typer.Context, output: Annotated[Path, typer.Option()]) -> None:
    """Gerar PDF do mesmo Markdown usado pelo documento web."""
    with operation(ctx) as service:
        if output.name == "backlog.json" or ".backloger" in output.resolve().parts:
            raise BacklogError("Exportação não pode substituir dados canônicos ou de recuperação")
        snapshot, source = service.report()
        content = documents.pdf(snapshot.backlog, source=source)
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(output, content)
        emit(ctx, {"output": str(output)})


@export_app.command("mermaid")
def export_mermaid(ctx: typer.Context, output: Path | None = None) -> None:
    with operation(ctx) as service:
        output_file(ctx, exports.mermaid(service.snapshot().backlog), output)


@app.command()
def graph(
    ctx: typer.Context,
    format: Literal["svg", "mermaid", "json"] = "svg",
    output: Path | None = None,
) -> None:
    with operation(ctx) as service:
        backlog = service.snapshot().backlog
        renderers: dict[str, Callable[[Backlog], str]] = {
            "svg": exports.svg,
            "mermaid": exports.mermaid,
            "json": lambda b: json.dumps(analyze(b), ensure_ascii=False, indent=2),
        }
        output_file(ctx, renderers[format](backlog), output)


@app.command()
def recover(ctx: typer.Context) -> None:
    """Recuperar transações interrompidas sem sobrescrever edições externas."""
    with operation(ctx) as service:
        emit(ctx, {"recovered": service.repository.recover()})


@app.command()
def backups(ctx: typer.Context) -> None:
    with operation(ctx) as service:
        path = safe_path(service.repository.root, ".backloger/.runtime/backups")
        records = []
        for file in sorted(path.glob("*.json")):
            source = safe_path(
                service.repository.root, str(file.relative_to(service.repository.root))
            )
            data = BackupRecord.model_validate(decode(read_bytes(source, 16 * 1024 * 1024)))
            records.append({"id": file.stem, "target": data.target, "event": data.event})
        emit(ctx, records)


@app.command()
def restore(
    ctx: typer.Context,
    item_id: str,
    backup: Annotated[str, typer.Option()],
    version: Annotated[int, typer.Option(min=1)],
    revision: str | None = None,
) -> None:
    with operation(ctx) as service:
        item, saved = service.restore(item_id, backup, version, revision)
        emit(ctx, {"item": item.model_dump(mode="json"), "revision": saved.revision})


@app.command()
def doctor(ctx: typer.Context) -> None:
    with operation(ctx) as service:
        snapshot = service.snapshot()
        from backloger.transactions import pending

        checks = {
            "python": sys.version.split()[0],
            "backloger": __version__,
            "storage": snapshot.storage,
            "items": len(snapshot.backlog.work_items),
            "read_only": service.repository.read_only,
            "docker_cli": shutil.which("docker") is not None,
            "pending_transactions": len(pending(service.repository.root)),
        }
        emit(ctx, checks)
        if checks["pending_transactions"]:
            raise BacklogError("Há transações pendentes; execute backloger recover")


@app.command()
def serve(
    ctx: typer.Context,
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8765,
    host: Literal["127.0.0.1", "0.0.0.0"] = "127.0.0.1",
    allow_remote: bool = False,
) -> None:
    """Iniciar aplicação local. Rede externa exige --allow-remote."""
    with operation(ctx) as service:
        service.snapshot()
        if host == "0.0.0.0" and not allow_remote:
            raise BacklogError("Use --allow-remote explicitamente para servir fora do loopback")
        import uvicorn

        from backloger.web import create_app

        uvicorn.run(
            create_app(service.repository.root, read_only=service.repository.read_only),
            host=host,
            port=port,
            proxy_headers=False,
            limit_concurrency=32,
            timeout_keep_alive=5,
            timeout_graceful_shutdown=15,
        )


def compose(ctx: typer.Context, args: list[str]) -> None:
    with operation(ctx):
        source = Path(__file__).resolve().parents[2]
        file = source / "compose.yaml"
        if not file.exists():
            raise BacklogError("Comando Docker requer checkout do código-fonte com compose.yaml")
        environment = {
            **os.environ,
            "BACKLOGER_PROJECT": str(ctx.obj["root"]),
            "BACKLOGER_READ_ONLY": str(ctx.obj["read_only"]).lower(),
        }
        result = subprocess.run(
            ["docker", "compose", "-f", str(file), *args], env=environment, check=False
        )
        raise typer.Exit(result.returncode)


@docker_app.command("up")
def docker_up(ctx: typer.Context) -> None:
    compose(ctx, ["up", "--build", "-d"])


@docker_app.command("down")
def docker_down(ctx: typer.Context) -> None:
    compose(ctx, ["down"])


@docker_app.command("logs")
def docker_logs(ctx: typer.Context) -> None:
    compose(ctx, ["logs", "--tail", "100"])
