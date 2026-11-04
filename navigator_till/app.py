"""The desk. One session per browser tab (a signed cookie would come later); state in memory.

Flow A (client): message -> parse -> quote (rules) -> explanation (agent) -> human YES ->
PayPal invoice created + sent -> paid (webhook, or the mock "I paid" button) -> receipt + pickup note.
Flow B (donor): message -> amount -> human YES -> PayPal order -> approved -> captured -> thank-you.
No money step happens without the YES button; the agent only ever proposes.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import agent, paypal, pricing

app = FastAPI(title="Navigator Till")
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
ORG = os.environ.get("NT_ORG", "TechEMPOWER")
ORG_EMAIL = os.environ.get("NT_ORG_EMAIL", "hi@techempower.org")
CURRENCY = "USD"

pp = paypal.client()
SESSIONS: dict[str, dict] = {}        # sid -> {"request", "quote", "invoice_id", "order_id", "log": [...]}


def _sid(request: Request) -> str:
    return request.cookies.get("nt_sid") or secrets.token_urlsafe(12)


def _state(sid: str) -> dict:
    return SESSIONS.setdefault(sid, {"log": []})


def _render(request: Request, name: str, sid: str, **ctx):
    st = _state(sid)
    resp = templates.TemplateResponse(request, name, {"org": ORG, "mock": paypal.is_mock(), "state": st, **ctx})
    resp.set_cookie("nt_sid", sid, httponly=True, samesite="lax")
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _render(request, "index.html", _sid(request))


@app.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form(...), email: str = Form("")):
    sid = _sid(request); st = _state(sid)
    st["log"].append(("you", message))
    req = agent.parse(message)
    st["request"] = req
    if email:
        st["email"] = email.strip()
    if req.kind == "donation":
        if req.missing:
            st["log"].append(("till", "Thank you. How much would you like to cover? A whole laptop is $200; any amount helps."))
            return _render(request, "index.html", sid)
        st["donation"] = req.donation_amount
        st["log"].append(("till", f"Thank you. ${req.donation_amount} toward a device for a neighbor who can't pay the full price. Press YES to open PayPal checkout."))
        return _render(request, "index.html", sid, confirm="donation")
    if req.kind == "unknown" or req.missing:
        ask = {"device": "which device you need (laptop, desktop, or a battery backup)",
               "household": "how many people live in your household",
               "income": "roughly what your household makes in a year, or a program you're on (CalFresh, Medi-Cal, SSI, Lifeline, WIC, Section 8, free lunch)"}
        need = [ask[m] for m in (req.missing or list(ask))]
        st["log"].append(("till", "I can price that. Tell me " + "; ".join(need) + "."))
        return _render(request, "index.html", sid)
    try:
        q = pricing.quote(req.device, req.household, req.annual_income, program=req.program)
    except (ValueError, KeyError) as e:
        st["log"].append(("till", f"I couldn't price that: {e}"))
        return _render(request, "index.html", sid)
    st["quote"] = q
    st["log"].append(("till", agent.explain(q)))
    if q.price == 0:
        st["log"].append(("till", "No invoice needed. Press YES and I'll write your pickup note."))
    else:
        st["log"].append(("till", f"Press YES and I'll send a PayPal invoice for ${q.price} to your email."))
    return _render(request, "index.html", sid, confirm="device")


@app.post("/confirm", response_class=HTMLResponse)
def confirm(request: Request, what: str = Form(...)):
    sid = _sid(request); st = _state(sid)
    if what == "device":
        q: pricing.Quote | None = st.get("quote")
        if not q:
            raise HTTPException(400, "nothing to confirm")
        if q.price == 0:
            st["receipt"] = agent.receipt(q, 0, "no-charge")
            st["log"].append(("till", st["receipt"]))
            return _render(request, "receipt.html", sid, quote=q, paid=0, ref="no-charge")
        inv = pp.create_invoice(recipient_email=st.get("email") or "client@example.test", amount=q.price,
                                currency=CURRENCY, memo=f"{ORG}: {q.device_label} (sliding scale, {q.band_label})")
        pp.send_invoice(inv.id)
        st["invoice_id"] = inv.id
        st["log"].append(("till", f"Invoice {inv.id} sent for ${inv.amount}. Pay it at the link; I'll write your pickup note when it clears."))
        return _render(request, "invoice.html", sid, invoice=inv, quote=q)
    if what == "donation":
        amt = st.get("donation")
        if not amt:
            raise HTTPException(400, "nothing to confirm")
        o = pp.create_order(amount=amt, currency=CURRENCY, note=f"{ORG} device fund: cover a neighbor's sliding-scale gap")
        st["order_id"] = o.id
        st["log"].append(("till", f"Order {o.id} created for ${o.amount}. Approve it on PayPal and I'll capture it."))
        return _render(request, "order.html", sid, order=o)
    raise HTTPException(400, "unknown confirmation")


@app.post("/webhook/paypal")
def webhook(request: Request, event_type: str = Form(...), resource_id: str = Form(...)):
    """PayPal webhook (sandbox) or the mock buttons. INVOICING.INVOICE.PAID marks the invoice paid;
    CHECKOUT.ORDER.APPROVED lets us capture. Signature verification is a sandbox-mode TODO (see README)."""
    if event_type == "INVOICING.INVOICE.PAID":
        if paypal.is_mock():
            pp.settle_invoice(resource_id)
        inv = pp.get_invoice(resource_id)
        for st in SESSIONS.values():
            if st.get("invoice_id") == inv.id and inv.status == "PAID":
                q = st["quote"]
                st["receipt"] = agent.receipt(q, inv.amount, inv.id)
                st["log"].append(("till", st["receipt"]))
        return {"ok": True, "status": inv.status}
    if event_type == "CHECKOUT.ORDER.APPROVED":
        if paypal.is_mock():
            pp.approve_order(resource_id)
        o = pp.capture_order(resource_id)
        for st in SESSIONS.values():
            if st.get("order_id") == o.id:
                st["thanks"] = f"Captured ${o.amount} (PayPal {o.id}). That covers {o.amount // 50} sliding-scale gaps of $50, or most of one laptop."
                st["log"].append(("till", st["thanks"]))
        return {"ok": True, "status": o.status}
    raise HTTPException(400, f"unhandled event {event_type}")


@app.get("/receipt", response_class=HTMLResponse)
def receipt(request: Request):
    sid = _sid(request); st = _state(sid)
    if st.get("receipt"):
        inv = pp.get_invoice(st["invoice_id"]) if st.get("invoice_id") else None
        return _render(request, "receipt.html", sid, quote=st["quote"], paid=inv.amount if inv else 0, ref=inv.id if inv else "no-charge")
    if st.get("thanks"):
        return _render(request, "thanks.html", sid)
    return RedirectResponse("/", status_code=303)


@app.post("/reset")
def reset(request: Request):
    SESSIONS.pop(request.cookies.get("nt_sid", ""), None)
    return RedirectResponse("/", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "mock": paypal.is_mock(), "version": __import__("navigator_till").__version__}
