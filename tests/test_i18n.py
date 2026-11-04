"""Spanish: ?lang=es sets a cookie; every UI string, the offline explainer, the receipt and the
quote's steps render in Spanish; English stays the default. The dictionaries must be complete."""
from fastapi.testclient import TestClient

from navigator_till import agent, i18n, pricing
from navigator_till.app import app


def test_dictionaries_cover_the_same_keys_and_labels():
    assert set(i18n.STRINGS["es"]) == set(i18n.STRINGS["en"])
    rules = pricing.load_rules()
    for d in rules["devices"].values():
        assert i18n.label("es", d["label"]) != d["label"]
    for b in rules["bands"]:
        assert i18n.label("es", b["label"]) != b["label"]
    assert i18n.label("es", "Some new label") == "Some new label"      # org adds a device: English fallback, no crash
    assert i18n.pick("fr") == "en" and i18n.pick(None) == "en" and i18n.pick("es") == "es"


def test_offline_explainer_receipt_and_steps_in_spanish():
    q = pricing.quote("laptop", 3, 28000)
    es = agent.explain_offline(q, "es")
    assert "línea de pobreza 2026 es $27,320" in es and "pagarías $50" in es and "$50" in es
    assert agent.explain_offline(q) == agent.explain_offline(q, "en") and "Here is how" in agent.explain_offline(q)
    assert i18n.steps(q, "en") == q.steps
    cat = pricing.quote("desktop", 4, None, program="calfresh")
    assert "Inscrito en Calfresh" in agent.explain_offline(cat, "es") and "gratis" in agent.explain_offline(cat, "es")
    assert agent.receipt_offline(q, 50, "INV2-1", "es").startswith("Pagado: $50 por una laptop reacondicionada")


def test_spanish_input_is_parsed_offline():
    r = agent.parse_offline("Necesito una laptop, somos 3 y ganamos $28,000 al año")
    assert r.kind == "device" and r.device == "laptop" and r.household == 3 and r.annual_income == 28000 and not r.missing
    r = agent.parse_offline("una computadora de escritorio, familia de 4, tengo Medi-Cal")
    assert r.device == "desktop" and r.household == 4 and r.program == "medi-cal"
    r = agent.parse_offline("Quiero donar $100 para cubrir una laptop")
    assert r.kind == "donation" and r.donation_amount == 100


def test_spanish_chat_invoice_and_receipt():
    c = TestClient(app)
    r = c.get("/?lang=es")
    assert "Hola. Puedo calcular" in r.text and 'lang="es"' in r.text and c.cookies.get("nt_lang") == "es"
    assert ">English<" in r.text                                              # switch back link
    r = c.post("/chat", data={"message": "Necesito una laptop, somos 3 y ganamos $28,000 al año", "email": "pat@example.test"})
    assert "SÍ envía una factura de PayPal por $50 a pat@example.test" in r.text and "SÍ, adelante" in r.text
    assert "Pulsa SÍ y envío una factura" in r.text and "línea de pobreza" in r.text and "Here is how" not in r.text
    r = c.post("/confirm", data={"what": "device"})
    assert "Factura enviada" in r.text and "Pagué la factura" in r.text and "Laptop reacondicionada" in r.text
    iid = "INV2-MOCK-" + r.text.split("INV2-MOCK-")[1].split("<")[0]
    assert c.post("/webhook/paypal", data={"event_type": "INVOICING.INVOICE.PAID", "resource_id": iid}).json()["status"] == "PAID"
    r = c.get("/receipt")
    assert "Recibo y nota de recogida" in r.text and "Pagaste" in r.text and "Pagado: $50" in r.text
    assert "Leer en voz alta" in r.text and "Imprimir" in r.text and "Cómo se calculó el precio" in r.text
    assert "hasta el 150% de la línea de pobreza" in r.text and "Volver al mostrador" in r.text
    assert "Read this aloud" not in r.text and "Receipt and pickup note" not in r.text


def test_spanish_donation_and_missing_info():
    c = TestClient(app)
    c.get("/?lang=es")
    r = c.post("/chat", data={"message": "laptop"})
    assert "Puedo calcular eso. Dime cuántas personas viven en tu hogar" in r.text
    r = c.post("/chat", data={"message": "Quiero donar $100 para cubrir una laptop"})
    assert "SÍ abre el pago de PayPal por $100" in r.text
    r = c.post("/confirm", data={"what": "donation"})
    assert "Orden de donación creada" in r.text and "Aprobé la orden" in r.text
    oid = "ORD-MOCK-" + r.text.split("ORD-MOCK-")[1].split("<")[0]
    c.post("/webhook/paypal", data={"event_type": "CHECKOUT.ORDER.APPROVED", "resource_id": oid})
    r = c.get("/receipt")
    assert "Gracias" in r.text and "Capturados $100" in r.text
    r = c.get("/?lang=en")
    assert "Hi. I can price" not in r.text and c.cookies.get("nt_lang") == "en"   # log kept; greeting only shows on an empty log


def test_english_is_default_and_unchanged():
    c = TestClient(app)
    r = c.get("/")
    assert 'lang="en"' in r.text and "Hi. I can price" in r.text and ">Español<" in r.text
    r = c.post("/chat", data={"message": "I need a laptop, there are 3 of us and we make about $28,000 a year"})
    assert "YES sends a PayPal invoice for $50 to your email" in r.text and "Here is how the price works" in r.text
