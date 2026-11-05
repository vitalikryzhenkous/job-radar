import datetime as dt
import warnings

import pytest

from jobradar.config import ConfigError, StaleFxWarning, load_fx, load_profile


def test_profile_missing_stories_is_clear_error(tmp_path):
    p = tmp_path / "profile.yaml"
    p.write_text("stories_path: ~/nope/stories.md\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="stories_path не найден"):
        load_profile(p)


def test_profile_expands_stories_path(tmp_path):
    s = tmp_path / "stories.md"
    s.write_text("x", encoding="utf-8")
    p = tmp_path / "profile.yaml"
    p.write_text(f"stories_path: {s}\n", encoding="utf-8")
    assert load_profile(p)["stories_path"] == str(s)


def test_fx_stale_warns(tmp_path):
    f = tmp_path / "fx.yaml"
    f.write_text("as_of: 2026-01-01\nto_pln: {USD: 3.65}\n", encoding="utf-8")
    with pytest.warns(StaleFxWarning):
        load_fx(f, today=dt.date(2026, 3, 1))


def test_fx_fresh_no_warning(tmp_path):
    f = tmp_path / "fx.yaml"
    f.write_text("as_of: 2026-11-05\nto_pln: {USD: 3.65}\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        load_fx(f, today=dt.date(2026, 11, 20))
