import pytest

from jobradar.config import ConfigError
from jobradar.rates import normalize_rate

FX = {"to_pln": {"PLN": 1.0, "USD": 3.65}}


def test_avance_day_rate():
    r = normalize_rate(1000, 1100, "PLN", "day", FX)
    assert r["pln_h"] == [125.0, 137.5]
    assert r["pln_month"] == [21000.0, 23100.0]
    assert r["pln_month_avg"] == [18900.0, 20790.0]


def test_usd_hour_matches_best_offer():
    r = normalize_rate(40, None, "USD", "hour", FX)
    assert r["pln_h"] == [146.0, 146.0]
    assert r["usd_h"] == [40.0, 40.0]


def test_monthly_rate_has_no_unpaid_discount():
    r = normalize_rate(25200, None, "PLN", "month", FX)
    assert r["pln_month_avg"] == r["pln_month"]


def test_unknown_currency():
    with pytest.raises(ConfigError):
        normalize_rate(1, 2, "GBP", "hour", FX)
