"""Tests for Milestone 1: Projects & Learnings weekday auto-scheduler and Slash-Skills registry."""

import pytest
from fastapi.testclient import TestClient

import jarvis.web as web_mod
from jarvis.store import TaskStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_m1.db"
    test_store = TaskStore(db_path=str(db_file), database_url="")
    test_store.add_routine_block("Monday", "Classes", "07:00", "16:00")
    monkeypatch.setattr(web_mod, "store", test_store)
    monkeypatch.setattr(web_mod.action_mgr, "store", test_store)
    monkeypatch.setattr(web_mod.briefing_engine, "store", test_store)
    with TestClient(web_mod.app) as c:
        yield c


def test_skills_endpoint_lists_all_seven_skills(client):
    res = client.get("/api/skills")
    assert res.status_code == 200
    cmds = {s["command"] for s in res.json()["skills"]}
    assert {"/automation", "/schedule", "/browser", "/swarm", "/goal", "/plugin", "/learn"}.issubset(cmds)


def test_project_propose_and_confirm_gate(client):
    # 1. Propose weekday slots deterministically
    prop = client.post(
        "/api/projects/propose-schedule",
        json={
            "title": "FastAPI Mastery",
            "category": "learning",
            "goal": "Build 2 async services",
            "total_hours": 2.0,
            "session_minutes": 60,
            "priority": "high",
        },
    )
    assert prop.status_code == 200
    slots = prop.json()["proposed_slots"]
    assert len(slots) >= 2

    # 2. Unconfirmed create MUST NOT persist
    unconfirmed = client.post(
        "/api/projects",
        json={
            "title": "FastAPI Mastery",
            "category": "learning",
            "confirmed": False,
        },
    )
    assert unconfirmed.status_code == 200
    assert unconfirmed.json()["requires_confirmation"] is True
    assert client.get("/api/projects").json()["projects"] == []

    # 3. Confirmed create persists project + scheduled tasks
    confirmed = client.post(
        "/api/projects",
        json={
            "title": "FastAPI Mastery",
            "category": "learning",
            "goal": "Build 2 async services",
            "total_hours": 2.0,
            "session_minutes": 60,
            "priority": "high",
            "confirmed": True,
            "selected_slots": slots[:2],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert len(confirmed.json()["scheduled_task_ids"]) == 2
    assert len(client.get("/api/projects").json()["projects"]) == 1
