import urllib.request

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Тесты не ходят в сеть: любой urlopen падает."""
    def blocked(*a, **k):
        raise RuntimeError("сеть в тестах запрещена")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
