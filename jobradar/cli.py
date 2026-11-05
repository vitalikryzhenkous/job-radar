"""python -m jobradar run|update|seed|status"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

from . import fx, pipeline, tracker
from .config import ROOT, ConfigError


def _job_dir(arg: str) -> Path:
    p = Path(arg)
    return p if p.is_dir() else ROOT / "jobs" / arg


def _run(args) -> int:
    res = pipeline.run(_job_dir(args.job_dir), fx.get_rates())
    print(pipeline.summary(res))
    return 0


def _update(args) -> int:
    d = _job_dir(args.slug)
    p = pipeline.add_message(d, args.text, args.source)
    print(f"Добавлено: {p.relative_to(d)}")
    print(pipeline.summary(pipeline.run(d, fx.get_rates())))
    return 0


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


def _fx(_args) -> int:
    r = fx.get_rates()
    rates = ", ".join(f"{k} {v}" for k, v in r["to_pln"].items() if k != "PLN")
    print(f"{rates} | fx_source={r['fx_source']} fx_origin={r['fx_origin']} fx_date={r['fx_date']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jobradar")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="механика шагов 2–5 и 10")
    run.add_argument("job_dir", help="jobs/<slug> или просто <slug>")
    run.set_defaults(func=_run)

    upd = sub.add_parser("update", help="дописать сообщение рекрутера и пересчитать")
    upd.add_argument("slug")
    upd.add_argument("text")
    upd.add_argument("--source", default="text", help="linkedin | email | text")
    upd.set_defaults(func=_update)

    sd = sub.add_parser("seed", help="засеять index.csv из CSV")
    sd.add_argument("csv")
    sd.set_defaults(func=_seed)

    sub.add_parser("fx", help="текущий курс и его источник").set_defaults(func=_fx)
    sub.add_parser("status", help="сводка index.csv").set_defaults(func=_status)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError, FileNotFoundError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
