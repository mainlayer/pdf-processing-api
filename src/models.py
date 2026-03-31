"""Pydantic models for the PDF processing API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OperationType(str, Enum):
    EXTRACT_TEXT = "extract_text"
    EXTRACT_TABLES = "extract_tables"
    SUMMARIZE = "summarize"
    SPLIT = "split"
    MERGE = "merge"


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


class PricingEntry(BaseModel):
    operation: str
    unit: str
    price_usd: float
    description: str


class PricingResponse(BaseModel):
    currency: str = "USD"
    pricing: list[PricingEntry]
    note: str


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentRequest(BaseModel):
    operation: OperationType
    page_count: int = Field(ge=0)
    payer_wallet: str


class PaymentResult(BaseModel):
    success: bool
    transaction_id: str | None = None
    amount_usd: float | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# PDF operation results
# ---------------------------------------------------------------------------


class ExtractTextResponse(BaseModel):
    filename: str
    page_count: int
    pages: list[dict[str, Any]]  # [{page: int, text: str}]
    total_characters: int
    transaction_id: str
    amount_charged_usd: float


class TableCell(BaseModel):
    row: int
    col: int
    value: str


class ExtractedTable(BaseModel):
    page: int
    table_index: int
    rows: int
    cols: int
    data: list[list[str]]


class ExtractTablesResponse(BaseModel):
    filename: str
    page_count: int
    tables_found: int
    tables: list[ExtractedTable]
    transaction_id: str
    amount_charged_usd: float


class SummarizeResponse(BaseModel):
    filename: str
    page_count: int
    summary: str
    key_points: list[str]
    word_count: int
    transaction_id: str
    amount_charged_usd: float


class SplitPageItem(BaseModel):
    page: int
    filename: str
    size_bytes: int
    content_b64: str  # base64-encoded single-page PDF


class SplitResponse(BaseModel):
    original_filename: str
    page_count: int
    pages: list[SplitPageItem]
    transaction_id: str
    amount_charged_usd: float


class MergeResponse(BaseModel):
    output_filename: str
    total_pages: int
    merged_file_size_bytes: int
    content_b64: str  # base64-encoded merged PDF
    transaction_id: str
    amount_charged_usd: float


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None
