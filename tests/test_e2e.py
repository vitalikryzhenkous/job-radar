"""Прогон pipeline по фикстурам против expected.yaml."""
import re
import shutil
import time

import pytest
import yaml

from jobradar import pipeline
from helpers import FIX, FX, ON, PROFILE, raw

EXPECTED = yaml.safe_load((FIX / "expected.yaml").read_text(encoding="utf-8"))


def cases():
    for slug, exp in EXPECTED.items():
        steps = {k: v for k, v in exp.items() if re.fullmatch(r"after_\d{3}", k)}
        idx = {k: v for k, v in exp.items() if k.endswith("_index")}
        if steps:
            for k, v in steps.items():
                yield pytest.param(slug, int(k[6:]), "seeded_index", v, id=f"{slug}-{k}")
        elif idx:
            for k, v in idx.items():
                yield pytest.param(slug, None, k, v, id=f"{slug}-{k}")
        else:
            yield pytest.param(slug, None, "seeded_index", exp, id=slug)


def _run(tmp_path, slug, upto, index):
    jd = tmp_path / slug
    (jd / "raw").mkdir(parents=True)
    for p in raw(slug, upto):
        shutil.copy(p, jd / "raw")
    idx = tmp_path / "index.csv"
    if index == "seeded_index":
        shutil.copy(FIX / "index_seed.csv", idx)
    return pipeline.run(jd, FX, index_path=idx, profile=PROFILE, on=ON)


@pytest.mark.parametrize("slug,upto,index,exp", list(cases()))
def test_case(tmp_path, slug, upto, index, exp):
    t0 = time.monotonic()
    r = _run(tmp_path, slug, upto, index)
    assert time.monotonic() - t0 < 120
    ex, f, sc = r["extract"], r["flags"], r["score"]
    assert sc["decision"] == exp["decision"], sc["reason"]
    checks = {
        "duplicate_by": lambda v: f["duplicates"][0]["by"] == v,
        "risks": lambda v: sorted(x["code"] for x in f["risks"]) == sorted(v),
        "blockers": lambda v: sorted(x["code"] for x in f["blockers"]) == sorted(v),
        "missing": lambda v: ex["missing"] == v,
        "contract": lambda v: ex["contract"] == v,
        "call_notes": lambda v: all(n in sc["call_notes"] for n in v),
        "hours": lambda v: {k: ex["hours"][k] for k in v} == v,
        "rate_pln_h": lambda v: ex["rate"]["pln_h"] == v,
        "below_market": lambda v: sc["below_market"] is v,
        "counter_pln_day": lambda v: sc["counter_pln_day"] == v,
        "floor_pln_day": lambda v: sc["floor_pln_day"] == v,
        "truncated": lambda v: ex["truncated"] is v,
        "screen_questions": lambda v: ex["screen_questions"] == v,
        "template": lambda v: sc["template"] == v,
        "reason": lambda v: sc["reason"] == v,
        "job": lambda v: sc["job"] == v,
        "coverage_below": lambda v: sc["coverage"] < v,
        "job_between": lambda v: sc["job"] is not None and v[0] <= sc["job"] <= v[1],
        "fit_at_least": lambda v: sc["fit"] >= v,
        "money_note": lambda v: sc["money_note"] == v,
        "pre_rtr_variant": lambda v: sc["pre_rtr"]["variant"] == v,
        "pre_rtr_failed": lambda v: sc["pre_rtr"]["failed"] == v,
        "pre_rtr_fixes": lambda v: sc["pre_rtr"]["fixes"] == v,
    }
    for key, v in exp.items():
        if key == "decision":
            continue
        assert key in checks, f"нет проверки для {key}"
        assert checks[key](v), f"{key}: ожидалось {v}"


def test_outputs_written_and_index_updated(tmp_path):
    r = _run(tmp_path, "02-forte-ai-product-engineer", None, "empty")
    jd = tmp_path / "02-forte-ai-product-engineer"
    for name in ("jd.md", "extract.json", "flags.json", "score.json", "verdict.md", "reply.md"):
        assert (jd / name).is_file()
    rows = (tmp_path / "index.csv").read_text(encoding="utf-8")
    assert "02-forte-ai-product-engineer" in rows and r["score"]["decision"] in rows
    assert r["score"]["fx_source"] == "fallback"


def test_rerun_not_duplicate_of_itself(tmp_path):
    _run(tmp_path, "03-inviso-applied-ai", None, "empty")
    jd = tmp_path / "03-inviso-applied-ai"
    again = pipeline.run(jd, FX, index_path=tmp_path / "index.csv", profile=PROFILE, on=ON)
    assert again["score"]["decision"] == "apply"


def test_add_message(tmp_path):
    jd = tmp_path / "x"
    (jd / "raw").mkdir(parents=True)
    (jd / "raw" / "001-email.txt").write_text("Hi", encoding="utf-8")
    assert pipeline.add_message(jd, "rate 1000 PLN/day").name == "002-text.txt"


def test_verdict_lists_unscored_job_risks(tmp_path):
    _run(tmp_path, "03-inviso-applied-ai", None, "empty")
    v = (tmp_path / "03-inviso-applied-ai" / "verdict.md").read_text(encoding="utf-8")
    assert "не учтено в балле: intermediary_no_client −10" in v


def test_verdict_and_reply_rtr(tmp_path):
    _run(tmp_path, "04-avance-ai-fullstack", 5, "seeded_index")
    jd = tmp_path / "04-avance-ai-fullstack"
    v = (jd / "verdict.md").read_text(encoding="utf-8")
    assert "не учтено в балле" not in v                    # job известен
    assert "Перед подписью RTR" in v and "исправить до RTR" in v
    reply = (jd / "reply.md").read_text(encoding="utf-8")
    assert "Own Limited Company: Yes" in reply and "JDG" in reply and "{" not in reply
