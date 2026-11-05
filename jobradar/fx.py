"""Курсы к PLN: NBP -> Frankfurter (ЕЦБ) -> кэш -> config/fx.yaml.

Результат: {"to_pln": {...}, "fx_source": nbp|frankfurter|cache|fallback,
            "fx_date": "YYYY-MM-DD", "fx_origin": источник данных в кэше}.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request
import warnings
from pathlib import Path
from typing import Callable

from .config import CONFIG, ConfigError, load_yaml

CURRENCIES = ("USD", "EUR")
CACHE = CONFIG / "fx.cache.json"
FALLBACK = CONFIG / "fx.yaml"
CACHE_TTL = dt.timedelta(hours=24)
MAX_AGE_DAYS = 7
TIMEOUT_S = 5

NBP_URL = "https://api.nbp.pl/api/exchangerates/rates/a/{code}/last/1/?format=json"
FRANKFURTER_URL = "https://api.frankfurter.app/latest?from={code}&to=PLN"

Fetch = Callable[[str], dict]


class StaleFxWarning(UserWarning):
    pass


def http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "job-radar/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


def _positive(x) -> float:
    x = float(x)
    if x <= 0:
        raise ValueError("курс <= 0")
    return x


def from_nbp(fetch: Fetch) -> tuple[dict, str]:
    rates, dates = {}, []
    for code in CURRENCIES:
        r = fetch(NBP_URL.format(code=code.lower()))["rates"][0]
        rates[code] = _positive(r["mid"])
        dates.append(dt.date.fromisoformat(r["effectiveDate"]))
    return rates, min(dates).isoformat()


def from_frankfurter(fetch: Fetch) -> tuple[dict, str]:
    rates, dates = {}, []
    for code in CURRENCIES:
        r = fetch(FRANKFURTER_URL.format(code=code))
        rates[code] = _positive(r["rates"]["PLN"])
        dates.append(dt.date.fromisoformat(r["date"]))
    return rates, min(dates).isoformat()


def _read_cache(path: Path) -> dict | None:
    try:
        c = json.loads(path.read_text(encoding="utf-8"))
        c["fetched_at"] = dt.datetime.fromisoformat(c["fetched_at"])
        return c
    except (OSError, ValueError, KeyError):
        return None


def _result(rates: dict, source: str, date: str, origin: str | None = None) -> dict:
    return {"to_pln": {"PLN": 1.0, **rates}, "fx_source": source,
            "fx_date": date, "fx_origin": origin or source}


def get_rates(fetch: Fetch = http_json, now: dt.datetime | None = None,
              cache: Path = CACHE, fallback: Path = FALLBACK) -> dict:
    now = now or dt.datetime.now()
    cached = _read_cache(cache)

    if cached and now - cached["fetched_at"] < CACHE_TTL:
        res = _result(cached["rates"], "cache", cached["fx_date"], cached["origin"])
    else:
        res = None
        for name, source in (("nbp", from_nbp), ("frankfurter", from_frankfurter)):
            try:
                rates, date = source(fetch)
            except Exception:  # сеть, HTTP, формат: пробуем следующий источник
                continue
            cache.write_text(json.dumps({"rates": rates, "fx_date": date, "origin": name,
                                         "fetched_at": now.isoformat()}), encoding="utf-8")
            res = _result(rates, name, date)
            break
        if res is None and cached:
            res = _result(cached["rates"], "cache", cached["fx_date"], cached["origin"])
        if res is None:
            fb = load_yaml(fallback)
            if not isinstance(fb.get("as_of"), dt.date):
                raise ConfigError("fx.yaml: as_of должен быть датой YYYY-MM-DD")
            rates = {k: v for k, v in fb["to_pln"].items() if k != "PLN"}
            res = _result(rates, "fallback", fb["as_of"].isoformat())

    age = (now.date() - dt.date.fromisoformat(res["fx_date"])).days
    if age > MAX_AGE_DAYS:
        warnings.warn(f"Курс от {res['fx_date']} ({age} дн., источник {res['fx_source']})",
                      StaleFxWarning, stacklevel=2)
    return res
