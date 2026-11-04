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
make test       # 37 tests, offline
make demo       # http://127.0.0.1:8077 in mock mode
```

Try: `I need a laptop, there are 3 of us and we make about $28,000 a year` → the desk shows the steps (poverty line for 3 is $27,320; $28,000 is 102% of it; band "up to 150%": pay 25% of $200 = **$50**) and asks for YES. Press YES → invoice page. In mock mode a button plays the payer; in the sandbox PayPal's hosted page does and the webhook (`POST /webhook/paypal`) marks it paid. Then `/receipt`.

Donor: `I want to cover a laptop for someone, $100` → YES → order → approve (mock button or PayPal page) → captured → thank-you.

### Sandbox mode

Copy `.env.example` to `.env`, set `MOCK=0`, `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` (a sandbox app from developer.paypal.com), then `make sandbox`. Point a sandbox webhook at `/webhook/paypal` for `INVOICING.INVOICE.PAID` and `CHECKOUT.ORDER.APPROVED` and put its id in `PAYPAL_WEBHOOK_ID`.

**Webhook verification.** In sandbox mode every delivery is checked with PayPal's `verify-webhook-signature` (the five `PAYPAL-TRANSMISSION-*` headers plus the raw event bytes, against `PAYPAL_WEBHOOK_ID`); anything that fails, arrives without the headers, or arrives while `PAYPAL_WEBHOOK_ID` is unset gets a 403. Even a verified event is not trusted on its own: an invoice's status is re-read from PayPal before a receipt is written, and an order is only "paid" when the capture call succeeds. The mock form buttons are accepted only in `MOCK=1`.

### Environment

| variable | default | what |
|---|---|---|
| `MOCK` | `1` | `0` calls the PayPal sandbox |
| `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` | | sandbox app credentials (environment only, never a file in the repo) |
| `PAYPAL_WEBHOOK_ID` | | the sandbox webhook's id; required in `MOCK=0` or every webhook is refused |
| `ANTHROPIC_API_KEY`, `NT_MODEL` | | optional Claude explainer; offline templates otherwise |
| `NT_DB` | `./navigator-till.db` | SQLite session store (gitignored, created `0600`) |
| `NT_DB_RETENTION_DAYS` | `30` | sessions idle longer than this are purged when the store opens |
| `NT_DESK_TOKEN` | | gate for `/desk`; required in `MOCK=0`, optional in the mock demo |
| `NT_ORG`, `NT_ORG_EMAIL` | TechEMPOWER | shown on the pages and in PayPal memos |

### The navigator view: `/desk`

`GET /desk` is the desk's own page: quotes today, unpaid invoices, paid pickups (including no-charge pickup notes) and donations captured, read from the session store. It shows emails and incomes, so set `NT_DESK_TOKEN` and open `/desk?token=…` once; the token is swapped for a cookie (an HMAC, not the secret) and the browser is redirected to the clean URL. In sandbox mode the page refuses to open without a token.

### Spanish

Add `?lang=es` to any page (or press **Español** in the header); a cookie keeps the choice. Every page string, the desk's chat replies, the offline explainer, the receipt and the quote's arithmetic render in Spanish, and the offline parser understands Spanish device, household, income and donation words ("Necesito una laptop, somos 3 y ganamos $28,000 al año"). With a Claude key the explainer is asked to write in Spanish. Device and band labels come from `pricing.yaml`; their Spanish lives in `navigator_till/i18n.py` and any label the org adds later falls back to its English text.

### Receipt

The receipt page has **Read this aloud** (the browser's own `speechSynthesis`, no server audio, no outside service; it is disabled with a note where the browser lacks it) and **Print**, which prints only the receipt card.

## Layout

```
navigator_till/pricing.yaml   the scale the org edits
navigator_till/pricing.py     rules → Quote (with its steps)
navigator_till/agent.py       parse + explain (Claude or offline)
navigator_till/paypal.py      Mock and Sandbox clients, same four calls, webhook verification
navigator_till/store.py       SQLite session store (one JSON document per session)
navigator_till/i18n.py        English and Spanish strings, Spanish quote steps
navigator_till/app.py         FastAPI desk: chat, YES, invoice/order, webhook, receipt, /desk
tests/                        pricing edges, mock lifecycles, end-to-end loops, webhook, store, i18n, desk
```

## What changed in 0.2.0

- Webhook signature verification in sandbox mode; the real PayPal JSON event body is accepted.
- Sessions persist in SQLite and survive a restart (`NT_DB`, retention purge, `0600` file).
- Receipt: read aloud (browser speech) and print only the card.
- Spanish for the whole desk (`?lang=es`), including the offline explainer and the quote's steps.
- `/desk`: the navigator's view of the day.

## Roadmap

- A signed session cookie and a navigator login instead of the desk token.
- Refunds and a "mark picked up" step on `/desk`.
- More languages: the dictionary in `i18n.py` is the only thing to add.

## License

MIT. Clinics and nonprofits: run your own copy and edit `pricing.yaml`.
