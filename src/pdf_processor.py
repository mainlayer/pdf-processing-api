"""PDF operations using pypdf (pure-Python, no native deps required).

All public functions are synchronous — they are called inside
`run_in_executor` from the async FastAPI handlers so the event loop
is never blocked.
"""

from __future__ import annotations

import base64
import io
import textwrap
from typing import Any

# ---------------------------------------------------------------------------
# Import strategy: prefer pypdf (maintained fork of PyPDF2).
# Fall back gracefully with an informative error at import time.
# ---------------------------------------------------------------------------
try:
    from pypdf import PdfReader, PdfWriter  # type: ignore[import]
    _PYPDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYPDF_AVAILABLE = False


def _require_pypdf() -> None:
    if not _PYPDF_AVAILABLE:
        raise RuntimeError(
            "pypdf is not installed. Run: pip install pypdf"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_pdf(data: bytes) -> "PdfReader":
    """Return a PdfReader from raw bytes."""
    _require_pypdf()
    return PdfReader(io.BytesIO(data))


def _writer_to_bytes(writer: "PdfWriter") -> bytes:
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _page_text(page: Any) -> str:  # noqa: ANN401
    """Extract text from a single pypdf page object."""
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def _simple_table_detection(text: str) -> list[list[str]] | None:
    """Heuristic table detection from plain text.

    Returns a list-of-rows (each row is a list of cell strings), or None
    if no table structure is detected.  This is intentionally simple —
    replace with a dedicated library (pdfplumber, camelot, etc.) for
    production use.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None

    # Look for lines that have 2+ tab or multi-space delimited columns
    table_rows: list[list[str]] = []
    for line in lines:
        # Try tab-separated first
        if "\t" in line:
            cells = [c.strip() for c in line.split("\t") if c.strip()]
        else:
            # Fall back to 2+ consecutive spaces as delimiter
            import re
            cells = [c.strip() for c in re.split(r"  +", line) if c.strip()]

        if len(cells) >= 2:
            table_rows.append(cells)

    return table_rows if len(table_rows) >= 2 else None


def _normalise_table(raw_rows: list[list[str]]) -> list[list[str]]:
    """Pad all rows to the same column width."""
    if not raw_rows:
        return []
    max_cols = max(len(r) for r in raw_rows)
    return [r + [""] * (max_cols - len(r)) for r in raw_rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_page_count(data: bytes) -> int:
    """Return the number of pages in a PDF."""
    reader = _read_pdf(data)
    return len(reader.pages)


def extract_text(data: bytes) -> dict[str, Any]:
    """Extract text from every page.

    Returns::

        {
            "page_count": int,
            "pages": [{"page": 1, "text": "..."}, ...],
            "total_characters": int,
        }
    """
    reader = _read_pdf(data)
    pages = []
    total_chars = 0

    for idx, page in enumerate(reader.pages, start=1):
        text = _page_text(page)
        pages.append({"page": idx, "text": text})
        total_chars += len(text)

    return {
        "page_count": len(reader.pages),
        "pages": pages,
        "total_characters": total_chars,
    }


def extract_tables(data: bytes) -> dict[str, Any]:
    """Extract tables from every page using heuristic text analysis.

    Returns::

        {
            "page_count": int,
            "tables_found": int,
            "tables": [
                {
                    "page": 1,
                    "table_index": 0,
                    "rows": int,
                    "cols": int,
                    "data": [[str, ...], ...],
                },
                ...
            ],
        }
    """
    reader = _read_pdf(data)
    tables: list[dict[str, Any]] = []
    table_index = 0

    for idx, page in enumerate(reader.pages, start=1):
        text = _page_text(page)
        raw = _simple_table_detection(text)
        if raw is not None:
            normalised = _normalise_table(raw)
            tables.append(
                {
                    "page": idx,
                    "table_index": table_index,
                    "rows": len(normalised),
                    "cols": len(normalised[0]) if normalised else 0,
                    "data": normalised,
                }
            )
            table_index += 1

    return {
        "page_count": len(reader.pages),
        "tables_found": len(tables),
        "tables": tables,
    }


def summarize(data: bytes) -> dict[str, Any]:
    """Generate a basic extractive summary of the PDF.

    Returns::

        {
            "page_count": int,
            "summary": str,
            "key_points": [str, ...],
            "word_count": int,
        }
    """
    reader = _read_pdf(data)
    all_text = "\n\n".join(_page_text(p) for p in reader.pages)
    words = all_text.split()
    word_count = len(words)

    # Extractive summary: take the first ~150 words as an overview paragraph.
    overview = " ".join(words[:150])
    if word_count > 150:
        overview += "..."

    # Key points: take the first sentence-like fragment from each page
    # (lines that end in a period and are longer than 40 chars).
    key_points: list[str] = []
    for page in reader.pages:
        text = _page_text(page)
        for line in text.splitlines():
            line = line.strip()
            if len(line) > 40 and line.endswith("."):
                # Wrap long lines for readability
                point = textwrap.shorten(line, width=200, placeholder="...")
                if point not in key_points:
                    key_points.append(point)
                break
        if len(key_points) >= 10:
            break

    summary = (
        f"This document contains {len(reader.pages)} page(s) and approximately "
        f"{word_count:,} words.\n\n{overview}"
    )

    return {
        "page_count": len(reader.pages),
        "summary": summary,
        "key_points": key_points,
        "word_count": word_count,
    }


def split_pdf(data: bytes) -> dict[str, Any]:
    """Split a PDF into individual single-page PDFs.

    Returns::

        {
            "page_count": int,
            "pages": [
                {
                    "page": 1,
                    "filename": "page_001.pdf",
                    "size_bytes": int,
                    "content_b64": str,   # base64-encoded PDF
                },
                ...
            ],
        }
    """
    reader = _read_pdf(data)
    pages: list[dict[str, Any]] = []

    for idx, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        page_bytes = _writer_to_bytes(writer)
        pages.append(
            {
                "page": idx,
                "filename": f"page_{idx:03d}.pdf",
                "size_bytes": len(page_bytes),
                "content_b64": base64.b64encode(page_bytes).decode(),
            }
        )

    return {
        "page_count": len(reader.pages),
        "pages": pages,
    }


def merge_pdfs(files_data: list[bytes], output_filename: str = "merged.pdf") -> dict[str, Any]:
    """Merge multiple PDFs into a single document.

    Returns::

        {
            "output_filename": str,
            "total_pages": int,
            "merged_file_size_bytes": int,
            "content_b64": str,   # base64-encoded merged PDF
        }
    """
    _require_pypdf()
    writer = PdfWriter()
    total_pages = 0

    for pdf_bytes in files_data:
        reader = _read_pdf(pdf_bytes)
        for page in reader.pages:
            writer.add_page(page)
            total_pages += 1

    merged_bytes = _writer_to_bytes(writer)

    return {
        "output_filename": output_filename,
        "total_pages": total_pages,
        "merged_file_size_bytes": len(merged_bytes),
        "content_b64": base64.b64encode(merged_bytes).decode(),
    }
