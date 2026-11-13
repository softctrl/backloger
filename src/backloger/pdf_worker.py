"""Isolated PDF renderer. No network, file URLs or user-supplied HTML/CSS."""

import gc
import json
import signal
import sys
from typing import Any

from backloger.pdf_layout import MAX_PARTS
from backloger.pdf_merge import MAX_PDF_BYTES, PDFLimitError


def deny_resource(url: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    raise ValueError("Recursos externos não são permitidos no PDF")


def main() -> None:
    import resource

    batch = sys.argv[1:] == ["--batch"]
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    cpu = 250 if batch else 25
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    try:
        try:
            from weasyprint import HTML
            from weasyprint.text.fonts import FontConfiguration
        except (ImportError, OSError):
            sys.stderr.write("BACKLOGER_PDF_ERROR:dependencies\n")
            raise SystemExit(1) from None
        limit = (16 if batch else 8) * 1024 * 1024
        source = sys.stdin.buffer.read(limit + 1)
        if len(source) > limit:
            raise ValueError("Documento excede o limite de renderização")
        fragments = json.loads(source) if batch else [source.decode()]
        if (
            not isinstance(fragments, list)
            or not 1 <= len(fragments) <= MAX_PARTS
            or not all(isinstance(part, str) for part in fragments)
        ):
            raise ValueError("Partes de PDF inválidas")
        fonts = FontConfiguration()
        parts: list[bytes] = []
        size = 0
        for fragment in fragments:
            signal.alarm(30)
            content = HTML(string=fragment, url_fetcher=deny_resource).write_pdf(font_config=fonts)
            signal.alarm(0)
            size += len(content)
            if size > MAX_PDF_BYTES:
                raise PDFLimitError("PDF excedeu 32 MiB")
            parts.append(content)
            gc.collect()
        if batch:
            from backloger.pdf_merge import merge

            signal.alarm(30)
            content = merge(parts)
            signal.alarm(0)
        else:
            content = parts[0]
        sys.stdout.buffer.write(content)
    except MemoryError:
        sys.stderr.write("BACKLOGER_PDF_ERROR:memory\n")
        raise SystemExit(1) from None
    except ImportError:
        sys.stderr.write("BACKLOGER_PDF_ERROR:dependencies\n")
        raise SystemExit(1) from None
    except PDFLimitError:
        sys.stderr.write("BACKLOGER_PDF_ERROR:limits\n")
        raise SystemExit(1) from None
    except Exception as exc:
        sys.stderr.write(f"BACKLOGER_PDF_ERROR:rendering:{type(exc).__name__}\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
