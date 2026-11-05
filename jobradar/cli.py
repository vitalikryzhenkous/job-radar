"""python -m jobradar run|update|seed|status"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from . import tracker
from .config import ConfigError


def _not_yet(_args) -> int:
    print("Ещё не реализовано: появится в ветке feat/extract.", file=sys.stderr)
    return 2


def _seed(args) -> int:
    n = tracker.seed(Path(args.csv))
    print(f"Засеяно строк: {n} -> {tracker.INDEX.name}")
    return 0


def _status(_args) -> int:
    rows = tracker.read_index()
    print(f"Всего: {len(rows)}")
    for status, n in sorted(collections.Counter(r["status"] for r in rows).items()):
        print(f"  {status}: {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jobradar")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="механика шагов 2–5 и 10")
    run.add_argument("job_dir")
    run.set_defaults(func=_not_yet)

    upd = sub.add_parser("update", help="дописать сообщение рекрутера и пересчитать")
    upd.add_argument("slug")
    upd.add_argument("text")
    upd.set_defaults(func=_not_yet)

    sd = sub.add_parser("seed", help="засеять index.csv из CSV")
    sd.add_argument("csv")
    sd.set_defaults(func=_seed)

    sub.add_parser("status", help="сводка index.csv").set_defaults(func=_status)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError, FileNotFoundError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
