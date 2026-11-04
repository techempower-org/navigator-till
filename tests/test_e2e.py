"""End to end in mock mode: chat -> quote -> YES -> invoice -> paid -> receipt; and the donor loop."""
import os

os.environ.setdefault("MOCK", "1")
os.environ.pop("ANTHROPIC_API_KEY", None)   # offline fallback on purpose

from fastapi.testclient import TestClient  # noqa: E402

from navigator_till import agent  # noqa: E402
from navigator_till.app import app  # noqa: E402


def test_offline_parser_reads_a_plain_sentence():
    r = agent.parse_offline("I need a laptop, there are 3 of us and we make about $28,000 a year")
    assert r.kind == "device" and r.device == "laptop" and r.household == 3 and r.annual_income == 28000 and r.missing == []
    r = agent.parse_offline("desktop please, family of 4, I'm on Medi-Cal")
    assert r.device == "desktop" and r.household == 4 and r.program == "medi-cal" and r.missing == []
    r = agent.parse_offline("I want to cover a laptop for someone, $100")
    assert r.kind == "donation" and r.donation_amount == 100
    r = agent.parse_offline("hello")
    assert r.kind == "unknown"


def test_client_loop_invoice_to_receipt():
    c = TestClient(app)
    r = c.post("/chat", data={"message": "I need a laptop, there are 3 of us and we make about $28,000 a year", "email": "pat@example.test"})
    assert r.status_code == 200 and "YES sends a PayPal invoice for $50" in r.text   # 3 people: FPL 27,320; 28,000 = 102% -> 25% of $200
    r = c.post("/confirm", data={"what": "device"})
    assert r.status_code == 200 and "Invoice sent" in r.text and "INV2-MOCK-" in r.text
    iid = r.text.split("INV2-MOCK-")[1].split("<")[0]
    r = c.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": f"INV2-MOCK-{iid}"})
    assert r.json()["status"] == "PAID"
    r = c.get("/receipt")
    assert r.status_code == 200 and "Receipt and pickup note" in r.text and "You paid" in r.text and "$50" in r.text
    assert "Read this aloud" in r.text and "speechSynthesis" in r.text          # browser TTS, no server audio
    assert "window.print()" in r.text and "@media print" in r.text               # print only the receipt card


def test_free_device_needs_no_invoice():
    c = TestClient(app)
    r = c.post("/chat", data={"message": "desktop please, family of 4, I'm on Medi-Cal"})
    assert "No charge" in r.text
    r = c.post("/confirm", data={"what": "device"})
    assert "Receipt and pickup note" in r.text and "no-charge" in r.text


def test_donor_loop_order_to_thanks():
    c = TestClient(app)
    r = c.post("/chat", data={"message": "I want to cover a laptop for someone, $100"})
    assert "YES opens PayPal checkout for $100" in r.text
    r = c.post("/confirm", data={"what": "donation"})
    assert "Donation order created" in r.text
    oid = "ORD-MOCK-" + r.text.split("ORD-MOCK-")[1].split("<")[0]
    r = c.post("/webhook/paypal", data={"event_type": "CHECKOUT.ORDER.APPROVED", "resource_id": oid})
    assert r.json()["status"] == "COMPLETED"
    assert "Thank you" in c.get("/receipt").text


def test_nothing_is_charged_without_yes():
    c = TestClient(app)
    c.post("/chat", data={"message": "laptop, 2 people, $40,000 a year"})
    from navigator_till.app import pp
    before = len(pp.invoices)
    c.post("/chat", data={"message": "actually make it a desktop"})
    assert len(pp.invoices) == before


def test_healthz():
    assert TestClient(app).get("/healthz").json()["mock"] is True


def test_another_session_cannot_settle_my_invoice():
    me = TestClient(app)
    r = me.post("/chat", data={"message": "laptop, there are 3 of us and we make about $28,000 a year"})
    r = me.post("/confirm", data={"what": "device"})
    iid = "INV2-MOCK-" + r.text.split("INV2-MOCK-")[1].split("<")[0]
    stranger = TestClient(app)
    r = stranger.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": iid})
    assert r.status_code == 403
    from navigator_till.app import pp
    assert pp.get_invoice(iid).status == "SENT"              # untouched
    assert me.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": iid}).json()["status"] == "PAID"


def test_unapproved_order_cannot_be_captured_by_a_stranger():
    me = TestClient(app)
    me.post("/chat", data={"message": "I want to cover a laptop for someone, $40"})
    r = me.post("/confirm", data={"what": "donation"})
    oid = "ORD-MOCK-" + r.text.split("ORD-MOCK-")[1].split("<")[0]
    assert TestClient(app).post("/webhook/paypal", data={"event_type": "CHECKOUT.ORDER.APPROVED", "resource_id": oid}).status_code == 403

