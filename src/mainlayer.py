"""Mainlayer payment middleware.

Handles billing for paid PDF operations via the Mainlayer API
(https://api.mainlayer.xyz).  Every charged endpoint must call
`charge_for_operation` before returning results to the caller.
"""

from __future__ import annotations

import os
import uuid
from typing import NamedTuple

import httpx
from fastapi import Header, HTTPException, status

from models import OperationType, PaymentResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAINLAYER_BASE_URL = os.getenv("MAINLAYER_BASE_URL", "https://api.mainlayer.xyz")
MAINLAYER_API_KEY = os.getenv("MAINLAYER_API_KEY", "")

# Price table in USD
PRICES: dict[OperationType, float] = {
    OperationType.EXTRACT_TEXT: 0.005,   # per page
    OperationType.EXTRACT_TABLES: 0.01,  # per page
    OperationType.SUMMARIZE: 0.02,       # per page
    OperationType.SPLIT: 0.002,          # per page
    OperationType.MERGE: 0.01,           # per call (flat)
}

# Merge is billed per-call, not per-page
FLAT_RATE_OPERATIONS: set[OperationType] = {OperationType.MERGE}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ChargeResult(NamedTuple):
    transaction_id: str
    amount_usd: float


def calculate_amount(operation: OperationType, page_count: int) -> float:
    """Return the amount in USD for an operation."""
    price = PRICES[operation]
    if operation in FLAT_RATE_OPERATIONS:
        return price
    return round(price * page_count, 6)


# ---------------------------------------------------------------------------
# Mainlayer client
# ---------------------------------------------------------------------------


async def _post_mainlayer(path: str, payload: dict) -> dict:
    """POST to the Mainlayer API and return the JSON response."""
    if not MAINLAYER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MAINLAYER_API_KEY is not configured on this server.",
        )

    headers = {
        "Authorization": f"Bearer {MAINLAYER_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{MAINLAYER_BASE_URL}{path}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach Mainlayer API: {exc}",
            )

    if response.status_code == 402:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment failed: insufficient balance or invalid wallet.",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payment rejected: payer wallet is not authorized.",
        )

    if not response.is_success:
        body = response.text[:512]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mainlayer API error ({response.status_code}): {body}",
        )

    return response.json()


async def charge_for_operation(
    payer_wallet: str,
    operation: OperationType,
    page_count: int,
) -> ChargeResult:
    """Debit the payer for the given operation and return a ChargeResult.

    In development mode (MAINLAYER_API_KEY not set, or
    MAINLAYER_DEV_MODE=true), the charge is simulated locally so that the
    rest of the stack can be exercised without a live key.
    """
    amount_usd = calculate_amount(operation, page_count)

    # Dev/test short-circuit
    dev_mode = os.getenv("MAINLAYER_DEV_MODE", "false").lower() == "true"
    if dev_mode or not MAINLAYER_API_KEY:
        fake_txn = f"dev-txn-{uuid.uuid4().hex[:12]}"
        return ChargeResult(transaction_id=fake_txn, amount_usd=amount_usd)

    payload = {
        "payer_wallet": payer_wallet,
        "operation": operation.value,
        "amount_usd": amount_usd,
        "page_count": page_count,
        "metadata": {
            "service": "pdf-processing-api",
            "operation": operation.value,
        },
    }

    data = await _post_mainlayer("/v1/charge", payload)

    transaction_id = data.get("transaction_id") or data.get("id") or uuid.uuid4().hex
    return ChargeResult(transaction_id=transaction_id, amount_usd=amount_usd)


# ---------------------------------------------------------------------------
# FastAPI dependency — validate X-Payer-Wallet header
# ---------------------------------------------------------------------------


def require_payer_wallet(
    x_payer_wallet: str = Header(
        ...,
        alias="X-Payer-Wallet",
        description="Mainlayer wallet address that will be charged for this request.",
    )
) -> str:
    """FastAPI dependency that extracts and validates the payer wallet header."""
    wallet = x_payer_wallet.strip()
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Payer-Wallet header must not be empty.",
        )
    return wallet
