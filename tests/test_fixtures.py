"""Структура фикстур: каждому ключу expected.yaml соответствует папка с raw/*.txt."""
import re
from pathlib import Path

import yaml

FIX = Path(__file__).parent / "fixtures"
EXPECTED = yaml.safe_load((FIX / "expected.yaml").read_text(encoding="utf-8"))


def test_every_case_has_raw():
    for slug, exp in EXPECTED.items():
        raw = sorted((FIX / slug / "raw").glob("*.txt"))
        assert raw, slug
        for key in exp:
            m = re.fullmatch(r"after_(\d{3})", key)
            if m:
                assert any(p.name.startswith(m[1]) for p in raw), f"{slug}: нет raw/{m[1]}-*"


def test_no_pii():
    pat = re.compile(r"[\w.]+@[\w.]+|\+\d{6,}|linkedin\.com/in/")
    for p in FIX.rglob("*.txt"):
        assert not pat.search(p.read_text(encoding="utf-8")), p
