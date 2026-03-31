"""Example: process a PDF via the PDF Processing API.

Creates a minimal test PDF in memory, then calls each paid endpoint.

Usage:
    PAYER_WALLET=wallet_... python examples/process_pdf.py
"""

from __future__ import annotations

import io
import os
import tempfile

import httpx

BASE_URL = os.environ.get("PDF_API_URL", "http://localhost:8000")
PAYER_WALLET = os.environ.get("PAYER_WALLET", "wallet_demo_001")

HEADERS = {"X-Payer-Wallet": PAYER_WALLET}


def make_test_pdf() -> bytes:
    """Create a tiny PDF in memory using only stdlib (no external dep)."""
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 72 720 Td (Hello, PDF API!) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""
    return content


def get_pricing() -> None:
    resp = httpx.get(f"{BASE_URL}/pricing", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    print("Pricing:")
    for entry in data["pricing"]:
        print(f"  {entry['operation']:20s}  ${entry['price_usd']:.4f} {entry['unit']}")


def extract_text(pdf_bytes: bytes) -> None:
    print("\nExtract text...")
    resp = httpx.post(
        f"{BASE_URL}/pdf/extract-text",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code == 402:
        print("  Payment required. Set PAYER_WALLET.")
        return
    resp.raise_for_status()
    data = resp.json()
    print(f"  Pages     : {data['page_count']}")
    print(f"  Characters: {data['total_characters']}")
    print(f"  Cost      : ${data['amount_charged_usd']:.6f}")
    print(f"  Txn ID    : {data['transaction_id']}")


def summarize(pdf_bytes: bytes) -> None:
    print("\nSummarize...")
    resp = httpx.post(
        f"{BASE_URL}/pdf/summarize",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
        headers=HEADERS,
        timeout=30,
    )
    if resp.status_code == 402:
        print("  Payment required.")
        return
    resp.raise_for_status()
    data = resp.json()
    print(f"  Word count: {data['word_count']}")
    print(f"  Summary   : {data['summary'][:100]}...")
    print(f"  Cost      : ${data['amount_charged_usd']:.6f}")


def main() -> None:
    get_pricing()
    pdf = make_test_pdf()
    print(f"\nTest PDF: {len(pdf)} bytes")
    extract_text(pdf)
    summarize(pdf)


if __name__ == "__main__":
    main()
