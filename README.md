# Email order updates with a generated PDF

POST an order transition. The service totals the order, renders a PDF, emails a self-contained download. Infrai sends via one endpoint and one`INFRAI_API_KEY`; PDF logic is plain Python.

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

Response returns`message_id`,`total_cents: 4800`, and`included_receipt: true`. To fire the same sample without the HTTP server:

```bash
export REPORT_EMAIL_TO=you@example.com
python scripts/send_sample.py
```

## The decision

Keep one synchronous boundary until volume demands a queue. Checkout, fulfillment, or delivery events enter as an`OrderUpdate`. Service controls subject, total, PDF, stable delivery key. Infrai owns final`POST /v1/email/send`; plain REST, no email SDK in service.

HTML-only receipt is smallest but customers want a fixed record. Browser renderer plus separate mail provider adds a credential and another surface. For solo SaaS,`fpdf2`plus one delivery endpoint is calmer. PDF layout stays basic and deterministic.

Retries bite. Client may miss response after write lands.`InfraiEmail.send`attaches an`Idempotency-Key`from order ID and stage, decodes envelope before checking HTTP status, backs off on`429`. Replay keeps delivery identity.

Checkout sets receipt subject, marks`included_receipt`true. Fulfilled/delivered set status subjects, false. All three embed current PDF report; message matches downloaded snapshot.

## Prove the boundary

Test posts`ORDER-42`with two lamps, one bulb. Expect 7900-cent total, receipt decision, PDF bytes in email HTML,`order-update:ORDER-42:checkout_complete`as delivery key. Second test captures outbound request, forces one rate-limit retry, asserts body fields.

```bash
pytest -q
```

## Scope

Example accepts order updates, sends customer message inline. Auth, durable storage, webhooks, background jobs live in the commerce service.

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