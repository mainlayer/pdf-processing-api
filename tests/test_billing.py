"""Tests for the PDF Processing API billing and endpoints."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure dev mode so charges are bypassed without an API key
os.environ["MAINLAYER_DEV_MODE"] = "true"

from src.main import app  # noqa: E402

WALLET = "wallet_test_001"
HEADERS = {"X-Payer-Wallet": WALLET}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def test_pricing_returns_all_operations(client):
    resp = client.get("/pricing")
    assert resp.status_code == 200
    body = resp.json()
    ops = {entry["operation"] for entry in body["pricing"]}
    assert "extract-text" in ops
    assert "summarize" in ops
    assert "merge" in ops


# ---------------------------------------------------------------------------
# Billing helpers
# ---------------------------------------------------------------------------


def test_calculate_amount_per_page():
    from src.billing import estimate_cost
    from src.models import OperationType

    cost = estimate_cost(OperationType.EXTRACT_TEXT, page_count=10)
    assert cost == pytest.approx(0.05, rel=1e-3)  # $0.005 * 10


def test_calculate_amount_flat_rate():
    from src.billing import estimate_cost
    from src.models import OperationType

    # Merge is flat-rate regardless of page count
    cost = estimate_cost(OperationType.MERGE, page_count=100)
    assert cost == pytest.approx(0.01, rel=1e-3)


# ---------------------------------------------------------------------------
# Extract text endpoint
# ---------------------------------------------------------------------------

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT /F1 12 Tf 72 720 Td (Test Page) Tj ET\nendstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
    b"0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n"
    b"0000000360 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n441\n%%EOF"
)


@pytest.fixture(autouse=True)
def mock_pdf_processor():
    """Mock the pypdf-based processor so tests run without pypdf installed."""
    with (
        patch("src.main.processor.get_page_count", return_value=2),
        patch(
            "src.main.processor.extract_text",
            return_value={"page_count": 2, "pages": [{"page": 1, "text": "Hello"}, {"page": 2, "text": "World"}], "total_characters": 10},
        ),
        patch(
            "src.main.processor.extract_tables",
            return_value={"page_count": 2, "tables_found": 1, "tables": [{"page": 1, "table_index": 0, "rows": 2, "cols": 2, "data": [["A", "B"], ["1", "2"]]}]},
        ),
        patch(
            "src.main.processor.summarize",
            return_value={"page_count": 2, "summary": "Test summary.", "key_points": ["Point one."], "word_count": 50},
        ),
        patch(
            "src.main.processor.split_pdf",
            return_value={"page_count": 2, "pages": [{"page": 1, "filename": "page_001.pdf", "size_bytes": 100, "content_b64": "AAAA"}, {"page": 2, "filename": "page_002.pdf", "size_bytes": 100, "content_b64": "BBBB"}]},
        ),
        patch(
            "src.main.processor.merge_pdfs",
            return_value={"output_filename": "merged.pdf", "total_pages": 4, "merged_file_size_bytes": 500, "content_b64": "CCCC"},
        ),
    ):
        yield


def test_extract_text_requires_wallet(client):
    resp = client.post(
        "/pdf/extract-text",
        files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert resp.status_code == 422  # missing required header


def test_extract_text_with_wallet(client):
    resp = client.post(
        "/pdf/extract-text",
        files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_count"] == 2
    assert body["total_characters"] == 10
    assert "transaction_id" in body
    assert body["amount_charged_usd"] == pytest.approx(0.01, rel=1e-3)  # $0.005 * 2


def test_extract_tables(client):
    resp = client.post(
        "/pdf/extract-tables",
        files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tables_found"] == 1
    assert body["amount_charged_usd"] == pytest.approx(0.02, rel=1e-3)  # $0.01 * 2


def test_summarize(client):
    resp = client.post(
        "/pdf/summarize",
        files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert body["amount_charged_usd"] == pytest.approx(0.04, rel=1e-3)  # $0.02 * 2


def test_split_pdf(client):
    resp = client.post(
        "/pdf/split",
        files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_count"] == 2
    assert len(body["pages"]) == 2


def test_merge_pdfs(client):
    resp = client.post(
        "/pdf/merge",
        files=[
            ("files", ("a.pdf", MINIMAL_PDF, "application/pdf")),
            ("files", ("b.pdf", MINIMAL_PDF, "application/pdf")),
        ],
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_pages"] == 4
    assert "content_b64" in body


def test_merge_requires_at_least_two_files(client):
    resp = client.post(
        "/pdf/merge",
        files=[("files", ("a.pdf", MINIMAL_PDF, "application/pdf"))],
        headers=HEADERS,
    )
    assert resp.status_code == 400


def test_empty_file_rejected(client):
    resp = client.post(
        "/pdf/extract-text",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=HEADERS,
    )
    assert resp.status_code == 400
