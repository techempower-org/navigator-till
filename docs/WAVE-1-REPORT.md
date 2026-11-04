# Navigator Till, wave 1 report

Branch `feat/wave-1` on familiar (`~/work/navigator-till`), written by Morpheus, Wednesday 2026-11-04 08:11–08:35 PST. Not pushed; the lead fetches, re-runs the gates, opens and merges the PR.

## Changed

1. **Webhook signature verification (sandbox).** `paypal.verify_webhook(headers, body, webhook_id, client=)` posts the five `PAYPAL-TRANSMISSION-*` headers and the raw event bytes (spliced in unchanged, since PayPal signs the bytes it sent) to `/v1/notifications/verify-webhook-signature`; True only on `SUCCESS`, False on FAILURE, missing headers, empty id or any transport error. `/webhook/paypal` reads PayPal's JSON event (`resource.invoice.id` or `resource.id`) as well as the mock form; in `MOCK=0` it answers 403 to anything unverified, to the form path, and when `PAYPAL_WEBHOOK_ID` is unset. The mock form path is unchanged in `MOCK=1`. A verified event is still not trusted for state: invoice status is re-read from PayPal; an order is paid only when capture succeeds.
2. **Persisted sessions.** `store.py`: one SQLite table, one JSON document per session, `Quote`/`Request` dataclasses rebuilt on read; path from `NT_DB` (default `./navigator-till.db`, gitignored). The in-memory `SESSIONS` dict is gone. Hardening from the security hook: file created `0600`, empty sessions never written, rows idle past `NT_DB_RETENTION_DAYS` (30) purged on open.
3. **Receipt read-aloud and print.** `speechSynthesis` in the browser (disabled with a note where absent; button toggles stop), `window.print()` with `@media print` that prints only the receipt card.
4. **Spanish.** `i18n.py`: en/es dictionaries covering every template string, every chat reply, the offline explainer, the receipt and the `/desk` page; Spanish for the YAML device/band labels with English fallback; `steps(q, lang)` rebuilds the quote's arithmetic from the Quote's numbers. `?lang=es` on any page sets `nt_lang`; the header carries an Español/English switch; the session remembers its language so a sandbox webhook writes the receipt in it. The offline parser also hears Spanish device, household, income and donation words. Claude, when keyed, is asked to write in Spanish.
5. **Navigator view.** `GET /desk`: quotes today, unpaid invoices, paid pickups (incl. no-charge pickup notes), donations captured, from the store (sessions now carry `quoted_at`/`invoiced_at`/`paid_at`/`donated_at` and the amounts). Optional `NT_DESK_TOKEN`: required in `MOCK=0` (fail closed), optional in the mock demo; `/desk?token=` is swapped for an HMAC cookie and redirected so the secret leaves the URL; `Cache-Control: no-store`.
6. **README** rewritten for 0.2.0 (verification, env table incl. `PAYPAL_WEBHOOK_ID`, `/desk`, Spanish, receipt); `.env.example` and Makefile updated; version **0.2.0** in `pyproject.toml` and `__init__.py`.
7. **Bug found by the live run, fixed:** `/receipt` re-read the invoice from the PayPal client's in-memory cache, so a persisted session 500'd after a restart. It now renders from the stored amount and reference; `SandboxPayPal.get_invoice`/`capture_order` rebuild an unknown invoice/order from PayPal's response, so a sandbox webhook arriving after a restart also works.
8. Small hook-driven hardening: Spanish income regex bounded, chat message capped at 2,000 chars.

## Checked

- `MOCK=1 .venv/bin/python -m pytest -q` after every step; final: **39 passed** (18 before).
- Red perturbation: `verify_webhook` forced to return True → 2 tests fail (`test_verify_webhook_false_on_failure_missing_headers_or_no_id`, `test_sandbox_rejects_bad_signature_form_path_and_missing_webhook_id`); restored → 39 pass.
- `gitleaks detect --no-git --source .` → no leaks found (exit 0).
- No file over 400 lines (largest: app.py 249, paypal.py 249, i18n.py 171). No `*.sh` in the repo, so `bash -n` had nothing to check.
- Live run on this box (uvicorn, port 8078, throwaway `NT_DB`): `GET /?lang=es` 200 → Spanish chat (`SÍ envía una factura de PayPal por $50 a pat@example.test`) → `/confirm` 200 → JSON webhook `{"ok":true,"status":"PAID"}` → `/receipt` 200 in Spanish with read-aloud, print and `@media print` → **server killed and restarted on the same DB** → `/receipt` 200 with `Pagado: $50` → `/desk` 200 showing Quotes today (1), Paid pickups (1), Unpaid (0), Donations (0); `/desk?lang=es` 200; DB file `-rw-------`; 0 errors/tracebacks in both server logs.
- Security-guidance hook findings on store.py, agent.py and app.py each addressed in a follow-up commit (see Changed 2, 5, 8).

## Evidence

Commits on `feat/wave-1` (main at `1ab6f0f`):

| sha | commit |
|---|---|
| 673cb38 | feat(webhook): verify PayPal signatures in sandbox mode; accept the real JSON event body |
| 14f4ef7 | feat(store): persist sessions in SQLite (NT_DB, default ./navigator-till.db) |
| 86d926b | fix(store): 0600 db file, skip empty sessions, purge rows idle past NT_DB_RETENTION_DAYS |
| b833cc9 | feat(receipt): read-aloud (browser speechSynthesis) and print-only-the-card buttons |
| 111b46c | feat(i18n): Spanish (?lang=es, nt_lang cookie) for every UI string, chat reply, explainer, receipt and quote steps |
| 3e675b6 | fix(chat): bound the Spanish income regex and cap a chat message at 2000 chars |
| 1b88bb5 | feat(desk): GET /desk navigator view |
| f36a1fd | fix(desk): fail closed in sandbox mode, redirect the token out of the URL, HMAC cookie, no-store |
| 5a4cc5b | docs: README for 0.2.0; bump version |
| 844c528 | fix: receipt and sandbox webhooks survive a restart |
| (this commit) | docs: wave 1 report; README test count 39 |

Tests: 39 (tests/test_webhook_verify.py 7, test_store.py 4, test_i18n.py 6, test_desk.py 4, plus the 18 existing with 2 new asserts on the receipt page). Diff vs main: 24 files, ~980 insertions, ~137 deletions.

PR URL: none yet; the brief says the lead opens it from this branch.

## Not verified

- **No call to the real PayPal sandbox.** `verify_webhook`, `get_invoice` rebuild and `capture_order` rebuild are tested against a monkeypatched httpx with response shapes taken from PayPal's docs (`verification_status`, `amount.value`, `primary_recipients[0].billing_info.email_address`, `purchase_units[0].payments.captures[0].amount`). No credentials, no network, per the brief. A first real sandbox delivery should be watched once.
- **Read-aloud and print were checked as rendered HTML/JS only** (no browser on this box). The script is small and uses only `speechSynthesis`/`window.print`; not executed.
- **Spanish wording** is my own, unreviewed by a native speaker; a navigator who speaks Spanish should read `i18n.py` once. The chat log keeps lines in the language they were written in; switching mid-conversation does not retranslate history (by design).
- **No cross-model (xreview) check**: the brief confines me to this box with no outbound calls. The webhook and desk-auth code are security-relevant, so the lead may want one before merge.
- **Desk "today"** uses the server's local date; the timestamps are stored with the server's zone offset. Fine for one desk, noted in case the server runs in UTC.
- Timestamps were not run through a timezone-change or midnight test.

## Lead's gate pass (money-e9, familiar, Wed 2026-11-04 08:3x)

- The build ran headless on familiar (wakizashi was offline), fresh clone from main 1ab6f0f, 11 commits.
- Gates re-run: 39 → **41 passed** after the fixes below; red perturbation (SUCCESS check broken → 4 failed, restored → green); gitleaks clean; no file over 400 lines.
- Cross-model review (Azure AI Foundry, gpt-6.1-sol-2026-09-29, read-only diff of paypal.py + app.py): MERGE-AFTER-FIXES. Fixed in 1b3afd1: a capture must answer COMPLETED (a PENDING capture settles nothing), and the invoice freezes the quote it billed (a later chat line cannot re-quote; an amount mismatch stops settlement). Accepted as-is: mock-mode /desk lists every stored session when no token is set (local demo only).
- Not verified by the lead either: a real PayPal sandbox call (needs the sandbox app, JP's card f7c09f0eb7a3); read-aloud and print in a browser; the Spanish wording by a native speaker.
