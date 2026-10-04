from __future__ import annotations

import httpx

from order_report_service.infrai_email import InfraiEmail, SendResult
from order_report_service.receipt_sender import OrderStage, OrderUpdate, send_order_update


class RecordingEmail:
    def __init__(self) -> None:
        self.call: dict[str, str] = {}

    def send(self, *, to: str, subject: str, html: str, idempotency_key: str) -> SendResult:
        self.call = {
            "to": to,
            "subject": subject,
            "html": html,
            "idempotency_key": idempotency_key,
        }
        return SendResult(message_id="msg_42", metadata={"provider": "selected"})


def sample(stage: OrderStage = OrderStage.CHECKOUT_COMPLETE) -> OrderUpdate:
    return OrderUpdate.model_validate(
        {
            "order_id": "ORDER-42",
            "customer_email": "buyer@example.com",
            "stage": stage,
            "currency": "USD",
            "items": [
                {"name": "Desk lamp", "quantity": 2, "unit_price_cents": 3500},
                {"name": "Bulb", "quantity": 1, "unit_price_cents": 900},
            ],
        }
    )


def test_checkout_sends_receipt_with_pdf_and_stable_delivery_key() -> None:
    email = RecordingEmail()

    result = send_order_update(sample(), email)

    assert result.total_cents == 7900
    assert result.included_receipt is True
    assert email.call["subject"] == "Receipt for order ORDER-42"
    assert "data:application/pdf;base64,JVBER" in email.call["html"]
    assert email.call["idempotency_key"] == "order-update:ORDER-42:checkout_complete"


def test_email_boundary_retries_and_sends_only_documented_body_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"message_id": "msg_99"}, "error": None, "metadata": {}},
        )

    client = InfraiEmail("test-key", transport=httpx.MockTransport(handler), sleep=lambda _: None)
    try:
        result = client.send(
            to="buyer@example.com",
            subject="Receipt",
            html="<p>Ready</p>",
            idempotency_key="order-update:42:checkout_complete",
        )
    finally:
        client.close()

    assert result.message_id == "msg_99"
    assert len(requests) == 2
    assert requests[1].method == "POST"
    assert requests[1].url.path == "/v1/email/send"
    assert requests[1].headers["Idempotency-Key"] == "order-update:42:checkout_complete"
    assert requests[1].read() == b'{"to":"buyer@example.com","subject":"Receipt","html":"<p>Ready</p>"}'

