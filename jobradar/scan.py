"""jr scan: страница списка justjoin.it -> пул вакансий с оценкой -> pool.md (рейтинг).

Читает только публичные HTML-страницы (JSON-LD schema.org), не /api/ (закрыт в robots.txt).
Пауза между запросами — DELAY секунд. index.csv не меняется: пул лежит в jobs/_pool/<дата>/.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import time
import unicodedata
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import pipeline, tracker
from .config import ROOT
from .score import skill_index, skill_weight

POOL = ROOT / "jobs" / "_pool"
UA = "job-radar/0.1 (personal use)"
DELAY = 2.0
LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)
ORDER = {"apply": 0, "clarify": 1, "skip": 2, "duplicate": 3, "stop_scam": 4}
CONTRACT = {"CONTRACTOR": "B2B", "FULL_TIME": None, "PART_TIME": None}
UNIT = {"HOUR": "hour", "DAY": "day", "MONTH": "month", "YEAR": "year"}


def fetch(url: str) -> str:
    if urlparse(url).path.startswith("/api/"):
        raise ValueError("/api/ закрыт в robots.txt")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


# площадки, с которых качаем страницы вакансий: (имя для raw-файла, путь страницы вакансии).
# robots.txt проверен для каждой; LinkedIn здесь не будет никогда (только вставка: jr add).
SITES = {
    "justjoin.it": ("justjoin", r"/job-offer/[\w-]+"),
    "nofluffjobs.com": ("nofluff", r"/(?:pl/)?job/[\w-]+"),         # robots: закрыты /api/, /posting/, */job/job/*
}
MAX_COLLECT = 100


def site_of(url: str) -> str:
    """Имя площадки для ссылки на вакансию или ValueError (чужой сайт, не https, не страница вакансии)."""
    u = urlparse(url)
    site = SITES.get(u.hostname or "")
    if u.scheme != "https" or not site or u.port or not re.fullmatch(site[1], u.path.rstrip("/")):
        raise ValueError(f"не страница вакансии поддерживаемой площадки: {url[:120]}")
    return site[0]


def _ld(page: str) -> list[dict]:
    out = []
    for m in LD.finditer(page):
        try:
            d = json.loads(m[1])
        except json.JSONDecodeError:
            continue
        for x in d if isinstance(d, list) else d.get("@graph", [d]):      # nofluff: список; бывает @graph
            if isinstance(x, dict):
                out.append(x)
    return out


def parse_list(page: str) -> list[dict]:
    """[{url, name}] из ItemList страницы списка."""
    for d in _ld(page):
        items = (d.get("mainEntity") or {}).get("itemListElement") or d.get("itemListElement") or []
        if items:
            return [{"url": i["url"], "name": i.get("name", "")} for i in items if i.get("url")]
    return []


def parse_offer(page: str) -> dict | None:
    return next((d for d in _ld(page) if d.get("@type") == "JobPosting"), None)


# языки — не в JobPosting, а в данных страницы (Next.js, JSON с экранированными кавычками)
LANGS = re.compile(r'\\?"languages\\?":\[((?:\{[^\]{}]*\},?)+)\]')
LANG_ITEM = re.compile(r'\\?"code\\?":\\?"([a-z]{2})\\?",\\?"level\\?":\\?"([A-Za-z0-9]+)')
LANG_NAME = {"pl": "Polish", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "uk": "Ukrainian", "ru": "Russian"}


def parse_languages(page: str) -> list[tuple[str, str]]:
    """[(Polish, C1), …] из первого списка languages с code/level (это сама вакансия)."""
    m = next((m for m in LANGS.finditer(page) if LANG_ITEM.search(m[1])), None)
    return [(LANG_NAME.get(c, c), lvl.upper()) for c, lvl in LANG_ITEM.findall(m[1])] if m else []


def html_text(s: str) -> list[str]:
    s = re.sub(r"<li[^>]*>", "\n- ", s)
    s = re.sub(r"</?(p|br|h\d|ul|ol|div)[^>]*>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return [line.strip() for line in s.splitlines() if line.strip() not in ("", "-")]


def posting_text(jp: dict, url: str, langs: list[tuple[str, str]] | None = None) -> str:
    """JobPosting -> текст в формате постинга (компания, роль, место — как LinkedIn-фикстуры)."""
    org = (jp.get("hiringOrganization") or {}).get("name") or "?"
    addr = ((jp.get("jobLocation") or {}).get("address") or {})
    city = addr.get("addressLocality") or ""
    country = {"PL": "Poland"}.get(addr.get("addressCountry"), addr.get("addressCountry") or "")
    remote = "Remote" if jp.get("jobLocationType") == "TELECOMMUTE" else ""
    types = jp.get("employmentType") or []
    types = [types] if isinstance(types, str) else types
    contract = [c for c in (CONTRACT.get(t) for t in types) if c]
    lines = [org, jp.get("title") or "?", ", ".join(x for x in (city, country) if x) + (f" · {remote}" if remote else ""),
             f"Source: {url}"]                       # не в конце: длинная последняя строка = признак обрезки
    sal = jp.get("baseSalary") or {}
    v = sal.get("value") or {}
    lo = v.get("minValue") or v.get("value")                     # nofluff: одно число в value
    if lo:
        unit = UNIT.get((v.get("unitText") or "").upper(), "month")
        lines.append(f"Salary: {lo:.0f} - {v.get('maxValue') or lo:.0f} "
                     f"{sal.get('currency', 'PLN')}/{unit}" + (f" ({', '.join(contract)})" if contract else ""))
    elif contract:
        lines.append("Contract: " + ", ".join(contract))
    lines.append("Languages: " + (", ".join(f"{n} {lvl}" for n, lvl in langs) if langs else "-"))   # «-» = проверено, нет
    lines += html_text(jp.get("description") or "")
    if skills := [x.get("value") for x in jp.get("skills") or [] if isinstance(x, dict) and x.get("type") == "main"]:
        lines.append("Requirements (must): " + ", ".join(skills))      # nofluff: обязательный стек отдельным полем
    return "\n".join(lines) + "\n"


def match(ex: dict, profile: dict) -> tuple[list[str], list[str]]:
    """(есть, нет): обязательный стек вакансии против навыков профиля."""
    idx = skill_index(profile)
    terms = list(dict.fromkeys(t for g in ex["stack"]["must"] for t in g["terms"]))
    have = [t for t in terms if skill_weight(t, idx) > 0]
    return have, [t for t in terms if t not in have]


def why(ex: dict, profile: dict) -> str:
    """Почему подходишь: что из обязательного стека есть в профиле и чего нет."""
    have, gaps = match(ex, profile)
    out = []
    if have:
        out.append("есть: " + ", ".join(have[:6]))
    if gaps:
        out.append("нет: " + ", ".join(gaps[:4]))
    return "; ".join(out) or "стек не указан"


def scan(url: str, rates: dict, *, limit: int = 50, profile: dict | None = None, index_path: Path = tracker.INDEX,
         out: Path | None = None, get=fetch, delay: float = DELAY, log=print) -> Path:
    from .config import load_profile
    if not url.startswith("https://justjoin.it/"):     # LinkedIn не качаем никогда: только jr add (вставка)
        raise ValueError("jr scan — только ссылки https://justjoin.it/ (LinkedIn — через jr add)")
    profile = profile or load_profile()
    out = out or POOL / dt.date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    items = parse_list(get(url))[:limit]
    if not items:
        raise ValueError("на странице нет списка вакансий (ItemList) — вёрстка могла измениться")
    rows = [r for n, it in enumerate(items, 1)
            if (r := _one(it["url"], "justjoin", out, rates, profile, index_path, get, delay, log, f"[{n}/{len(items)}]"))]
    (out / "pool.md").write_text(pool_md(rows, profile, url), encoding="utf-8")
    seen = {"url": url, "at": dt.datetime.now().isoformat(timespec="seconds"), "slugs": [r["slug"] for r in rows]}
    (out / "scan.json").write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")   # для «пропала»
    return out / "pool.md"


# ---------- дубли внутри пула: одна вакансия на нескольких площадках / в нескольких городах = одна карточка.
# Ключ — компания без юр. формы и страны + роль. Карточка — самая ранняя (по времени raw); остальные — алиасы:
# у оценённых раньше файлы остаются (карта их прячет), новые при сборе не оцениваются, а получают dup.json.
LEGAL = re.compile(r"\b(sp z o o|sp k|sp j|spolka z ograniczona odpowiedzialnoscia|spolka akcyjna|p s a|s a|sa"
                   r"|gmbh|ltd|limited|inc|llc|b v|polska|poland|group)\b")


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ł", "l"))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).split())


def card_key(company: str | None, role: str | None) -> str:
    """'' — нет компании или роли: такую не склеиваем."""
    co, ro = " ".join(LEGAL.sub(" ", _norm(company)).split()), _norm(role)
    return f"{co}|{ro}" if co and ro else ""


def _born(d: Path) -> float:
    return min(f.stat().st_mtime for f in (d / "raw").glob("*.txt"))


def pool_groups(pool: Path) -> tuple[dict, dict]:
    """({ключ: карточка}, {slug: карточка}) для всех вакансий пула (карточка сама себе — тоже)."""
    by_key, of, dirs = {}, {}, []
    for d in (p for p in pool.iterdir() if p.is_dir() and (p / "raw").is_dir()) if pool.is_dir() else ():
        if (d / "dup.json").is_file():
            of[d.name] = json.loads((d / "dup.json").read_text(encoding="utf-8"))["of"]
        elif (d / "extract.json").is_file():
            ex = json.loads((d / "extract.json").read_text(encoding="utf-8"))
            dirs.append((_born(d), d.name, card_key(ex["company"], ex["role"])))
    for _, slug, k in sorted(dirs):
        of[slug] = by_key.setdefault(k, slug) if k else slug
    for slug, c in list(of.items()):                 # dup.json на карточку, которая сама дубль -> к корню
        while of.get(c, c) != c:
            c = of[c]
        of[slug] = c
    return by_key, of


def _one(url, site, out, rates, profile, index_path, get, delay, log, tag, groups=None) -> dict | None:
    """Скачать страницу вакансии (если ещё нет) -> raw/001-<site>.txt -> оценка. None — на странице нет JobPosting.

    groups = pool_groups(out): дубль карточки пула не оценивается — пишется dup.json, возвращается {"dup_of": …}."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    d = out / slug
    f = d / "raw" / f"001-{site}.txt"
    old = f.read_text(encoding="utf-8") if f.is_file() else ""
    if "\nLanguages: " not in old:            # нет или скачано до поля языков — один раз докачать
        time.sleep(delay)
        page = get(url)
        jp = parse_offer(page)
        if not jp:
            log(f"{tag} пропуск, нет JobPosting: {url}")
            return None
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(posting_text(jp, url, parse_languages(page)), encoding="utf-8")
    if groups is not None:
        by_key, of = groups
        if slug not in of:                         # новая: ключ по тем же правилам, что и оценка, но без оценки
            from .extract import extract
            from .normalize import normalize
            ex = extract(normalize(sorted((d / "raw").glob("*.txt"))), rates)
            k = card_key(ex["company"], ex["role"])
            if k in by_key:
                of[slug] = by_key[k]
                (d / "dup.json").write_text(json.dumps({"of": of[slug], "company": ex["company"], "role": ex["role"]},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
            else:
                of[slug] = slug
                if k:
                    by_key[k] = slug
        if of[slug] != slug:
            log(f"{tag} дубль     → {of[slug]}  {slug}")
            return {"slug": slug, "url": url, "dup_of": of[slug]}
    res = pipeline.run(d, rates, index_path=index_path, profile=profile, write_index=False)
    sc = res["score"]
    log(f"{tag} {sc['decision']:<9} fit {sc['fit']:>3} job {sc['job'] if sc['job'] is not None else 'н/д':>3}  {slug}")
    return {"slug": slug, "url": url, "res": res}


def collect(urls: list[str], rates: dict, *, profile: dict | None = None, index_path: Path = tracker.INDEX,
            out: Path | None = None, get=fetch, delay: float = DELAY, log=print) -> dict:
    """Ссылки на вакансии со страницы списка (из расширения браузера) -> пул дня. Возвращает {решение: число}.

    Все ссылки проверяются ДО первого запроса: одна чужая — отказ целиком (расширение шлёт только своё)."""
    from .config import load_profile
    urls = list(dict.fromkeys(u.split("?")[0].split("#")[0].rstrip("/") for u in urls))   # без utm, без дублей
    if not urls:
        raise ValueError("нет ссылок на вакансии")
    if len(urls) > MAX_COLLECT:
        raise ValueError(f"за раз до {MAX_COLLECT} вакансий, пришло {len(urls)}")
    sites = [site_of(u) for u in urls]
    profile = profile or load_profile()
    out = out or POOL / dt.date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    groups = pool_groups(out)
    cards, dups, none = {}, 0, 0                   # карточка -> решение; дубли считаем отдельно
    for n, (u, site) in enumerate(zip(urls, sites), 1):
        r = _one(u, site, out, rates, profile, index_path, get, delay, log, f"[{n}/{len(urls)}]", groups)
        if not r:
            none += 1
        else:
            c = r.get("dup_of", r["slug"])
            dups += c in cards                         # эта вакансия в сборе уже есть (другой город / площадка)
            cards[c] = cards.get(c) or (None if "dup_of" in r else r["res"]["score"]["decision"])
    from .poolmap import overrides                 # ручные решения — как на карте
    ov = overrides(out)
    for c, dec in cards.items():
        ov_dec = (ov.get(c) or {}).get("decision")
        if ov_dec or dec is None:
            sc = out / c / "score.json"
            cards[c] = ov_dec or (json.loads(sc.read_text(encoding="utf-8"))["decision"] if sc.is_file() else "нет данных")
    got = {}
    for dec in cards.values():
        got[dec] = got.get(dec, 0) + 1
    for k, v in (("duplicate", dups), ("нет данных", none)):
        if v:
            got[k] = got.get(k, 0) + v
    batch = {"at": dt.datetime.now().isoformat(timespec="seconds"), "urls": len(urls), "slugs": sorted(cards)}
    (out / "collect.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")   # фильтр «этот сбор»
    return got


def _key(r: dict):
    sc = r["res"]["score"]
    return ORDER.get(sc["decision"], 9), -sc["fit"], -(sc["job"] if sc["job"] is not None else -1)


def pool_md(rows: list[dict], profile: dict, src: str) -> str:
    rows = sorted(rows, key=_key)
    L = [f"# Пул вакансий {dt.date.today().isoformat()}", "", f"Источник: {src}", f"Всего: {len(rows)}", ""]
    for dec in ORDER:
        part = [r for r in rows if r["res"]["score"]["decision"] == dec]
        if not part:
            continue
        L += [f"## {dec} ({len(part)})", ""]
        for i, r in enumerate(part, 1):
            ex, f, sc = r["res"]["extract"], r["res"]["flags"], r["res"]["score"]
            job = sc["job"] if sc["job"] is not None else "н/д"
            rate = f"{ex['rate']['pln_h'][0]:.0f}–{ex['rate']['pln_h'][1]:.0f} PLN/ч" if ex["rate"] else "ставка ?"
            L.append(f"{i}. **{ex['company'] or '?'} — {ex['role'] or '?'}** · fit {sc['fit']} · job {job} · {rate}"
                     + (f" ({sc['money_note']})" if sc["money_note"] else ""))
            L.append(f"   - {why(ex, profile)}")
            flags = [x["code"] for x in f["blockers"] + f["risks"]]
            if dec in ("skip", "duplicate", "stop_scam"):
                L.append(f"   - причина: {sc['reason']}")
            elif flags:
                L.append("   - риски: " + ", ".join(flags))
            L.append(f"   - {r['url']} · `jr take {r['slug']}`")
        L.append("")
    return "\n".join(L)


def take(slug: str, pool: Path | None = None, jobs: Path = ROOT / "jobs") -> Path:
    """Перенести вакансию из пула в jobs/ (дальше как обычная: jr <slug>, index.csv)."""
    hits = sorted((pool or POOL).glob(f"*/{slug}"), reverse=True)
    if not hits:
        raise FileNotFoundError(f"нет в пуле: {slug}")
    dst = jobs / slug
    if dst.exists():
        raise ValueError(f"уже в jobs/: {slug}")
    dst.mkdir(parents=True)
    (dst / "raw").mkdir()
    for p in (hits[0] / "raw").glob("*.txt"):
        (dst / "raw" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return dst
