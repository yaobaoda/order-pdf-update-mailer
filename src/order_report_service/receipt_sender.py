from __future__ import annotations

import base64
import html
from enum import Enum
from typing import Protocol

from fpdf import FPDF
from pydantic import BaseModel, EmailStr, Field, model_validator

from .infrai_email import SendResult


class OrderStage(str, Enum):
    CHECKOUT_COMPLETE = "checkout_complete"
    FULFILLED = "fulfilled"
    DELIVERED = "delivered"


class LineItem(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class OrderUpdate(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    customer_email: EmailStr
    stage: OrderStage
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    items: list[LineItem] = Field(min_length=1)
    tracking_reference: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def tracking_follows_fulfillment(self) -> "OrderUpdate":
        if self.stage is OrderStage.CHECKOUT_COMPLETE and self.tracking_reference:
            raise ValueError("tracking_reference starts at fulfillment")
        return self


class DeliveryReceipt(BaseModel):
    order_id: str
    stage: OrderStage
    message_id: str
    total_cents: int
    included_receipt: bool


class EmailPort(Protocol):
    def send(
        self, *, to: str, subject: str, html: str, idempotency_key: str
    ) -> SendResult:
        """Send one customer-facing order message."""


def order_total(update: OrderUpdate) -> int:
    return sum(item.quantity * item.unit_price_cents for item in update.items)


def render_pdf(update: OrderUpdate) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, f"Order report {update.order_id}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, f"Status: {update.stage.value}", new_x="LMARGIN", new_y="NEXT")
    for item in update.items:
        amount = item.quantity * item.unit_price_cents
        pdf.cell(
            0,
            7,
            f"{item.quantity} x {item.name}: {amount / 100:.2f} {update.currency}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, f"Total: {order_total(update) / 100:.2f} {update.currency}")
    output = pdf.output()
    return bytes(output)


def compose_message(update: OrderUpdate, pdf_bytes: bytes) -> tuple[str, str]:
    subjects = {
        OrderStage.CHECKOUT_COMPLETE: f"Receipt for order {update.order_id}",
        OrderStage.FULFILLED: f"Order {update.order_id} has shipped",
        OrderStage.DELIVERED: f"Order {update.order_id} was delivered",
    }
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    safe_id = html.escape(update.order_id)
    body = (
        f"<p>Order <strong>{safe_id}</strong> is now "
        f"{html.escape(update.stage.value)}.</p>"
        f'<p><a download="order-{safe_id}.pdf" '
        f'href="data:application/pdf;base64,{encoded}">Download the PDF report</a></p>'
    )
    if update.tracking_reference:
        body += f"<p>Tracking reference: {html.escape(update.tracking_reference)}</p>"
    return subjects[update.stage], body


def send_order_update(update: OrderUpdate, email: EmailPort) -> DeliveryReceipt:
    pdf_bytes = render_pdf(update)
    subject, body = compose_message(update, pdf_bytes)
    result = email.send(
        to=str(update.customer_email),
        subject=subject,
        html=body,
        idempotency_key=f"order-update:{update.order_id}:{update.stage.value}",
    )
    return DeliveryReceipt(
        order_id=update.order_id,
        stage=update.stage,
        message_id=result.message_id,
        total_cents=order_total(update),
        included_receipt=update.stage is OrderStage.CHECKOUT_COMPLETE,
    )
