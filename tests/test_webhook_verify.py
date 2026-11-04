"""Webhook signature verification: PayPal's JSON event shape, verify-webhook-signature in sandbox
mode, and the mock form path staying open in mock mode. httpx is monkeypatched; nothing leaves the box."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from navigator_till import app as appmod, paypal, pricing
from navigator_till.app import app

HEADERS = {"PAYPAL-TRANSMISSION-ID": "t-1", "PAYPAL-TRANSMISSION-TIME": "2026-11-04T16:00:00Z",
           "PAYPAL-TRANSMISSION-SIG": "sig==", "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/cert.pem",
           "PAYPAL-AUTH-ALGO": "SHA256withRSA"}


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def _fake_http(monkeypatch, verdict="SUCCESS", invoice_status="PAID", seen=None):
    def post(url, headers=None, content=None, json=None, data=None, timeout=None):
        if url.endswith("/v1/oauth2/token"):
            return FakeResp({"access_token": "tok", "expires_in": 3000})
        if url.endswith("/verify-webhook-signature"):
            if seen is not None:
                seen.append(content)
            return FakeResp({"verification_status": verdict})
        raise AssertionError(f"unexpected POST {url}")

    def get(url, headers=None, timeout=None):
        return FakeResp({"status": invoice_status, "amount": {"value": "50.00", "currency_code": "USD"},
                         "detail": {"currency_code": "USD", "note": "laptop"},
                         "primary_recipients": [{"billing_info": {"email_address": "pat@example.test"}}]})
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)


def test_verify_webhook_splices_raw_body_and_headers(monkeypatch):
    seen = []
    _fake_http(monkeypatch, seen=seen)
    sb = paypal.SandboxPayPal(client_id="id", secret="sec")
    raw = b'{"event_type":"INVOICING.INVOICE.PAID","resource":{"invoice":{"id":"INV2-X"}}}'
    assert paypal.verify_webhook(HEADERS, raw, "WH-123", client=sb) is True
    sent = json.loads(seen[0])
    assert sent["webhook_id"] == "WH-123" and sent["transmission_id"] == "t-1" and sent["auth_algo"] == "SHA256withRSA"
    assert sent["cert_url"].startswith("https://") and sent["transmission_sig"] == "sig=="
    assert seen[0].endswith(b'"webhook_event": ' + raw + b"}")          # bytes as received, not re-serialised


def test_verify_webhook_false_on_failure_missing_headers_or_no_id(monkeypatch):
    _fake_http(monkeypatch, verdict="FAILURE")
    sb = paypal.SandboxPayPal(client_id="id", secret="sec")
    assert paypal.verify_webhook(HEADERS, b"{}", "WH-1", client=sb) is False
    _fake_http(monkeypatch, verdict="SUCCESS")
    assert paypal.verify_webhook({k: v for k, v in HEADERS.items() if k != "PAYPAL-TRANSMISSION-SIG"}, b"{}", "WH-1", client=sb) is False
    assert paypal.verify_webhook(HEADERS, b"{}", "", client=sb) is False


@pytest.fixture
def sandbox(monkeypatch):
    """Sandbox mode with a fake PayPal: one SENT invoice bound to a session, token and verify stubbed."""
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-123")
    sb = paypal.SandboxPayPal(client_id="id", secret="sec")
    monkeypatch.setattr(appmod, "pp", sb)
    q = pricing.quote("laptop", 3, 28000)
    inv = paypal.Invoice(id="INV2-SB-1", status="SENT", recipient_email="pat@example.test", amount=q.price,
                         currency="USD", memo="laptop", link="https://sandbox.paypal.com/i/INV2-SB-1")
    sb.invoices[inv.id] = inv
    appmod.store.put("sb-session", {"log": [], "quote": q, "invoice_id": inv.id})
    yield sb
    appmod.store.delete("sb-session")


EVENT = {"id": "WH-EVT-1", "event_type": "INVOICING.INVOICE.PAID", "resource": {"invoice": {"id": "INV2-SB-1", "status": "PAID"}}}


def test_sandbox_json_event_verified_writes_receipt(monkeypatch, sandbox):
    _fake_http(monkeypatch, verdict="SUCCESS")
    r = TestClient(app).post("/webhook/paypal", json=EVENT, headers=HEADERS)
    assert r.status_code == 200 and r.json() == {"ok": True, "status": "PAID"}
    assert appmod.store.get("sb-session")["receipt"].startswith("Paid: $50")


def test_sandbox_rejects_bad_signature_form_path_and_missing_webhook_id(monkeypatch, sandbox):
    _fake_http(monkeypatch, verdict="FAILURE")
    c = TestClient(app)
    assert c.post("/webhook/paypal", json=EVENT, headers=HEADERS).status_code == 403
    _fake_http(monkeypatch, verdict="SUCCESS")
    assert c.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": "INV2-SB-1"}).status_code == 403
    assert c.post("/webhook/paypal", json=EVENT).status_code == 403                 # no transmission headers
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID")
    assert c.post("/webhook/paypal", json=EVENT, headers=HEADERS).status_code == 403
    assert "receipt" not in appmod.store.get("sb-session")


def test_mock_mode_accepts_json_event_for_own_session():
    c = TestClient(app)
    c.post("/chat", data={"message": "laptop, there are 3 of us and we make about $28,000 a year"})
    r = c.post("/confirm", data={"what": "device"})
    iid = "INV2-MOCK-" + r.text.split("INV2-MOCK-")[1].split("<")[0]
    r = c.post("/webhook/paypal", json={"event_type": "INVOICING.INVOICE.PAID", "resource": {"invoice": {"id": iid}}})
    assert r.json()["status"] == "PAID"
    assert c.post("/webhook/paypal", json={"event_type": "INVOICING.INVOICE.PAID"}).status_code == 400


def test_sandbox_webhook_after_restart_rebuilds_invoice_from_paypal(monkeypatch, sandbox):
    """The process restarted: the session is in SQLite but the client's invoice cache is empty."""
    _fake_http(monkeypatch, verdict="SUCCESS")
    sandbox.invoices.clear()
    r = TestClient(app).post("/webhook/paypal", json=EVENT, headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "PAID"
    st = appmod.store.get("sb-session")
    assert st["paid"] == 50 and st["receipt"].startswith("Paid: $50") and sandbox.get_invoice("INV2-SB-1").recipient_email == "pat@example.test"


def test_sandbox_capture_after_restart_rebuilds_order(monkeypatch, sandbox):
    def post(url, headers=None, content=None, json=None, data=None, timeout=None):
        if url.endswith("/v1/oauth2/token"):
            return FakeResp({"access_token": "tok", "expires_in": 3000})
        if url.endswith("/verify-webhook-signature"):
            return FakeResp({"verification_status": "SUCCESS"})
        if url.endswith("/v2/checkout/orders/ORD-SB-9/capture"):
            return FakeResp({"id": "ORD-SB-9", "status": "COMPLETED",
                             "purchase_units": [{"payments": {"captures": [{"amount": {"value": "100.00", "currency_code": "USD"}}]}}]})
        raise AssertionError(f"unexpected POST {url}")
    monkeypatch.setattr(httpx, "post", post)
    appmod.store.put("donor", {"log": [], "donation": 100, "order_id": "ORD-SB-9"})
    r = TestClient(app).post("/webhook/paypal", json={"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "ORD-SB-9"}}, headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    assert appmod.store.get("donor")["thanks"].startswith("Captured $100")
    appmod.store.delete("donor")
