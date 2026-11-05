import datetime as dt
import json
import warnings

import pytest

from jobradar import fx

NOW = dt.datetime(2026, 11, 5, 12, 0)
NBP = {
    "usd": {"table": "A", "code": "USD", "rates": [{"no": "214/A/NBP/2026", "effectiveDate": "2026-11-04", "mid": 3.6512}]},
    "eur": {"table": "A", "code": "EUR", "rates": [{"no": "214/A/NBP/2026", "effectiveDate": "2026-11-04", "mid": 4.2731}]},
}
FRANK = {
    "USD": {"amount": 1.0, "base": "USD", "date": "2026-11-04", "rates": {"PLN": 3.66}},
    "EUR": {"amount": 1.0, "base": "EUR", "date": "2026-11-04", "rates": {"PLN": 4.27}},
}


def fake(nbp_ok=True, frank_ok=True):
    calls = []
    def fetch(url):
        calls.append(url)
        if "nbp.pl" in url:
            if not nbp_ok:
                raise OSError("NBP down")
            return NBP[url.split("/rates/a/")[1].split("/")[0]]
        if not frank_ok:
            raise OSError("Frankfurter down")
        return FRANK[url.split("from=")[1].split("&")[0]]
    fetch.calls = calls
    return fetch


@pytest.fixture
def paths(tmp_path):
    fb = tmp_path / "fx.yaml"
    fb.write_text("as_of: 2026-11-05\nto_pln: {PLN: 1.0, USD: 3.65}\n", encoding="utf-8")
    return {"cache": tmp_path / "fx.cache.json", "fallback": fb}


def test_nbp_ok_writes_cache(paths):
    r = fx.get_rates(fake(), NOW, **paths)
    assert r["fx_source"] == "nbp" and r["fx_date"] == "2026-11-04"
    assert r["to_pln"] == {"PLN": 1.0, "USD": 3.6512, "EUR": 4.2731}
    assert json.loads(paths["cache"].read_text())["origin"] == "nbp"


def test_fresh_cache_skips_network(paths):
    fx.get_rates(fake(), NOW, **paths)
    f = fake()
    r = fx.get_rates(f, NOW + dt.timedelta(hours=23), **paths)
    assert r["fx_source"] == "cache" and r["fx_origin"] == "nbp" and f.calls == []


def test_expired_cache_refetches(paths):
    fx.get_rates(fake(), NOW, **paths)
    f = fake()
    assert fx.get_rates(f, NOW + dt.timedelta(hours=25), **paths)["fx_source"] == "nbp"
    assert f.calls


def test_nbp_down_uses_frankfurter(paths):
    r = fx.get_rates(fake(nbp_ok=False), NOW, **paths)
    assert r["fx_source"] == "frankfurter" and r["to_pln"]["USD"] == 3.66


def test_all_down_uses_stale_cache(paths):
    fx.get_rates(fake(), NOW, **paths)
    r = fx.get_rates(fake(False, False), NOW + dt.timedelta(days=2), **paths)
    assert r["fx_source"] == "cache"


def test_all_down_no_cache_uses_fallback(paths):
    r = fx.get_rates(fake(False, False), NOW, **paths)
    assert r["fx_source"] == "fallback" and r["to_pln"] == {"PLN": 1.0, "USD": 3.65}


def test_malformed_nbp_is_failure(paths):
    def fetch(url):
        if "nbp.pl" in url:
            return {"rates": [{"mid": "x"}]}
        return fake()(url)
    assert fx.get_rates(fetch, NOW, **paths)["fx_source"] == "frankfurter"


def test_old_rate_warns(paths):
    with pytest.warns(fx.StaleFxWarning):
        fx.get_rates(fake(), dt.datetime(2026, 11, 13), **paths)


def test_recent_rate_no_warning(paths):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fx.get_rates(fake(), dt.datetime(2026, 11, 11), **paths)


def test_real_http_blocked_in_tests():
    with pytest.raises(RuntimeError, match="запрещена"):
        fx.http_json(fx.NBP_URL.format(code="usd"))
