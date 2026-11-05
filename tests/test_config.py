import pytest

from jobradar.config import ConfigError, load_profile


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
