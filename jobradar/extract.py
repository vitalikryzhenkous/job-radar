"""Normalized -> extract.json: поля вакансии regex'ами и словарями. Без модели."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .normalize import Normalized
from .rates import normalize_rate

DICTS = Path(__file__).parent / "dicts"
WARSAW = ZoneInfo("Europe/Warsaw")
I = re.I


def _load(name: str) -> dict:
    return yaml.safe_load((DICTS / name).read_text(encoding="utf-8"))


TECH = {k: [re.compile(p, I) for p in v] for k, v in _load("tech.yaml").items()}
_PLACES = _load("places.yaml")
CITIES = {k: re.compile("|".join(v), I) for k, v in _PLACES["cities"].items()}
COUNTRIES = {k: re.compile("|".join(v), I) for k, v in _PLACES["countries"].items()}

ALT = re.compile(r"\bat least one\b|\be\.g\.|\bor (equivalent|similar)\b|\bsuch as\b|\bany of\b", I)
PARENS = re.compile(r"\([^)]*\)")
INTERMEDIARY = re.compile(
    r"\bour client\b|one of our clients|on behalf of|partnering with|we'?re working with an?\b|"
    r"we are working with an?\b|recruitment and placement|greetings from", I)
ROLE_LINE = re.compile(r"^role\s*[:\-–]+\s*[:\-–]?\s*(.+)$", I)
ROLE_OUTREACH = re.compile(r"working on an? (.+?) (opportunity|role|position)", I)
COMPANY_GREET = re.compile(r"greetings from ([A-Z][\w&.]*(?: [A-Z][\w&.]*)*)", I)
JOB_ID = re.compile(r"\b(JOB-[A-Z0-9]{4,})\b|\bjob no\.?\s*([A-Z0-9-]{4,})|\b(?:ref|req)\.?\s*(?:no\.?|#)\s*([A-Z0-9-]{4,})", I)
SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|staff)\b", I)
BELOW = re.compile(r"\b(junior|jr\.?|regular|mid|middle|intern)\b", I)
ADMIN = re.compile(r"focused on admin|\badministrator\b|\badmin(istration)? role\b|\bsysadmin\b", I)
YEARS = re.compile(r"(\d+)\s*(?:\+|–\s*\d+|-\s*\d+)?\s*(?:\+\s*)?(?:years?|yrs|лет)\b(.{0,70})", I)
GENERAL_CTX = re.compile(r"^\W*(?:of\s+)?(?:experience\s+)?(?:in|of|with)?\s*(software|engineering|development|experience|professional|full-stack|commercial)", I)
AI_CTX = re.compile(r"\b(ai|artificial intelligence|llm|ml|machine learning|genai)\b", I)
POLISH_HI = re.compile(r"(advanced|fluent|c1|c2|native|proficient)[^.]{0,30}\bpolish\b|\bpolish\b[^.]{0,20}(advanced|fluent|c1|c2|native)", I)
ENGLISH_HI = re.compile(r"(c1|c2|native|fluent)[^.]{0,20}\benglish\b|\benglish\b[^.]{0,20}(c1|c2|native)", I)
DEGREE = re.compile(r"\b(BS|BSc|B\.S\.|bachelor'?s?|master'?s?|MSc|degree)\b[^.]{0,40}\b(computer science|CS|engineering|IT)\b", I)
DEGREE_SOFT = re.compile(r"or equivalent (practical )?experience|preferred|nice to have", I)
PHD = re.compile(r"\b(phd|ph\.d\.|doctorate)\b", I)
RESIDENCY = re.compile(r"\b(residency|resident|citizenship|citizen)\b[^.]{0,15}\b(in|of)\s+([A-Z][a-z]+)", I)
US_AUTH = re.compile(r"authori[sz]ed to work in the (us|u\.s\.|united states)|us work authori[sz]ation|"
                     r"based in the (us|u\.s\.)|must (be located|reside) in the (us|united states)", I)
HOURS = re.compile(r"from\s+(\d{1,2})(?::(\d\d))?\s*(am|pm)?\s*to\s+(\d{1,2})(?::(\d\d))?\s*(am|pm)?\s*"
                   r"(eastern|pacific|central|cet|cest|uk|gmt|utc)?", I)
TZ = {"eastern": "America/New_York", "pacific": "America/Los_Angeles", "central": "America/Chicago",
      "cet": "Europe/Warsaw", "cest": "Europe/Warsaw", "uk": "Europe/London", "gmt": "UTC", "utc": "UTC"}
B2B = re.compile(r"\bb2b\b|\bfreelance\b|\bcontract(or)?\b|\+\s*vat\b|\bJDG\b", I)
UOP = re.compile(r"\buop\b|umowa o prac|permanent employee|direct-hire|employment contract|base salary", I)
RATE = re.compile(
    r"(?P<cur1>\$|€|USD|EUR|PLN)?\s*(?P<lo>\d[\d,.]*\s*[kK]?)\s*(?:-|–|to|до)\s*(?P<cur2>\$|€|USD|EUR|PLN)?\s*"
    r"(?P<hi>\d[\d,.]*\s*[kK]?)\s*(?P<cur3>USD|EUR|PLN|zł|zl)?\s*/?\s*(?P<unit>h|hour|hr|day|d|month|mo|yr|year)?\b", I)
# LinkedIn RU/EN: «От 150K USD/yr до 240K USD/yr», «From 150K USD/yr to 240K USD/yr»
RATE_FROM_TO = re.compile(
    r"(?:от|from)\s+(?P<lo>\d[\d,.]*\s*[kK]?)\s*(?P<cur1>USD|EUR|PLN|\$|€)\s*/\s*(?P<unit>h|hour|hr|day|d|month|mo|yr|year)\s+"
    r"(?:до|to)\s+(?P<hi>\d[\d,.]*\s*[kK]?)", I)
STAGES = re.compile(r"(\d+)\s*(?:-|–)?\s*(?:stage|round|step)s?\b", I)
ONSITE_DAYS = re.compile(r"\b(once|one|1|twice|two|2|three|3|four|4)\s*(?:days?|times?)?\s*(?:a|per)\s*weeks?\b", I)
SCREEN_Q = re.compile(r"(\d+)\s+hard requirements", I)
NUM = {"once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4}
CUR = {"$": "USD", "€": "EUR", "zł": "PLN", "zl": "PLN"}
UNIT = {"h": "hour", "hr": "hour", "d": "day", "mo": "month", "yr": "year"}


def techs(text: str) -> list[str]:
    return [name for name, pats in TECH.items() if any(p.search(text) for p in pats)]


def tech_groups(lines: list[str]) -> list[dict]:
    """Строка требований -> группа терминов; alt=True, если подходит любой из них."""
    out = []
    for line in lines:
        terms = techs(line)
        if terms:
            bare = PARENS.sub("", line)
            # core: термины вне скобок в строке без маркера альтернатив — обязательны все
            core = [] if ALT.search(bare) else techs(bare)
            out.append({"line": line, "terms": terms, "alt": bool(ALT.search(line)), "core": core})
    return out


def _amount(s: str) -> float:
    s = s.strip().replace(",", "").replace(" ", "")
    k = s.lower().endswith("k")
    return float(s.rstrip("kK")) * (1000 if k else 1)


def parse_rate(text: str, fx: dict) -> dict | None:
    if m := RATE_FROM_TO.search(text):
        cur = CUR.get(m["cur1"], m["cur1"].upper())
        unit = UNIT.get(m["unit"].lower(), m["unit"].lower())
        lo, hi = _amount(m["lo"]), _amount(m["hi"])
        return {"min": lo, "max": hi, "currency": cur, "unit": unit, "gross_vat": False,
                "evidence": m.group(0).strip(), **normalize_rate(lo, hi, cur, unit, fx)}
    for m in RATE.finditer(text):
        cur = m["cur1"] or m["cur2"] or m["cur3"]
        if not cur:
            continue
        cur = CUR.get(cur.lower(), CUR.get(cur, cur.upper()))
        unit = m["unit"]
        unit = UNIT.get(unit.lower(), unit.lower()) if unit else None
        lo, hi = _amount(m["lo"]), _amount(m["hi"])
        if unit is None:
            unit = "year" if lo >= 20000 and cur in ("USD", "EUR") else "month" if lo >= 5000 else "day" if lo >= 500 else "hour"
        return {"min": lo, "max": hi, "currency": cur, "unit": unit,
                "gross_vat": bool(re.search(r"\+\s*vat", text, I)), "evidence": m.group(0).strip(),
                **normalize_rate(lo, hi, cur, unit, fx)}
    return None


def parse_hours(text: str, on: dt.date) -> dict | None:
    m = HOURS.search(text)
    if not m or not m[7]:
        return None
    tz = ZoneInfo(TZ[m[7].lower()])

    def conv(h, mi, ap):
        h = int(h) % 12 + (12 if (ap or "").lower() == "pm" else 0) if ap else int(h)
        t = dt.datetime.combine(on, dt.time(h, int(mi or 0)), tz).astimezone(WARSAW)
        return t.strftime("%H:%M")

    return {"start": conv(m[1], m[2], m[3]), "end": conv(m[4], m[5], m[6]), "tz": "Europe/Warsaw",
            "source_tz": TZ[m[7].lower()], "on": on.isoformat(), "evidence": m.group(0).strip()}


def parse_years(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        for m in YEARS.finditer(line):
            ctx = m[2]
            if GENERAL_CTX.search(ctx):
                kind = "general"
            elif AI_CTX.search(ctx):
                kind = "ai"
            else:
                t = techs(ctx)
                kind = t[0] if t else "general"
            out.append({"years": int(m[1]), "of": kind, "evidence": m.group(0).strip()})
    return out


def _clean_role(s: str) -> str:
    s = re.sub(r"\((?:f/m/x|m/f/d|m/w/d|k/m|f/m|m/f)\)", "", s, flags=I)
    s = re.sub(r"[\"”]?\s*[-–]\s*(?:Poland|Polska|Remote)\b.*$", "", s, flags=I)
    return s.strip(" \"'“”–-")


def _company_role(n: Normalized) -> tuple[str | None, str | None]:
    head = n.messages[0].lines if n.messages else []
    def is_place(s: str) -> bool:
        return any(c.search(s) for c in (*COUNTRIES.values(), *CITIES.values()))

    if not n.outreach and len(head) >= 2:
        if len(head) >= 3 and is_place(head[2]) and not is_place(head[0]):
            return head[0], _clean_role(head[1])
        if is_place(head[1]):
            return None, _clean_role(head[0])
    company = role = None
    text = n.text()
    if m := COMPANY_GREET.search(text):
        company = m[1].strip().rstrip(".!")
    for line in text.splitlines():
        if m := ROLE_LINE.match(line):
            role = _clean_role(m[1])
            break
    if not role and (m := ROLE_OUTREACH.search(text)):
        role = m[1].strip()
    return company, role


def role_class(role: str | None, text: str) -> str:
    if ADMIN.search(text):
        return "admin"
    r = (role or "").lower()
    if re.search(r"forward deployed|applied ai|ai product engineer|\bai engineer\b|llm engineer|genai engineer", r):
        return "fde_applied_ai"
    if re.search(r"full ?-?stack", r):
        return "fullstack_ai" if re.search(r"\bai\b", r) else "fullstack"
    if re.search(r"front ?-?end|angular|react", r):
        return "fullstack"
    return "other"


def extract(n: Normalized, fx: dict, on: dt.date | None = None) -> dict:
    on = on or dt.date.today()
    text = n.text()
    req = n.sections.get("requirements") or (
        n.header + n.sections.get("about", []) + n.sections.get("responsibilities", []))
    nice = n.sections.get("nice", [])
    req_text, all_text = "\n".join(req), text
    company, role = _company_role(n)
    intermediary = bool(INTERMEDIARY.search(text)) or (n.outreach and not company)
    jid = next((g for m in JOB_ID.finditer(text) for g in m.groups() if g), None)

    level = None
    if role and BELOW.search(role):
        level = BELOW.search(role)[1].lower()
    elif role and SENIOR.search(role):
        level = SENIOR.search(role)[1].lower()
    years = parse_years(req)
    if level is None and any(y["of"] == "general" and y["years"] >= 5 for y in years):
        level = "senior"

    remote = "hybrid" if re.search(r"\bhybrid\b(?!\s+(search|retrieval|cloud))|гибрид", text, I) else \
        "full" if re.search(r"\bremote\b|удаленн", text, I) else \
        "onsite" if re.search(r"\bonsite\b|on-site|in the office", text, I) else None
    days = None
    if remote == "hybrid" and (m := ONSITE_DAYS.search(text)):
        days = NUM.get(m[1].lower(), int(m[1]) if m[1].isdigit() else None)
    cities = [c for c, p in CITIES.items() if p.search(text)]
    countries = [c for c, p in COUNTRIES.items() if p.search(text)]

    contract = []
    if B2B.search(text):
        contract.append("B2B")
    if UOP.search(text):
        contract.append("UoP")

    res = RESIDENCY.search(req_text)
    degree = DEGREE.search(req_text)
    rate = parse_rate(text, fx)
    hours = parse_hours(text, on)
    polish = "must" if POLISH_HI.search(req_text) else "nice" if POLISH_HI.search("\n".join(nice)) else None

    data = {
        "job_id": jid,
        "company": company,
        "poster": {"type": "intermediary" if intermediary else ("employer" if company else "unknown"),
                   "name": company},
        "client_named": False if intermediary else None,
        "source_kind": "outreach" if n.outreach else "posting",
        "greeting_names": [m.greeting_name for m in n.messages if m.greeting_name],
        "role": role,
        "role_class": role_class(role, text),
        "level": level,
        "location": {"remote": remote, "onsite_days_per_week": days, "cities": cities, "countries": countries},
        "residency_required": res[3] if res else None,
        "work_auth": "US" if US_AUTH.search(text) else None,
        "hours": hours,
        "contract": contract,
        "rate": rate,
        "stack": {"must": tech_groups(req), "nice": tech_groups(nice)},
        "years": years,
        "languages": {"polish_high": polish, "english_high": bool(ENGLISH_HI.search(req_text))},
        "degree": {"required": bool(degree) and not DEGREE_SOFT.search(degree.string[degree.start():degree.end() + 60]),
                   "cs": bool(degree), "phd": bool(PHD.search(req_text)),
                   "evidence": degree.group(0) if degree else None},
        "interview_stages": int(m[1]) if (m := STAGES.search(text)) else None,
        "screen_questions": int(m[1]) if (m := SCREEN_Q.search(text)) else None,
        "truncated": n.truncated,
        "requirements_lines": len(req),
    }
    key = {"rate": rate, "contract": contract, "role": role,
           "location": remote or cities or countries}
    if intermediary:
        key["client"] = data["client_named"]
    data["missing"] = [k for k in ("rate", "contract", "client", "role", "location") if k in key and not key[k]]
    return data
