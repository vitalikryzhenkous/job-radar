from jobradar.config import CONFIG, load_yaml
from jobradar.score import decide, group_score, skill_index
from helpers import PROFILE

W = load_yaml(CONFIG / "weights.yaml")
IDX = skill_index(PROFILE)
NOFLAGS = {"scam": [], "blockers": [], "risks": []}


def ex(**kw):
    base = {"source_kind": "posting", "missing": []}
    return {**base, **kw}


def test_group_alt_max_vs_mean():
    g = {"terms": ["TypeScript", "Go"], "alt": True}
    assert group_score(g, IDX) == 1.0
    assert group_score({**g, "alt": False}, IDX) == 0.5
    assert group_score({"terms": ["RAG"], "alt": False}, IDX) == 0.5   # pet


def test_decision_order():
    scam = {**NOFLAGS, "scam": [{"code": "asks_documents"}]}
    assert decide(ex(), scam, 90, 90, 1, [], W)[0] == "stop_scam"
    block = {**NOFLAGS, "blockers": [{"code": "us_only", "evidence": ""}]}
    assert decide(ex(), block, 90, 90, 1, [], W)[0] == "skip"
    assert decide(ex(), NOFLAGS, 90, 90, 1, [{"by": "job_id", "slug": "x"}], W)[0] == "duplicate"
    assert decide(ex(source_kind="outreach", missing=["rate"]), NOFLAGS, 90, 90, 1, [], W)[0] == "clarify"
    assert decide(ex(), NOFLAGS, 70, 60, 1, [], W)[0] == "apply"
    assert decide(ex(), NOFLAGS, 75, 40, 0.8, [], W)[0] == "clarify"
    assert decide(ex(), NOFLAGS, 40, 40, 1, [], W)[0] == "skip"
    assert decide(ex(), NOFLAGS, 60, 55, 1, [], W)[0] == "clarify"


def test_low_coverage_decides_by_fit():
    assert decide(ex(), NOFLAGS, 75, None, 0.3, [], W)[0] == "apply"
    assert decide(ex(), NOFLAGS, 60, None, 0.3, [], W)[0] == "clarify"
    assert decide(ex(), NOFLAGS, 40, None, 0.3, [], W)[0] == "skip"
    block = {**NOFLAGS, "blockers": [{"code": "us_only", "evidence": ""}]}
    assert decide(ex(), block, 90, None, 0.3, [], W)[0] == "skip"     # блокер раньше fit
    out = ex(source_kind="outreach", missing=["rate"])
    assert decide(out, NOFLAGS, 90, None, 0.3, [], W)[0] == "clarify"  # outreach — как было


def test_job_from_known_parts_only():
    from jobradar.score import job_score
    market = load_yaml(CONFIG / "market.yaml")
    e = {"rate": None, "location": {"remote": "full", "cities": [], "onsite_days_per_week": None},
         "contract": ["B2B"], "interview_stages": None, "poster": {"type": "employer"}, "client_named": None,
         "hours": None, "role_class": "fde_applied_ai"}
    job, parts, cov, _ = job_score(e, PROFILE, W, market)
    assert set(parts) == {"format", "contract", "direct"}    # неизвестные не нулём, их просто нет
    assert cov == 0.3 and job == 100


def test_known_job_thresholds():
    from jobradar.score import needs_counter
    assert decide(ex(), NOFLAGS, 75, 60, 0.7, [], W)[0] == "apply"
    d = decide(ex(), NOFLAGS, 75, 45, 0.7, [], W)[0]
    assert d == "clarify" and needs_counter(d, 75, 45, W)          # 40–59 -> торг, low_rate
    assert decide(ex(), NOFLAGS, 90, 39, 0.7, [], W)[0] == "skip"     # job < 40
    assert not needs_counter("clarify", 65, 45, W)                     # fit < 70 -> без контрпредложения
    assert not needs_counter("clarify", 75, None, W)                   # job н/д


def test_fit_risks_apply_when_job_unknown():
    """Диплом, Python, польский бьют по fit даже при job н/д."""
    import copy
    from helpers import FX, ON, raw
    from jobradar import flags as fl
    from jobradar.extract import extract
    from jobradar.normalize import normalize
    from jobradar.score import score
    market = load_yaml(CONFIG / "market.yaml")
    n = normalize(raw("03-inviso-applied-ai"))
    e = extract(n, FX, ON)
    f = fl.check(e, PROFILE, n.text())
    base = score(e, f, [], PROFILE, W, market, FX)
    assert base["job"] is None
    for code, pen in (("cs_degree_required", -5), ("python_must", -5), ("python_5y_must", -10), ("polish_c1_must", -10)):
        f2 = copy.deepcopy(f)
        f2["risks"].append({"code": code, "evidence": "test"})
        sc = score(e, f2, [], PROFILE, W, market, FX)
        assert sc["job"] is None and sc["fit"] == max(0, base["fit"] + pen), code


def test_pre_rtr_link_domain():
    import copy
    from helpers import FX, ON, raw
    from jobradar import flags as fl
    from jobradar.extract import extract
    from jobradar.normalize import normalize
    from jobradar.score import pre_rtr, money_advice, job_score
    market = load_yaml(CONFIG / "market.yaml")
    n = normalize(raw("04-avance-ai-fullstack", 5))
    e = extract(n, FX, ON)
    f = fl.check(e, PROFILE, n.text(), FX)
    _, _, _, money = job_score(e, PROFILE, W, market)
    adv = money_advice(e, PROFILE, FX, money)
    ok = pre_rtr(e, f, adv, PROFILE, FX)
    assert [i["status"] for i in ok["checklist"]] == ["ok", "ok", "check", "check", "ok"]
    for dom, st in (("docusign.net", "ok"), ("rtr-forms.example", "fail")):
        e2 = copy.deepcopy(e)
        e2["rtr"]["link_domains"] = [dom]
        assert pre_rtr(e2, f, adv, PROFILE, FX)["checklist"][4]["status"] == st, dom


def test_money_note():
    from jobradar.score import money_note
    assert money_note({"below_market": True, "below_best_offer": True}) == "ставка ниже рынка и лучшего оффера"
    assert money_note({"below_market": False, "below_best_offer": False}) is None
