"""jr map: пул -> map.html (Fit × Job и города). Один файл, без сети и внешних библиотек.

Данные только из файлов пула (extract/score/flags.json, verdict.md, reply.md) — модель не нужна.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .config import load_profile
from .scan import POOL, why

TEMPLATE = Path(__file__).with_name("poolmap.html")
# (lon, lat) — только для схемы на вкладке «Города»
CITY_XY = {
    "Warszawa": (21.01, 52.23), "Kraków": (19.94, 50.06), "Poznań": (16.93, 52.41), "Wrocław": (17.04, 51.11),
    "Gdańsk": (18.65, 54.35), "Gdynia": (18.53, 54.52), "Łódź": (19.46, 51.76), "Szczecin": (14.55, 53.43),
    "Katowice": (19.02, 50.26), "Lublin": (22.57, 51.25), "Bydgoszcz": (18.00, 53.12), "Białystok": (23.16, 53.13),
    "Rzeszów": (22.00, 50.04), "Toruń": (18.60, 53.01), "Opole": (17.93, 50.67), "Kielce": (20.63, 50.87),
    "Olsztyn": (20.49, 53.78), "Gliwice": (18.67, 50.29), "Sopot": (18.57, 54.44),
}
ALIAS = {"Warsaw": "Warszawa", "Cracow": "Kraków", "Krakow": "Kraków", "Poznan": "Poznań", "Wroclaw": "Wrocław",
         "Gdansk": "Gdańsk", "Lodz": "Łódź"}


def km(a: tuple, b: tuple) -> int:
    (lo1, la1), (lo2, la2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)))


def _raw_head(d: Path) -> tuple[str, str]:
    """(город, url) из шапки текста, который записал jr scan."""
    lines = (sorted((d / "raw").glob("*.txt"))[0]).read_text(encoding="utf-8").splitlines()
    city = lines[2].split(",")[0].strip() if len(lines) > 2 else ""
    url = next((x[8:] for x in lines[:6] if x.startswith("Source: ")), "")
    return ALIAS.get(city, city), url


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def rows(pool_dir: Path, profile: dict) -> list[dict]:
    home = ALIAS.get(profile.get("location", {}).get("city", ""), profile.get("location", {}).get("city", ""))
    out = []
    for d in sorted(p for p in pool_dir.iterdir() if (p / "score.json").is_file()):
        ex = json.loads(_read(d / "extract.json"))
        sc = json.loads(_read(d / "score.json"))
        f = json.loads(_read(d / "flags.json"))
        city, url = _raw_head(d)
        rate = ex["rate"]["pln_h"] if ex["rate"] else None
        out.append({
            "slug": d.name, "url": url, "company": ex["company"] or "?", "role": ex["role"] or "?",
            "decision": sc["decision"], "reason": sc["reason"], "fit": sc["fit"], "job": sc["job"],
            "rate": rate, "money_note": sc["money_note"], "remote": ex["location"]["remote"],
            "onsite_days": ex["location"]["onsite_days_per_week"], "city": city,
            "km": km(CITY_XY[city], CITY_XY[home]) if city in CITY_XY and home in CITY_XY else None,
            "why": why(ex, profile), "risks": [x["code"] for x in f["blockers"] + f["risks"]],
            "call_notes": sc.get("call_notes") or [], "verdict": _read(d / "verdict.md"),
            "reply": _read(d / "reply.md"), "template": sc["template"],
        })
    return out


def rescore(pool_dir: Path, fx: dict, profile: dict, index_path: Path) -> int:
    """Пересчитать вакансии пула по сохранённым текстам (без сети): после правки профиля, весов, словарей."""
    from . import pipeline
    dirs = [p for p in sorted(pool_dir.iterdir()) if (p / "raw").is_dir()]
    for d in dirs:
        pipeline.run(d, fx, index_path=index_path, profile=profile, write_index=False)
    return len(dirs)


def latest() -> Path:
    return max((p for p in POOL.iterdir() if p.is_dir()), key=lambda p: p.name)


def render(pool_dir: Path | None = None, profile: dict | None = None) -> Path:
    pool_dir = pool_dir or latest()
    profile = profile or load_profile()
    home = profile.get("location", {}).get("city", "")
    data = {"date": pool_dir.name, "home": ALIAS.get(home, home), "cities": CITY_XY,
            "rows": rows(pool_dir, profile)}
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")     # не закрыть <script> данными
    out = pool_dir / "map.html"
    out.write_text(TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", js), encoding="utf-8")
    return out
