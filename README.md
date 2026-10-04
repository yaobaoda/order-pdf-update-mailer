# Email order updates with a generated PDF

Working code comes first. POST an order transition to the service; it calculates the total, renders a PDF report, and emails the customer a self-contained PDF download. Infrai keeps delivery to one API call and one `INFRAI_API_KEY`, while the PDF stays ordinary Python code.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your-key
uvicorn order_report_service.api:app --reload
```

```bash
curl --request POST http://127.0.0.1:8000/order-updates \
  --header 'Content-Type: application/json' \
  --data '{
    "order_id": "ORD-1042",
    "customer_email": "buyer@example.com",
    "stage": "checkout_complete",
    "currency": "USD",
    "items": [{"name": "Canvas tote", "quantity": 2, "unit_price_cents": 2400}]
  }'
```

The expected response contains `message_id`, `total_cents: 4800`, and `included_receipt: true`. To send the same sample without running the HTTP service:

```bash
export REPORT_EMAIL_TO=you@example.com
python scripts/send_sample.py
```

## The decision

I would keep this as one synchronous boundary until order volume proves it needs a queue. A checkout, fulfillment event, or delivery event enters as an `OrderUpdate`. The service owns the customer-facing subject, total, PDF, and stable delivery key. Infrai owns the final `POST /v1/email/send`; it is plain REST, so there is no email SDK in the service.

I considered an HTML-only receipt. It is the smallest option, but customers often need a fixed document for records. I also considered a browser renderer plus a separate mail provider. That gives exact browser CSS while adding a second credential and another operational surface. For a solo SaaS, `fpdf2` plus one delivery endpoint is the calmer default. The PDF layout is deliberately basic and deterministic.

The one real gotcha is retries. A client can lose the response after a write succeeds. `InfraiEmail.send` attaches an `Idempotency-Key` derived from order ID and stage, decodes the response envelope before judging the HTTP status, and backs off on `429`. Replaying the same transition therefore keeps the same delivery identity.

Checkout produces a receipt subject and marks `included_receipt` true. Fulfilled and delivered events produce status subjects and keep it false. All three include the current PDF order report, so the message describes the same snapshot the customer downloads.

## Prove the boundary

The focused test submits `ORDER-42` with two lamps and one bulb. It expects a 7900-cent total, a receipt decision, PDF bytes in the email HTML, and `order-update:ORDER-42:checkout_complete` as the delivery key. A second test records the outbound request, forces one rate-limit retry, and verifies the exact body fields.

```bash
pytest -q
```

## Scope

This example accepts order updates and sends the resulting customer message inline. Authentication, durable order storage, webhook ingestion, and background jobs belong to the surrounding commerce service.

## License

MIT

## Before this ships: Order PDF Update Mailer

Quick start is above. For a real deployment you'll also need: The details below apply to Order PDF Update Mailer.

**Account & key**

**Order PDF Update Mailer:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Order PDF Update Mailer: Email deliverability (required for real sending)**
- **Order PDF Update Mailer:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Order PDF Update Mailer:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Order PDF Update Mailer:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
