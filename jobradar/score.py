"""extract + flags -> score.json: fit, job, покрытие, решение, шаблон ответа. Без модели."""
from __future__ import annotations

from .rates import HOURS_PER_DAY, HOURS_PER_MONTH, normalize_rate

LEVEL_W = {"strong": 1.0, "core": 1.0, "production": 1.0, "basic": 0.5, "pet": 0.5}
ENGLISH_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2", "native"]


# ---------- профиль

def skill_index(profile: dict) -> dict[str, dict]:
    idx = {}
    for s in profile.get("skills", []):
        for name in [s["name"], *s.get("aliases", [])]:
            idx[name.lower()] = s
    return idx


def skill_weight(term: str, idx: dict) -> float:
    s = idx.get(term.lower())
    return LEVEL_W.get(s["level"], 0.0) if s else 0.0


def group_score(g: dict, idx: dict) -> float:
    w = [skill_weight(t, idx) for t in g["terms"]]
    return max(w) if g["alt"] else sum(w) / len(w)


# ---------- fit

def fit_score(ex: dict, profile: dict, weights: dict) -> tuple[float, dict]:
    W = weights["fit"]
    idx = skill_index(profile)
    exp = profile.get("experience", {})
    parts = {}

    parts["role"] = W["role"].get(ex["role_class"], 0)

    must, nice = ex["stack"]["must"], ex["stack"]["nice"]
    pairs = [(group_score(g, idx), 1.0) for g in must] + [(group_score(g, idx), 0.5) for g in nice]
    if pairs:
        parts["stack"] = W["stack"] * sum(s * w for s, w in pairs) / sum(w for _, w in pairs)
    else:
        parts["stack"] = W["stack"] / 2          # стек не указан

    general = [y for y in ex["years"] if y["of"] == "general"]
    level = ex["level"]
    if level is None and any(y["years"] >= 5 for y in general):
        level = "senior"
    parts["level"] = {"senior": W["level"], "sr": W["level"], "sr.": W["level"]}.get(
        level, 0 if level in {"junior", "jr", "regular", "mid", "middle", "intern"} else W["level"] * 2 / 3)

    checks = [group_score(g, idx) for g in must]
    for y in ex["years"]:
        have = {"general": exp.get("total_years"), "ai": exp.get("ai_years")}.get(y["of"])
        if have is None:
            s = idx.get(y["of"].lower(), {})
            have = s.get("years")
        if have is None:
            checks.append(0.5)                    # неизвестно
        else:
            checks.append(1.0 if have >= y["years"] else 0.5 if have >= y["years"] - 1 else 0.0)
    if ex["languages"]["english_high"]:
        checks.append(0.5)
    if ex["residency_required"]:
        checks.append(1.0 if ex["residency_required"].lower() in {"poland", "pl", "polska"} else 0.0)
    parts["must"] = W["must"] * (sum(checks) / len(checks) if checks else 0.5)

    # Польский и диплом — только через риски, чтобы не штрафовать дважды.
    english = profile.get("languages", {}).get("English", "B2")
    ld = W["lang_degree"]
    if ex["languages"]["english_high"] and ENGLISH_ORDER.index(english) < ENGLISH_ORDER.index("C1"):
        ld -= 5
    parts["lang_degree"] = max(0, ld)

    parts = {k: round(v, 1) for k, v in parts.items()}
    return sum(parts.values()), parts


# ---------- job

def market_row(ex: dict, market: dict) -> dict:
    key = market["role_map"].get(ex["role_class"], "fullstack_senior")
    return {"key": key, **market["roles"][key]}


def travel_pln_h(ex: dict, profile: dict, weights: dict) -> float:
    loc, city = ex["location"], profile["location"]["city"].lower()
    days = loc["onsite_days_per_week"] or 0
    if loc["remote"] != "hybrid" or not [c for c in loc["cities"] if c.lower() != city]:
        return 0.0
    t = weights["travel"]
    return t["other_city_trip_pln"] * days * t["weeks_per_month"] / HOURS_PER_MONTH


def job_score(ex: dict, profile: dict, weights: dict, market: dict) -> tuple[float | None, dict, float, dict]:
    """Балл по известным частям: сумма известных / их максимум × 100. Неизвестные не считаются нулём.
    parts: {часть: [балл, максимум]} только для известных; coverage = доля известных весов."""
    W = weights["job"]
    parts: dict[str, list[float]] = {}
    mk = market_row(ex, market)
    rate = ex["rate"]
    money = {"market": mk, "effective_pln_h": None, "travel_pln_h": round(travel_pln_h(ex, profile, weights), 2)}
    if rate:
        eff = sum(rate["pln_h"]) / 2 - money["travel_pln_h"]
        money["effective_pln_h"] = round(eff, 2)
        lo, hi = mk["min"], mk["max"]
        if eff >= hi:
            m = W["money"]
        elif eff >= lo:
            m = W["money"] / 2 + W["money"] / 2 * (eff - lo) / (hi - lo)
        else:
            m = W["money"] / 2 * max(0.0, 1 - (lo - eff) / (0.3 * lo))
        parts["money"] = [m, W["money"]]

    half = W["contract"] / 2
    loc = ex["location"]
    city = profile["location"]["city"].lower()
    other = [c for c in loc["cities"] if c.lower() != city]
    if loc["remote"]:
        if loc["remote"] == "full" or (loc["remote"] == "hybrid" and not other and loc["cities"]):
            fmt = half
        elif loc["remote"] == "hybrid" and other:
            fmt = {1: half / 2, 2: half / 5}.get(loc["onsite_days_per_week"], 0)
        else:
            fmt = half / 2
        parts["format"] = [fmt, half]
    if ex["contract"]:
        preferred = profile.get("contract", {}).get("preferred", ["B2B"])
        parts["contract"] = [half if any(x in preferred for x in ex["contract"]) else half / 2, half]

    # company: до исследования неизвестна -> не входит в балл

    st = ex["interview_stages"]
    if st:
        parts["process"] = [W["process"] if st <= 3 else W["process"] * 0.7 if st == 4 else W["process"] * 0.3,
                            W["process"]]

    p = ex["poster"]["type"]
    if p != "unknown":
        parts["direct"] = [W["direct"] if p == "employer" else W["direct"] / 2 if ex["client_named"] else 0,
                           W["direct"]]

    if h := ex["hours"]:
        parts["hours"] = [W["hours"] if h["end"] <= "18:00" else W["hours"] / 2, W["hours"]]

    parts = {k: [round(s, 1), mx] for k, (s, mx) in parts.items()}
    known_max = sum(mx for _, mx in parts.values())
    coverage = round(known_max / sum(W.values()), 2)
    job = sum(s for s, _ in parts.values()) / known_max * 100 if known_max else None
    return job, parts, coverage, money


# ---------- деньги для ответа

def to_pln_day(amount: dict, fx: dict) -> float:
    r = normalize_rate(amount["amount"], None, amount["currency"], amount["unit"], fx)
    return r["pln_day"][0]


def money_advice(ex: dict, profile: dict, fx: dict, money: dict) -> dict:
    rate = ex["rate"]
    out = {"below_market": None, "below_best_offer": None, "counter_pln_day": None, "floor_pln_day": None}
    if not rate:
        return out
    mk = money["market"]
    out["below_market"] = money["effective_pln_h"] < mk["min"]
    if best := profile.get("best_offer"):
        best_h = to_pln_day(best, fx) / HOURS_PER_DAY
        out["below_best_offer"] = rate["pln_h"][1] < best_h
    if out["below_market"]:
        floor = to_pln_day(profile["min_rate"], fx) if profile.get("min_rate") else None
        counter = round(rate["pln_day"][1] / 50) * 50
        out["floor_pln_day"] = round(floor) if floor else None
        out["counter_pln_day"] = max(counter, out["floor_pln_day"] or 0)
    return out


# ---------- итог

def _penalties(flags: dict, weights: dict, ex: dict, money: dict) -> dict[str, float]:
    pen = {"fit": 0.0, "job": 0.0}
    for r in flags["risks"]:
        w = weights["risks"].get(r["code"])
        if not w:
            continue
        if r["code"] == "hours_after_18" and money["effective_pln_h"] and money["effective_pln_h"] >= money["market"]["min"]:
            continue                              # ставка не ниже рынка — часы не штрафуем
        pen[w["target"]] += w["penalty"]
    return pen


def is_empty(ex: dict) -> bool:
    """Письмо без сути: ни стека, ни ставки, ни контракта, ни локации."""
    loc = ex["location"]
    return not (ex["stack"]["must"] or ex["rate"] or ex["contract"] or loc["remote"] or loc["cities"])


def decide(ex: dict, flags: dict, fit: float, job: float | None, coverage: float, dups: list,
           weights: dict) -> tuple[str, str]:
    D = weights["decision"]
    if flags["scam"]:
        return "stop_scam", flags["scam"][0]["code"]
    if flags["blockers"]:
        b = flags["blockers"][0]
        return "skip", b["evidence"] if b["code"] == "admin_role" else b["code"]
    if dups:
        return "duplicate", f"{dups[0]['by']}: {dups[0]['slug']}"
    if ex["source_kind"] == "outreach" and ex["missing"]:
        return "clarify", "missing: " + ", ".join(ex["missing"])
    if job is None or coverage < D["min_coverage"]:
        # данных о вакансии мало: решаем по fit, остальное на звонке
        if fit >= D["apply"]["fit"]:
            return "apply", f"fit {fit:.0f}, job н/д (coverage {coverage:.0%}), остальное на звонке"
        if fit < D["skip_below"]:
            return "skip", f"fit {fit:.0f} < {D['skip_below']}, job н/д"
        return "clarify", f"fit {fit:.0f}, job н/д (coverage {coverage:.0%})"
    if fit >= D["apply"]["fit"] and job >= D["apply"]["job"]:
        return "apply", "оба порога пройдены"
    if fit < D["skip_below"] and job < D["skip_below"]:
        return "skip", "оба балла < порога"
    return "clarify", "пограничные баллы"


def template(decision: str, ex: dict, flags: dict, adv: dict) -> str | None:
    if decision == "stop_scam":
        return "scam"
    if decision == "duplicate":
        return None
    if is_empty(ex):
        return "empty"
    if decision == "skip":
        return "mismatch"
    if adv["below_market"]:
        return "low_rate"
    if any(r["code"] == "intermediary_no_client" for r in flags["risks"]):
        return "intermediary"
    return "good"


def call_notes(ex: dict, profile: dict) -> list[str]:
    notes = []
    pref = profile.get("contract", {}).get("preferred", ["B2B"])
    if not ex["contract"] or not any(c in pref for c in ex["contract"]):
        notes.append(f"уточнить {pref[0]} на звонке")
    if not ex["rate"]:
        notes.append("спросить вилку ставки")
    if ex["poster"]["type"] == "intermediary" and not ex["client_named"]:
        notes.append("спросить имя клиента")
    return notes


def job_label(sc: dict) -> str:
    return f"{sc['job']} (coverage {sc['coverage']:.0%})" if sc["job"] is not None \
        else f"н/д (coverage {sc['coverage']:.0%})"


def score(ex: dict, flags: dict, dups: list, profile: dict, weights: dict, market: dict, fx: dict) -> dict:
    D = weights["decision"]
    fit, fit_parts = fit_score(ex, profile, weights)
    job, job_parts, coverage, money = job_score(ex, profile, weights, market)
    pen = _penalties(flags, weights, ex, money)
    fit = max(0, min(100, round(fit + pen["fit"])))
    if job is not None and coverage >= D["min_coverage"]:
        job = max(0, min(100, round(job + pen["job"])))
    else:
        job = None                                # н/д: мало известных частей
    if flags["blockers"]:
        fit, job = 0, (0 if job is not None else None)
    decision, reason = decide(ex, flags, fit, job, coverage, dups, weights)
    adv = money_advice(ex, profile, fx, money)
    research = decision in ("apply", "clarify") and fit >= D["research_min"] \
        and (job is None or job >= D["research_min"]) and bool(ex["missing"])
    return {
        "fit": fit, "job": job, "coverage": coverage,
        "fit_parts": fit_parts, "job_parts": job_parts, "penalties": pen,
        "decision": decision, "reason": reason,
        "template": template(decision, ex, flags, adv),
        "call_notes": call_notes(ex, profile) if decision == "apply" else [],
        "research_needed": research,
        "missing": ex["missing"],
        "money": money, **adv,
        "fx_source": fx.get("fx_source"), "fx_date": fx.get("fx_date"),
    }
