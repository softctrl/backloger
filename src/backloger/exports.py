"""Deterministic reports with context-specific output escaping."""

import csv
import html
import io

import networkx as nx

from backloger.graph import dependency_graph
from backloger.models import Backlog
from backloger.report_markdown import markdown as markdown


def csv_report(backlog: Backlog) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["id", "title", "type", "status", "priority", "owner"])
    for item in sorted(backlog.work_items, key=lambda i: i.id):
        row = [item.id, item.title, item.type, item.status, item.priority, item.owner or ""]
        # CSV formula injection also applies to tab and CR-prefixed cells.
        writer.writerow(
            ["'" + c if c.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else c for c in row]
        )
    return stream.getvalue()


def mermaid(backlog: Backlog) -> str:
    graph = dependency_graph(backlog)
    lines = ["flowchart LR"]
    ids = {item.id: f"n{index}" for index, item in enumerate(backlog.work_items)}
    for item in backlog.work_items:
        label = f"{item.id}: {item.title}"
        # Mermaid entity escapes avoid breaking its quoted label grammar.
        label = "".join(c if c.isalnum() or c in " :.,-_" else f"#{ord(c)};" for c in label)
        lines.append(f'  {ids[item.id]}["{label}"]')
    lines.extend(f"  {ids[a]} --> {ids[b]}" for a, b in sorted(graph.edges))
    return "\n".join(lines) + "\n"


def svg(backlog: Backlog) -> str:
    graph = dependency_graph(backlog)
    levels = list(nx.topological_generations(graph))
    positions = {
        node: (40 + level * 290, 40 + index * 90)
        for level, nodes in enumerate(levels)
        for index, node in enumerate(sorted(nodes))
    }
    width = max(400, len(levels) * 290 + 40)
    height = max(160, max((len(level) for level in levels), default=1) * 90 + 40)
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Dependências">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" '
        'refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#686e78"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#f6f5f0"/>',
    ]
    for a, b in sorted(graph.edges):
        x, y = positions[a]
        tx, ty = positions[b]
        output.append(
            f'<path d="M{x + 240},{y + 25} L{tx},{ty + 25}" stroke="#686e78" '
            'fill="none" marker-end="url(#arrow)"/>'
        )
    for item in backlog.work_items:
        x, y = positions[item.id]
        output.extend(
            [
                f'<rect x="{x}" y="{y}" width="240" height="54" rx="8" '
                'fill="white" stroke="#c6c8c4"/>',
                f'<text x="{x + 10}" y="{y + 21}" font-family="sans-serif" '
                f'font-size="12">{html.escape(item.id)}</text>',
                f'<text x="{x + 10}" y="{y + 41}" font-family="sans-serif" '
                f'font-size="12">{html.escape(item.title[:28])}</text>',
            ]
        )
    return "\n".join([*output, "</svg>"]) + "\n"
