"""jr map: пул -> map.html (Fit × Job и города). Один файл, без сети и внешних библиотек.

Данные только из файлов пула (extract/score/flags.json, verdict.md, reply.md) — модель не нужна.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

import yaml

from .config import load_profile
from . import skills as skills_mod
from .config import ROOT
from .scan import POOL, match, why

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


LINK = re.compile(r"https?://(?:www\.)?linkedin\.com/jobs/view/\d+|https?://justjoin\.it/job-offer/\S+")
DECISIONS = ("apply", "clarify", "skip")
STATUSES = ("applied", "replied", "call", "offer", "rejected")          # отклик; пусто — не подавался
JOBS = ROOT / "jobs"


def _raw_head(d: Path) -> tuple[str, str]:
    """(город, url) из шапки: jr scan пишет «Source:» и город в 3-й строке; во вставке ищем ссылку в тексте."""
    text = (sorted((d / "raw").glob("*.txt"))[0]).read_text(encoding="utf-8")
    lines = text.splitlines()
    city = re.split(r"[,·]", lines[2])[0].strip() if len(lines) > 2 else ""
    url = next((x[8:] for x in lines[:6] if x.startswith("Source: ")), "")
    if not url and (m := LINK.search(text)):
        url = m[0]
    return ALIAS.get(city, city), url


# ---------- ручные решения (jr move)

def overrides(pool_dir: Path) -> dict:
    p = pool_dir / "overrides.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def move(pool_dir: Path, name: str, decision: str, why: str = "") -> str:
    """Ручное решение по вакансии пула. decision=auto — снять. Баллы не меняются."""
    if decision not in (*DECISIONS, "auto"):
        raise ValueError(f"решение: {', '.join(DECISIONS)} или auto")
    hits = [p.name for p in pool_dir.iterdir() if (p / "raw").is_dir() and name.lower() in p.name]
    slug = name if name in hits else hits[0] if len(hits) == 1 else None
    if not slug:
        raise ValueError(f"«{name}»: " + ("нет в пуле" if not hits else "несколько: " + ", ".join(sorted(hits))))
    ov = overrides(pool_dir)
    if decision == "auto":
        ov.pop(slug, None)
    else:
        ov[slug] = {"decision": decision, "why": why, "date": dt.date.today().isoformat()}
    (pool_dir / "overrides.yaml").write_text(yaml.safe_dump(ov, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return slug


# ---------- статусы откликов: общий файл пулов, ключ — slug (переживает новые сканы)

def statuses(pool_root: Path = POOL) -> dict:
    p = pool_root / "status.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def set_status(slug: str, status: str, note: str = "", pool_root: Path = POOL) -> None:
    if status not in (*STATUSES, ""):
        raise ValueError(f"статус: {', '.join(STATUSES)} или пусто")
    st = statuses(pool_root)
    if status:
        st[slug] = {"status": status, "note": note, "date": dt.date.today().isoformat()}
    else:
        st.pop(slug, None)
    pool_root.mkdir(parents=True, exist_ok=True)
    (pool_root / "status.yaml").write_text(yaml.safe_dump(st, allow_unicode=True, sort_keys=True), encoding="utf-8")


def _seen(pool_dir: Path) -> set | None:
    """Слаги последнего скана этого пула; None — скан ещё без scan.json (старый пул)."""
    p = pool_dir / "scan.json"
    return set(json.loads(p.read_text(encoding="utf-8"))["slugs"]) if p.is_file() else None


def _earlier(pool_dir: Path) -> set:
    return {d.name for p in pool_dir.parent.iterdir() if p.is_dir() and p.name < pool_dir.name for d in p.iterdir()}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def rows(pool_dir: Path, profile: dict) -> list[dict]:
    home = ALIAS.get(profile.get("location", {}).get("city", ""), profile.get("location", {}).get("city", ""))
    ov, st, seen, before = overrides(pool_dir), statuses(pool_dir.parent), _seen(pool_dir), _earlier(pool_dir)
    taken = {r["slug"]: r.get("status") or "new" for r in _index()}
    out = []
    for d in sorted(p for p in pool_dir.iterdir() if (p / "score.json").is_file()):
        ex = json.loads(_read(d / "extract.json"))
        sc = json.loads(_read(d / "score.json"))
        f = json.loads(_read(d / "flags.json"))
        city, url = _raw_head(d)
        if city not in CITY_XY and ex["location"]["cities"]:          # вставка LinkedIn: город из extract
            city = ALIAS.get(ex["location"]["cities"][0], ex["location"]["cities"][0])
        manual = ov.get(d.name)
        have, gaps = match(ex, profile)
        scanned = any((d / "raw").glob("*-justjoin.txt"))
        rate = ex["rate"]["pln_h"] if ex["rate"] else None
        out.append({
            "slug": d.name, "url": url, "company": ex["company"] or "?", "role": ex["role"] or "?",
            "decision": manual["decision"] if manual else sc["decision"], "auto": sc["decision"],
            "manual": (manual.get("why") or "") if manual else None, "reason": sc["reason"], "fit": sc["fit"], "job": sc["job"],
            "rate": rate, "money_note": sc["money_note"], "remote": ex["location"]["remote"],
            "onsite_days": ex["location"]["onsite_days_per_week"], "city": city,
            "km": km(CITY_XY[city], CITY_XY[home]) if city in CITY_XY and home in CITY_XY else None,
            "why": why(ex, profile), "risks": [x["code"] for x in f["blockers"] + f["risks"]],
            "call_notes": sc.get("call_notes") or [], "verdict": _read(d / "verdict.md"),
            "reply": _read(d / "reply.md"), "template": sc["template"], "have": have, "gaps": gaps,
            "status": st.get(d.name), "taken": taken.get(d.name, "new") if (JOBS / d.name).is_dir() else None,
            "new": bool(before) and d.name not in before,
            "gone": scanned and seen is not None and d.name not in seen,     # нет в последнем скане сайта
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


def _index() -> list[dict]:
    from .tracker import INDEX, read_index
    return read_index(INDEX)


def data(pool_dir: Path | None = None, profile: dict | None = None) -> dict:
    pool_dir = pool_dir or latest()
    profile = profile or load_profile()
    home = profile.get("location", {}).get("city", "")
    return {"date": pool_dir.name, "home": ALIAS.get(home, home), "cities": CITY_XY,
            "pools": sorted((p.name for p in POOL.iterdir() if p.is_dir()), reverse=True) if POOL.is_dir() else [],
            "skills": skills_mod.listing(profile), "levels": skills_mod.LEVELS, "statuses": STATUSES,
            "api": None, "rows": rows(pool_dir, profile)}


def html(d: dict) -> str:
    js = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")     # не закрыть <script> данными
    return TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", js)


def render(pool_dir: Path | None = None, profile: dict | None = None) -> Path:
    pool_dir = pool_dir or latest()
    out = pool_dir / "map.html"
    out.write_text(html(data(pool_dir, profile)), encoding="utf-8")
    return out
