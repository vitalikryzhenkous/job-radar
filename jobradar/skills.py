"""Уровень навыка в config/profile.yaml: правка одной строки (комментарии владельца целы) + бэкап в logs/."""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

import yaml

from .config import CONFIG, ROOT

LEVELS = ("strong", "core", "production", "basic", "pet", "none")     # none — «не владею», вес 0
NAME = re.compile(r"^[\w .+#/-]{1,40}$")


def _line_re(name: str) -> re.Pattern:
    q = re.escape(name)
    return re.compile(rf"^(\s*-\s*\{{\s*name:\s*(?:{q}|\"{q}\"|'{q}')\s*,[^\n]*?\blevel:\s*)[\w-]+", re.M)


def set_level(name: str, level: str, path: Path = CONFIG / "profile.yaml", backups: Path = ROOT / "logs") -> str:
    """Изменить уровень (или добавить навык в конец skills). Возвращает «changed» / «added» / «same»."""
    name = name.strip()
    if level not in LEVELS:
        raise ValueError(f"уровень: {', '.join(LEVELS)}")
    if not NAME.match(name):
        raise ValueError("имя навыка: буквы, цифры, пробел и . + # / - (до 40)")
    text = path.read_text(encoding="utf-8")
    known = {s["name"].lower(): s for s in yaml.safe_load(text).get("skills", [])}
    if (s := known.get(name.lower())) and s.get("level") == level:
        return "same"
    if s:
        new, n = _line_re(s["name"]).subn(lambda m: m[1] + level, text, count=1)
        if n != 1:
            raise ValueError(f"«{s['name']}» записан не одной строкой {{name: …, level: …}} — поправь руками")
        what = "changed"
    else:
        lines = text.splitlines(keepends=True)
        start = next(i for i, x in enumerate(lines) if x.startswith("skills:"))
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i][0].isspace()), len(lines))
        last = max(i for i in range(start + 1, end) if re.match(r"\s*-\s*\{\s*name:", lines[i]))
        lines.insert(last + 1, f"  - {{name: {json.dumps(name, ensure_ascii=False)}, level: {level}}}"
                               f"   # jr serve {dt.date.today().isoformat()}\n")
        new, what = "".join(lines), "added"
    backups.mkdir(parents=True, exist_ok=True)
    bak = backups / f"profile.yaml.bak-{dt.datetime.now():%Y-%m-%d-%H%M%S}"
    shutil.copy2(path, bak)
    path.write_text(new, encoding="utf-8")
    try:                                                    # проверка: файл читается и уровень стал нужным
        got = {s["name"].lower(): s.get("level") for s in yaml.safe_load(path.read_text(encoding="utf-8"))["skills"]}
        assert got.get(name.lower()) == level
    except Exception as e:
        shutil.copy2(bak, path)
        raise ValueError(f"правка не прошла проверку, профиль восстановлен из {bak.name}") from e
    return what


def listing(profile: dict) -> list[dict]:
    return [{"name": s["name"], "level": s.get("level"), "note": s.get("note") or s.get("where") or ""}
            for s in profile.get("skills", [])]
