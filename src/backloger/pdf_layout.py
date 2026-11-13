"""Split internally generated reports at semantic boundaries before layout."""

from dataclasses import dataclass, field
from html.parser import HTMLParser

from backloger.errors import BacklogError

PART_BYTES = 32 * 1024
MAX_PARTS = 128
TABLE_ROWS = 20
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass
class Element:
    tag: str
    start: str
    classes: set[str] = field(default_factory=set)
    children: list["Element | str"] = field(default_factory=list)
    void: bool = False

    def markup(self) -> str:
        return (
            self.start
            + "".join(markup(child) for child in self.children)
            + ("" if self.void else f"</{self.tag}>")
        )


def markup(node: Element | str) -> str:
    return node.markup() if isinstance(node, Element) else node


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Element("", "", void=True)
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(
            tag,
            self.get_starttag_text() or "",
            set((dict(attrs).get("class") or "").split()),
            void=tag in VOID,
        )
        self.stack[-1].children.append(element)
        if not element.void:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")


def card_markup(node: Element | str) -> str:
    if isinstance(node, str):
        return node
    if "item-metadata" in node.classes:
        body = next(
            child for child in node.children if isinstance(child, Element) and child.tag == "tbody"
        )
        rows = []
        for row in body.children:
            if not isinstance(row, Element):
                continue
            cells = [child for child in row.children if isinstance(child, Element)]
            fields = []
            for index in range(0, len(cells), 2):
                label = "".join(markup(child) for child in cells[index].children)
                value = "".join(markup(child) for child in cells[index + 1].children)
                fields.append(f"<strong>{label}:</strong> {value}")
            rows.append("<p>" + " · ".join(fields) + "</p>")
        return '<div class="pdf-metadata">' + "".join(rows) + "</div>"
    return (
        node.start
        + "".join(card_markup(child) for child in node.children)
        + ("" if node.void else f"</{node.tag}>")
    )


def blocks(node: Element | str) -> list[str]:
    if isinstance(node, str):
        return [node]
    if "report-subsection" in node.classes:
        return [part for child in node.children for part in blocks(child)]
    if "report-work-item" in node.classes:
        return [card_markup(node)]
    if node.tag != "table":
        return [node.markup()]
    body = next(
        (child for child in node.children if isinstance(child, Element) and child.tag == "tbody"),
        None,
    )
    if body is None:
        return [node.markup()]
    rows = [child for child in body.children if isinstance(child, Element) and child.tag == "tr"]
    if len(rows) <= TABLE_ROWS:
        return [node.markup()]
    header = "".join(markup(child) for child in node.children if child is not body)
    return [
        node.start
        + header
        + "<tbody>"
        + "".join(row.markup() for row in rows[index : index + TABLE_ROWS])
        + "</tbody></table>"
        for index in range(0, len(rows), TABLE_ROWS)
    ]


def report_parts(document: str) -> list[str]:
    """Keep charts/cards intact and repeat headers when a large table is split."""
    if len(document.encode()) <= PART_BYTES or "<main class=" not in document:
        return [document]
    parser = ReportParser()
    parser.feed(document)
    html = next(child for child in parser.root.children if isinstance(child, Element))
    head = next(
        child for child in html.children if isinstance(child, Element) and child.tag == "head"
    )
    body = next(
        child for child in html.children if isinstance(child, Element) and child.tag == "body"
    )
    main = next(
        child for child in body.children if isinstance(child, Element) and child.tag == "main"
    )
    # Global numbering is stamped after merging, so chunk-local totals stay hidden.
    style = (
        "<style>@page { @bottom-right { content: none; } }"
        "@media print { table { border-collapse: separate; border-spacing: 0; }"
        ".report-work-item { break-inside: auto; }"
        ".pdf-metadata { font-size: 7pt; padding: 5px 0; }"
        ".pdf-metadata p { margin: 0 0 2px; } }</style>"
    )
    prefix = (
        "<!doctype html>"
        + html.start
        + head.markup().replace("</head>", style + "</head>")
        + body.start
        + main.start
    )
    suffix = "</main></body></html>"
    parts: list[str] = []
    pending: list[str] = []
    size = 0
    for child in main.children:
        for block in blocks(child):
            length = len(block.encode())
            if pending and size + length > PART_BYTES:
                parts.append(prefix + "".join(pending) + suffix)
                pending, size = [], 0
            pending.append(block)
            size += length
    if pending:
        parts.append(prefix + "".join(pending) + suffix)
    if len(parts) > MAX_PARTS:
        raise BacklogError("Relatório exige mais de 128 partes de PDF; exporte HTML ou Markdown")
    return parts if len(parts) > 1 else [document]
