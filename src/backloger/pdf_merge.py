"""Merge only PDFs created by our isolated renderer and stamp global pagination."""

import io

MAX_PDF_BYTES = 32 * 1024 * 1024


class PDFLimitError(ValueError):
    pass


def merge(parts: list[bytes]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for part in parts:
        reader = PdfReader(io.BytesIO(part))
        if not writer.pages and reader.metadata:
            writer.add_metadata({"/Title": reader.metadata.title or "Backlog"})
        writer.append(reader)
        if len(writer.pages) > 2000:
            raise PDFLimitError("PDF excedeu 2000 páginas")
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    total = len(writer.pages)
    for number, page in enumerate(writer.pages, 1):
        resources = page["/Resources"]
        if not isinstance(resources, DictionaryObject):
            raise ValueError("Recursos de página inválidos")
        if "/Font" not in resources:
            resources[NameObject("/Font")] = DictionaryObject()
        fonts = resources["/Font"]
        if not isinstance(fonts, DictionaryObject):
            raise ValueError("Fontes de página inválidas")
        fonts[NameObject("/BacklogerPageNumber")] = font
        label = f"{number} / {total}"
        x = float(page.mediabox.right) - 43 - len(label) * 4
        # WeasyPrint flips its content coordinate system. Isolate that graphics
        # state so the final footer uses normal PDF coordinates and orientation.
        stamp = (
            "\nQ\nq 0.157 0.408 0.337 rg BT /BacklogerPageNumber 8 Tf "
            f"{x:g} 28 Td ({label}) Tj ET Q\n"
        ).encode("ascii")
        prefix = DecodedStreamObject()
        prefix.set_data(b"q\n")
        stream = DecodedStreamObject()
        stream.set_data(stamp)
        previous = page.raw_get("/Contents") if "/Contents" in page else None
        resolved = previous.get_object() if previous is not None else None
        contents = ArrayObject([writer._add_object(prefix)])
        contents.extend(
            list(resolved) if isinstance(resolved, ArrayObject) else [previous] if previous else []
        )
        contents.append(writer._add_object(stream))
        page[NameObject("/Contents")] = contents
    output = io.BytesIO()
    writer.write(output)
    if output.tell() > MAX_PDF_BYTES:
        raise PDFLimitError("PDF excedeu 32 MiB")
    return output.getvalue()
