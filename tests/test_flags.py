import copy

from jobradar import flags as fl
from jobradar.extract import extract
from jobradar.normalize import normalize
from helpers import FX, ON, PROFILE, raw


def run(slug, upto=None):
    n = normalize(raw(slug, upto))
    e = extract(n, FX, ON)
    return e, fl.check(e, PROFILE, n.text())


def codes(items):
    return sorted(r["code"] for r in items)


def test_sii_risks():
    _, f = run("01-sii-fde")
    assert codes(f["risks"]) == ["polish_c1_must", "python_must"]


def test_avance_risks():
    _, f = run("04-avance-ai-fullstack", 1)
    assert codes(f["risks"]) == sorted(["intermediary_no_client", "truncated", "hours_after_18", "cs_degree_required"])


def test_wrong_name_and_onsite():
    _, f = run("07-ai-engineer-warsaw-admin", 1)
    assert codes(f["risks"]) == sorted(["wrong_name", "onsite_other_city_1d", "intermediary_no_client"])
    _, f2 = run("07-ai-engineer-warsaw-admin")
    assert codes(f2["blockers"]) == ["admin_role"]


def test_us_only():
    _, f = run("06-us-only-fde")
    assert codes(f["blockers"]) == ["us_only"]


def test_onsite_3d_blocker():
    e, _ = run("07-ai-engineer-warsaw-admin", 1)
    e = copy.deepcopy(e)
    e["location"]["onsite_days_per_week"] = 3
    assert "onsite_other_city_3d" in codes(fl.check(e, PROFILE)["blockers"])


def test_scam():
    e, _ = run("05-empty-outreach")
    f = fl.check(e, PROFILE, "Please send a scan of your passport and continue on Telegram")
    assert codes(f["scam"]) == ["asks_documents", "moves_to_messenger"]


def test_duplicates():
    e, _ = run("01-sii-fde")
    idx = [{"slug": "sii-x", "company": "Sii", "role": "FDE", "job_id": "JOB-7MFKW", "status": "applied"}]
    assert fl.duplicates(e, idx, "01-sii-fde", True)[0]["by"] == "job_id"
    e2, _ = run("02-forte-ai-product-engineer")
    idx2 = [{"slug": "forte-group-ai-product-engineer", "company": "Forte Group",
             "role": "AI Product Engineer", "job_id": "", "status": "applied"}]
    assert fl.duplicates(e2, idx2, "02-forte", True)[0]["by"] == "company_role"
    # своя строка: повторный прогон — не дубль, первый прогон по уже поданной — дубль
    assert fl.duplicates(e2, idx2, "forte-group-ai-product-engineer", False) == []
    assert fl.duplicates(e2, idx2, "forte-group-ai-product-engineer", True)
