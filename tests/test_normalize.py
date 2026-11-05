from jobradar.normalize import clean_lines, is_truncated, normalize, split_sections, to_markdown
from helpers import raw


def test_linkedin_noise_removed():
    lines = clean_lines("Подать заявку\nСохранить\nRole\nПольша · 5 часов назад · 71 кандидат")
    assert "Подать заявку" not in lines and "Сохранить" not in lines
    assert lines[0] == "Role"
    assert all("назад" not in x for x in lines)


def test_sections_split():
    header, sec = split_sections(["Title", "Requirements:", "- Python", "Nice to have:", "- Go"])
    assert header == ["Title"]
    assert sec["requirements"] == ["Python"] and sec["nice"] == ["Go"]


def test_truncation():
    assert is_truncated(["a", "2 hard requirements to screen for when meeting them:", "Thanks,"])
    assert not is_truncated(["a", "b", "c", "All good."])


def test_outreach_and_greeting():
    n = normalize(raw("07-ai-engineer-warsaw-admin"))
    assert n.outreach
    assert [m.greeting_name for m in n.messages] == ["Maksim", "Vitalii"]
    assert not normalize(raw("02-forte-ai-product-engineer")).outreach


def test_avance_truncated_after_001_and_003():
    assert normalize(raw("04-avance-ai-fullstack", 1)).truncated
    assert normalize(raw("04-avance-ai-fullstack")).messages[2].truncated


def test_markdown_has_sections():
    md = to_markdown(normalize(raw("02-forte-ai-product-engineer")))
    assert "## Requirements" in md and "## Responsibilities" in md
