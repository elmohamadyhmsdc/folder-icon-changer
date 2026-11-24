from app.services import searcher


class FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=0):
        self.store[key] = value


def test_empty_results_are_not_cached(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(searcher, "_cache", type("C", (), {"get": staticmethod(fake.get), "set": staticmethod(fake.set)}))
    calls = []

    def fetch():
        calls.append(1)
        return [] if len(calls) == 1 else [{"name": "ok"}]

    assert searcher._cached_fetch("k", fetch) == []
    assert fake.store == {}                      # failure not cached
    assert searcher._cached_fetch("k", fetch) == [{"name": "ok"}]
    assert searcher._cached_fetch("k", fetch) == [{"name": "ok"}]
    assert len(calls) == 2                       # success IS cached
