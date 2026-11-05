"""jobs/<slug>/raw/*.txt -> jd.md, extract.json, flags.json, score.json + строка в index.csv."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import flags as fl
from . import tracker
from .config import CONFIG, load_profile, load_yaml
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
    f = fl.check(ex, profile, text)
    index = tracker.read_index(index_path)
    dups = fl.duplicates(ex, index, slug, first_run)
    f["duplicates"] = dups
    f["same_company"] = fl.same_company(ex, index, slug)
    sc = score(ex, f, dups, profile, weights, market, fx)

    (job_dir / "jd.md").write_text(to_markdown(n), encoding="utf-8")
    _dump(job_dir / "extract.json", ex)
    _dump(job_dir / "flags.json", f)
    _dump(job_dir / "score.json", sc)

    if write_index and sc["decision"] != "duplicate":
        old = next((r for r in index if r["slug"] == slug), None)
        tracker.upsert({
            "slug": slug, "company": ex["company"] or "", "role": ex["role"] or "", "job_id": ex["job_id"] or "",
            "status": (old or {}).get("status") or ("skipped" if sc["decision"] in ("skip", "stop_scam") else "new"),
            "fit": sc["fit"], "job": "" if sc["job"] is None else sc["job"], "decision": sc["decision"],
        }, index_path)
    return {"extract": ex, "flags": f, "score": sc}


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
    if f["same_company"]:
        lines.append("Уже есть в компании: " + ", ".join(f["same_company"]))
    lines.append(f"Шаблон: {sc['template']}  research: {sc['research_needed']}  fx: {sc['fx_source']} {sc['fx_date']}")
    return "\n".join(lines)
