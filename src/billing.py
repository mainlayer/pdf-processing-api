"""Per-page billing helpers for the PDF Processing API.

Thin wrappers over the mainlayer.py charge functions that add pricing
logic and structured logging.
"""

from __future__ import annotations

import logging
import os

from .mainlayer import (
    PRICES,
    ChargeResult,
    calculate_amount,
    charge_for_operation,
)
from .models import OperationType

logger = logging.getLogger(__name__)


def get_pricing_table() -> dict[str, dict[str, object]]:
    """Return human-readable pricing for all operations."""
    return {
        "extract_text": {
            "unit": "per page",
            "price_usd": PRICES[OperationType.EXTRACT_TEXT],
        },
        "extract_tables": {
            "unit": "per page",
            "price_usd": PRICES[OperationType.EXTRACT_TABLES],
        },
        "summarize": {
            "unit": "per page",
            "price_usd": PRICES[OperationType.SUMMARIZE],
        },
        "split": {
            "unit": "per page",
            "price_usd": PRICES[OperationType.SPLIT],
        },
        "merge": {
            "unit": "per call (flat)",
            "price_usd": PRICES[OperationType.MERGE],
        },
    }


def estimate_cost(operation: OperationType, page_count: int) -> float:
    """Return the estimated cost in USD without charging."""
    return calculate_amount(operation, page_count)


async def bill_and_process(
    payer_wallet: str,
    operation: OperationType,
    page_count: int,
) -> ChargeResult:
    """Charge the payer wallet for the given operation and return the result.

    Delegates to mainlayer.charge_for_operation.  All error handling
    (insufficient balance, network errors) is propagated upward as
    FastAPI HTTPExceptions from within that function.
    """
    amount = calculate_amount(operation, page_count)
    logger.info(
        "Billing %s pages for %s: $%.6f wallet=%s",
        page_count,
        operation.value,
        amount,
        payer_wallet,
    )
    return await charge_for_operation(payer_wallet, operation, page_count)
