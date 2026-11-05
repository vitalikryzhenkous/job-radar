from jobradar.extract import extract, parse_hours, parse_rate, tech_groups
from jobradar.normalize import normalize
from helpers import FX, ON, raw


def ex(slug, upto=None):
    return extract(normalize(raw(slug, upto)), FX, ON)


def test_rate_day_pln_vat():
    r = parse_rate("Hi Vitalii, 1000 to 1100 PLN /Day(Gross)+VAT", FX)
    assert (r["min"], r["max"], r["currency"], r["unit"]) == (1000, 1100, "PLN", "day")
    assert r["pln_h"] == [125.0, 137.5] and r["gross_vat"]


def test_rate_year_usd():
    r = parse_rate("От 150K USD/yr до 240K USD/yr", FX)
    assert r["unit"] == "year" and r["currency"] == "USD" and r["min"] == 150000


def test_hours_et_to_warsaw():
    h = parse_hours("Required to work from 6am to 2pm eastern US time", ON)
    assert (h["start"], h["end"], h["tz"]) == ("12:00", "20:00", "Europe/Warsaw")


def test_alt_and_core():
    g = tech_groups(["Pragmatic Python skills and LLM APIs (LangChain, LangGraph, or equivalent)",
                     "backend language (Python, Node.js, or similar) and SQL",
                     "at least one language — e.g., Python, Go"])
    assert "Python" in g[0]["core"]
    assert "Python" not in g[1]["core"] and "SQL" in g[1]["core"]
    assert g[2]["alt"] and g[2]["core"] == []


def test_sii():
    e = ex("01-sii-fde")
    assert e["job_id"] == "JOB-7MFKW" and e["role_class"] == "fde_applied_ai"
    assert e["languages"]["polish_high"] == "must" and e["residency_required"] == "Poland"


def test_forte_header_and_remote():
    e = ex("02-forte-ai-product-engineer")
    assert (e["company"], e["role"]) == ("Forte Group", "AI Product Engineer")
    assert e["location"]["remote"] == "full"          # «Hybrid search» — не формат работы
    assert e["poster"]["type"] == "employer" and e["level"] == "senior"


def test_inviso_uop_intermediary():
    e = ex("03-inviso-applied-ai")
    assert (e["company"], e["role"]) == ("Inviso", "Applied AI Engineer")
    assert e["contract"] == ["UoP"] and e["poster"]["type"] == "intermediary"


def test_avance_steps():
    e1 = ex("04-avance-ai-fullstack", 1)
    assert e1["missing"] == ["rate", "client"] and e1["degree"]["required"]
    assert e1["role"] == "AI Fullstack Developer" and e1["contract"] == ["B2B"]
    e3 = ex("04-avance-ai-fullstack", 3)
    assert e3["rate"]["pln_h"] == [125.0, 137.5] and e3["screen_questions"] == 2


def test_empty_and_us_and_onsite():
    assert ex("05-empty-outreach")["missing"] == ["rate", "contract", "client", "location"]
    assert ex("06-us-only-fde")["work_auth"] == "US"
    e7 = ex("07-ai-engineer-warsaw-admin", 1)
    assert e7["location"]["onsite_days_per_week"] == 1 and e7["location"]["cities"] == ["Warsaw"]
    assert e7["role_class"] == "fde_applied_ai"
    assert ex("07-ai-engineer-warsaw-admin")["role_class"] == "admin"


def test_role_class_non_dev():
    from jobradar.extract import role_class
    assert role_class("Senior IT Business Analyst with AI - Freelance", "") == "non_dev"
    assert role_class("AI Product Owner", "") == "non_dev"
    assert role_class("Senior AI Governance Consultant", "") == "non_dev"
    assert role_class("AI Governance Engineer", "") == "other"          # инженер — не отсекаем
    assert role_class("Senior AI Engineer", "") == "fde_applied_ai"


def test_company_with_country_in_name(tmp_path):
    p = tmp_path / "001-justjoin.txt"
    p.write_text("ACME Polska\nAI Engineer\nWarszawa, Poland · Remote\nSalary: 100 - 180 PLN/hour (B2B)\nWe build agents.\n")
    e = extract(normalize([p]), FX, ON)
    assert (e["company"], e["role"]) == ("ACME Polska", "AI Engineer")


def test_polish_level():
    from jobradar.extract import polish_level
    assert polish_level("Org\nRole\nGdańsk\nLanguages: English C1, Polish C1\n", "") == "C1"
    assert polish_level("Languages: English B2\n", "") is None
    assert polish_level("", "Advanced level of Polish and English") == "C1"
    assert polish_level("", "Polish B2 or higher") == "B2"
    assert polish_level("", "Polish at A2 level, English C1") == "A2"
    assert polish_level("", "Experience with Polish market") is None
