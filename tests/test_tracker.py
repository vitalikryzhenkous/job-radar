from jobradar import tracker


def test_slugify_polish():
    assert tracker.slugify("Łódź Soft", "AI Engineer") == "lodz-soft-ai-engineer"


def test_upsert_keeps_old_fields(tmp_path):
    idx = tmp_path / "index.csv"
    tracker.upsert({"company": "Sii", "role": "FDE", "job_id": "JOB-1", "status": "applied"}, idx)
    tracker.upsert({"company": "Sii", "role": "FDE", "status": "in_process"}, idx)
    rows = tracker.read_index(idx)
    assert len(rows) == 1
    assert rows[0]["job_id"] == "JOB-1" and rows[0]["status"] == "in_process"


def test_seed(tmp_path):
    src = tmp_path / "s.csv"
    src.write_text("company,role,job_id,status,applied_date,note\nA,,,applied,2026-10-28,\nB,,,closed,,\n",
                   encoding="utf-8")
    assert tracker.seed(src, tmp_path / "index.csv") == 2
