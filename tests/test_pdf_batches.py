import io
import signal
import subprocess
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from backloger import documents, exports, pdf_layout
from backloger.models import Backlog, Project, WorkItem


def report(count: int) -> Backlog:
    return Backlog(
        project=Project(name="Relatório completo", key="SYS"),
        work_items=[
            WorkItem(
                id=f"SYS-{number:03}",
                title=f"Entrega exclusiva {number}",
                description=(
                    f"Escopo integral {number}: ação, revisão e validação <script> & dados."
                ),
                owner=f"Equipe {number}",
                labels=["auditoria"],
                estimate={"unit": "hours", "value": number},
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                updated_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
            for number in range(1, count + 1)
        ],
    )


@pytest.mark.unit
def test_large_report_parts_preserve_every_card_field_and_inventory_row() -> None:
    backlog = report(482)
    source = exports.markdown(backlog)
    html = documents.report_html(source, backlog.project.name)
    parts = pdf_layout.report_parts(html)
    assert 1 < len(parts) <= pdf_layout.MAX_PARTS
    combined = "".join(parts)
    assert combined.count('class="report-work-item"') == 482
    assert '<table class="report-table item-metadata"' not in combined
    assert combined.count('class="pdf-metadata"') == 482
    assert combined.count('class="report-table inventory-table"') > 1
    for number in range(1, 483):
        assert f"Entrega exclusiva {number}</h3>" in combined
        assert f"Escopo integral {number}:" in combined
        assert f"Equipe {number}" in combined
    assert "&lt;script&gt; &amp; dados." in combined
    assert "Critérios de leitura" in combined
    assert all(part.endswith("</main></body></html>") for part in parts)
    assert source == exports.markdown(backlog)


@pytest.mark.unit
def test_single_fragment_keeps_original_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_layout, "PART_BYTES", 100)
    html = (
        "<html><head><style>" + " " * 100 + "</style></head><body>"
        '<main class="markdown-document"><p>Texto curto</p></main></body></html>'
    )
    assert pdf_layout.report_parts(html) == [html]


@pytest.mark.integration
def test_multipart_pdf_has_full_text_and_continuous_global_page_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pdf_layout, "PART_BYTES", 8 * 1024)
    backlog = report(4)
    source = exports.markdown(backlog)
    assert len(pdf_layout.report_parts(documents.report_html(source, backlog.project.name))) > 1
    result = documents.pdf(backlog, source=source)
    reader = PdfReader(io.BytesIO(result))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for number in range(1, 5):
        assert f"Entrega exclusiva {number}" in text
        assert f"Escopo integral {number}:" in text
        assert f"Equipe {number}" in text
    assert "Estado:" in text and "Estimativa:" in text and "Criação (UTC):" in text
    assert "<script> & dados." in text
    for number, page in enumerate(reader.pages, 1):
        label = f"{number} / {len(reader.pages)}"
        coordinates = []

        def visitor(text, cm, tm, font, size, expected=label, found=coordinates):
            if text.strip() == expected:
                found.append((cm, tm, size))

        assert page.extract_text(visitor_text=visitor).rstrip().endswith(label)
        assert len(coordinates) == 1
        cm, tm, size = coordinates[0]
        assert cm == [1, 0, 0, 1, 0, 0]
        assert tm[5] == 28 and size == 8
    assert reader.metadata is not None and "Relatório completo" in reader.metadata.title


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exit_code", "diagnostic", "message"),
    [
        (1, b"BACKLOGER_PDF_ERROR:memory\n", "limite de memória"),
        (1, b"BACKLOGER_PDF_ERROR:dependencies\n", "WeasyPrint/Pango"),
        (1, b"BACKLOGER_PDF_ERROR:limits\n", "32 MiB ou 2.000 páginas"),
        (-signal.SIGXCPU, b"", "limite de recursos"),
        (-signal.SIGALRM, b"", "parte do PDF excedeu 30 segundos"),
        (-signal.SIGSEGV, b"", "renderizador falhou"),
        (0, b"", "renderizador falhou"),
    ],
)
def test_renderer_reports_actual_failure_and_releases_slot(
    exit_code: int,
    diagnostic: bytes,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess("pdf", exit_code, b"", diagnostic + b"private data")

    monkeypatch.setattr(documents.subprocess, "run", failed)
    for _ in range(2):
        with pytest.raises(documents.PDFUnavailable, match=message) as error:
            documents.render_pdf("<html>Seguro</html>")
        assert "private data" not in str(error.value)
    assert "private data" not in caplog.text


@pytest.mark.unit
def test_batch_pdf_timeout_is_bounded_and_releases_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "report_parts", lambda source: [source, source])
    calls = []

    def timeout(*args: object, **kwargs: object) -> None:
        calls.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired("pdf", 300)

    monkeypatch.setattr(documents.subprocess, "run", timeout)
    for _ in range(2):
        with pytest.raises(documents.PDFUnavailable, match="300 segundos"):
            documents.render_pdf("<html>Relatório em partes</html>")
    assert calls == [300, 300]
