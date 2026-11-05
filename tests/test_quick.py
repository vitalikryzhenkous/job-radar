"""jr: новая вакансия, письмо по слагу, show и ls — во временной папке, без сети."""
import io
import shutil

import pytest

from jobradar import quick
from helpers import FIX, FX, PROFILE, raw


@pytest.fixture
def jr(tmp_path, monkeypatch):
    monkeypatch.setattr(quick, "JOBS", tmp_path / "jobs")
    monkeypatch.setattr(quick, "INDEX", tmp_path / "index.csv")
    monkeypatch.setattr(quick.fx, "get_rates", lambda: FX)
    monkeypatch.setattr(quick.pipeline, "load_profile", lambda: PROFILE)
    (tmp_path / "jobs").mkdir()

    def call(*args, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        return quick.main(list(args))
    return call


def test_new_then_update_then_show(jr, capsys, tmp_path):
    msgs = [p.read_text(encoding="utf-8") for p in raw("04-avance-ai-fullstack")]
    assert jr(stdin=msgs[0]) == 0
    d = tmp_path / "jobs" / "avance-consulting-ai-fullstack-developer"
    assert (d / "raw" / "001-email.txt").is_file() and (d / "verdict.md").is_file()
    for m in msgs[1:]:
        assert jr("avance", stdin=m) == 0                  # начало слага достаточно
    assert len(list((d / "raw").glob("*.txt"))) == 5
    out = capsys.readouterr().out
    assert "RTR:" in out and "черновик ответа" in out
    assert jr("show", "avance") == 0 and "Перед подписью RTR" in capsys.readouterr().out
    assert jr("ls") == 0 and "avance-consulting" in capsys.readouterr().out


def test_errors(jr, capsys):
    assert jr(stdin="") == 1
    assert jr("nope", stdin="x") == 1
    assert "jr ls" in capsys.readouterr().err


def test_guess_source():
    assert quick.guess_source("Об этой вакансии\n...") == "linkedin"
    assert quick.guess_source("Subject: RTR\nHi") == "email"
    assert quick.guess_source("Hi, 1000 PLN/day") == "text"


def test_take_from_pool(jr, capsys, tmp_path, monkeypatch):
    src = tmp_path / "jobs" / "_pool" / "2026-11-05" / "northwind-labs-senior-ai-engineer" / "raw"
    src.mkdir(parents=True)
    shutil.copy(FIX / "08-synthetic-low-job" / "raw" / "001-linkedin.txt", src / "001-justjoin.txt")
    monkeypatch.setattr(quick.scan, "POOL", tmp_path / "jobs" / "_pool")
    assert jr("take", "northwind-labs-senior-ai-engineer") == 0
    assert "northwind-labs-senior-ai-engineer" in (tmp_path / "index.csv").read_text()
    assert jr("show", "northwind") == 0                     # _pool не мешает поиску по началу слага
    assert jr("take", "northwind-labs-senior-ai-engineer") == 1   # второй раз — уже в jobs/
