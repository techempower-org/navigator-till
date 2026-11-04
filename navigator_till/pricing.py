"""Sliding-scale pricing. Rules only: this module never calls a model.

The quote carries every number it used so the explanation layer (agent.py) and the
receipt can show the arithmetic, the way a navigator would on paper.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RULES_PATH = Path(os.environ.get("NT_PRICING", Path(__file__).with_name("pricing.yaml")))


@dataclass(frozen=True)
class Quote:
    device: str
    device_label: str
    list_price: int
    household: int
    annual_income: int | None
    fpl: int
    pct_of_fpl: int | None
    band_label: str
    pay_share: float
    price: int
    categorical: str | None = None
    steps: list[str] = field(default_factory=list)

    @property
    def gap(self) -> int:
        """What a donor would cover to make this device free: list minus what the client pays."""
        return self.list_price - self.price


def load_rules(path: Path | None = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)
    for key in ("devices", "fpl", "bands"):
        if key not in rules:
            raise ValueError(f"pricing rules missing '{key}'")
    return rules


def poverty_line(rules: dict, household: int) -> int:
    if household < 1:
        raise ValueError("household must be at least 1")
    f = rules["fpl"]
    return int(f["first"] + f["each_additional"] * (household - 1))


def quote(device: str, household: int, annual_income: int | None, *, program: str | None = None,
          rules: dict | None = None) -> Quote:
    """Price one device for one household. `program` is a categorical-eligibility program the
    client is enrolled in (e.g. "calfresh"); it places them in the first band without an income."""
    rules = rules or load_rules()
    if device not in rules["devices"]:
        raise KeyError(f"unknown device '{device}'; known: {', '.join(rules['devices'])}")
    d = rules["devices"][device]
    list_price = int(d["list"])
    fpl = poverty_line(rules, household)
    steps: list[str] = [f"{d['label']}: list price ${list_price}."]
    cat = (program or "").strip().lower() or None
    if cat and cat in [c.lower() for c in rules.get("categorical", [])]:
        band = rules["bands"][0]
        pct = None
        steps.append(f"Enrolled in {cat.title()}: that places the household in the first band ({band['label']}).")
    else:
        cat = None
        if annual_income is None:
            raise ValueError("annual_income is required unless a categorical program applies")
        if annual_income < 0:
            raise ValueError("annual_income cannot be negative")
        pct = int(round(100 * annual_income / fpl))
        steps.append(f"Household of {household}: the 2026 poverty line is ${fpl:,} a year.")
        steps.append(f"Income ${annual_income:,} is {pct}% of that line.")
        band = next(b for b in rules["bands"] if b["up_to_pct"] is None or pct <= b["up_to_pct"])
    share = float(band["pay"])
    price = int(round(list_price * share))
    steps.append(f"Band '{band['label']}': the client pays {int(share * 100)}% of list = ${price}.")
    return Quote(device=device, device_label=d["label"], list_price=list_price, household=household,
                 annual_income=annual_income, fpl=fpl, pct_of_fpl=pct, band_label=band["label"],
                 pay_share=share, price=price, categorical=cat, steps=steps)
