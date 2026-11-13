"""One Markdown source for the web document and the downloadable PDF."""

import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from backloger import exports
from backloger.errors import BacklogError
from backloger.models import Backlog
from backloger.report_charts import render_chart

PDF_TIMEOUT = 30
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
PDF_SLOTS = BoundedSemaphore(1)


class PDFUnavailable(BacklogError):
    code = "pdf_unavailable"
    http_status = 503


def render_markdown(source: str) -> str:
    # Raw HTML, images and links are disabled: the report is a local, textual
    # export, so it cannot fetch resources or create navigation from user data.
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    parser.enable("table").disable(["image", "link", "autolink"])
    tokens = parser.parse(source)
    section = tables = 0
    decorated: list[Token] = []
    inside_item = False
    inside_group = False
    for index, token in enumerate(tokens):
        if token.type == "fence" and token.info == "mermaid":
            chart = render_chart(token.content)
            if chart:
                # Only our bounded SVG generator can create trusted HTML tokens.
                token.type, token.tag, token.nesting, token.content = "html_block", "", 0, chart
        if token.type == "heading_open" and token.tag == "h2":
            if inside_group:
                decorated.append(Token("html_block", "", 0, content="</div>"))
                inside_group = False
            if inside_item:
                decorated.append(Token("html_block", "", 0, content="</article>"))
                inside_item = False
            section += 1
            token.attrSet("id", f"section-{section}")
        if token.type == "heading_open" and token.tag == "h3" and index + 1 < len(tokens):
            if inside_group:
                decorated.append(Token("html_block", "", 0, content="</div>"))
                inside_group = False
            title = tokens[index + 1].content
            if section == 7 and re.match(r"^[A-Z][A-Z0-9]{1,15}-[0-9]{3,9} — ", title):
                if inside_item:
                    decorated.append(Token("html_block", "", 0, content="</article>"))
                decorated.append(
                    Token("html_block", "", 0, content='<article class="report-work-item">')
                )
                inside_item = True
                token.attrSet("class", "work-item-title")
            else:
                decorated.append(
                    Token("html_block", "", 0, content='<div class="report-subsection">')
                )
                inside_group = True
        if token.type == "table_open":
            tables += 1
            first_cell = next(
                (
                    tokens[j].content
                    for j in range(index + 1, len(tokens))
                    if tokens[j].type == "inline"
                ),
                "",
            )
            style = (
                "executive-metrics"
                if tables == 1
                else {
                    "ID": "inventory-table",
                    "Campo": "item-metadata",
                    "Atividade bloqueada": "dependency-table",
                    "Data/hora": "history-table",
                }.get(first_cell, "")
            )
            token.attrSet("class", "report-table " + style)
        if token.type == "inline" and token.children:
            first = token.children[0]
            if first.type == "text" and first.content.startswith(("[x] ", "[ ] ")):
                first.content = ("✓ " if first.content.startswith("[x]") else "○ ") + first.content[
                    4:
                ]
        decorated.append(token)
    if inside_item:
        decorated.append(Token("html_block", "", 0, content="</article>"))
    if inside_group:
        decorated.append(Token("html_block", "", 0, content="</div>"))
    return str(parser.renderer.render(decorated, parser.options, {}))


def report_html(source: str, project_name: str, *, standalone: bool = False) -> str:
    style = (Path(__file__).parent / "static/report.css").read_text()
    actions = (
        (
            "<nav class='document-actions' aria-label='Ações do documento'>"
            "<a href='/#document'>← Voltar ao projeto</a><div>"
            "<a href='/api/v1/export/markdown' download>Markdown</a>"
            "<a href='/api/v1/export/pdf' download>Baixar PDF</a>"
            "<button id='print-document' type='button'>Imprimir</button></div></nav>"
        )
        if standalone
        else ""
    )
    script = "<script defer src='/static/report.js'></script>" if standalone else ""
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Backlog — {html.escape(project_name)}</title><style>{style}</style>{script}"
        f"</head><body>{actions}<main class='markdown-document'>"
        "<header class='report-brand'><span>BACKLOGER</span>"
        "<span>GESTÃO E ACOMPANHAMENTO DE ENTREGAS</span></header>"
        f"{render_markdown(source)}"
        "<footer>Backloger · Documento gerado a partir dos dados canônicos do projeto"
        "</footer></main>"
        "</body></html>"
    )


def pdf(
    backlog: Backlog,
    *,
    events: list[dict[str, Any]] | None = None,
    at: datetime | None = None,
    source: str | None = None,
) -> bytes:
    source = source if source is not None else exports.markdown(backlog, events=events, at=at)
    if len(source.encode()) > MAX_DOCUMENT_BYTES:
        raise BacklogError(
            "Documento maior que 2 MiB; exporte Markdown para processá-lo localmente"
        )
    return render_pdf(report_html(source, backlog.project.name))


def render_pdf(document: str) -> bytes:
    """Render internally generated HTML through the same isolated worker."""
    if len(document.encode()) > 8 * 1024 * 1024:
        raise BacklogError("Documento excede 8 MiB; reduza a visão exportada")
    if not PDF_SLOTS.acquire(blocking=False):
        raise PDFUnavailable("Há um PDF sendo gerado; aguarde e tente novamente")
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-m", "backloger.pdf_worker"],
            input=document.encode(),
            capture_output=True,
            timeout=PDF_TIMEOUT,
            check=False,
        )
        if result.returncode or not result.stdout.startswith(b"%PDF-"):
            raise PDFUnavailable(
                "Não foi possível gerar o PDF. Verifique WeasyPrint/Pango no ambiente "
                "ou baixe o Markdown."
            )
        if len(result.stdout) > 32 * 1024 * 1024:
            raise BacklogError("PDF excedeu o limite de 32 MiB")
        return result.stdout
    except subprocess.TimeoutExpired as exc:
        raise PDFUnavailable(
            "O PDF excedeu 30 segundos; baixe o Markdown ou reduza o documento"
        ) from exc
    finally:
        PDF_SLOTS.release()
