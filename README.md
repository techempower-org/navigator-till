# Navigator Till

A plain-language front desk for a small nonprofit's device program. A client (or a navigator sitting with them) says what they need; the desk prices a refurbished laptop or desktop on the organization's **sliding scale**, explains the arithmetic in plain words, and, only after the person presses **YES**, sends a **PayPal invoice**. When it is paid, the desk writes the receipt and pickup note. A donor can walk up to the same desk and cover a neighbor's gap through **PayPal checkout**.

Built by [TechEMPOWER](https://techempower.org), a Nevada County, California 501(c)(3), for the PayPal AI Hackathon 2026. The scale and prices in `pricing.yaml` are the ones our desk really uses.

## The split that makes it trustworthy

- **Rules compute.** Every price comes from `navigator_till/pricing.py` reading `pricing.yaml` (list prices, the 2026 poverty guideline, income bands, categorical programs). The quote carries every step, so a navigator can check it on paper.
- **The agent explains.** `navigator_till/agent.py` turns a sentence into a structured request and turns a quote into a 6th-grade-reading-level explanation. With `ANTHROPIC_API_KEY` set it uses Claude; without it, a deterministic parser and templates do the same job offline. It never changes a number and never touches PayPal.
- **PayPal moves money, after a human YES.** `navigator_till/paypal.py` wraps Invoicing v2 (client pays) and Orders v2 (donor covers the gap). `MOCK=1` (default) keeps the same payload shapes in memory so the whole loop runs on a laptop with no keys; `MOCK=0` with sandbox credentials calls `api-m.sandbox.paypal.com`.

## Run it

```bash
make setup      # python3 -m venv .venv && pip install -e ".[dev,ai]"
make test       # 15 tests, offline
make demo       # http://127.0.0.1:8077 in mock mode
```

Try: `I need a laptop, there are 3 of us and we make about $28,000 a year` → the desk shows the steps (poverty line for 3 is $27,320; $28,000 is 102% of it; band "up to 150%": pay 25% of $200 = **$50**) and asks for YES. Press YES → invoice page. In mock mode a button plays the payer; in the sandbox PayPal's hosted page does and the webhook (`POST /webhook/paypal`) marks it paid. Then `/receipt`.

Donor: `I want to cover a laptop for someone, $100` → YES → order → approve (mock button or PayPal page) → captured → thank-you.

### Sandbox mode

Copy `.env.example` to `.env`, set `MOCK=0`, `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` (a sandbox app from developer.paypal.com), then `make sandbox`. Point a sandbox webhook at `/webhook/paypal` for `INVOICING.INVOICE.PAID` and `CHECKOUT.ORDER.APPROVED`. Webhook signature verification is not implemented yet (see Roadmap); do not expose this to the internet without it.

## Layout

```
navigator_till/pricing.yaml   the scale the org edits
navigator_till/pricing.py     rules → Quote (with its steps)
navigator_till/agent.py       parse + explain (Claude or offline)
navigator_till/paypal.py      Mock and Sandbox clients, same four calls
navigator_till/app.py         FastAPI desk: chat, YES, invoice/order, webhook, receipt
tests/                        pricing edges, mock lifecycles, end-to-end loops
```

## Roadmap (the hackathon week)

- Webhook signature verification and a persisted session store.
- Read-aloud and print buttons on the receipt (the desk serves people who do not read easily).
- Spanish.
- A navigator view: today's quotes, unpaid invoices, pickups.

## License

MIT. Clinics and nonprofits: run your own copy and edit `pricing.yaml`.
