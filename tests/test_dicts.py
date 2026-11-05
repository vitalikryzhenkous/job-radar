from jobradar.extract import techs


def test_new_tech_terms_found():
    found = techs("Cypress, NUnit, Storybook, custom elements, SonarCloud")
    assert {"Cypress", "NUnit", "Storybook", "Web Components", "SonarQube"} <= set(found)


def test_service_companies():
    from jobradar.extract import SERVICE_COS
    hit = {k for k, p in SERVICE_COS.items() if p.search("Tata Consultancy Services, Hexaware Europe, HCLTech")}
    assert hit == {"TCS", "Hexaware", "HCLTech"}
    assert not any(p.search("Hexagon, Persistence layer") for p in SERVICE_COS.values())
