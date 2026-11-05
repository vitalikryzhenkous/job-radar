"""jr scan / take: страница списка и вакансии из сохранённых синтетических HTML, без сети."""
from jobradar import scan
from helpers import FIX, FX, PROFILE

J = FIX / "justjoin"
PAGES = {"list": "list.html", "northwind": "offer-good.html", "contoso": "offer-low.html", "fabrikam": "offer-none.html"}


def fake_get(calls):
    def get(url):
        calls.append(url)
        key = "list" if "/job-offers/" in url else url.rsplit("/", 1)[-1].split("-")[0]
        return (J / PAGES[key]).read_text(encoding="utf-8")
    return get


def test_parse_list_and_offer():
    items = scan.parse_list((J / "list.html").read_text())
    assert len(items) == 3 and items[0]["name"] == "Senior AI Engineer"
    jp = scan.parse_offer((J / "offer-good.html").read_text())
    t = scan.posting_text(jp, items[0]["url"])
    assert t.splitlines()[:5] == ["Northwind Labs", "Senior AI Engineer", "Kraków, Poland · Remote",
                                  f"Source: {items[0]['url']}", "Salary: 26000 - 33000 PLN/month (B2B)"]
    assert "- 5+ years of Python" in t and "<" not in t
    assert scan.parse_offer("<html></html>") is None


def test_api_blocked():
    import pytest
    with pytest.raises(ValueError):
        scan.fetch("https://justjoin.it/api/offers")


def test_scan_pool_and_take(tmp_path):
    calls, logs = [], []
    url = "https://justjoin.it/job-offers/remote/ai?employment-types=b2b"
    idx = tmp_path / "index.csv"
    pool = tmp_path / "pool" / "2026-11-05"
    md = scan.scan(url, FX, profile=PROFILE, index_path=idx, out=pool, get=fake_get(calls), delay=0, log=logs.append)
    text = md.read_text(encoding="utf-8")
    assert len(calls) == 4 and not idx.exists()                     # index.csv не тронут
    assert "пропуск, нет JobPosting" in logs[2]
    assert text.index("Northwind Labs") < text.index("Contoso")     # лучшее выше
    assert "truncated" not in text and "jr take northwind-labs-senior-ai-engineer-krakow-ai" in text and "есть: " in text
    # повторный прогон: уже скачанные страницы не запрашиваются
    calls.clear()
    scan.scan(url, FX, profile=PROFILE, index_path=idx, out=pool, get=fake_get(calls), delay=0, log=logs.append)
    assert len(calls) == 2                                          # список + страница без JobPosting
    dst = scan.take("northwind-labs-senior-ai-engineer-krakow-ai", pool.parent, tmp_path / "jobs")
    assert (dst / "raw" / "001-justjoin.txt").is_file() and not (dst / "score.json").exists()
