"""Tests for the Claude insights/chat layer.

The PURE tests (render_context, _parse_json) and the FAKE-CLIENT tests (daily_insight,
chat) run anywhere — no DB, no network, no `anthropic` package needed (the client is
injected). The endpoint tests are Docker-gated like the rest of the API suite (they
load app.main, which connects to a throwaway TimescaleDB and mocks the Anthropic call).
"""
import importlib

import pytest

from app import insights
from tests.conftest import requires_docker


# ── Fake Anthropic client (no network, records calls) ─────────────────────────

class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, blocks):
        self.content = blocks


class _FakeMessages:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        return self._owner.response


class FakeClient:
    """Stand-in for anthropic.Anthropic — returns a canned response, records kwargs."""

    def __init__(self, text="hi"):
        self.calls = []
        self.response = _Resp([_Block(text)])
        self.messages = _FakeMessages(self)


# ── render_context (pure) ─────────────────────────────────────────────────────

def test_render_context_formats_metrics():
    daily = [
        {"day": "2026-05-29", "recovery": 55, "strain": 12.3, "total_sleep_min": 430,
         "efficiency": 0.9, "deep_min": 90, "rem_min": 100, "light_min": 240,
         "resting_hr": 52, "avg_hrv": 73, "spo2_pct": 96, "resp_rate_bpm": 15.2,
         "skin_temp_dev_c": -0.3, "exercise_count": 1},
    ]
    workouts = [{"kind": "run", "duration_s": 1800, "avg_hr": 150, "peak_hr": 178,
                 "strain": 11.0, "calories_kcal": 420}]
    profile = {"age": 31, "sex": "male", "height_cm": 180, "weight_kg": 77.5}

    ctx = insights.render_context(daily=daily, workouts=workouts,
                                  profile=profile, target_day="2026-05-30")

    assert "Target day: 2026-05-30" in ctx
    assert "age 31" in ctx and "male" in ctx
    assert "recovery 55%" in ctx          # recovery is a 0-100 score
    assert "eff 90%" in ctx               # efficiency 0.9 -> 90%
    assert "HRV 73 ms" in ctx
    assert "run" in ctx and "30 min" in ctx and "420 kcal" in ctx


def test_render_context_handles_empty_and_nulls():
    ctx = insights.render_context(daily=[], workouts=[], profile=None,
                                  target_day="2026-05-30")
    assert "(no daily metrics in this range)" in ctx
    # A row full of Nones renders em dashes, not a crash.
    ctx2 = insights.render_context(
        daily=[{"day": "2026-05-30", "recovery": None, "strain": None,
                "total_sleep_min": None, "efficiency": None}],
        workouts=[], profile=None, target_day="2026-05-30")
    assert "recovery —" in ctx2          # bare em dash, no unit, when value is None
    assert "workouts 0" in ctx2


# ── _parse_json (pure) ────────────────────────────────────────────────────────

def test_parse_json_plain_fenced_and_prose():
    assert insights._parse_json('{"a": 1}') == {"a": 1}
    assert insights._parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert insights._parse_json('Sure!\n{"a": 3}\nHope that helps') == {"a": 3}
    with pytest.raises(Exception):
        insights._parse_json("no json here")


# ── daily_insight (fake client) ───────────────────────────────────────────────

def test_daily_insight_parses_and_sets_request_fields():
    fake = FakeClient(text='{"summary":"Solid week.","observations":["HRV trending up"],'
                           '"recommendations":["Keep sleep consistent"]}')
    out = insights.daily_insight("CTX-BLOCK", client=fake, model="claude-opus-4-8")

    assert out["summary"] == "Solid week."
    assert out["observations"] == ["HRV trending up"]
    assert out["recommendations"] == ["Keep sleep consistent"]

    (kwargs,) = fake.calls
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["thinking"] == {"type": "adaptive"}
    # Non-medical disclaimer rides in the (cached) system prompt.
    assert "NOT a medical device" in kwargs["system"][0]["text"]
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # The metrics context is handed to the model in the user turn.
    assert "CTX-BLOCK" in kwargs["messages"][0]["content"]


def test_daily_insight_normalizes_missing_keys():
    fake = FakeClient(text='{"summary":"ok"}')   # no observations/recommendations
    out = insights.daily_insight("ctx", client=fake)
    assert out == {"summary": "ok", "observations": [], "recommendations": []}


def test_daily_insight_tolerates_code_fences():
    fake = FakeClient(text='```json\n{"summary":"x","observations":[],"recommendations":[]}\n```')
    out = insights.daily_insight("ctx", client=fake)
    assert out["summary"] == "x"


# ── chat (fake client) ────────────────────────────────────────────────────────

def test_chat_returns_text_and_grounds_on_context():
    fake = FakeClient(text="Your recovery dipped because sleep was short.")
    msgs = [{"role": "user", "content": "Why was my recovery low?"}]
    reply = insights.chat(msgs, "CTX-BLOCK", client=fake, model="claude-opus-4-8")

    assert reply == "Your recovery dipped because sleep was short."
    (kwargs,) = fake.calls
    assert kwargs["messages"] == msgs
    # System carries persona + the metrics context, both cached.
    assert len(kwargs["system"]) == 2
    assert "CTX-BLOCK" in kwargs["system"][1]["text"]
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in kwargs["system"])


# ── Endpoint tests (Docker-gated; Anthropic call is mocked) ───────────────────

@pytest.fixture
def claude_client(clean_db, tmp_path, monkeypatch):
    """A TestClient with Claude configured, but insights.make_client patched to a fake
    so no real Anthropic request is made."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("WHOOP_API_KEY", "secret")
    monkeypatch.setenv("WHOOP_DB_DSN", clean_db)
    monkeypatch.setenv("WHOOP_RAW_ROOT", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    import app.main as m
    importlib.reload(m)

    fake = FakeClient(text='{"summary":"You are well recovered.","observations":[],'
                           '"recommendations":["Train hard today"]}')
    calls = {"n": 0}

    def _make(_key):
        calls["n"] += 1
        return fake

    monkeypatch.setattr(m.insights, "make_client", _make)
    tc = TestClient(m.app, headers={"Authorization": "Bearer secret"})
    tc._fake = fake          # type: ignore[attr-defined]
    tc._make_calls = calls   # type: ignore[attr-defined]
    return tc


@requires_docker
def test_insights_endpoint_generates_and_caches(claude_client, clean_db):
    import psycopg
    from app import store

    with psycopg.connect(clean_db) as conn:
        store.ensure_device(conn, "devI")
        store.upsert_daily_metrics(conn, "devI", "2026-05-30", {
            "total_sleep_min": 440, "efficiency": 0.92, "resting_hr": 50,
            "avg_hrv": 80, "recovery": 78, "strain": 9.0, "exercise_count": 0})
        conn.commit()

    r = claude_client.get("/v1/insights", params={"device": "devI", "date": "2026-05-30"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "You are well recovered."
    assert body["recommendations"] == ["Train hard today"]
    assert body["model"] == "claude-opus-4-8"
    assert claude_client._make_calls["n"] == 1

    # Second call (no refresh) is served from the daily_insights cache — no new Claude call.
    r2 = claude_client.get("/v1/insights", params={"device": "devI", "date": "2026-05-30"})
    assert r2.status_code == 200
    assert r2.json()["summary"] == "You are well recovered."
    assert claude_client._make_calls["n"] == 1

    # refresh=true regenerates.
    r3 = claude_client.get("/v1/insights",
                           params={"device": "devI", "date": "2026-05-30", "refresh": "true"})
    assert r3.status_code == 200
    assert claude_client._make_calls["n"] == 2


@requires_docker
def test_chat_endpoint(claude_client):
    claude_client._fake.response = _Resp([_Block("Because your sleep was short.")])
    r = claude_client.post("/v1/chat", json={
        "device": "devI",
        "messages": [{"role": "user", "content": "Why was recovery low?"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == "Because your sleep was short."


@requires_docker
def test_chat_validation(claude_client):
    # Empty messages → 422.
    assert claude_client.post("/v1/chat", json={"device": "d", "messages": []}).status_code == 422
    # Must start with a user turn.
    bad = claude_client.post("/v1/chat", json={
        "device": "d", "messages": [{"role": "assistant", "content": "hi"}]})
    assert bad.status_code == 422


@requires_docker
def test_insights_503_when_unconfigured(clean_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("WHOOP_API_KEY", "secret")
    monkeypatch.setenv("WHOOP_DB_DSN", clean_db)
    monkeypatch.setenv("WHOOP_RAW_ROOT", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import app.main as m
    importlib.reload(m)
    tc = TestClient(m.app, headers={"Authorization": "Bearer secret"})

    r = tc.get("/v1/insights", params={"device": "d", "date": "2026-05-30"})
    assert r.status_code == 503
    r2 = tc.post("/v1/chat", json={"device": "d",
                                   "messages": [{"role": "user", "content": "hi"}]})
    assert r2.status_code == 503
