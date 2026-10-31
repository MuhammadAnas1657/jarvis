"""End-to-end integration tests for Jarvis pipeline, security boundaries, and FastAPI routes."""

import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from jarvis.actions import ActionManager
from jarvis.briefing import DailyBriefing
from jarvis.extract import TaskExtractor
from jarvis.store import TaskStore
from jarvis.timeparse import parse_time_with_analysis
from jarvis.tts import TextToSpeech
from jarvis.web import app, store as web_store


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_pipeline.db"
    return TaskStore(db_path=str(db_file))


def test_e2e_extraction_and_staging(temp_store):
    extractor = TaskExtractor()
    transcript = "buddy kal subah 9 baje client ke sath meeting schedule kardo"

    tasks = extractor.extract_tasks(transcript)
    assert len(tasks) > 0
    task_data = tasks[0]

    assert "meeting" in task_data["title"].lower() or "client" in task_data["title"].lower()
    assert task_data["due_datetime"] is not None
    assert task_data["due_datetime"].hour == 9
    assert task_data["recommendation"] is not None

    task_id = temp_store.add_task(
        title=task_data["title"],
        description=task_data["description"],
        original_transcript=transcript,
        raw_due_text=task_data["raw_due_text"],
        due_datetime=task_data["due_datetime"],
        priority=task_data["priority"],
        status="pending_review",
        clarification_question=task_data.get("clarification_question"),
        recommendation=task_data.get("recommendation")
    )

    pending = temp_store.get_pending_tasks()
    assert any(t["id"] == task_id for t in pending)

    # User confirms the task
    assert temp_store.update_task_status(task_id, "confirmed") is True
    confirmed_task = temp_store.get_task(task_id)
    assert confirmed_task["status"] == "confirmed"


def test_clarification_analysis():
    # User specifies "kal" but no clock time -> Should flag a clarification
    res_dt, analysis = parse_time_with_analysis("kal meeting with client")
    assert res_dt is not None
    assert analysis["clarification"] is not None
    assert "09:00 AM" in analysis["clarification"]


def test_briefing_generation(temp_store):
    from datetime import datetime
    from jarvis.timeparse import DEFAULT_TIMEZONE
    now = datetime.now(DEFAULT_TIMEZONE)

    temp_store.add_task(
        title="Urgent review",
        due_datetime=now,
        status="confirmed"
    )

    engine = DailyBriefing(store=temp_store)
    briefing = engine.generate_briefing()

    assert briefing["id"] > 0
    assert "Urgent review" in briefing["text"]
    assert briefing["scheduled_count"] >= 1


def test_action_whitelist_guardrails(temp_store):
    mgr = ActionManager(store=temp_store)

    # 1. Unconfirmed attempt must return confirmation_required
    res1 = mgr.execute_action("open_app", {"app": "calc"}, user_confirmed=False)
    assert res1["status"] == "confirmation_required"

    # 2. Unwhitelisted application must be rejected
    res2 = mgr.execute_action("open_app", {"app": "malicious_script.exe"}, user_confirmed=True)
    assert res2["status"] == "error"
    assert "not in the whitelist" in res2["message"]

    # 3. Path boundary restriction: outside folder must be rejected
    res3 = mgr.execute_action("open_folder", {"path": "C:\\Windows\\System32"}, user_confirmed=True)
    assert res3["status"] == "error"
    assert "outside allowed directories" in res3["message"]


def test_tts_safe_from_injection(tmp_path):
    tts = TextToSpeech()
    target_wav = tmp_path / "safe_test.wav"
    # Malicious injection text with shell expansions and quotes
    malicious_text = 'Hello $(calc.exe) "; Stop-Process -Name svchost; "'
    res = tts.speak(malicious_text, output_wav=str(target_wav))
    # Must not throw, and safely handles via stdin
    if res:
        assert Path(res).exists()


def test_web_api_routes():
    client = TestClient(app)

    # 1. Check status
    r_status = client.get("/api/status")
    assert r_status.status_code == 200
    assert r_status.json()["status"] == "online"

    # 2. Quick add task via API
    r_add = client.post("/api/tasks/quick-add", json={"text": "kal shaam 6:30 baje team dinner"})
    assert r_add.status_code == 200
    created_ids = r_add.json()["ids"]
    assert len(created_ids) > 0
    task_id = created_ids[0]

    # 3. Confirm task
    r_conf = client.post(f"/api/tasks/{task_id}/confirm")
    assert r_conf.status_code == 200
    assert r_conf.json()["status"] == "confirmed"

    # 4. Check tasks list
    r_list = client.get("/api/tasks")
    assert r_list.status_code == 200
    all_tasks = r_list.json()
    assert any(t["id"] == task_id for t in all_tasks)
