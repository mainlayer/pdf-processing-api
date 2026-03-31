"""PDF processor — thin re-export from pdf_processor for cleaner imports.

The actual implementation lives in pdf_processor.py (which uses pypdf).
This module provides a stable public API for the main.py layer.
"""

from .pdf_processor import (
    extract_tables,
    extract_text,
    get_page_count,
    merge_pdfs,
    split_pdf,
    summarize,
)

__all__ = [
    "get_page_count",
    "extract_text",
    "extract_tables",
    "summarize",
    "split_pdf",
    "merge_pdfs",
]
