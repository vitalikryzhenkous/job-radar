"""jobs/<slug>/raw/*.txt -> jd.md, extract.json, flags.json, score.json, verdict.md, reply.md + строка в index.csv."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import flags as fl
from . import tracker
from .config import CONFIG, ROOT, load_profile, load_yaml
from .extract import extract
from .normalize import normalize, to_markdown
from .score import job_label


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def run(job_dir: Path, fx: dict, *, index_path: Path = tracker.INDEX, profile: dict | None = None,
        on: dt.date | None = None, write_index: bool = True) -> dict:
    from .score import score

    job_dir = Path(job_dir)
    raw = sorted((job_dir / "raw").glob("*.txt"))
    if not raw:
        raise FileNotFoundError(f"Нет сообщений в {job_dir / 'raw'}")
    profile = profile or load_profile()
    weights = load_yaml(CONFIG / "weights.yaml")
    market = load_yaml(CONFIG / "market.yaml")
    first_run = not (job_dir / "score.json").exists()
    slug = job_dir.name

    n = normalize(raw)
    ex = extract(n, fx, on)
    text = n.text()
    f = fl.check(ex, profile, text, fx)
    index = tracker.read_index(index_path)
    dups = fl.duplicates(ex, index, slug, first_run)
    f["duplicates"] = dups
    f["same_company"] = fl.same_company(ex, index, slug)
    sc = score(ex, f, dups, profile, weights, market, fx)

    (job_dir / "jd.md").write_text(to_markdown(n), encoding="utf-8")
    _dump(job_dir / "extract.json", ex)
    _dump(job_dir / "flags.json", f)
    _dump(job_dir / "score.json", sc)
    (job_dir / "verdict.md").write_text(verdict(ex, f, sc, weights), encoding="utf-8")
    if draft := reply_draft(ex, sc, profile):
        (job_dir / "reply.md").write_text(draft, encoding="utf-8")

    if write_index and sc["decision"] != "duplicate":
        old = next((r for r in index if r["slug"] == slug), None)
        tracker.upsert({
            "slug": slug, "company": ex["company"] or "", "role": ex["role"] or "", "job_id": ex["job_id"] or "",
            "status": (old or {}).get("status") or ("skipped" if sc["decision"] in ("skip", "stop_scam") else "new"),
            "fit": sc["fit"], "job": "" if sc["job"] is None else sc["job"], "decision": sc["decision"],
        }, index_path)
    return {"extract": ex, "flags": f, "score": sc}


STATUS = {"ok": "✓", "fail": "✗", "check": "?"}


def unscored_job_risks(f: dict, sc: dict, weights: dict) -> list[str]:
    """Риски job со штрафом, которые не вошли в балл, потому что job н/д."""
    if sc["job"] is not None:
        return []
    out = []
    for r in f["risks"]:
        w = weights["risks"].get(r["code"]) or {}
        if w.get("target") == "job" and w.get("penalty"):
            out.append(f"{r['code']} {w['penalty']:+g}".replace("-", "−"))
    return out


def verdict(ex: dict, f: dict, sc: dict, weights: dict) -> str:
    """Человекочитаемый итог: что решено, почему и что сделать дальше."""
    L = [f"# {ex['company'] or '?'} — {ex['role'] or '?'}", "",
         f"- Решение: **{sc['decision']}** ({sc['reason']})",
         f"- fit {sc['fit']}, job {job_label(sc)}"]
    if miss := unscored_job_risks(f, sc, weights):
        L.append("- не учтено в балле: " + ", ".join(miss))
    for title, key in (("Скам", "scam"), ("Блокеры", "blockers"), ("Риски", "risks")):
        if f[key]:
            L.append(f"- {title}: " + "; ".join(f"{r['code']} ({r['evidence']})" for r in f[key]))
    if sc["missing"]:
        L.append("- Нет данных: " + ", ".join(sc["missing"]))
    if r := ex["rate"]:
        L.append(f"- Ставка: {r['pln_h'][0]}–{r['pln_h'][1]} PLN/ч, рынок {sc['money']['market']['min']}–"
                 f"{sc['money']['market']['max']}" + (f"; {sc['money_note']}" if sc["money_note"] else ""))
    if sc["counter_pln_day"]:
        L.append(f"- Контрпредложение: {sc['counter_pln_day']} PLN/день (floor {sc['floor_pln_day']})")
    if sc["call_notes"]:
        L.append("- На звонок: " + "; ".join(sc["call_notes"]))
    if rtr := sc["pre_rtr"]:
        L += ["", f"## Перед подписью RTR (вариант ответа: {rtr['variant']})"]
        L += [f"- {STATUS[i['status']]} {i['item']}" + (f" — {i['evidence']}" if i["evidence"] else "")
              for i in rtr["checklist"]]
        L += [f"- {x}" for x in rtr["fixes"]]
    if f.get("same_company"):
        L.append("- Уже есть в компании: " + ", ".join(f["same_company"]))
    L += ["", f"Шаблон: {sc['template'] or '—'}; research: {sc['research_needed']}; "
              f"fx: {sc['fx_source']} {sc['fx_date']}", ""]
    return "\n".join(L)


TEMPLATES = ROOT / "templates"
QUESTIONS = {"rate": "- What is the rate range?", "contract": "- Is it a B2B contract?",
             "client": "- Who is the end client?", "role": "- What is the exact role and team?",
             "location": "- Is it fully remote, and if not, where is the office?"}


class _Keep(dict):
    def __missing__(self, key):            # неизвестное поле остаётся {поле} — заполнит модель
        return "{" + key + "}"


def reply_draft(ex: dict, sc: dict, profile: dict) -> str | None:
    """Черновик ответа: шаблон + поля из score/extract. Дописывает и проверяет модель в /job-eval."""
    name = sc["template"]
    if not name or not (TEMPLATES / f"{name}.md").is_file():
        return None
    text = (TEMPLATES / f"{name}.md").read_text(encoding="utf-8")
    if name == "rtr":
        parts = text.split("## ")
        text = next(p for p in parts if p.startswith(sc["pre_rtr"]["variant"])).split("\n", 1)[1].strip() + "\n"
    fixes = []
    if (ex.get("submission") or {}).get("ltd") and profile.get("contract", {}).get("entity"):
        fixes.append(f"- Business form: please change \"{ex['submission']['ltd_evidence']}\" to No. "
                     f"I invoice as a sole proprietor ({profile['contract']['entity']}).")
    fields = _Keep(
        recruiter="[name]", first_name=profile.get("first_name", ""), role=ex["role"] or "[role]",
        company=ex["company"] or "[company]", client=ex.get("client") or "the client",
        counter_pln_day=sc["counter_pln_day"] or "[rate]", floor_pln_day=sc["floor_pln_day"] or "",
        questions="\n".join(QUESTIONS[m] for m in sc["missing"] if m in QUESTIONS),
        fixes="\n".join(fixes))
    out = re.sub(r"\n(?=\n\n)", "", text.format_map(fields))     # пустые {fixes}/{questions} без лишних строк
    return re.sub(r"(\n- [^\n]*)\n\n(?=- )", r"\1\n", out)


def add_message(job_dir: Path, text: str, source: str = "text") -> Path:
    raw = Path(job_dir) / "raw"
    if not raw.is_dir():
        raise FileNotFoundError(f"Нет вакансии: {job_dir}")
    nums = [int(p.name[:3]) for p in raw.glob("[0-9][0-9][0-9]-*.txt")]
    p = raw / f"{max(nums, default=0) + 1:03d}-{source}.txt"
    p.write_text(text.rstrip() + "\n", encoding="utf-8")
    return p


def summary(res: dict) -> str:
    ex, f, sc = res["extract"], res["flags"], res["score"]
    lines = [
        f"{ex['company'] or '?'} — {ex['role'] or '?'} [{ex['role_class']}, {ex['source_kind']}]",
        f"fit {sc['fit']}  job {job_label(sc)}  -> {sc['decision']} ({sc['reason']})",
    ]
    if f["scam"]:
        lines.append("СКАМ: " + ", ".join(r["code"] for r in f["scam"]))
    if f["blockers"]:
        lines.append("Блокеры: " + ", ".join(r["code"] for r in f["blockers"]))
    if f["risks"]:
        lines.append("Риски: " + ", ".join(r["code"] for r in f["risks"]))
    if sc["missing"]:
        lines.append("Нет данных: " + ", ".join(sc["missing"]))
    if ex["rate"]:
        r = ex["rate"]
        lines.append(f"Ставка: {r['pln_h'][0]}–{r['pln_h'][1]} PLN/ч; рынок {sc['money']['market']['min']}–"
                     f"{sc['money']['market']['max']}; ниже рынка: {sc['below_market']}")
    if sc["counter_pln_day"]:
        lines.append(f"Counter {sc['counter_pln_day']} PLN/день, floor {sc['floor_pln_day']} PLN/день")
    if sc["call_notes"]:
        lines.append("На звонок: " + "; ".join(sc["call_notes"]))
    if rtr := sc["pre_rtr"]:
        lines.append("RTR: " + " ".join(STATUS[i["status"]] for i in rtr["checklist"]) + f" -> {rtr['variant']}")
        lines += rtr["fixes"]
    if f["same_company"]:
        lines.append("Уже есть в компании: " + ", ".join(f["same_company"]))
    lines.append(f"Шаблон: {sc['template']}  research: {sc['research_needed']}  fx: {sc['fx_source']} {sc['fx_date']}")
    return "\n".join(lines)
