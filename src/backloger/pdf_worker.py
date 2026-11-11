"""Isolated PDF renderer. No network, file URLs or user-supplied HTML/CSS."""

import sys
from typing import Any


def deny_resource(url: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    raise ValueError("Recursos externos não são permitidos no PDF")


def main() -> None:
    # A separate process lets the parent enforce a hard rendering timeout.
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
    from weasyprint import HTML

    source = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
    if len(source) > 8 * 1024 * 1024:
        raise ValueError("Documento excede o limite de renderização")
    content = HTML(string=source.decode(), url_fetcher=deny_resource).write_pdf()
    sys.stdout.buffer.write(content)


if __name__ == "__main__":
    main()
