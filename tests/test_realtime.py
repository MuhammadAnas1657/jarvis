"""Tests for WebSocket /ws, PostgresEventBus fallback, and /api/voice/transcribe."""

import io
import pytest
from fastapi.testclient import TestClient

import jarvis.web as web_mod
from jarvis.store import TaskStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_realtime.db"
    test_store = TaskStore(db_path=str(db_file), database_url="")
    monkeypatch.setattr(web_mod, "store", test_store)
    monkeypatch.setattr(web_mod.action_mgr, "store", test_store)
    monkeypatch.setattr(web_mod.briefing_engine, "store", test_store)
    with TestClient(web_mod.app) as c:
        yield c


def test_websocket_ping_and_broadcast(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["event"] == "ping"
        assert hello["data"]["status"] == "connected"

        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["event"] == "ping"
        assert pong["data"]["pong"] is True


def test_websocket_receives_action_confirmed_event(client):
    with client.websocket_connect("/ws") as ws:
        _ = ws.receive_json()  # initial connected ping

        res = client.post(
            "/api/actions/execute",
            json={
                "action": "create_reminder",
                "params": {"title": "WS Realtime Test", "priority": "high"},
                "user_confirmed": True,
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        ev1 = ws.receive_json()
        assert ev1["event"] == "action_confirmed"
        assert ev1["type"] == "create_reminder"

        ev2 = ws.receive_json()
        assert ev2["event"] == "reminder_added"


def test_voice_transcribe_ptt_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        web_mod,
        "groq_transcribe",
        lambda path, prompt=None: {"text": "Mark today university commute done"},
    )

    audio_bytes = io.BytesIO(b"RIFF....WAVEfmt ")
    res = client.post(
        "/api/voice/transcribe",
        files={"file": ("ptt.webm", audio_bytes, "audio/webm")},
    )
    assert res.status_code == 200
    assert res.json() == {"text": "Mark today university commute done"}
