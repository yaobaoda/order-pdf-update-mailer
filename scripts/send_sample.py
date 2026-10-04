from __future__ import annotations

import json
import os

from order_report_service.infrai_email import InfraiEmail
from order_report_service.receipt_sender import OrderStage, OrderUpdate, send_order_update


def main() -> None:
    api_key = os.environ.get("INFRAI_API_KEY")
    recipient = os.environ.get("REPORT_EMAIL_TO")
    if not api_key or not recipient:
        raise SystemExit("Set INFRAI_API_KEY and REPORT_EMAIL_TO")

    update = OrderUpdate.model_validate(
        {
            "order_id": "ORD-1042",
            "customer_email": recipient,
            "stage": OrderStage.CHECKOUT_COMPLETE,
            "currency": "USD",
            "items": [{"name": "Canvas tote", "quantity": 2, "unit_price_cents": 2400}],
        }
    )
    email = InfraiEmail(api_key)
    try:
        receipt = send_order_update(update, email)
        print(json.dumps(receipt.model_dump(mode="json"), indent=2))
    finally:
        email.close()


if __name__ == "__main__":
    main()

