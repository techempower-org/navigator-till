"""GET /desk: today's quotes, unpaid invoices, paid pickups, donations captured; optional token gate."""
import re

import pytest
from fastapi.testclient import TestClient

from navigator_till import app as appmod
from navigator_till.app import app
from navigator_till.store import Store


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "store", Store(tmp_path / "desk.db"))
    monkeypatch.delenv("NT_DESK_TOKEN", raising=False)


def _section(html, heading):
    return html.split(heading, 1)[1].split("</div>", 1)[0]


def test_desk_lists_quotes_unpaid_pickups_and_donations(fresh):
    a = TestClient(app)                                                 # quoted, invoiced, unpaid
    a.post("/chat", data={"message": "laptop, there are 3 of us and we make about $28,000 a year", "email": "a@example.test"})
    a.post("/confirm", data={"what": "device"})
    b = TestClient(app)                                                 # quoted, paid, picked up
    b.post("/chat", data={"message": "desktop, 2 people, we make $40,000 a year", "email": "b@example.test"})
    r = b.post("/confirm", data={"what": "device"})
    iid = "INV2-MOCK-" + r.text.split("INV2-MOCK-")[1].split("<")[0]
    b.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": iid})
    c = TestClient(app)                                                 # free, pickup note only
    c.post("/chat", data={"message": "laptop, family of 4, I'm on CalFresh"})
    c.post("/confirm", data={"what": "device"})
    d = TestClient(app)                                                 # donor
    d.post("/chat", data={"message": "I want to cover a laptop for someone, $100"})
    r = d.post("/confirm", data={"what": "donation"})
    oid = "ORD-MOCK-" + r.text.split("ORD-MOCK-")[1].split("<")[0]
    d.post("/webhook/paypal", data={"event_type": "CHECKOUT.ORDER.APPROVED", "resource_id": oid})
    e = TestClient(app)                                                 # only asked a question: no quote
    e.post("/chat", data={"message": "laptop"})

    html = TestClient(app).get("/desk").text
    assert "Quotes today (3)" in html and "Unpaid invoices (1)" in html and "Paid pickups (2)" in html and "Donations captured (1)" in html
    q = _section(html, "Quotes today")
    assert "$28,000" in q and "invoice sent" in q and "Calfresh" in q and "ready for pickup" in q
    u = _section(html, "Unpaid invoices")
    assert "a@example.test" in u and "$50" in u and "b@example.test" not in u
    p = _section(html, "Paid pickups")
    assert "b@example.test" in p and iid in p and "no charge" in p and "$90" in p   # desktop $180, 2 people at 174%: 50%
    assert oid in _section(html, "Donations captured") and "$100" in _section(html, "Donations captured")
    assert "Vista del navegador" in TestClient(app).get("/desk?lang=es").text


def test_desk_is_empty_and_quiet_on_a_fresh_store(fresh):
    html = TestClient(app).get("/desk").text
    assert html.count("None yet.") == 4 and "Quotes today (0)" in html


def test_desk_token_gate(fresh, monkeypatch):
    monkeypatch.setenv("NT_DESK_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.get("/desk").status_code == 403
    assert c.get("/desk?token=wrong").status_code == 403
    r = c.get("/desk?token=s3cret", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/desk"      # the secret leaves the URL
    assert "s3cret" not in c.cookies.get("nt_desk")                       # a digest, not the token
    r = c.get("/desk")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"   # the cookie keeps it
    forged = TestClient(app, cookies={"nt_desk": "s3cret"})
    assert forged.get("/desk").status_code == 403


def test_desk_fails_closed_in_sandbox_mode_without_a_token(fresh, monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    assert TestClient(app).get("/desk").status_code == 403
    monkeypatch.setenv("NT_DESK_TOKEN", "s3cret")
    c = TestClient(app, base_url="https://testserver")                     # the cookie is Secure there
    c.get("/desk?token=s3cret")
    assert c.get("/desk").status_code == 200
    plain = TestClient(app)
    plain.get("/desk?token=s3cret")
    assert plain.get("/desk").status_code == 403                           # Secure cookie never rides plain http
