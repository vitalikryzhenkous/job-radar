"""Загрузка конфигов. Ошибки — понятным текстом, без трейсбеков для пользователя."""
from __future__ import annotations

import datetime as dt
import warnings
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
FX_MAX_AGE_DAYS = 30


class ConfigError(Exception):
    pass


class StaleFxWarning(UserWarning):
    pass


def load_yaml(path: Path | str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Нет файла {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile(path: Path | str | None = None) -> dict:
    path = Path(path) if path else CONFIG / "profile.yaml"
    if not path.is_file():
        raise ConfigError(
            f"Нет {path}. Скопируй config/profile.example.yaml в config/profile.yaml и заполни."
        )
    profile = load_yaml(path)
    raw = profile.get("stories_path")
    if not raw:
        raise ConfigError(f"В {path} нет stories_path")
    stories = Path(raw).expanduser()
    if not stories.is_file():
        raise ConfigError(f"stories_path не найден: {stories} (задан в {path})")
    profile["stories_path"] = str(stories)
    return profile


def load_fx(path: Path | str | None = None, today: dt.date | None = None) -> dict:
    fx = load_yaml(path or CONFIG / "fx.yaml")
    as_of = fx.get("as_of")
    if not isinstance(as_of, dt.date):
        raise ConfigError("fx.yaml: as_of должен быть датой YYYY-MM-DD")
    age = ((today or dt.date.today()) - as_of).days
    if age > FX_MAX_AGE_DAYS:
        warnings.warn(
            f"Курс в fx.yaml от {as_of} ({age} дн.), обнови", StaleFxWarning, stacklevel=2
        )
    return fx
