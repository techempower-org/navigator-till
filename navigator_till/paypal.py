"""PayPal adapter: Invoicing v2 (client pays a sliding-scale invoice) and Orders v2 (a donor covers
the gap). MOCK=1 (the default) keeps everything in memory with the same payload shapes as the
sandbox calls, so the whole loop runs offline; set MOCK=0 plus PAYPAL_CLIENT_ID / PAYPAL_SECRET
(from the environment only, never a file in this repo) to hit https://api-m.sandbox.paypal.com.

Money moves only after a human confirmation in app.py; this module never decides to charge.
"""
from __future__ import annotations

import base64
import json
import itertools
import os
import time
from dataclasses import dataclass, field

import httpx

SANDBOX = "https://api-m.sandbox.paypal.com"


def is_mock() -> bool:
    return os.environ.get("MOCK", "1") != "0"


@dataclass
class Invoice:
    id: str
    status: str                     # DRAFT -> SENT -> PAID (PayPal's own states)
    recipient_email: str
    amount: int
    currency: str
    memo: str
    link: str
    events: list[str] = field(default_factory=list)


@dataclass
class Order:
    id: str
    status: str                     # CREATED -> APPROVED -> COMPLETED
    amount: int
    currency: str
    note: str
    approve_link: str
    events: list[str] = field(default_factory=list)


class MockPayPal:
    """In-memory stand-in with the sandbox's shapes. `settle_invoice`/`approve_order` play the
    part of the payer; in sandbox that is PayPal's hosted page plus a webhook."""

    def __init__(self) -> None:
        self._n = itertools.count(1001)
        self.invoices: dict[str, Invoice] = {}
        self.orders: dict[str, Order] = {}

    # Invoicing v2
    def create_invoice(self, *, recipient_email: str, amount: int, currency: str, memo: str) -> Invoice:
        if amount <= 0:
            raise ValueError("invoice amount must be positive")
        iid = f"INV2-MOCK-{next(self._n)}"
        inv = Invoice(id=iid, status="DRAFT", recipient_email=recipient_email, amount=amount, currency=currency,
                      memo=memo, link=f"https://sandbox.paypal.com/invoice/p/#{iid}", events=["created (mock)"])
        self.invoices[iid] = inv
        return inv

    def send_invoice(self, invoice_id: str) -> Invoice:
        inv = self.invoices[invoice_id]
        if inv.status != "DRAFT":
            raise ValueError(f"invoice {invoice_id} is {inv.status}, not DRAFT")
        inv.status = "SENT"; inv.events.append("sent (mock)")
        return inv

    def get_invoice(self, invoice_id: str) -> Invoice:
        return self.invoices[invoice_id]

    def settle_invoice(self, invoice_id: str) -> Invoice:   # the payer's part, mock only
        inv = self.invoices[invoice_id]
        if inv.status != "SENT":
            raise ValueError(f"invoice {invoice_id} is {inv.status}, not SENT")
        inv.status = "PAID"; inv.events.append("paid (mock webhook INVOICING.INVOICE.PAID)")
        return inv

    # Orders v2
    def create_order(self, *, amount: int, currency: str, note: str) -> Order:
        if amount <= 0:
            raise ValueError("order amount must be positive")
        oid = f"ORD-MOCK-{next(self._n)}"
        o = Order(id=oid, status="CREATED", amount=amount, currency=currency, note=note,
                  approve_link=f"https://www.sandbox.paypal.com/checkoutnow?token={oid}", events=["created (mock)"])
        self.orders[oid] = o
        return o

    def approve_order(self, order_id: str) -> Order:          # the donor's part, mock only
        o = self.orders[order_id]
        if o.status != "CREATED":
            raise ValueError(f"order {order_id} is {o.status}, not CREATED")
        o.status = "APPROVED"; o.events.append("approved (mock)")
        return o

    def capture_order(self, order_id: str) -> Order:
        o = self.orders[order_id]
        if o.status != "APPROVED":
            raise ValueError(f"order {order_id} is {o.status}, not APPROVED")
        o.status = "COMPLETED"; o.events.append("captured (mock)")
        return o


def _dollars(value) -> int:
    """PayPal sends amounts as strings ("50.00"); the desk prices in whole dollars."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


class SandboxPayPal:
    """The same four calls against the PayPal sandbox (REST, OAuth client credentials)."""

    def __init__(self, client_id: str | None = None, secret: str | None = None, base: str = SANDBOX) -> None:
        self.client_id = client_id or os.environ["PAYPAL_CLIENT_ID"]
        self.secret = secret or os.environ["PAYPAL_SECRET"]
        self.base = base
        self._token: tuple[str, float] | None = None
        self.invoices: dict[str, Invoice] = {}
        self.orders: dict[str, Order] = {}

    def _auth(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        cred = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        r = httpx.post(f"{self.base}/v1/oauth2/token", headers={"Authorization": f"Basic {cred}"},
                       data={"grant_type": "client_credentials"}, timeout=20)
        r.raise_for_status()
        j = r.json()
        self._token = (j["access_token"], time.time() + int(j.get("expires_in", 3000)))
        return self._token[0]

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self._auth()}", "Content-Type": "application/json"}

    def create_invoice(self, *, recipient_email: str, amount: int, currency: str, memo: str) -> Invoice:
        body = {"detail": {"currency_code": currency, "note": memo},
                "primary_recipients": [{"billing_info": {"email_address": recipient_email}}],
                "items": [{"name": memo[:120], "quantity": "1", "unit_amount": {"currency_code": currency, "value": f"{amount}.00"}}]}
        r = httpx.post(f"{self.base}/v2/invoicing/invoices", headers=self._h(), json=body, timeout=30)
        r.raise_for_status()
        href = r.json().get("href", "")
        iid = href.rsplit("/", 1)[-1]
        inv = Invoice(id=iid, status="DRAFT", recipient_email=recipient_email, amount=amount, currency=currency,
                      memo=memo, link=href, events=["created (sandbox)"])
        self.invoices[iid] = inv
        return inv

    def send_invoice(self, invoice_id: str) -> Invoice:
        r = httpx.post(f"{self.base}/v2/invoicing/invoices/{invoice_id}/send", headers=self._h(),
                       json={"send_to_recipient": True}, timeout=30)
        r.raise_for_status()
        inv = self.invoices[invoice_id]
        inv.status = "SENT"; inv.events.append("sent (sandbox)")
        inv.link = r.json().get("href", inv.link)
        return inv

    def get_invoice(self, invoice_id: str) -> Invoice:
        r = httpx.get(f"{self.base}/v2/invoicing/invoices/{invoice_id}", headers=self._h(), timeout=30)
        r.raise_for_status()
        j = r.json()
        inv = self.invoices.get(invoice_id)
        if inv is None:                                       # created before a restart: rebuild from PayPal's answer
            detail = j.get("detail") or {}
            email = (((j.get("primary_recipients") or [{}])[0]).get("billing_info") or {}).get("email_address", "")
            inv = Invoice(id=invoice_id, status=j.get("status", "UNKNOWN"), recipient_email=email,
                          amount=_dollars((j.get("amount") or {}).get("value")), currency=detail.get("currency_code", "USD"),
                          memo=detail.get("note", ""), link=(detail.get("metadata") or {}).get("recipient_view_url", ""),
                          events=["read (sandbox)"])
            self.invoices[invoice_id] = inv
        inv.status = j.get("status", inv.status)
        return inv

    def settle_invoice(self, invoice_id: str) -> Invoice:
        raise RuntimeError("in sandbox the payer settles on PayPal's page; the webhook updates the status")

    def create_order(self, *, amount: int, currency: str, note: str) -> Order:
        body = {"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": currency, "value": f"{amount}.00"},
                                                          "description": note[:127]}]}
        r = httpx.post(f"{self.base}/v2/checkout/orders", headers=self._h(), json=body, timeout=30)
        r.raise_for_status()
        j = r.json()
        approve = next((l["href"] for l in j.get("links", []) if l.get("rel") in ("approve", "payer-action")), "")
        o = Order(id=j["id"], status=j.get("status", "CREATED"), amount=amount, currency=currency, note=note,
                  approve_link=approve, events=["created (sandbox)"])
        self.orders[o.id] = o
        return o

    def approve_order(self, order_id: str) -> Order:
        raise RuntimeError("in sandbox the donor approves on PayPal's page")

    def capture_order(self, order_id: str) -> Order:
        r = httpx.post(f"{self.base}/v2/checkout/orders/{order_id}/capture", headers=self._h(), timeout=30)
        r.raise_for_status()
        j = r.json()
        o = self.orders.get(order_id)
        if o is None:                                         # created before a restart: rebuild from the capture
            try:
                cap = j["purchase_units"][0]["payments"]["captures"][0]["amount"]
            except (KeyError, IndexError, TypeError):
                cap = {}
            o = Order(id=order_id, status="CREATED", amount=_dollars(cap.get("value")), currency=cap.get("currency_code", "USD"),
                      note="", approve_link="", events=["read (sandbox)"])
            self.orders[order_id] = o
        o.status = j.get("status", "UNKNOWN"); o.events.append(f"capture answered {o.status} (sandbox)")
        return o


def client() -> MockPayPal | SandboxPayPal:
    return MockPayPal() if is_mock() else SandboxPayPal()


# Webhook signature verification (sandbox and live share the same endpoint shape).
TRANSMISSION_HEADERS = ("paypal-transmission-id", "paypal-transmission-time", "paypal-transmission-sig",
                        "paypal-cert-url", "paypal-auth-algo")


def verify_webhook(headers, body: bytes | str, webhook_id: str, *, client: "SandboxPayPal | None" = None) -> bool:
    """True only when PayPal answers verification_status == "SUCCESS" for this delivery.

    `headers` is any case-insensitive mapping (Starlette's request.headers works); `body` is the
    raw event body exactly as received: it is spliced into the verify request untouched, because
    PayPal signs the bytes it sent, not a re-serialised copy. Missing headers, an empty webhook id,
    or any transport error count as not verified."""
    if not webhook_id:
        return False
    h = {k: headers.get(k) or headers.get(k.upper()) for k in TRANSMISSION_HEADERS}
    if not all(h.values()):
        return False
    raw = body.decode() if isinstance(body, bytes) else body
    meta = {"auth_algo": h["paypal-auth-algo"], "cert_url": h["paypal-cert-url"],
            "transmission_id": h["paypal-transmission-id"], "transmission_sig": h["paypal-transmission-sig"],
            "transmission_time": h["paypal-transmission-time"], "webhook_id": webhook_id}
    payload = json.dumps(meta)[:-1] + ', "webhook_event": ' + raw + "}"
    pp = client or SandboxPayPal()
    try:
        r = httpx.post(f"{pp.base}/v1/notifications/verify-webhook-signature", headers=pp._h(),
                       content=payload.encode(), timeout=20)
        r.raise_for_status()
        return r.json().get("verification_status") == "SUCCESS"
    except (httpx.HTTPError, ValueError, KeyError):
        return False
