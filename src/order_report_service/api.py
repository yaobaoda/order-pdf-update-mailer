from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .infrai_email import InfraiEmail, InfraiError
from .receipt_sender import DeliveryReceipt, OrderUpdate, send_order_update

app = FastAPI(title="Order report mailer")


@app.post("/order-updates", response_model=DeliveryReceipt)
def create_order_update(update: OrderUpdate) -> DeliveryReceipt:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")

    email = InfraiEmail(api_key)
    try:
        return send_order_update(update, email)
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=caller_status,
            detail={"code": exc.code, "error": dict(exc.detail)},
        ) from exc
    finally:
        email.close()

