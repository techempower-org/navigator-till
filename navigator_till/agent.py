"""The conversation layer. Two jobs, and only these two: (1) turn what a person typed into a
structured request, (2) explain a quote or a receipt in plain language. It never computes a price
and never touches PayPal. With ANTHROPIC_API_KEY set it uses Claude; without it, a deterministic
parser and templates, so tests and the mock demo run offline and judges can run it without a key.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from . import i18n
from .pricing import Quote

MODEL = os.environ.get("NT_MODEL", "claude-sonnet-5-5")

DEVICE_WORDS = {                # English first, then the Spanish words the desk hears
    "laptop-plus": ("better laptop", "newer laptop", "laptop plus", "more memory", "laptop mejor", "más memoria"),
    "laptop": ("laptop", "notebook", "chromebook", "portátil", "portatil"),
    "desktop": ("desktop", "tower", "pc with a monitor", "escritorio", "torre"),
    "ups": ("battery backup", "ups", "surge", "batería de respaldo", "bateria de respaldo"),
}
PROGRAM_WORDS = ("calfresh", "medi-cal", "medical", "medi cal", "ssi", "lifeline", "wic", "section 8", "sección 8", "seccion 8",
                 "free lunch", "almuerzo gratis")
DONATION_WORDS = ("donate", "donation", "cover a", "pay for someone", "sponsor", "gift", "donar", "donación", "donacion", "cubrir una", "cubrir la")


@dataclass
class Request:
    kind: str                       # "device" | "donation" | "unknown"
    device: str | None = None
    household: int | None = None
    annual_income: int | None = None
    program: str | None = None
    donation_amount: int | None = None
    missing: list[str] | None = None


def _money(text: str) -> int | None:
    m = re.search(r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\s*(k|thousand))?\b", text)
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    if m.group(2):
        n *= 1000
    return n


def parse_offline(text: str) -> Request:
    t = text.lower()
    if any(w in t for w in DONATION_WORDS):
        amt = _money(t)
        return Request(kind="donation", donation_amount=amt, missing=[] if amt else ["amount"])
    device = next((d for d, words in DEVICE_WORDS.items() if any(w in t for w in words)), None)
    program = next((p for p in PROGRAM_WORDS if p in t), None)
    if program in ("medical", "medi cal"):
        program = "medi-cal"
    program = {"sección 8": "section 8", "seccion 8": "section 8", "almuerzo gratis": "free lunch"}.get(program, program)
    hh = re.search(r"(?:household|family|people|of|somos|hogar de|familia de)\s*(?:of\s*)?(\d{1,2})\b|(\d{1,2})\s*(?:people|of us|personas|in (?:my|the) (?:house|family))", t)
    household = int(next(g for g in hh.groups() if g)) if hh else None
    inc = None
    m = re.search(r"(?:make|earn|income|bring in|get|gan\w{0,5}|ingresos?)\D{0,20}\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\s*(k|thousand|mil))?\s*(a|per|/|al|por)?\s*(year|yr|month|mo|año|ano|mes)?", t)
    if m:
        inc = int(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        if m.group(4) in ("month", "mo", "mes"):
            inc *= 12
    missing = []
    if not device:
        missing.append("device")
    if not household:
        missing.append("household")
    if inc is None and not program:
        missing.append("income")
    return Request(kind="device" if device or household or inc or program else "unknown", device=device,
                   household=household, annual_income=inc, program=program, missing=missing)


def explain_offline(q: Quote, lang: str = "en") -> str:
    T = i18n.tr(lang)
    lines = [T("explain_intro", device=i18n.label(lang, q.device_label).lower())]
    lines += [f"- {s}" for s in i18n.steps(q, lang)]
    lines.append(T("explain_free") if q.price == 0 else T("explain_pay", price=q.price))
    lines.append(T("explain_fix"))
    return "\n".join(lines)


def receipt_offline(q: Quote, paid: int, ref: str, lang: str = "en") -> str:
    return i18n.t(i18n.pick(lang), "receipt_text", paid=paid, device=i18n.label(lang, q.device_label).lower(), ref=ref)


def _claude(system: str, user: str) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic  # optional dependency
    except ImportError:
        return None
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(model=MODEL, max_tokens=600, system=system,
                                 messages=[{"role": "user", "content": user}])
    return "".join(getattr(b, "text", "") for b in msg.content).strip() or None


PARSE_SYSTEM = (
    "You turn one message from a client of a small digital-equity nonprofit into JSON with keys "
    "kind ('device'|'donation'|'unknown'), device ('laptop'|'laptop-plus'|'desktop'|'ups'|null), household (int|null), "
    "annual_income (int dollars per year|null), program (one of calfresh, medi-cal, ssi, lifeline, wic, 'section 8', 'free lunch', or null), "
    "donation_amount (int|null). Reply with JSON only. Never guess a number that was not said."
)
EXPLAIN_SYSTEM = (
    "You explain a price to a client of a small nonprofit at a 6th-grade reading level, warmly and briefly, "
    "using ONLY the numbers given. Never change a number. End by inviting a correction if a number is wrong."
)


def parse(text: str) -> Request:
    out = _claude(PARSE_SYSTEM, text)
    if out:
        try:
            j = json.loads(out[out.find("{"): out.rfind("}") + 1])
            r = Request(kind=j.get("kind") or "unknown", device=j.get("device"), household=j.get("household"),
                        annual_income=j.get("annual_income"), program=j.get("program"), donation_amount=j.get("donation_amount"))
            r.missing = [k for k, v in (("device", r.device), ("household", r.household)) if r.kind == "device" and not v]
            if r.kind == "device" and r.annual_income is None and not r.program:
                r.missing.append("income")
            if r.kind == "donation" and not r.donation_amount:
                r.missing = ["amount"]
            return r
        except (ValueError, AttributeError):
            pass
    return parse_offline(text)


def explain(q: Quote, lang: str = "en") -> str:
    facts = "\n".join(q.steps) + f"\nFinal price to the client: ${q.price}."
    system = EXPLAIN_SYSTEM + (" Write in Spanish." if i18n.pick(lang) == "es" else "")
    return _claude(system, facts) or explain_offline(q, lang)


def receipt(q: Quote, paid: int, ref: str, lang: str = "en") -> str:
    return receipt_offline(q, paid, ref, lang)
