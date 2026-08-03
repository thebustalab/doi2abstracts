"""Offline tests for Client._get retry/backoff, with a fake session."""

from doi2abstracts import client as client_mod
from doi2abstracts.client import Client


class FakeResp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return {}


class FakeSession:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return FakeResp(status)


def _client(monkeypatch, statuses, max_retries=3):
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_: None)  # no real waiting
    c = Client(email="t@example.edu", max_retries=max_retries)
    c.session = FakeSession(statuses)
    return c


def test_retries_429_then_succeeds(monkeypatch):
    c = _client(monkeypatch, [429, 429, 200])
    resp = c._get("http://x")
    assert resp is not None and resp.status_code == 200
    assert c.session.calls == 3


def test_gives_up_after_max_retries(monkeypatch):
    c = _client(monkeypatch, [503], max_retries=2)
    resp = c._get("http://x")
    assert resp is None
    assert c.session.calls == 3  # initial + 2 retries


def test_404_is_not_retried(monkeypatch):
    c = _client(monkeypatch, [404, 200])
    resp = c._get("http://x")
    assert resp is None
    assert c.session.calls == 1  # terminal, no retry
