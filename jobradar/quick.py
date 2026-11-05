"""jr — короткий вход в Job Radar. Текст вставляется в терминал, конец ввода Ctrl+D.

  jr               новая вакансия: слаг, папка и прогон сами
  jr <slug>        новое письмо по вакансии (можно начало слага) + пересчёт
  jr show <slug>   показать verdict и черновик ответа без пересчёта
  jr ls            список вакансий
  jr scan <url>    пул с justjoin.it (до 50, пауза 2 с) -> jobs/_pool/<дата>/pool.md, index.csv не меняется
  jr map [дата]    пересчитать пул (без сети) и открыть карту в браузере (Fit × Job, города, черновики ответов)
  jr take <slug>   вакансия из пула -> jobs/<slug> + index.csv (status new)
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import fx, pipeline, poolmap, scan, tracker
from .config import ROOT, ConfigError, load_profile
from .extract import extract
from .normalize import normalize

JOBS = ROOT / "jobs"
INDEX = tracker.INDEX
LINKEDIN = re.compile(r"Подать заявку|Простая подача|Об этой вакансии|Easy Apply|About the job|\bapplicants\b", re.I)
EMAIL = re.compile(r"^subject:|^from:|greetings from|\[email removed\]|@[\w-]+\.\w+", re.I | re.M)


def guess_source(text: str) -> str:
    return "linkedin" if LINKEDIN.search(text) else "email" if EMAIL.search(text) else "text"


def read_text() -> str:
    if sys.stdin.isatty():
        print("Вставь текст, затем Enter и Ctrl+D:", file=sys.stderr)
    text = sys.stdin.read().strip()
    if not text:
        raise ValueError("пустой ввод")
    return text


def new_slug(text: str, rates: dict) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "001-text.txt"
        p.write_text(text + "\n", encoding="utf-8")
        ex = extract(normalize([p]), rates)
    base = tracker.slugify(ex["company"] or "", ex["role"] or "") or dt.datetime.now().strftime("job-%Y%m%d-%H%M")
    slug, i = base, 2
    while (JOBS / slug).exists():          # тот же слаг: новая папка, дубль поймает index.csv
        slug, i = f"{base}-{i}", i + 1
    return slug


def find(name: str) -> Path:
    if (JOBS / name).is_dir():
        return JOBS / name
    hits = sorted(p for p in JOBS.iterdir() if p.is_dir() and not p.name.startswith("_") and name.lower() in p.name)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise FileNotFoundError(f"нет вакансии «{name}» (jr ls — список)")
    raise ValueError(f"«{name}» подходит к нескольким: " + ", ".join(p.name for p in hits))


def show(d: Path, res: dict | None = None) -> None:
    if res:
        print(pipeline.summary(res))
    else:
        print((d / "verdict.md").read_text(encoding="utf-8"))
    if (d / "reply.md").is_file():
        print("\n--- черновик ответа (reply.md) ---")
        print((d / "reply.md").read_text(encoding="utf-8"))
    print(f"\nПапка: {d}")


def open_in_browser(path: Path) -> bool:
    """WSL: открыть файл в браузере Windows по умолчанию. Нет explorer.exe — просто вернуть False."""
    if not shutil.which("explorer.exe"):
        return False
    win = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()
    subprocess.run(["explorer.exe", win], capture_output=True)   # explorer.exe возвращает 1 даже при успехе
    return True


def ls() -> None:
    rows = tracker.read_index(INDEX)
    if not rows:
        print("index.csv пуст")
    for r in rows:
        print(f"{r['slug']:<45} {r.get('decision', ''):<10} fit {r.get('fit', ''):>3}  job {r.get('job') or 'н/д':>3}  "
              f"{r['status']}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args[:1] in (["-h"], ["--help"], ["help"]):
            print(__doc__)
        elif args[:1] == ["ls"]:
            ls()
        elif args[:1] == ["scan"] and len(args) == 2:
            md = scan.scan(args[1], fx.get_rates(), index_path=INDEX)
            print(f"Готово: {md}\nКарта: {poolmap.render(md.parent)}")
        elif args[:1] == ["map"] and len(args) <= 2:
            pool, profile = scan.POOL / args[1] if len(args) == 2 else poolmap.latest(), load_profile()
            n = poolmap.rescore(pool, fx.get_rates(), profile, INDEX)     # профиль/словари могли измениться
            out = poolmap.render(pool, profile)
            print(f"Пересчитано: {n}")
            print(f"Карта: {out}" + ("" if open_in_browser(out) else " (открой файл в браузере)"))
        elif args[:1] == ["take"] and len(args) == 2:
            d = scan.take(args[1], jobs=JOBS)
            show(d, pipeline.run(d, fx.get_rates(), index_path=INDEX))
        elif args[:1] == ["show"] and len(args) == 2:
            show(find(args[1]))
        elif not args:
            text, rates = read_text(), fx.get_rates()
            d = JOBS / new_slug(text, rates)
            (d / "raw").mkdir(parents=True)
            (d / "raw" / f"001-{guess_source(text)}.txt").write_text(text + "\n", encoding="utf-8")
            show(d, pipeline.run(d, rates, index_path=INDEX))
        elif len(args) == 1:
            d = find(args[0])
            text = read_text()
            p = pipeline.add_message(d, text, guess_source(text))
            print(f"Добавлено: {p.name}")
            show(d, pipeline.run(d, fx.get_rates(), index_path=INDEX))
        else:
            print(__doc__)
            return 2
    except (ConfigError, ValueError, FileNotFoundError, OSError) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
