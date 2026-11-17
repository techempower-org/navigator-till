"""/api/version: the realm-sigil contract (status.realm.watch CHECK sigil-coverage, 2026-11-17)."""
import re

import pytest
from fastapi.testclient import TestClient

from navigator_till.app import app


def test_a_stamped_image_serves_name_and_hash(monkeypatch):
    monkeypatch.setenv("SIGIL_HASH", "a0c13ed")
    r = TestClient(app).get("/api/version")
    v = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert re.fullmatch(r".+ · a0c13ed", v["version"]) and v["hash"] == "a0c13ed" and v["dirty"] is False
    assert v["repo"] == "https://github.com/techempower-org/navigator-till"


@pytest.mark.parametrize("stamp", [None, "", "dev", "a0c13e", "a0c13ed; rm -rf /", "g0c13ed"])
def test_no_or_junk_stamp_says_dev(monkeypatch, stamp):
    if stamp is None:
        monkeypatch.delenv("SIGIL_HASH", raising=False)
    else:
        monkeypatch.setenv("SIGIL_HASH", stamp)
    v = TestClient(app).get("/api/version").json()
    assert v["hash"] == "dev" and v["dirty"] is True
