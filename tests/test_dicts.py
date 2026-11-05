from jobradar.extract import techs


def test_new_tech_terms_found():
    found = techs("Cypress, NUnit, Storybook, custom elements, SonarCloud")
    assert {"Cypress", "NUnit", "Storybook", "Web Components", "SonarQube"} <= set(found)
