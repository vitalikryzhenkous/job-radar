import datetime as dt
from pathlib import Path

import yaml

FIX = Path(__file__).parent / "fixtures"
ON = dt.date(2026, 11, 5)
FX = {"to_pln": {"PLN": 1.0, "USD": 3.9097, "EUR": 4.4014}, "fx_source": "fallback", "fx_date": "2026-11-04"}
PROFILE = yaml.safe_load((FIX / "profile.yaml").read_text(encoding="utf-8"))


def raw(slug: str, upto: int | None = None) -> list[Path]:
    files = sorted((FIX / slug / "raw").glob("*.txt"))
    return files[:upto] if upto else files
