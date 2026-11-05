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


def test_map_html(tmp_path):
    import json
    from jobradar import poolmap
    pool = tmp_path / "2026-11-05"
    scan.scan("https://justjoin.it/job-offers/x", FX, profile=PROFILE, index_path=tmp_path / "i.csv", out=pool,
              get=fake_get([]), delay=0, log=lambda *a: None)
    assert poolmap.rescore(pool, FX, PROFILE, tmp_path / "i.csv") == 2 and not (tmp_path / "i.csv").exists()
    html = poolmap.render(pool, PROFILE).read_text(encoding="utf-8")
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst DEC", 1)[0])
    assert {r["company"] for r in data["rows"]} == {"Northwind Labs", "Contoso"}
    r = next(r for r in data["rows"] if r["company"] == "Northwind Labs")
    assert r["city"] == "Kraków" and r["url"].endswith("krakow-ai") and r["reply"] and r["km"] > 300
    assert "/*DATA*/" not in html and "<script src" not in html                    # офлайн, без CDN


def test_add_and_move(tmp_path, monkeypatch):
    import json
    from jobradar import poolmap, quick
    pool = tmp_path / "2026-11-05"
    pool.mkdir()
    monkeypatch.setattr(quick, "INDEX", tmp_path / "i.csv")
    a = (FIX / "08-synthetic-low-job" / "raw" / "001-linkedin.txt").read_text(encoding="utf-8")
    b = (FIX / "02-forte-ai-product-engineer" / "raw").glob("*.txt").__next__().read_text(encoding="utf-8")
    slugs = quick.add_to_pool(f"{a}\nhttps://www.linkedin.com/jobs/view/123/?x=1\n---\n{b}", FX, pool)
    assert len(slugs) == 2 and all((pool / s / "raw").is_dir() for s in slugs)
    head = (pool / slugs[0] / "raw" / "001-linkedin.txt").read_text(encoding="utf-8").splitlines()
    assert head[3] == "Source: https://www.linkedin.com/jobs/view/123" and "x=1" not in "".join(head)
    poolmap.rescore(pool, FX, PROFILE, tmp_path / "i.csv")
    assert poolmap.move(pool, slugs[0][:8], "apply", "роль моя") == slugs[0]
    data = json.loads(poolmap.render(pool, PROFILE).read_text(encoding="utf-8")
                      .split("const DATA = ", 1)[1].split(";\nconst DEC", 1)[0])
    r = {x["slug"]: x for x in data["rows"]}
    assert r[slugs[0]]["decision"] == "apply" and r[slugs[0]]["manual"] == "роль моя"
    assert r[slugs[0]]["url"] == "https://www.linkedin.com/jobs/view/123" and r[slugs[1]]["manual"] is None
    poolmap.move(pool, slugs[0], "auto")
    assert poolmap.overrides(pool) == {} and not (tmp_path / "i.csv").exists()
    import pytest
    with pytest.raises(ValueError):
        poolmap.move(pool, slugs[0], "maybe")


def test_languages_from_page():
    page = ('<script>self.__next_f.push([1,"{\\"slug\\":\\"x\\",\\"languages\\":[{\\"code\\":\\"en\\",\\"level\\":\\"C1\\"},'
            '{\\"code\\":\\"pl\\",\\"level\\":\\"C1\\"}]}"])</script>'
            '<script>{"layout":{"languages":{"pl":"Polish","en":"English"}}}</script>')
    assert scan.parse_languages(page) == [("English", "C1"), ("Polish", "C1")]
    assert scan.parse_languages("<html></html>") == []


def test_scan_only_justjoin(tmp_path):
    import pytest
    from jobradar import scan
    for bad in ("https://www.linkedin.com/jobs/search-results/?currentJobId=1", "http://justjoin.it/x", "https://justjoin.it.evil.com/"):
        with pytest.raises(ValueError):
            scan.scan(bad, {}, out=tmp_path, get=lambda u: (_ for _ in ()).throw(AssertionError("сеть")), profile={})
    assert not any(tmp_path.iterdir())
