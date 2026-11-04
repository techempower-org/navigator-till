import pytest

from navigator_till import pricing


def test_poverty_line_scales_by_household():
    r = pricing.load_rules()
    assert pricing.poverty_line(r, 1) == r["fpl"]["first"]
    assert pricing.poverty_line(r, 3) == r["fpl"]["first"] + 2 * r["fpl"]["each_additional"]
    with pytest.raises(ValueError):
        pricing.poverty_line(r, 0)


def test_bands_edges_are_inclusive():
    r = pricing.load_rules()
    fpl1 = pricing.poverty_line(r, 1)
    assert pricing.quote("laptop", 1, fpl1).price == 0                      # exactly 100%: free
    assert pricing.quote("laptop", 1, int(fpl1 * 1.01)).price == 50         # 101%: 25% of $200
    assert pricing.quote("laptop", 1, int(fpl1 * 1.5)).price == 50          # exactly 150%
    assert pricing.quote("laptop", 1, int(fpl1 * 2.0)).price == 100         # exactly 200%
    assert pricing.quote("laptop", 1, int(fpl1 * 3.0)).price == 150         # exactly 300%
    assert pricing.quote("laptop", 1, int(fpl1 * 3.01)).price == 200        # 301%: full list


def test_categorical_program_skips_income():
    q = pricing.quote("desktop", 4, None, program="CalFresh")
    assert q.price == 0 and q.categorical == "calfresh" and q.pct_of_fpl is None
    assert any("CalFresh" in s or "Calfresh" in s for s in q.steps)


def test_unknown_program_falls_back_to_income():
    q = pricing.quote("desktop", 2, 70_000, program="gym membership")   # 2 people: FPL 21,640; 70,000 = 323%
    assert q.categorical is None and q.price == 180


def test_errors():
    with pytest.raises(KeyError):
        pricing.quote("phone", 1, 1000)
    with pytest.raises(ValueError):
        pricing.quote("laptop", 1, None)
    with pytest.raises(ValueError):
        pricing.quote("laptop", 1, -5)


def test_quote_shows_its_work_and_gap():
    q = pricing.quote("laptop-plus", 2, 30_000)
    assert q.list_price == 280 and q.price + q.gap == 280
    assert len(q.steps) == 4 and "Band" in q.steps[-1]
