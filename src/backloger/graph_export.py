"""Canonical graph exports: callers provide bounded geometry, never markup."""

import html
import math
import textwrap
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backloger import documents
from backloger.errors import BacklogError
from backloger.graph import analyze
from backloger.models import Backlog, Identifier

Coordinate = Annotated[float, Field(ge=-10_000_000, le=10_000_000, allow_inf_nan=False)]


class GraphPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: Coordinate
    y: Coordinate
    width: Annotated[float, Field(ge=40, le=400, allow_inf_nan=False)] = 200
    height: Annotated[float, Field(ge=24, le=180, allow_inf_nan=False)] = 72


class GraphExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    positions: Annotated[dict[Identifier, GraphPosition], Field(min_length=1, max_length=2000)]
    scope: Literal["project", "remaining"] = "remaining"
    highlight_critical: bool = False


class GraphDocument:
    def __init__(self, backlog: Backlog, request: GraphExport):
        items = {item.id: item for item in backlog.work_items}
        if not set(request.positions) <= items.keys():
            raise BacklogError("A visão contém uma atividade inexistente neste projeto")
        self.backlog = backlog
        self.request = request
        self.items = {key: items[key] for key in request.positions}
        self.analysis = analyze(backlog, blocker_limit=1)
        self.schedule = self.analysis["critical_paths"][request.scope]
        self.edges = [
            edge
            for edge in self.analysis["edges"]
            if edge["source"] in self.items and edge["target"] in self.items
        ]
        self.categories = {status.id: status.category for status in backlog.project.statuses}
        self.statuses = {status.id: status.name for status in backlog.project.statuses}
        positions = request.positions.values()
        left = min(p.x - p.width / 2 for p in positions) - 45
        top = min(p.y - p.height / 2 for p in positions) - 45
        right = max(p.x + p.width / 2 for p in positions) + 45
        bottom = max(p.y + p.height / 2 for p in positions) + 45
        self.bounds = (left, top, right - left, bottom - top)

    def svg(self, bounds: tuple[float, float, float, float] | None = None, marker: int = 0) -> str:
        x, y, width, height = bounds or self.bounds
        critical_nodes = set(self.schedule["nodes"]) if self.request.highlight_critical else set()
        critical_edges = {(edge["source"], edge["target"]) for edge in self.schedule["edges"]}
        output = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {width:g} {height:g}" '
            'role="img" aria-label="Grafo de dependências" font-family="DejaVu Sans, sans-serif">',
            '<defs><marker id="arrow' + str(marker) + '" markerWidth="8" markerHeight="8" '
            'refX="7" refY="4" orient="auto-start-reverse"><path d="M0,0 L8,4 L0,8" '
            'fill="#6e8373"/></marker></defs>',
            f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" fill="#fff"/>',
        ]
        for edge in self.edges:
            a, b = self.request.positions[edge["source"]], self.request.positions[edge["target"]]
            if (
                max(a.x, b.x) < x
                or min(a.x, b.x) > x + width
                or max(a.y, b.y) < y
                or min(a.y, b.y) > y + height
            ):
                continue
            horizontal = abs(b.x - a.x) >= abs(b.y - a.y)
            direction = 1 if (b.x >= a.x if horizontal else b.y >= a.y) else -1
            ax, ay = (
                (a.x + direction * a.width / 2, a.y)
                if horizontal
                else (a.x, a.y + direction * a.height / 2)
            )
            bx, by = (
                (b.x - direction * b.width / 2, b.y)
                if horizontal
                else (b.x, b.y - direction * b.height / 2)
            )
            color = (
                "#c64d25"
                if self.request.highlight_critical
                and (edge["source"], edge["target"]) in critical_edges
                else "#8a9b91"
            )
            output.append(
                f'<path d="M{ax:g},{ay:g} L{bx:g},{by:g}" fill="none" stroke="{color}" '
                f'stroke-width="2" marker-end="url(#arrow{marker})"/>'
            )
        colors = {
            "pending": "#edf1e8",
            "active": "#fff0d7",
            "done": "#e1eee4",
            "cancelled": "#f1f2ef",
        }
        for key, item in self.items.items():
            point = self.request.positions[key]
            px, py = point.x - point.width / 2, point.y - point.height / 2
            if px + point.width < x or px > x + width or py + point.height < y or py > y + height:
                continue
            color = "#c64d25" if key in critical_nodes else "#829b88"
            fill = colors[self.categories[item.status]]
            output.append(f"<g><title>{html.escape(key + ' · ' + item.title)}</title>")
            output.append(
                f'<rect x="{px:g}" y="{py:g}" width="{point.width:g}" height="{point.height:g}" '
                f'rx="7" fill="{fill}" stroke="{color}" stroke-width="2"/>'
            )
            output.append(
                f'<text x="{point.x:g}" y="{py + 18:g}" font-size="12" text-anchor="middle" '
                f'font-weight="bold" fill="#264535">{html.escape(key)}</text>'
            )
            if point.height >= 60:
                lines = textwrap.wrap(item.title, width=max(10, int(point.width / 7)))
                if len(lines) > 2:
                    lines[1] = lines[1][:-1] + "…"
                lines = lines[:2]
                for index, line in enumerate(lines):
                    output.append(
                        f'<text x="{point.x:g}" y="{py + 36 + index * 14:g}" font-size="11" '
                        f'text-anchor="middle" fill="#40583f">{html.escape(line)}</text>'
                    )
            output.append("</g>")
        return "".join([*output, "</svg>"])

    def pdf(self) -> bytes:
        left, top, width, height = self.bounds
        columns, rows = math.ceil(width / 1080), math.ceil(height / 620)
        if columns * rows > 36:
            raise BacklogError(
                "A visão exige mais de 36 páginas de grafo. Use uma vizinhança menor, "
                "reorganize o grafo ou exporte SVG para zoom sem perda."
            )
        title = html.escape(self.backlog.project.name)
        if self.schedule["method"] == "estimate":
            unit = {"hours": "horas", "days": "dias", "points": "pontos"}[self.schedule["unit"]]
            mode = f"Caminho crítico por estimativas: {self.schedule['duration']:g} {unit}"
        elif self.schedule["method"] == "structure":
            mode = "Cadeia de precedência sem previsão de duração"
        else:
            mode = "Nenhuma atividade pendente no escopo de cálculo"
        scope = "atividades restantes" if self.request.scope == "remaining" else "projeto completo"
        pages = [
            f"<section><h1>Dependências — {title}</h1><p>{len(self.items)} atividades · "
            f"{len(self.edges)} relações · {mode}. {html.escape(self.schedule['reason'])}</p>"
            f"<p>Cálculo: {scope}. O desenho inclui somente as atividades da visão exportada; "
            "filtros não alteram a duração calculada para esse escopo.</p>"
        ]
        if columns * rows > 1:
            pages.append(
                "<p>Panorama. As páginas seguintes dividem o grafo em regiões "
                "para preservar a leitura.</p>"
            )
        pages.extend([self.svg(), "</section>"])
        if columns * rows > 1:
            for row in range(rows):
                for column in range(columns):
                    tile = (
                        left + column * 1080,
                        top + row * 620,
                        min(1080, width - column * 1080),
                        min(620, height - row * 620),
                    )
                    pages.append(
                        f"<section><h2>Região {row + 1}, {column + 1}</h2>"
                        f"{self.svg(tile, 1 + row * columns + column)}</section>"
                    )
        pages.append(
            '<section class="inventory"><h2>Atividades da visão exportada</h2>'
            "<p>Pré-requisito → dependente. Laranja destaca as rotas selecionadas. "
            "Estimativas técnicas não representam uma previsão de calendário.</p>"
            "<table><thead><tr><th>ID</th><th>Atividade</th><th>Estado</th>"
            "<th>Pré-requisitos diretos</th></tr></thead><tbody>"
        )
        parents: dict[str, list[str]] = {key: [] for key in self.items}
        for edge in self.analysis["edges"]:
            if edge["target"] in parents:
                label = edge["source"]
                if label not in self.items:
                    label += " (fora da visão)"
                parents[edge["target"]].append(label)
        for key, item in sorted(self.items.items()):
            cells = [key, item.title, self.statuses[item.status], ", ".join(parents[key]) or "—"]
            pages.append(
                "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in cells) + "</tr>"
            )
        pages.append("</tbody></table></section>")
        content = "".join(pages)
        if len(content.encode()) > documents.MAX_DOCUMENT_BYTES:
            raise BacklogError("Grafo maior que 2 MiB; reduza a visão ou exporte SVG")
        style = (Path(__file__).parent / "static/graph-report.css").read_text()
        return documents.render_pdf(
            f'<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            f"<title>Dependências — {title}</title><style>{style}</style>"
            f"<body>{content}</body></html>"
        )
