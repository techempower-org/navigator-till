"""UI strings in English (default) and Spanish. `?lang=es` on any page sets the nt_lang cookie.
Templates call t('key', ...); app.py and agent.py call tr(lang). Device and band labels come from
the org's pricing.yaml, so their Spanish lives in LABELS keyed by the English text and falls back
to English for any label the org adds later. steps() rebuilds the quote's arithmetic in the
chosen language from the Quote's numbers, never from a model.
"""
from __future__ import annotations

from typing import Callable

from .pricing import Quote

LANGS = ("en", "es")
DEFAULT = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "lang_name": "English", "switch_to": "Español", "switch_lang": "es",
        "mock_pill": "mock PayPal", "sandbox_pill": "PayPal sandbox",
        "tagline": "Tell the desk what you need. The price comes from the sliding scale, the words come from the agent, and nothing is charged until you press YES.",
        "footer": "Prices follow {org}'s sliding scale (editable YAML); the agent explains and never calculates.",
        "source": "Source (MIT)", "you": "you", "desk": "the desk",
        "greeting": "Hi. I can price a refurbished laptop or desktop for your household, or take a donation that covers one for a neighbor. For example: \"I need a laptop, there are 3 of us and I'm on CalFresh\" or \"I want to cover a laptop for someone, $100\".",
        "ready": "Ready?", "no_charge_yes": "No charge. YES writes your pickup note.",
        "yes_invoice": "YES sends a PayPal invoice for ${price} to {email}.", "your_email": "your email",
        "yes_checkout": "YES opens PayPal checkout for ${amount}.", "nothing_until": "Nothing happens until you press it.",
        "yes_button": "YES, go ahead", "no_button": "No, start over", "type_here": "Type here…",
        "email_placeholder": "Email for the invoice or receipt (optional)", "send": "Send",
        "invoice_sent": "Invoice sent", "invoice": "Invoice", "amount": "Amount", "status": "Status", "pay_at": "Pay at",
        "for": "For", "events": "Events:", "mock_payer": "Mock payer:",
        "mock_payer_text": "in the sandbox PayPal's hosted page takes the payment and a webhook tells us. Here, press this to play the payer.",
        "i_paid": "I paid the invoice", "see_receipt": "See the receipt after paying",
        "after_pay": "After the client pays on PayPal, the webhook marks it paid and the", "receipt_link": "receipt", "appears": "appears.",
        "back": "Back to the desk", "order_created": "Donation order created", "order": "Order", "approve_at": "Approve at",
        "mock_donor": "Mock donor:", "mock_donor_text": "in the sandbox the donor approves on PayPal's page; press this to play the donor, then we capture.",
        "i_approved": "I approved the order", "see_thanks": "See the thank-you after approving",
        "receipt_title": "Receipt", "receipt_heading": "Receipt and pickup note", "device": "Device", "list_price": "List price",
        "band": "Band", "you_paid": "You paid", "reference": "Reference", "how_worked": "How the price was worked out",
        "read_aloud": "Read this aloud", "stop_reading": "Stop reading", "no_tts": "Read aloud not available in this browser",
        "print": "Print", "start_over": "Start over", "thank_you": "Thank you",
        # chat replies (app.py)
        "ask_amount": "Thank you. How much would you like to cover? A whole laptop is $200; any amount helps.",
        "donation_ready": "Thank you. ${amount} toward a device for a neighbor who can't pay the full price. Press YES to open PayPal checkout.",
        "need_device": "which device you need (laptop, desktop, or a battery backup)",
        "need_household": "how many people live in your household",
        "need_income": "roughly what your household makes in a year, or a program you're on (CalFresh, Medi-Cal, SSI, Lifeline, WIC, Section 8, free lunch)",
        "can_price": "I can price that. Tell me {needs}.", "cannot_price": "I couldn't price that: {error}",
        "free_yes": "No invoice needed. Press YES and I'll write your pickup note.",
        "invoice_yes": "Press YES and I'll send a PayPal invoice for ${price} to your email.",
        "invoice_sent_msg": "Invoice {id} sent for ${amount}. Pay it at the link; I'll write your pickup note when it clears.",
        "invoice_open": "Invoice {id} for ${amount} is still open, so the price stays as billed. Pay it or press Start over to quote again.",
        "order_created_msg": "Order {id} created for ${amount}. Approve it on PayPal and I'll capture it.",
        "captured_msg": "Captured ${amount} (PayPal {id}). That covers {gaps} sliding-scale gaps of $50, or most of one laptop.",
        # offline explainer and receipt (agent.py)
        "explain_intro": "Here is how the price works for the {device}.",
        "explain_free": "So this one is free for you. We only ask that you pick it up and let us show you how it works.",
        "explain_pay": "So you would pay ${price}. We send a PayPal invoice; you can pay by card, bank, or PayPal, and there is no fee to you.",
        "explain_fix": "If the income or household number is off, tell me and I will redo it.",
        "receipt_text": "Paid: ${paid} for one {device} (PayPal reference {ref}). Pick-up: TechEMPOWER, 136 Idaho Maryland Rd, Grass Valley, weekdays 10-4; bring this note. Your device comes with a 90-day warranty and free help getting set up.",
        "step_list": "{device}: list price ${list_price}.",
        "step_program": "Enrolled in {program}: that places the household in the first band ({band}).",
        "step_fpl": "Household of {household}: the 2026 poverty line is ${fpl:,} a year.",
        "step_pct": "Income ${income:,} is {pct}% of that line.",
        "step_band": "Band '{band}': the client pays {share}% of list = ${price}.",
        # navigator view (/desk)
        "desk_title": "Navigator view", "desk_today": "Today", "desk_quotes": "Quotes today", "desk_unpaid": "Unpaid invoices",
        "desk_pickups": "Paid pickups", "desk_donations": "Donations captured", "desk_none": "None yet.", "when": "When",
        "household": "Household", "income": "Income", "program": "Program", "price": "Price", "email": "Email",
        "paid": "Paid", "stage": "Stage", "stage_quoted": "quoted", "stage_invoiced": "invoice sent", "stage_paid": "paid",
        "stage_pickup": "ready for pickup", "no_charge": "no charge",
    },
    "es": {
        "lang_name": "Español", "switch_to": "English", "switch_lang": "en",
        "mock_pill": "PayPal simulado", "sandbox_pill": "PayPal sandbox",
        "tagline": "Dile al mostrador qué necesitas. El precio sale de la escala móvil, las palabras las pone el agente, y no se cobra nada hasta que pulses SÍ.",
        "footer": "Los precios siguen la escala móvil de {org} (YAML editable); el agente explica y nunca calcula.",
        "source": "Código fuente (MIT)", "you": "tú", "desk": "el mostrador",
        "greeting": "Hola. Puedo calcular el precio de una laptop o computadora de escritorio reacondicionada para tu hogar, o recibir una donación que cubra una para un vecino. Por ejemplo: \"Necesito una laptop, somos 3 y tengo CalFresh\" o \"Quiero cubrir una laptop para alguien, $100\".",
        "ready": "¿Listo?", "no_charge_yes": "Sin costo. SÍ escribe tu nota de recogida.",
        "yes_invoice": "SÍ envía una factura de PayPal por ${price} a {email}.", "your_email": "tu correo",
        "yes_checkout": "SÍ abre el pago de PayPal por ${amount}.", "nothing_until": "No pasa nada hasta que lo pulses.",
        "yes_button": "SÍ, adelante", "no_button": "No, empezar de nuevo", "type_here": "Escribe aquí…",
        "email_placeholder": "Correo para la factura o el recibo (opcional)", "send": "Enviar",
        "invoice_sent": "Factura enviada", "invoice": "Factura", "amount": "Monto", "status": "Estado", "pay_at": "Pagar en",
        "for": "Para", "events": "Eventos:", "mock_payer": "Pagador simulado:",
        "mock_payer_text": "en el sandbox la página de PayPal cobra y un webhook nos avisa. Aquí, pulsa esto para hacer de pagador.",
        "i_paid": "Pagué la factura", "see_receipt": "Ver el recibo después de pagar",
        "after_pay": "Cuando el cliente paga en PayPal, el webhook la marca pagada y aparece el", "receipt_link": "recibo", "appears": ".",
        "back": "Volver al mostrador", "order_created": "Orden de donación creada", "order": "Orden", "approve_at": "Aprobar en",
        "mock_donor": "Donante simulado:", "mock_donor_text": "en el sandbox el donante aprueba en la página de PayPal; pulsa esto para hacer de donante y luego capturamos.",
        "i_approved": "Aprobé la orden", "see_thanks": "Ver el agradecimiento después de aprobar",
        "receipt_title": "Recibo", "receipt_heading": "Recibo y nota de recogida", "device": "Equipo", "list_price": "Precio de lista",
        "band": "Tramo", "you_paid": "Pagaste", "reference": "Referencia", "how_worked": "Cómo se calculó el precio",
        "read_aloud": "Leer en voz alta", "stop_reading": "Dejar de leer", "no_tts": "Lectura en voz alta no disponible en este navegador",
        "print": "Imprimir", "start_over": "Empezar de nuevo", "thank_you": "Gracias",
        "ask_amount": "Gracias. ¿Cuánto quieres cubrir? Una laptop completa cuesta $200; cualquier cantidad ayuda.",
        "donation_ready": "Gracias. ${amount} para un equipo de un vecino que no puede pagar el precio completo. Pulsa SÍ para abrir el pago de PayPal.",
        "need_device": "qué equipo necesitas (laptop, computadora de escritorio o batería de respaldo)",
        "need_household": "cuántas personas viven en tu hogar",
        "need_income": "más o menos cuánto gana tu hogar al año, o un programa que tengas (CalFresh, Medi-Cal, SSI, Lifeline, WIC, Sección 8, almuerzo gratis)",
        "can_price": "Puedo calcular eso. Dime {needs}.", "cannot_price": "No pude calcular eso: {error}",
        "free_yes": "No hace falta factura. Pulsa SÍ y escribo tu nota de recogida.",
        "invoice_yes": "Pulsa SÍ y envío una factura de PayPal por ${price} a tu correo.",
        "invoice_sent_msg": "Factura {id} enviada por ${amount}. Págala en el enlace; escribo tu nota de recogida cuando se acredite.",
        "invoice_open": "La factura {id} por ${amount} sigue abierta, así que el precio queda como se facturó. Págala o pulsa Empezar de nuevo para cotizar otra vez.",
        "order_created_msg": "Orden {id} creada por ${amount}. Apruébala en PayPal y la capturo.",
        "captured_msg": "Capturados ${amount} (PayPal {id}). Eso cubre {gaps} tramos de $50 de la escala móvil, o casi una laptop.",
        "explain_intro": "Así se calcula el precio de la {device}.",
        "explain_free": "Así que esta es gratis para ti. Solo pedimos que la recojas y nos dejes mostrarte cómo funciona.",
        "explain_pay": "Así que pagarías ${price}. Enviamos una factura de PayPal; puedes pagar con tarjeta, banco o PayPal, sin comisión para ti.",
        "explain_fix": "Si el ingreso o el número de personas no es correcto, dímelo y lo rehago.",
        "receipt_text": "Pagado: ${paid} por una {device} (referencia PayPal {ref}). Recogida: TechEMPOWER, 136 Idaho Maryland Rd, Grass Valley, de lunes a viernes de 10 a 4; trae esta nota. Tu equipo incluye 90 días de garantía y ayuda gratis para configurarlo.",
        "step_list": "{device}: precio de lista ${list_price}.",
        "step_program": "Inscrito en {program}: eso coloca al hogar en el primer tramo ({band}).",
        "step_fpl": "Hogar de {household}: la línea de pobreza 2026 es ${fpl:,} al año.",
        "step_pct": "Un ingreso de ${income:,} es el {pct}% de esa línea.",
        "step_band": "Tramo '{band}': el cliente paga el {share}% del precio de lista = ${price}.",
        "desk_title": "Vista del navegador", "desk_today": "Hoy", "desk_quotes": "Cotizaciones de hoy", "desk_unpaid": "Facturas sin pagar",
        "desk_pickups": "Recogidas pagadas", "desk_donations": "Donaciones capturadas", "desk_none": "Todavía nada.", "when": "Cuándo",
        "household": "Hogar", "income": "Ingreso", "program": "Programa", "price": "Precio", "email": "Correo",
        "paid": "Pagado", "stage": "Etapa", "stage_quoted": "cotizado", "stage_invoiced": "factura enviada", "stage_paid": "pagado",
        "stage_pickup": "listo para recoger", "no_charge": "sin costo",
    },
}

# pricing.yaml labels (English, org-edited) -> Spanish; unknown labels fall back to the English text.
LABELS = {
    "es": {
        "Refurbished laptop": "Laptop reacondicionada",
        "Refurbished laptop (newer, more memory)": "Laptop reacondicionada (más nueva, más memoria)",
        "Refurbished desktop with monitor": "Computadora de escritorio reacondicionada con monitor",
        "Battery backup (as-is)": "Batería de respaldo (tal cual)",
        "at or below the poverty line": "en la línea de pobreza o por debajo",
        "up to 150% of the poverty line": "hasta el 150% de la línea de pobreza",
        "up to 200% of the poverty line": "hasta el 200% de la línea de pobreza",
        "up to 300% of the poverty line": "hasta el 300% de la línea de pobreza",
        "above 300% of the poverty line": "más del 300% de la línea de pobreza",
    },
}


def pick(value: str | None) -> str:
    return value if value in LANGS else DEFAULT


def t(lang: str, key: str, **kw) -> str:
    table = STRINGS.get(lang) or STRINGS[DEFAULT]
    return (table.get(key) or STRINGS[DEFAULT][key]).format(**kw)


def tr(lang: str) -> Callable[..., str]:
    lang = pick(lang)
    return lambda key, **kw: t(lang, key, **kw)


def label(lang: str, text: str) -> str:
    return LABELS.get(pick(lang), {}).get(text, text)


def steps(q: Quote, lang: str) -> list[str]:
    """The quote's arithmetic in `lang`, rebuilt from the Quote's numbers (English: the rules' own steps)."""
    if pick(lang) == DEFAULT:
        return list(q.steps)
    T = tr(lang)
    band = label(lang, q.band_label)
    out = [T("step_list", device=label(lang, q.device_label), list_price=q.list_price)]
    if q.categorical:
        out.append(T("step_program", program=q.categorical.title(), band=band))
    else:
        out.append(T("step_fpl", household=q.household, fpl=q.fpl))
        out.append(T("step_pct", income=q.annual_income, pct=q.pct_of_fpl))
    out.append(T("step_band", band=band, share=int(q.pay_share * 100), price=q.price))
    return out
