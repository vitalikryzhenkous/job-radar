"""extract.json -> flags.json: блокеры, риски, скам, дубли. Без модели."""
from __future__ import annotations

import re

from .tracker import slugify

I = re.I
SCAM = {
    "asks_documents": re.compile(r"\b(passport|pesel|id card|bank (account|details)|iban|скан паспорта)\b", I),
    "moves_to_messenger": re.compile(r"\b(telegram|whatsapp|signal app)\b", I),
    "pay_to_start": re.compile(r"\b(pay|fee|deposit|purchase)\b[^.]{0,40}\b(training|equipment|laptop|course|starter kit)\b", I),
    "long_unpaid_test": re.compile(r"\b(unpaid|free)\b[^.]{0,30}\b(test|task|assignment)\b|\b(test|task|assignment)\b[^.]{0,40}\b([4-9]|\d\d)\s*(days|hours)\b", I),
}
FREE_MAIL = re.compile(r"[\w.+-]+@(gmail|outlook|hotmail|yahoo|proton(mail)?|wp|o2|interia)\.\w+", I)
BANKING = re.compile(r"\b(bank(ing)?|fintech|financial services)\b", I)
INDUSTRIAL_ML = re.compile(r"industrial (ml|ai|machine learning)|predictive maintenance|computer vision|"
                           r"train(ing)? models from scratch|manufacturing (ml|ai)", I)
BELOW = {"junior", "jr", "jr.", "regular", "mid", "middle", "intern"}
HOME_COUNTRY = {"poland", "pl", "polska"}


def _risk(code: str, evidence: str) -> dict:
    return {"code": code, "evidence": evidence}


def _end_after(hours: dict | None, limit: str = "18:00") -> bool:
    return bool(hours) and hours["end"] > limit


def floor_pln_day(profile: dict, fx: dict | None) -> float | None:
    from .score import to_pln_day
    return round(to_pln_day(profile["min_rate"], fx)) if fx and profile.get("min_rate") else None


def submission_mismatch(ex: dict, profile: dict, fx: dict | None) -> list[str]:
    """Что в submission summary расходится с профилем: форма бизнеса, ставка ниже floor."""
    sub = ex.get("submission")
    if not sub:
        return []
    out = []
    entity = profile.get("contract", {}).get("entity")
    if sub["ltd"] and entity and entity.lower() not in ("ltd", "sp. z o.o.", "limited company"):
        out.append(f"{sub['ltd_evidence']} -> {entity}")
    if sub["rate"] and (floor := floor_pln_day(profile, fx)):
        from .score import to_pln_day
        day = to_pln_day(sub["rate"], fx)
        if day < floor:
            out.append(f"ставка {round(day)} PLN/день < floor {floor}")
    return out


def check(ex: dict, profile: dict, text: str = "", fx: dict | None = None) -> dict:
    """Возвращает {blockers, risks, scam}. Дубли — отдельно: duplicates()."""
    blockers, risks, scam = [], [], []
    city = profile["location"]["city"].lower()
    loc = ex["location"]
    other_city = [c for c in loc["cities"] if c.lower() != city]
    must_core = {t for g in ex["stack"]["must"] for t in g.get("core", [])}
    req_text = " ".join(g["line"] for g in ex["stack"]["must"])

    # --- блокеры
    if ex["work_auth"] == "US" or (ex["residency_required"] or "").lower() in {"us", "usa", "united states"}:
        blockers.append(_risk("us_only", "US work authorization / residency"))
    elif ex["residency_required"] and ex["residency_required"].lower() not in HOME_COUNTRY:
        blockers.append(_risk("foreign_residency", ex["residency_required"]))
    if ex["level"] in BELOW:
        blockers.append(_risk("level_below_senior", ex["level"]))
    if "Java" in must_core and BANKING.search(text):
        blockers.append(_risk("java_banking_must", "Java must + banking"))
    if INDUSTRIAL_ML.search(req_text):
        blockers.append(_risk("industrial_ml_must", INDUSTRIAL_ML.search(req_text)[0]))
    if ex["degree"]["phd"]:
        blockers.append(_risk("phd_required", "PhD"))
    days = loc["onsite_days_per_week"]
    if other_city and (loc["remote"] == "onsite" or (days or 0) >= 3):
        blockers.append(_risk("onsite_other_city_3d", f"{other_city[0]}: {days or 'full'} d/week"))
    if ex["role_class"] == "admin":
        blockers.append(_risk("admin_role", "admin_role_vs_builder_profile"))
    if ex["role_class"] == "non_dev":
        blockers.append(_risk("non_dev_role", f"не разработка: {ex['role']}"))

    # --- риски
    if ex["poster"]["type"] == "intermediary" and not ex["client_named"]:
        risks.append(_risk("intermediary_no_client", ex["poster"]["name"] or "recruiter"))
    if _end_after(ex["hours"]):
        risks.append(_risk("hours_after_18", f"{ex['hours']['start']}–{ex['hours']['end']} Warsaw"))
    if ex["degree"]["required"] and ex["degree"]["cs"]:
        risks.append(_risk("cs_degree_required", ex["degree"]["evidence"]))
    py5 = [y for y in ex["years"] if y["of"] == "Python" and y["years"] >= 5]
    if py5:
        risks.append(_risk("python_5y_must", py5[0]["evidence"]))
    elif "Python" in must_core:
        risks.append(_risk("python_must", next(g["line"] for g in ex["stack"]["must"] if "Python" in g.get("core", []))))
    if ex["truncated"]:
        risks.append(_risk("truncated", "описание обрывается"))
    pol = ex["languages"]["polish_high"]
    if pol:
        risks.append(_risk(f"polish_c1_{pol}", "Polish C1+"))
    first = profile.get("first_name")
    wrong = [n for n in ex["greeting_names"] if first and n.lower() != first.lower()]
    if wrong:
        risks.append(_risk("wrong_name", f"Hi {wrong[0]}"))
    if other_city and days in (1, 2) and loc["remote"] == "hybrid":
        risks.append(_risk(f"onsite_other_city_{days}d", f"{other_city[0]}: {days} d/week"))

    if ex["poster"]["type"] == "intermediary" and ex.get("client_is_service_co"):
        risks.append(_risk("intermediary_chain", f"{ex['poster']['name'] or 'recruiter'} -> {ex['client']}"))
    if ex.get("rtr", {}).get("requested"):
        risks.append(_risk("rtr_request", ", ".join(ex["rtr"]["link_domains"]) or "без ссылки"))
    if mism := submission_mismatch(ex, profile, fx):
        risks.append(_risk("submission_mismatch", "; ".join(mism)))

    # --- скам
    for code, pat in SCAM.items():
        if m := pat.search(text):
            scam.append(_risk(code, m[0]))
    if (m := FREE_MAIL.search(text)) and ex["poster"]["type"] != "unknown" and ex["company"]:
        scam.append(_risk("email_domain_mismatch", m[0].split("@")[1]))

    return {"blockers": blockers, "risks": risks, "scam": scam}


def duplicates(ex: dict, index: list[dict], own_slug: str, first_run: bool) -> list[dict]:
    """Совпадение с index.csv по job_id, затем по компания+роль.
    Своя строка считается дублем только на первом прогоне и если её статус уже не new."""
    def others(r: dict) -> bool:
        return r["slug"] != own_slug or (first_run and r.get("status") not in ("", "new"))

    out = []
    if ex["job_id"]:
        out += [{"by": "job_id", "slug": r["slug"], "status": r["status"]}
                for r in index if others(r) and r.get("job_id") == ex["job_id"]]
    if not out and ex["company"] and ex["role"]:
        key = slugify(ex["company"], ex["role"])
        out += [{"by": "company_role", "slug": r["slug"], "status": r["status"]}
                for r in index if others(r) and slugify(r["company"], r["role"]) == key]
    return out


def same_company(ex: dict, index: list[dict], own_slug: str) -> list[str]:
    """Инфо: уже есть отклики в эту компанию (не дубль)."""
    if not ex["company"]:
        return []
    c = slugify(ex["company"])
    return [r["slug"] for r in index if r["slug"] != own_slug and slugify(r["company"]) == c]
