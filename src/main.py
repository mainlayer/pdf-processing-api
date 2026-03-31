"""PDF Processing API — pay per page via Mainlayer.

Endpoints
---------
POST /pdf/extract-text    $0.005/page
POST /pdf/extract-tables  $0.01/page
POST /pdf/summarize       $0.02/page
POST /pdf/split           $0.002/page
POST /pdf/merge           $0.01/call
GET  /pricing             free
"""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import List

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import pdf_processor as processor
from mainlayer import (
    PRICES,
    charge_for_operation,
    require_payer_wallet,
)
from models import (
    ErrorDetail,
    ExtractTablesResponse,
    ExtractTextResponse,
    ExtractedTable,
    MergeResponse,
    OperationType,
    PricingEntry,
    PricingResponse,
    SplitPageItem,
    SplitResponse,
    SummarizeResponse,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("pdf-processing-api")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PDF Processing API",
    description=(
        "PDF processing for AI agents — pay per page, no subscription. "
        "Powered by Mainlayer."
    ),
    version="1.0.0",
    contact={
        "name": "Mainlayer",
        "url": "https://mainlayer.fr",
    },
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024
MAX_MERGE_FILES = int(os.getenv("MAX_MERGE_FILES", "20"))


async def _read_upload(upload: UploadFile) -> bytes:
    """Read an uploaded file, enforcing size limits."""
    data = await upload.read()
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File '{upload.filename}' exceeds the maximum allowed size of "
                f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file '{upload.filename}' is empty.",
        )
    return data


async def _run_sync(fn, *args):
    """Run a blocking function in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(fn, *args))


def _validate_pdf_content_type(upload: UploadFile) -> None:
    """Raise 400 if the upload content-type is clearly not a PDF."""
    ct = (upload.content_type or "").lower()
    filename = (upload.filename or "").lower()
    if ct and ct not in ("application/pdf", "application/octet-stream", "") and not filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected a PDF file, got content-type '{upload.content_type}'.",
        )


# ---------------------------------------------------------------------------
# Routes — free
# ---------------------------------------------------------------------------


@app.get(
    "/pricing",
    response_model=PricingResponse,
    tags=["Info"],
    summary="Return per-operation pricing",
)
async def get_pricing() -> PricingResponse:
    """Return the current pricing schedule (no auth required)."""
    entries = [
        PricingEntry(
            operation="extract-text",
            unit="per page",
            price_usd=PRICES[OperationType.EXTRACT_TEXT],
            description="Extract raw text from every page of the PDF.",
        ),
        PricingEntry(
            operation="extract-tables",
            unit="per page",
            price_usd=PRICES[OperationType.EXTRACT_TABLES],
            description="Detect and extract tabular data from each page.",
        ),
        PricingEntry(
            operation="summarize",
            unit="per page",
            price_usd=PRICES[OperationType.SUMMARIZE],
            description="Generate an extractive summary and key points.",
        ),
        PricingEntry(
            operation="split",
            unit="per page",
            price_usd=PRICES[OperationType.SPLIT],
            description="Split the PDF into individual single-page files.",
        ),
        PricingEntry(
            operation="merge",
            unit="per call",
            price_usd=PRICES[OperationType.MERGE],
            description="Merge multiple PDFs into a single document.",
        ),
    ]
    return PricingResponse(
        pricing=entries,
        note="Billing is handled via Mainlayer. Supply your wallet in X-Payer-Wallet.",
    )


# ---------------------------------------------------------------------------
# Routes — paid
# ---------------------------------------------------------------------------


@app.post(
    "/pdf/extract-text",
    response_model=ExtractTextResponse,
    tags=["PDF"],
    summary="Extract text from a PDF ($0.005/page)",
    responses={
        402: {"model": ErrorDetail, "description": "Payment required"},
        413: {"model": ErrorDetail, "description": "File too large"},
    },
)
async def extract_text(
    file: UploadFile = File(..., description="PDF file to process"),
    payer_wallet: str = Depends(require_payer_wallet),
) -> ExtractTextResponse:
    """Extract all text from a PDF document.

    - **file**: multipart PDF upload
    - **X-Payer-Wallet**: Mainlayer wallet address (header)

    Charged at **$0.005 per page**.
    """
    _validate_pdf_content_type(file)
    data = await _read_upload(file)

    page_count: int = await _run_sync(processor.get_page_count, data)
    if page_count == 0:
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    charge = await charge_for_operation(payer_wallet, OperationType.EXTRACT_TEXT, page_count)

    result = await _run_sync(processor.extract_text, data)

    logger.info(
        "extract-text wallet=%s pages=%d txn=%s amount=$%.4f",
        payer_wallet,
        page_count,
        charge.transaction_id,
        charge.amount_usd,
    )

    return ExtractTextResponse(
        filename=file.filename or "upload.pdf",
        page_count=result["page_count"],
        pages=result["pages"],
        total_characters=result["total_characters"],
        transaction_id=charge.transaction_id,
        amount_charged_usd=charge.amount_usd,
    )


@app.post(
    "/pdf/extract-tables",
    response_model=ExtractTablesResponse,
    tags=["PDF"],
    summary="Extract tables from a PDF ($0.01/page)",
    responses={
        402: {"model": ErrorDetail, "description": "Payment required"},
        413: {"model": ErrorDetail, "description": "File too large"},
    },
)
async def extract_tables(
    file: UploadFile = File(..., description="PDF file to process"),
    payer_wallet: str = Depends(require_payer_wallet),
) -> ExtractTablesResponse:
    """Extract tabular data from a PDF document.

    Uses heuristic analysis of text layout to detect tables.
    Replace the `pdf_processor.extract_tables` implementation with
    pdfplumber or camelot for higher fidelity in production.

    Charged at **$0.01 per page**.
    """
    _validate_pdf_content_type(file)
    data = await _read_upload(file)

    page_count: int = await _run_sync(processor.get_page_count, data)
    if page_count == 0:
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    charge = await charge_for_operation(payer_wallet, OperationType.EXTRACT_TABLES, page_count)

    result = await _run_sync(processor.extract_tables, data)

    logger.info(
        "extract-tables wallet=%s pages=%d tables=%d txn=%s amount=$%.4f",
        payer_wallet,
        page_count,
        result["tables_found"],
        charge.transaction_id,
        charge.amount_usd,
    )

    tables = [ExtractedTable(**t) for t in result["tables"]]

    return ExtractTablesResponse(
        filename=file.filename or "upload.pdf",
        page_count=result["page_count"],
        tables_found=result["tables_found"],
        tables=tables,
        transaction_id=charge.transaction_id,
        amount_charged_usd=charge.amount_usd,
    )


@app.post(
    "/pdf/summarize",
    response_model=SummarizeResponse,
    tags=["PDF"],
    summary="Summarize a PDF ($0.02/page)",
    responses={
        402: {"model": ErrorDetail, "description": "Payment required"},
        413: {"model": ErrorDetail, "description": "File too large"},
    },
)
async def summarize(
    file: UploadFile = File(..., description="PDF file to process"),
    payer_wallet: str = Depends(require_payer_wallet),
) -> SummarizeResponse:
    """Generate an extractive summary and bullet-point key takeaways.

    Charged at **$0.02 per page**.
    """
    _validate_pdf_content_type(file)
    data = await _read_upload(file)

    page_count: int = await _run_sync(processor.get_page_count, data)
    if page_count == 0:
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    charge = await charge_for_operation(payer_wallet, OperationType.SUMMARIZE, page_count)

    result = await _run_sync(processor.summarize, data)

    logger.info(
        "summarize wallet=%s pages=%d txn=%s amount=$%.4f",
        payer_wallet,
        page_count,
        charge.transaction_id,
        charge.amount_usd,
    )

    return SummarizeResponse(
        filename=file.filename or "upload.pdf",
        page_count=result["page_count"],
        summary=result["summary"],
        key_points=result["key_points"],
        word_count=result["word_count"],
        transaction_id=charge.transaction_id,
        amount_charged_usd=charge.amount_usd,
    )


@app.post(
    "/pdf/split",
    response_model=SplitResponse,
    tags=["PDF"],
    summary="Split a PDF into individual pages ($0.002/page)",
    responses={
        402: {"model": ErrorDetail, "description": "Payment required"},
        413: {"model": ErrorDetail, "description": "File too large"},
    },
)
async def split_pdf(
    file: UploadFile = File(..., description="PDF file to split"),
    payer_wallet: str = Depends(require_payer_wallet),
) -> SplitResponse:
    """Split a multi-page PDF into separate single-page PDF files.

    Each page is returned as a base64-encoded PDF in the response.

    Charged at **$0.002 per page**.
    """
    _validate_pdf_content_type(file)
    data = await _read_upload(file)

    page_count: int = await _run_sync(processor.get_page_count, data)
    if page_count == 0:
        raise HTTPException(status_code=400, detail="PDF contains no pages.")

    charge = await charge_for_operation(payer_wallet, OperationType.SPLIT, page_count)

    result = await _run_sync(processor.split_pdf, data)

    logger.info(
        "split wallet=%s pages=%d txn=%s amount=$%.4f",
        payer_wallet,
        page_count,
        charge.transaction_id,
        charge.amount_usd,
    )

    pages = [SplitPageItem(**p) for p in result["pages"]]

    return SplitResponse(
        original_filename=file.filename or "upload.pdf",
        page_count=result["page_count"],
        pages=pages,
        transaction_id=charge.transaction_id,
        amount_charged_usd=charge.amount_usd,
    )


@app.post(
    "/pdf/merge",
    response_model=MergeResponse,
    tags=["PDF"],
    summary="Merge multiple PDFs into one ($0.01/call)",
    responses={
        402: {"model": ErrorDetail, "description": "Payment required"},
        413: {"model": ErrorDetail, "description": "File too large"},
    },
)
async def merge_pdfs(
    files: List[UploadFile] = File(..., description="Two or more PDF files to merge"),
    payer_wallet: str = Depends(require_payer_wallet),
) -> MergeResponse:
    """Merge two or more PDFs into a single document.

    Files are merged in the order they are supplied.
    The merged PDF is returned as a base64-encoded string.

    Charged at **$0.01 per call** (flat rate, regardless of page count).
    """
    if len(files) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least two PDF files are required for merging.",
        )
    if len(files) > MAX_MERGE_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot merge more than {MAX_MERGE_FILES} files in a single request.",
        )

    for upload in files:
        _validate_pdf_content_type(upload)

    # Read all files concurrently
    files_data = await asyncio.gather(*[_read_upload(f) for f in files])

    # Flat-rate charge — page_count=0 triggers MERGE flat-rate logic
    charge = await charge_for_operation(payer_wallet, OperationType.MERGE, page_count=0)

    result = await _run_sync(processor.merge_pdfs, list(files_data))

    logger.info(
        "merge wallet=%s files=%d total_pages=%d txn=%s amount=$%.4f",
        payer_wallet,
        len(files),
        result["total_pages"],
        charge.transaction_id,
        charge.amount_usd,
    )

    return MergeResponse(
        output_filename=result["output_filename"],
        total_pages=result["total_pages"],
        merged_file_size_bytes=result["merged_file_size_bytes"],
        content_b64=result["content_b64"],
        transaction_id=charge.transaction_id,
        amount_charged_usd=charge.amount_usd,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Info"], include_in_schema=False)
async def health():
    return {"status": "ok", "service": "pdf-processing-api"}


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
