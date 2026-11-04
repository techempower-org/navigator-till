"""Sessions persist in SQLite and survive a restart (a new Store on the same file, a new app store)."""
from fastapi.testclient import TestClient

from navigator_till import agent, pricing
from navigator_till import app as appmod
from navigator_till.app import app
from navigator_till.store import Store


def test_roundtrip_restores_dataclasses(tmp_path):
    s = Store(tmp_path / "s.db")
    q = pricing.quote("laptop", 3, 28000)
    s.put("a", {"log": [("you", "hi"), ("till", "ok")], "quote": q, "request": agent.parse_offline("laptop, 3 of us, $28,000"),
                "invoice_id": "INV2-1", "email": "pat@example.test"})
    st = s.get("a")
    assert st["quote"] == q and isinstance(st["quote"], pricing.Quote) and st["quote"].gap == 150
    assert isinstance(st["request"], agent.Request) and st["request"].household == 3
    assert st["log"] == [("you", "hi"), ("till", "ok")] and st["email"] == "pat@example.test"
    assert s.get("nope") is None


def test_survives_restart_find_and_delete(tmp_path):
    path = tmp_path / "s.db"
    Store(path).put("a", {"log": [], "invoice_id": "INV2-1"})
    Store(path).put("b", {"log": [], "invoice_id": "INV2-2"})
    again = Store(path)                                     # "restart": a fresh handle on the same file
    assert [sid for sid, _ in again.find("invoice_id", "INV2-2")] == ["b"]
    assert len(again.items()) == 2
    again.put("a", {"log": [("till", "paid")], "invoice_id": "INV2-1", "receipt": "x"})
    assert again.get("a")["receipt"] == "x" and again.get("a")["invoice_id"] == "INV2-1"
    again.delete("a")
    assert again.get("a") is None and len(again.items()) == 1


def test_app_session_survives_store_reopen(monkeypatch):
    c = TestClient(app)
    c.post("/chat", data={"message": "laptop, there are 3 of us and we make about $28,000 a year", "email": "pat@example.test"})
    r = c.post("/confirm", data={"what": "device"})
    iid = "INV2-MOCK-" + r.text.split("INV2-MOCK-")[1].split("<")[0]
    monkeypatch.setattr(appmod, "store", Store(appmod.store.path))   # the process restarts; same file
    assert "Invoice INV2-MOCK-" in c.get("/").text                   # the chat log is still there
    assert c.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": iid}).json()["status"] == "PAID"
    assert "You paid" in c.get("/receipt").text
    c.post("/reset")
    assert "Invoice INV2-MOCK-" not in c.get("/").text


def test_empty_sessions_are_not_written_and_old_ones_are_purged(tmp_path):
    import os, sqlite3, stat
    path = tmp_path / "s.db"
    s = Store(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    s.put("blank", {"log": []})
    assert s.get("blank") is None
    s.put("old", {"log": [("you", "hi")]})
    with sqlite3.connect(path) as c:
        c.execute("UPDATE sessions SET updated_at = '2020-01-01T00:00:00+00:00' WHERE sid = 'old'")
    assert Store(path).get("old") is None                   # purged on open
