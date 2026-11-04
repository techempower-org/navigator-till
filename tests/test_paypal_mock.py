import pytest

from navigator_till import paypal


def test_invoice_lifecycle():
    pp = paypal.MockPayPal()
    inv = pp.create_invoice(recipient_email="a@example.test", amount=50, currency="USD", memo="laptop")
    assert inv.status == "DRAFT" and inv.id.startswith("INV2-MOCK-")
    with pytest.raises(ValueError):
        pp.settle_invoice(inv.id)                 # cannot pay a draft
    assert pp.send_invoice(inv.id).status == "SENT"
    with pytest.raises(ValueError):
        pp.send_invoice(inv.id)                   # cannot send twice
    assert pp.settle_invoice(inv.id).status == "PAID"
    assert pp.get_invoice(inv.id).events[-1].startswith("paid")


def test_order_lifecycle():
    pp = paypal.MockPayPal()
    o = pp.create_order(amount=100, currency="USD", note="gap")
    assert o.status == "CREATED" and "checkoutnow" in o.approve_link
    with pytest.raises(ValueError):
        pp.capture_order(o.id)                    # capture before approval
    assert pp.approve_order(o.id).status == "APPROVED"
    assert pp.capture_order(o.id).status == "COMPLETED"


def test_rejects_non_positive_amounts():
    pp = paypal.MockPayPal()
    with pytest.raises(ValueError):
        pp.create_invoice(recipient_email="a@b.test", amount=0, currency="USD", memo="x")
    with pytest.raises(ValueError):
        pp.create_order(amount=-1, currency="USD", note="x")


def test_mock_is_default(monkeypatch):
    monkeypatch.delenv("MOCK", raising=False)
    assert paypal.is_mock() and isinstance(paypal.client(), paypal.MockPayPal)
    monkeypatch.setenv("MOCK", "0")
    assert not paypal.is_mock()
