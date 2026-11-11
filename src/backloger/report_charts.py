"""Portable Mermaid charts and bounded, script-free SVG for HTML and PDF."""

import html
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Number = Annotated[float, Field(ge=0, le=1_000_000, allow_inf_nan=False)]
Label = Annotated[str, Field(min_length=1, max_length=180)]
COLORS = ("#286856", "#df8853", "#7d97ba", "#ba6271", "#929b8f", "#a590bd")
PREFIX = "%% backloger-chart-v1 "


class Series(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Label
    values: Annotated[list[Number | None], Field(min_length=1, max_length=60)]


class Chart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["donut", "bar", "line"]
    title: Label
    labels: Annotated[list[Label], Field(min_length=1, max_length=60)]
    series: Annotated[list[Series], Field(min_length=1, max_length=3)]
    colors: Annotated[
        list[Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]], Field(max_length=60)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def matching_lengths(self) -> "Chart":
        if any(len(series.values) != len(self.labels) for series in self.series):
            raise ValueError("Séries e rótulos devem ter o mesmo tamanho")
        if self.colors and len(self.colors) != len(self.labels):
            raise ValueError("Cores e rótulos devem ter o mesmo tamanho")
        return self


def mermaid_label(value: str) -> str:
    # Entity escapes are understood by Mermaid, without allowing its grammar,
    # directives or HTML to be injected through project/status/owner names.
    return "".join(c if c.isalnum() or c in " /.-_" else f"#{ord(c)};" for c in value)


def chart_markdown(chart: Chart) -> str:
    data = chart.model_dump_json()
    lines = ["```mermaid", PREFIX + data]
    if chart.kind == "donut":
        lines.extend(["pie showData", f"    title {mermaid_label(chart.title)}"])
        lines.extend(
            f'    "{mermaid_label(label)}" : {value:g}'
            for label, value in zip(chart.labels, chart.series[0].values, strict=True)
            if value is not None and value > 0
        )
    else:
        # Mermaid has no null samples: only observed dates are plotted there.
        # The embedded metadata retains gaps for the native SVG renderer.
        indices = [
            index for index in range(len(chart.labels)) if chart.series[0].values[index] is not None
        ]
        labels = [mermaid_label(chart.labels[index]) for index in indices]
        maximum = max((v for s in chart.series for v in s.values if v is not None), default=1)
        lines.extend(
            [
                "xychart-beta",
                f'    title "{mermaid_label(chart.title)}"',
                "    x-axis [" + ", ".join(json.dumps(label) for label in labels) + "]",
                f'    y-axis "Atividades" 0 --> {max(1, math.ceil(maximum))}',
            ]
        )
        for series in chart.series:
            values = [series.values[index] for index in indices]
            if values and all(value is not None for value in values):
                lines.append(
                    "    "
                    + ("line" if chart.kind == "line" else "bar")
                    + " ["
                    + ", ".join(f"{value:g}" for value in values if value is not None)
                    + "]"
                )
    return "\n".join([*lines, "```", ""])


def _text(x: float, y: float, value: str, *, size: int = 12, anchor: str = "start") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="#455b57">{html.escape(value)}</text>'
    )


def _donut(chart: Chart) -> tuple[int, list[str]]:
    values = chart.series[0].values
    total = sum(value or 0 for value in values)
    height = max(245, 60 + len(chart.labels) * 28)
    parts = ['<circle cx="128" cy="126" r="76" fill="none" stroke="#e8eeeb" stroke-width="30"/>']
    offset = 0.0
    for index, (label, value) in enumerate(zip(chart.labels, values, strict=True)):
        amount = value or 0
        color = chart.colors[index] if chart.colors else COLORS[index % len(COLORS)]
        if total and amount:
            length = amount / total * 2 * math.pi * 76
            parts.append(
                f'<circle cx="128" cy="126" r="76" fill="none" stroke="{color}" '
                f'stroke-width="30" stroke-dasharray="{length:.4f} {2 * math.pi * 76:.4f}" '
                f'stroke-dashoffset="{-offset:.4f}" transform="rotate(-90 128 126)"/>'
            )
            offset += length
        y = 55 + index * 28
        parts.extend(
            [
                f'<rect x="255" y="{y - 10}" width="10" height="10" rx="2" fill="{color}"/>',
                _text(278, y, label[:38]),
                _text(648, y, f"{amount:g} · {amount / total:.0%}" if total else "0", anchor="end"),
            ]
        )
    parts.extend(
        [
            _text(128, 130, f"{total:g}", size=32, anchor="middle"),
            _text(128, 152, "atividades", size=11, anchor="middle"),
        ]
    )
    return height, parts


def _plot(chart: Chart) -> tuple[int, list[str]]:
    left, top, width, height = 52, 24, 584, 165
    maximum = max(1, max((v for s in chart.series for v in s.values if v is not None), default=1))
    maximum = max(1, math.ceil(maximum / 4)) * 4
    parts = []
    for tick in range(5):
        y = top + height * tick / 4
        parts.extend(
            [
                f'<path d="M{left},{y} h{width}" stroke="#e5ece8" fill="none"/>',
                _text(left - 10, y + 4, f"{maximum * (4 - tick) / 4:g}", size=10, anchor="end"),
            ]
        )
    count = len(chart.labels)

    def x_for(index: int) -> float:
        return left + (index + 0.5) * width / count

    for index, label in enumerate(chart.labels):
        if count <= 10 or index in {0, count - 1} or index % max(1, count // 6) == 0:
            parts.append(
                _text(x_for(index), top + height + 22, label[:18], size=10, anchor="middle")
            )
    for series_index, series in enumerate(chart.series):
        color = COLORS[series_index]
        previous: tuple[float, float] | None = None
        for index, value in enumerate(series.values):
            if value is None:
                previous = None
                continue
            x, y = x_for(index), top + height - value / maximum * height
            if chart.kind == "bar":
                bar_width = min(50, width / count * 0.7 / len(chart.series))
                x += (series_index - (len(chart.series) - 1) / 2) * bar_width
                parts.append(
                    f'<rect x="{x - bar_width / 2:.2f}" y="{y:.2f}" '
                    f'width="{bar_width - 2:.2f}" height="{value / maximum * height:.2f}" '
                    f'rx="3" fill="{color}"/>'
                )
                if count <= 8:
                    parts.append(_text(x, y - 7, f"{value:g}", size=10, anchor="middle"))
            else:
                if previous:
                    dash = ' stroke-dasharray="6 4"' if series_index else ""
                    parts.append(
                        f'<path d="M{previous[0]:.2f},{previous[1]:.2f} L{x:.2f},{y:.2f}" '
                        f'stroke="{color}" stroke-width="2.5" fill="none"{dash}/>'
                    )
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"/>')
                previous = x, y
    for index, series in enumerate(chart.series):
        x = 52 + index * 195
        parts.extend(
            [
                f'<rect x="{x}" y="234" width="10" height="10" rx="2" fill="{COLORS[index]}"/>',
                _text(x + 18, 243, series.name, size=11),
            ]
        )
    return 263, parts


def render_chart(content: str) -> str | None:
    """Render only the versioned, validated metadata emitted by this exporter."""
    first = content.split("\n", 1)[0]
    if not first.startswith(PREFIX) or len(content) > 64_000:
        return None
    try:
        chart = Chart.model_validate_json(first[len(PREFIX) :])
    except (ValidationError, ValueError):
        return None
    height, parts = _donut(chart) if chart.kind == "donut" else _plot(chart)
    title = html.escape(chart.title, quote=True)
    return (
        f'<figure class="report-chart"><svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 680 {height}" role="img" aria-label="{title}" '
        'font-family="DejaVu Sans, sans-serif">'
        f"<title>{title}</title>{''.join(parts)}</svg></figure>\n"
    )
