"""Пересчёт ставки в PLN/ч, PLN/день, PLN/мес, PLN/мес средн., $/ч."""
from __future__ import annotations

from .config import ConfigError

HOURS_PER_DAY = 8
HOURS_PER_MONTH = 168
PAID_SHARE = 0.9  # B2B: ~20 неоплачиваемых дней в год
UNIT_HOURS = {"hour": 1, "day": HOURS_PER_DAY, "month": HOURS_PER_MONTH}


def normalize_rate(lo: float, hi: float | None, currency: str, unit: str, fx: dict) -> dict:
    to_pln = fx["to_pln"]
    if currency not in to_pln:
        raise ConfigError(f"Нет курса {currency} в fx.yaml")
    if unit not in UNIT_HOURS:
        raise ConfigError(f"Неизвестная единица ставки: {unit}")
    hi = lo if hi is None else hi

    def per_hour(x: float) -> float:
        return x * to_pln[currency] / UNIT_HOURS[unit]

    h = [per_hour(lo), per_hour(hi)]
    # Месячная ставка уже фиксирована: неоплачиваемые дни её не уменьшают.
    paid = 1.0 if unit == "month" else PAID_SHARE

    def pair(k: float) -> list[float]:
        return [round(x * k, 2) for x in h]

    return {
        "pln_h": pair(1),
        "pln_day": pair(HOURS_PER_DAY),
        "pln_month": pair(HOURS_PER_MONTH),
        "pln_month_avg": pair(HOURS_PER_MONTH * paid),
        "usd_h": pair(1 / to_pln["USD"]),
    }
