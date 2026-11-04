"""The desk. One session per browser tab (a signed cookie would come later); state in SQLite (store.py).

Flow A (client): message -> parse -> quote (rules) -> explanation (agent) -> human YES ->
PayPal invoice created + sent -> paid (webhook, or the mock "I paid" button) -> receipt + pickup note.
Flow B (donor): message -> amount -> human YES -> PayPal order -> approved -> captured -> thank-you.
No money step happens without the YES button; the agent only ever proposes.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from . import agent, i18n, paypal, pricing
from .store import Store

app = FastAPI(title="Navigator Till")
templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
ORG = os.environ.get("NT_ORG", "TechEMPOWER")
ORG_EMAIL = os.environ.get("NT_ORG_EMAIL", "hi@techempower.org")
CURRENCY = "USD"

pp = paypal.client()
store = Store()                       # sid -> {"request", "quote", "invoice_id", "order_id", "log": [...]}


def _sid(request: Request) -> str:
    return request.cookies.get("nt_sid") or secrets.token_urlsafe(12)


def _state(sid: str) -> dict:
    return store.get(sid) or {"log": []}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="minutes")


def _lang(request: Request) -> str:
    """?lang=es wins, then the nt_lang cookie, then English."""
    return i18n.pick(request.query_params.get("lang") or request.cookies.get("nt_lang"))


def _render(request: Request, name: str, sid: str, st: dict, **ctx):
    lang = _lang(request)
    store.put(sid, st)                                          # every handler mutates st, then renders
    resp = templates.TemplateResponse(request, name, {"org": ORG, "mock": paypal.is_mock(), "state": st, "lang": lang,
                                                      "t": i18n.tr(lang), "label": lambda x: i18n.label(lang, x),
                                                      "steps": lambda q: i18n.steps(q, lang), **ctx})
    resp.set_cookie("nt_sid", sid, httponly=True, samesite="lax")
    resp.set_cookie("nt_lang", lang, samesite="lax", max_age=60 * 60 * 24 * 365)
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    sid = _sid(request)
    return _render(request, "index.html", sid, _state(sid))


@app.post("/chat", response_class=HTMLResponse)
def chat(request: Request, message: str = Form(...), email: str = Form("")):
    sid = _sid(request); st = _state(sid); lang = st["lang"] = _lang(request); T = i18n.tr(lang)
    message = message.strip()[:2000]                            # a chat line, not a document
    st["log"].append(("you", message))
    req = agent.parse(message)
    st["request"] = req
    if email:
        st["email"] = email.strip()
    if req.kind == "donation":
        if req.missing:
            st["log"].append(("till", T("ask_amount")))
            return _render(request, "index.html", sid, st)
        st["donation"] = req.donation_amount
        st["log"].append(("till", T("donation_ready", amount=req.donation_amount)))
        return _render(request, "index.html", sid, st, confirm="donation")
    if req.kind == "unknown" or req.missing:
        need = [T("need_" + m) for m in (req.missing or ["device", "household", "income"])]
        st["log"].append(("till", T("can_price", needs="; ".join(need))))
        return _render(request, "index.html", sid, st)
    try:
        q = pricing.quote(req.device, req.household, req.annual_income, program=req.program)
    except (ValueError, KeyError) as e:
        st["log"].append(("till", T("cannot_price", error=e)))
        return _render(request, "index.html", sid, st)
    if st.get("invoice_id") and not st.get("receipt"):
        st["log"].append(("till", T("invoice_open", id=st["invoice_id"], amount=st["invoice_amount"])))
        return _render(request, "index.html", sid, st)
    st["quote"] = q; st["quoted_at"] = _now()
    st["log"].append(("till", agent.explain(q, lang)))
    st["log"].append(("till", T("free_yes") if q.price == 0 else T("invoice_yes", price=q.price)))
    return _render(request, "index.html", sid, st, confirm="device")


@app.post("/confirm", response_class=HTMLResponse)
def confirm(request: Request, what: str = Form(...)):
    sid = _sid(request); st = _state(sid); lang = st["lang"] = _lang(request); T = i18n.tr(lang)
    if what == "device":
        q: pricing.Quote | None = st.get("quote")
        if not q:
            raise HTTPException(400, "nothing to confirm")
        if q.price == 0:
            st["receipt"] = agent.receipt(q, 0, "no-charge", lang); st["paid"] = 0; st["paid_at"] = _now()
            st["log"].append(("till", st["receipt"]))
            return _render(request, "receipt.html", sid, st, quote=q, paid=0, ref="no-charge")
        inv = pp.create_invoice(recipient_email=st.get("email") or "client@example.test", amount=q.price,
                                currency=CURRENCY, memo=f"{ORG}: {q.device_label} (sliding scale, {q.band_label})")
        pp.send_invoice(inv.id)
        st["invoice_id"] = inv.id; st["invoice_amount"] = inv.amount; st["invoiced_at"] = _now()
        st["invoiced_quote"] = q                                  # frozen copy: later chat lines cannot change what was billed
        st["log"].append(("till", T("invoice_sent_msg", id=inv.id, amount=inv.amount)))
        return _render(request, "invoice.html", sid, st, invoice=inv, quote=q)
    if what == "donation":
        amt = st.get("donation")
        if not amt:
            raise HTTPException(400, "nothing to confirm")
        o = pp.create_order(amount=amt, currency=CURRENCY, note=f"{ORG} device fund: cover a neighbor's sliding-scale gap")
        st["order_id"] = o.id
        st["log"].append(("till", T("order_created_msg", id=o.id, amount=o.amount)))
        return _render(request, "order.html", sid, st, order=o)
    raise HTTPException(400, "unknown confirmation")


@app.post("/webhook/paypal")
async def webhook(request: Request):
    """PayPal webhook (sandbox) or the mock buttons. Two shapes: PayPal's JSON event (event_type +
    resource) or the mock form (event_type + resource_id). In sandbox mode every delivery must pass
    PayPal's verify-webhook-signature for PAYPAL_WEBHOOK_ID, else 403; the mock form path is never
    accepted there. The event body is never trusted on its own even when verified: for an invoice we
    re-read its status from PayPal before writing a receipt; for an order the capture call is the
    proof (PayPal refuses to capture an order nobody approved). In mock mode the caller may only
    settle the invoice/order of its own session (cookie), so one tab cannot mark another's paid."""
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.body()
        try:
            event = json.loads(body)
        except ValueError:
            raise HTTPException(400, "invalid JSON event")
        res = event.get("resource") or {}
        event_type, resource_id, is_form = event.get("event_type", ""), (res.get("invoice") or {}).get("id") or res.get("id") or "", False
    else:
        form = await request.form()
        body, event_type, resource_id, is_form = b"", str(form.get("event_type", "")), str(form.get("resource_id", "")), True
    if not event_type or not resource_id:
        raise HTTPException(400, "event_type and a resource id are required")
    return await run_in_threadpool(_settle, request, event_type, resource_id, body, is_form)


def _settle(request: Request, event_type: str, resource_id: str, body: bytes, is_form: bool):
    if not paypal.is_mock():
        webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID", "")
        if is_form or not webhook_id or not paypal.verify_webhook(request.headers, body, webhook_id, client=pp):
            raise HTTPException(403, "webhook signature not verified")
    sid = _sid(request); mine = _state(sid)
    if event_type == "INVOICING.INVOICE.PAID":
        if paypal.is_mock():
            if mine.get("invoice_id") != resource_id:
                raise HTTPException(403, "mock payer may only settle this session's invoice")
            pp.settle_invoice(resource_id)
        inv = pp.get_invoice(resource_id)                 # sandbox: status comes from PayPal, not the caller
        if inv.status != "PAID":
            return {"ok": False, "status": inv.status}
        for sid2, st in store.find("invoice_id", inv.id):
            if not st.get("receipt"):
                if st.get("invoice_amount") not in (None, inv.amount):   # the invoice is the contract, not the chat
                    return {"ok": False, "status": "AMOUNT_MISMATCH", "invoice": inv.id}
                st["receipt"] = agent.receipt(st.get("invoiced_quote") or st["quote"], inv.amount, inv.id, st.get("lang", "en"))
                st["paid"] = inv.amount; st["paid_at"] = _now()
                st["log"].append(("till", st["receipt"]))
                store.put(sid2, st)
        return {"ok": True, "status": inv.status}
    if event_type == "CHECKOUT.ORDER.APPROVED":
        if paypal.is_mock():
            if mine.get("order_id") != resource_id:
                raise HTTPException(403, "mock donor may only approve this session's order")
            pp.approve_order(resource_id)
        try:
            o = pp.capture_order(resource_id)              # PayPal refuses unless the payer approved
        except (ValueError, httpx.HTTPStatusError) as e:
            raise HTTPException(409, f"order not capturable: {e}") from e
        if o.status != "COMPLETED":                        # an approved-but-not-captured order is not a donation
            return {"ok": False, "status": o.status}
        for sid2, st in store.find("order_id", o.id):
            if not st.get("thanks"):
                st["thanks"] = i18n.t(st.get("lang", "en"), "captured_msg", amount=o.amount, id=o.id, gaps=o.amount // 50)
                st["donated_at"] = _now()
                st["log"].append(("till", st["thanks"]))
                store.put(sid2, st)
        return {"ok": True, "status": o.status}
    raise HTTPException(400, f"unhandled event {event_type}")


@app.get("/receipt", response_class=HTMLResponse)
def receipt(request: Request):
    sid = _sid(request); st = _state(sid)
    if st.get("receipt"):                                      # written only after PayPal confirmed; no re-read needed
        return _render(request, "receipt.html", sid, st, quote=st["quote"], paid=st.get("paid", 0), ref=st.get("invoice_id") or "no-charge")
    if st.get("thanks"):
        return _render(request, "thanks.html", sid, st)
    return RedirectResponse("/", status_code=303)


def _desk_cookie(token: str) -> str:
    return hmac.new(token.encode(), b"navigator-till desk", "sha256").hexdigest()


@app.get("/desk", response_class=HTMLResponse)
def desk(request: Request):
    """The navigator's view: quotes today, unpaid invoices, paid pickups, donations captured.
    It shows emails and incomes, so: open without a token only in the mock demo; in sandbox mode
    NT_DESK_TOKEN is required (403 when unset). Visit /desk?token=... once: the token is swapped for
    a cookie holding its HMAC and the browser is redirected so the secret leaves the URL."""
    token = os.environ.get("NT_DESK_TOKEN", "")
    if not token and not paypal.is_mock():
        raise HTTPException(403, "set NT_DESK_TOKEN to open the desk in sandbox mode")
    if token:
        given = request.query_params.get("token")
        if given is not None:
            if not secrets.compare_digest(given, token):
                raise HTTPException(403, "desk token required")
            resp = RedirectResponse("/desk", status_code=303)
            resp.set_cookie("nt_desk", _desk_cookie(token), httponly=True, samesite="lax", secure=not paypal.is_mock(), max_age=12 * 3600)
            return resp
        if not secrets.compare_digest(request.cookies.get("nt_desk", ""), _desk_cookie(token)):
            raise HTTPException(403, "desk token required")
    rows = [st for _, st in store.items()]
    today = date.today().isoformat()
    ctx = {"today": today,
           "quotes": [st for st in rows if st.get("quote") and str(st.get("quoted_at", "")).startswith(today)],
           "unpaid": [st for st in rows if st.get("invoice_id") and not st.get("receipt")],
           "pickups": [st for st in rows if st.get("receipt")],
           "donations": [st for st in rows if st.get("thanks")]}
    sid = _sid(request)
    resp = _render(request, "desk.html", sid, _state(sid), **ctx)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/reset")
def reset(request: Request):
    store.delete(request.cookies.get("nt_sid", ""))
    return RedirectResponse("/", status_code=303)


@app.get("/healthz")
def healthz():
    return {"ok": True, "mock": paypal.is_mock(), "version": __import__("navigator_till").__version__}
