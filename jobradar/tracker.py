"""index.csv: трекер вакансий. Ключ — slug."""
from __future__ import annotations

import csv
import datetime as dt
import re
import unicodedata
from pathlib import Path

from .config import ROOT

INDEX = ROOT / "index.csv"
COLUMNS = [
    "slug", "company", "role", "job_id", "status", "applied_date",
    "fit", "job", "decision", "note", "updated",
]
STATUSES = {"new", "applied", "in_process", "closed", "skipped"}
_TRANSLIT = str.maketrans({"ł": "l", "Ł": "L"})  # не раскладывается NFKD


def slugify(*parts: str) -> str:
    text = " ".join(p for p in parts if p).translate(_TRANSLIT)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_index(path: Path = INDEX) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_index(rows: list[dict], path: Path = INDEX) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def upsert(row: dict, path: Path = INDEX) -> dict:
    if row.get("status") and row["status"] not in STATUSES:
        raise ValueError(f"Неизвестный статус: {row['status']}")
    row = {**row, "slug": row.get("slug") or slugify(row.get("company", ""), row.get("role", ""))}
    row["updated"] = dt.date.today().isoformat()
    rows = read_index(path)
    for i, old in enumerate(rows):
        if old["slug"] == row["slug"]:
            rows[i] = {**old, **{k: v for k, v in row.items() if v not in (None, "")}}
            break
    else:
        rows.append({c: row.get(c, "") for c in COLUMNS})
    write_index(rows, path)
    return row


def seed(src: Path, path: Path = INDEX) -> int:
    """Засев из CSV с колонками company,role,job_id,status,applied_date,note."""
    with Path(src).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        upsert(r, path)
    return len(rows)
