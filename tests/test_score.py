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
    assert decide(ex(), NOFLAGS, 75, 40, 0.3, [], W)[0] == "apply"     # posting с малым покрытием
    assert decide(ex(), NOFLAGS, 75, 40, 0.8, [], W)[0] == "clarify"
    assert decide(ex(), NOFLAGS, 40, 40, 1, [], W)[0] == "skip"
    assert decide(ex(), NOFLAGS, 60, 55, 1, [], W)[0] == "clarify"
