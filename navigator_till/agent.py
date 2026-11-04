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

from .pricing import Quote

MODEL = os.environ.get("NT_MODEL", "claude-sonnet-5-5")

DEVICE_WORDS = {
    "laptop-plus": ("better laptop", "newer laptop", "laptop plus", "more memory"),
    "laptop": ("laptop", "notebook", "chromebook"),
    "desktop": ("desktop", "tower", "pc with a monitor"),
    "ups": ("battery backup", "ups", "surge"),
}
PROGRAM_WORDS = ("calfresh", "medi-cal", "medical", "medi cal", "ssi", "lifeline", "wic", "section 8", "free lunch")


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
    if any(w in t for w in ("donate", "donation", "cover a", "pay for someone", "sponsor", "gift")):
        amt = _money(t)
        return Request(kind="donation", donation_amount=amt, missing=[] if amt else ["amount"])
    device = next((d for d, words in DEVICE_WORDS.items() if any(w in t for w in words)), None)
    program = next((p for p in PROGRAM_WORDS if p in t), None)
    if program in ("medical", "medi cal"):
        program = "medi-cal"
    hh = re.search(r"(?:household|family|people|of)\s*(?:of\s*)?(\d{1,2})\b|(\d{1,2})\s*(?:people|of us|in (?:my|the) (?:house|family))", t)
    household = int(next(g for g in hh.groups() if g)) if hh else None
    inc = None
    m = re.search(r"(?:make|earn|income|bring in|get)\D{0,20}\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\s*(k|thousand))?\s*(a|per|/)?\s*(year|yr|month|mo)?", t)
    if m:
        inc = int(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        if m.group(4) in ("month", "mo"):
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


def explain_offline(q: Quote) -> str:
    lines = [f"Here is how the price works for the {q.device_label.lower()}."]
    lines += [f"- {s}" for s in q.steps]
    if q.price == 0:
        lines.append("So this one is free for you. We only ask that you pick it up and let us show you how it works.")
    else:
        lines.append(f"So you would pay ${q.price}. We send a PayPal invoice; you can pay by card, bank, or PayPal, and there is no fee to you.")
    lines.append("If the income or household number is off, tell me and I will redo it.")
    return "\n".join(lines)


def receipt_offline(q: Quote, paid: int, ref: str) -> str:
    return (f"Paid: ${paid} for one {q.device_label.lower()} (PayPal reference {ref}). "
            f"Pick-up: TechEMPOWER, 136 Idaho Maryland Rd, Grass Valley, weekdays 10-4; bring this note. "
            f"Your device comes with a 90-day warranty and free help getting set up.")


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


def explain(q: Quote) -> str:
    facts = "\n".join(q.steps) + f"\nFinal price to the client: ${q.price}."
    return _claude(EXPLAIN_SYSTEM, facts) or explain_offline(q)


def receipt(q: Quote, paid: int, ref: str) -> str:
    return receipt_offline(q, paid, ref)
