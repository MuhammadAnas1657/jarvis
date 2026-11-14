"""Integration tests for Jarvis FastAPI Web Dashboard, Mobile Installer, Voice Capture, and Accountability Endpoints."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import jarvis.key_pool as key_pool_module
import jarvis.web as web_module
from jarvis.actions import ActionManager
from jarvis.briefing import DailyBriefing
from jarvis.store import ReminderStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a FastAPI TestClient backed by an isolated temporary database."""
    db_file = tmp_path / "test_web_jarvis.db"
    isolated_store = ReminderStore(db_path=str(db_file))
    monkeypatch.setattr(web_module, "store", isolated_store)
    monkeypatch.setattr(web_module, "action_mgr", ActionManager(store=isolated_store))
    monkeypatch.setattr(web_module, "briefing_engine", DailyBriefing(store=isolated_store))
    return TestClient(web_module.app)


def test_dashboard_and_pwa_static_assets(client):
    # 1. Dashboard HTML
    res_index = client.get("/")
    assert res_index.status_code == 200
    html = res_index.text
    assert "JARVIS" in html
    assert "JARVIS" in html
    assert "openMobileInstallModal" in html
    assert "Record Voice (Urdu/English)" in html
    assert "Anas, wake up!" in html
    assert "/static/app.js" in html
    assert "/static/icon.svg" in html

    # 2. PWA Manifest, Icon & Service Worker
    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200
    manifest_data = res_manifest.json()
    assert manifest_data["short_name"] == "JARVIS"
    assert any("/static/icon.svg" in icon.get("src", "") for icon in manifest_data.get("icons", []))

    res_icon_static = client.get("/static/icon.svg")
    assert res_icon_static.status_code == 200
    assert "<svg" in res_icon_static.text

    res_icon_root = client.get("/icon.svg")
    assert res_icon_root.status_code == 200
    assert "<svg" in res_icon_root.text

    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200
    assert "CACHE_NAME" in res_sw.text

    # 3. Mounted /static/app.js
    res_app_js = client.get("/static/app.js")
    assert res_app_js.status_code == 200
    assert "speechSynthesis" in res_app_js.text
    assert "Anas, wake up!" in res_app_js.text
    assert "Online — Synced with Native PostgreSQL" in res_app_js.text
    assert "Offline Mode — Running from Local Device Cache" in res_app_js.text


def test_mobile_install_info_endpoint(client):
    res = client.get("/api/mobile/install-info")
    assert res.status_code == 200
    data = res.json()
    assert "install_url" in data
    assert "lan_ip" in data
    assert "port" in data
    assert data["apk_project_path"] == "mobile/"
    assert data["install_url"].startswith(f"http://{data['lan_ip']}:")
    assert "<svg" in data["qr_svg"]
    assert "</svg>" in data["qr_svg"]


def test_voice_capture_endpoint_audio_and_text_fallback(client, monkeypatch):
    # 1. Test JSON text fallback with Roman-Urdu time expression
    res_text = client.post(
        "/api/voice/capture",
        json={"text": "kal subah 9 baje client architecture review schedule kardo", "stage_task": True},
    )
    assert res_text.status_code == 200
    text_data = res_text.json()
    assert "kal subah 9 baje" in text_data["transcript"]
    parsed_task = text_data["parsed_task"]
    assert "client architecture review" in parsed_task["title"].lower()
    assert parsed_task["due_iso"] is not None
    assert "09:00" in parsed_task["due_iso"]
    assert parsed_task["estimated_minutes"] == 60
    assert text_data["staged_task_id"] is not None

    # 2. Test audio file upload via MediaRecorder multipart/form-data
    monkeypatch.setattr(
        key_pool_module,
        "groq_transcribe",
        lambda audio_path, **kwargs: "derh ghanta baad urgent production deployment check",
    )
    res_audio = client.post(
        "/api/voice/capture",
        files={"file": ("voice_capture.webm", b"RIFF-fake-webm-audio-bytes", "audio/webm")},
        data={"stage_task": "true"},
    )
    assert res_audio.status_code == 200
    audio_data = res_audio.json()
    assert audio_data["transcript"] == "derh ghanta baad urgent production deployment check"
    assert audio_data["parsed_task"]["due_iso"] is not None
    assert audio_data["parsed_task"]["estimated_minutes"] == 90
    assert audio_data["parsed_task"]["priority"] == "urgent"


def test_delete_weekly_routine_and_alarm_endpoints(client):
    # 1. Create and delete a weekly routine block
    res_routine = client.post(
        "/api/routine/weekly",
        json={
            "day_of_week": "Tuesday",
            "title": "Temporary Routine Block",
            "start_time": "14:00",
            "end_time": "15:00",
        },
    )
    assert res_routine.status_code == 200
    block_id = res_routine.json()["id"]
    assert block_id is not None

    res_del_routine = client.delete(f"/api/routine/weekly/{block_id}")
    assert res_del_routine.status_code == 200
    assert res_del_routine.json()["success"] is True

    remaining_blocks = client.get("/api/routine/weekly").json()["weekly_routine"]
    assert all(b["id"] != block_id for b in remaining_blocks)

    # 2. Create and delete an alarm
    res_alarm = client.post(
        "/api/alarms",
        json={"alarm_time": "05:45", "label": "Anas, wake up!", "first_task_prompt": "Fajr Prayer"},
    )
    assert res_alarm.status_code == 200
    alarm_id = res_alarm.json()["id"]

    res_del_alarm = client.delete(f"/api/alarms/{alarm_id}")
    assert res_del_alarm.status_code == 200
    assert res_del_alarm.json()["success"] is True

    remaining_alarms = client.get("/api/alarms").json()["alarms"]
    assert all(a["id"] != alarm_id for a in remaining_alarms)


def test_no_container_references_in_web_and_ui_files():
    project_root = Path(__file__).resolve().parent.parent
    forbidden_word = "doc" + "ker"
    checked_files = [
        project_root / "jarvis" / "web.py",
        project_root / "templates" / "index.html",
        project_root / "static" / "app.js",
        project_root / "static" / "sw.js",
        project_root / "static" / "manifest.json",
        project_root / "static" / "icon.svg",
    ]
    for file_path in checked_files:
        assert file_path.exists(), f"Expected file {file_path} to exist"
        content = file_path.read_text(encoding="utf-8").lower()
        assert forbidden_word not in content, f"Found forbidden reference in {file_path.name}"


def test_existing_reminders_tasks_and_actions_endpoints(client):
    # Create reminder via /reminders (starts in pending_review per AGENTS.md)
    res_create = client.post(
        "/reminders",
        json={"title": "Call supplier", "raw_due_text": "kal subah 10 baje", "priority": "high"},
    )
    assert res_create.status_code == 200
    rem_id = res_create.json()["id"]
    assert res_create.json()["status"] == "pending_review"

    # List via /reminders
    res_list = client.get("/reminders")
    assert res_list.status_code == 200
    assert any(r["id"] == rem_id for r in res_list.json())

    # Confirm via /reminders/{id}/confirm
    res_conf = client.post(f"/reminders/{rem_id}/confirm")
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"

    # Delete via /reminders/{id}/delete
    res_del = client.post(f"/reminders/{rem_id}/delete")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"

    # Propose action without confirmation -> must require confirmation
    res_propose = client.post(
        "/actions/propose",
        json={"action": "open_app", "params": {"app": "calc"}, "confirmed": False},
    )
    assert res_propose.status_code == 200
    assert res_propose.json()["status"] == "confirmation_required"


def test_weekly_routine_and_advisory_hard_audit_workflow(client):
    # 1. Add fixed weekly routine blocks (e.g., 14 hours locked out of 16 waking hours -> 120m true free)
    res_r1 = client.post(
        "/api/routine/weekly",
        json={
            "day_of_week": "Daily",
            "title": "Core Deep Work & Client Calls",
            "start_time": "06:00",
            "end_time": "18:00",
            "category": "work",
            "is_locked": True,
        },
    )
    assert res_r1.status_code == 200

    res_r2 = client.post(
        "/api/routine/weekly",
        json={
            "day_of_week": "Daily",
            "title": "Gym & Evening Family Block",
            "start_time": "18:00",
            "end_time": "20:00",
            "category": "health",
            "is_locked": True,
        },
    )
    assert res_r2.status_code == 200

    # 2. Fetch weekly routine & check true free minutes (06:00..22:00 = 960m, locked = 840m, free = 120m)
    res_get = client.get("/api/routine/weekly")
    assert res_get.status_code == 200
    r_data = res_get.json()
    assert len(r_data["weekly_routine"]) == 2
    assert r_data["total_locked_minutes"] == 840
    assert r_data["true_free_minutes"] == 120

    # 3. Run Advisory Hard Routine Audit with overload + time conflict
    proposed = [
        {"title": "Urgent API Patch", "estimated_minutes": 60, "preferred_time": "20:00", "priority": "urgent"},
        {"title": "Overlapping Call", "estimated_minutes": 45, "preferred_time": "10:00", "priority": "high"},
        {"title": "Backlog Documentation", "estimated_minutes": 90, "preferred_time": None, "priority": "low"},
    ]
    res_audit = client.post("/api/routine/audit", json={"tasks": proposed})
    assert res_audit.status_code == 200
    report = res_audit.json()

    assert report["advisory_mode"] is True
    assert report["is_overloaded"] is True
    assert len(report["warnings"]) >= 1
    assert len(report["core_schedule"]) >= 1
    assert len(report["overflow_tasks"]) >= 1

    # 4. Commit without user confirmation -> must stage in pending_review and require confirmation
    res_unconfirmed = client.post(
        "/api/routine/commit",
        json={
            "mode": "core_only",
            "core_schedule": report["core_schedule"],
            "overflow_tasks": report["overflow_tasks"],
            "user_confirmed": False,
        },
    )
    assert res_unconfirmed.status_code == 200
    assert res_unconfirmed.json()["status"] == "confirmation_required"
    assert res_unconfirmed.json()["requires_confirmation"] is True

    # 5. Commit with mode="core_only" and user_confirmed=True
    res_commit_core = client.post(
        "/api/routine/commit",
        json={
            "mode": "core_only",
            "core_schedule": report["core_schedule"],
            "overflow_tasks": report["overflow_tasks"],
            "user_confirmed": True,
        },
    )
    assert res_commit_core.status_code == 200
    core_json = res_commit_core.json()
    assert core_json["status"] == "confirmed"
    assert core_json["committed_count"] == len(report["core_schedule"])

    # 6. Commit with mode="force_all" and user_confirmed=True
    res_commit_force = client.post(
        "/api/routine/commit",
        json={
            "mode": "force_all",
            "core_schedule": report["core_schedule"],
            "overflow_tasks": report["overflow_tasks"],
            "user_confirmed": True,
        },
    )
    assert res_commit_force.status_code == 200
    force_json = res_commit_force.json()
    assert force_json["status"] == "confirmed"
    assert force_json["committed_count"] == len(report["core_schedule"]) + len(report["overflow_tasks"])


def test_strict_proof_of_wake_alarm_workflow(client):
    # 1. Create alarm
    res_create = client.post(
        "/api/alarms",
        json={
            "alarm_time": "06:15",
            "label": "Anas, wake up!",
            "first_task_prompt": "Fajr & Architecture Sprint",
        },
    )
    assert res_create.status_code == 200
    alarm_id = res_create.json()["id"]
    assert "Anas, wake up!" in res_create.json()["wake_loop_phrase"]

    # 2. Attempting to verify wake without phrase or task check must fail (400)
    res_fail = client.post(
        f"/api/alarms/{alarm_id}/verify-wake",
        json={"verification_phrase": "", "first_task_confirmed": False},
    )
    assert res_fail.status_code == 400

    # 3. Verify wake with spoken/typed verification phrase -> transitions to acknowledged
    res_ok = client.post(
        f"/api/alarms/{alarm_id}/verify-wake",
        json={"verification_phrase": "I am awake and starting Fajr & Architecture Sprint", "first_task_confirmed": True},
    )
    assert res_ok.status_code == 200
    ok_data = res_ok.json()
    assert ok_data["verified"] is True
    assert ok_data["state"] == "acknowledged"
    assert ok_data["alarm"]["state"] == "acknowledged"


def test_nightly_audit_and_course_learning_quiz(client):
    # Create a course and log yesterday's reflection first
    res_course = client.post(
        "/api/courses",
        json={"title": "Distributed Systems & PostgreSQL", "instructor": "Anas Academy", "total_modules": 12},
    )
    assert res_course.status_code == 200
    course_id = res_course.json()["id"]

    # Log initial lesson (acts as yesterday's lesson for the next nightly audit)
    res_day1 = client.post(
        "/api/audit/nightly",
        json={
            "course_id": course_id,
            "topic": "Write-Ahead Logging (WAL) and MVCC in PostgreSQL",
            "raw_reflection": "Today I learned how PostgreSQL uses Write-Ahead Logging for crash recovery and MVCC snapshots for non-blocking concurrent reads.",
            "tasks": [
                {"title": "Setup Native PostgreSQL 16", "completed": True},
                {"title": "Write store unit tests", "completed": True},
            ],
        },
    )
    assert res_day1.status_code == 200
    day1_data = res_day1.json()
    assert day1_data["discipline"]["score_pct"] == 100.0
    assert "Write-Ahead Logging" in day1_data["structured_notes"]
    assert len(day1_data["recall_quiz"]) == 2

    # Log second lesson and verify the 2-question recall quiz tests yesterday's WAL/MVCC lesson
    res_day2 = client.post(
        "/api/audit/nightly",
        json={
            "course_id": course_id,
            "topic": "Connection Pooling with PgBouncer",
            "raw_reflection": "Learned transaction pooling vs session pooling in PgBouncer.",
            "tasks": [
                {"title": "Task A", "completed": True},
                {"title": "Task B", "completed": False},
            ],
        },
    )
    assert res_day2.status_code == 200
    day2_data = res_day2.json()
    assert day2_data["discipline"]["score_pct"] == 50.0
    assert len(day2_data["recall_quiz"]) == 2
    assert "Write-Ahead Logging" in day2_data["recall_quiz"][0]["topic"]


def test_business_deliverables_and_small_task_buddy(client):
    # 1. Add two deliverables with different urgency profiles
    r1 = client.post(
        "/api/business/deliverables",
        json={
            "client_name": "Alpha Logistics",
            "title": "Low Urgency Monthly Report",
            "deadline": "2026-12-25T18:00:00+05:00",
            "estimated_hours": 2.0,
            "impact_score": 4,
        },
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/business/deliverables",
        json={
            "client_name": "Nexus Fintech",
            "title": "Critical Production API Launch",
            "deadline": "2026-11-13T16:00:00+05:00",
            "estimated_hours": 6.0,
            "impact_score": 10,
        },
    )
    assert r2.status_code == 200
    ranked = r2.json()["deliverables"]
    assert len(ranked) == 2
    assert ranked[0]["title"] == "Critical Production API Launch"
    assert ranked[0]["urgency_score"] >= ranked[1]["urgency_score"]

    # 2. Run Autonomous Small-Task Buddy across modes ('draft', 'breakdown', 'sop', 'research')
    for mode in ("draft", "breakdown", "sop", "research"):
        res_st = client.post(
            "/api/business/small-task",
            json={"prompt": f"Prepare {mode} for Native PostgreSQL server deployment", "task_type": mode},
        )
        assert res_st.status_code == 200
        st_data = res_st.json()
        assert st_data["task_type"] == mode
        assert st_data["status"] == "pending_review"
        assert st_data["requires_confirmation"] is True
        assert len(st_data["result_content"]) > 20

    # 3. Confirm a staged small task
    last_id = st_data["id"]
    res_conf = client.post(f"/api/business/small-task/{last_id}/confirm")
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"


def test_offline_pwa_sync_payload_completeness(client):
    # Populate data across categories
    client.post("/reminders", json={"title": "Offline cached reminder", "confirmed": True})
    client.post(
        "/api/routine/weekly",
        json={"day_of_week": "Monday", "title": "Deep Work", "start_time": "09:00", "end_time": "11:00"},
    )
    client.post("/api/alarms", json={"alarm_time": "06:00", "label": "Anas, wake up!"})
    client.post("/api/courses", json={"title": "FastAPI Mastery"})
    client.post(
        "/api/business/deliverables",
        json={"client_name": "Client X", "title": "Spec Doc", "deadline": "2026-11-20", "estimated_hours": 3, "impact_score": 8},
    )
    client.post("/api/business/small-task", json={"prompt": "Write onboarding SOP", "task_type": "sop"})

    res_sync = client.get("/api/sync")
    assert res_sync.status_code == 200
    payload = res_sync.json()

    for key in (
        "reminders",
        "weekly_routine",
        "alarms",
        "courses",
        "business_deliverables",
        "small_tasks",
    ):
        assert key in payload
        assert isinstance(payload[key], list)
        assert len(payload[key]) >= 1


def test_chat_endpoint_basic_and_groq_completion(client, monkeypatch):
    recorded_calls = []

    def mock_groq_chat_completion(messages, model="llama-3.3-70b-versatile", **kwargs):
        recorded_calls.append({"messages": messages, "model": model, "kwargs": kwargs})
        return "Hello Anas! Today your top priority should be completing the client API launch."

    monkeypatch.setattr(key_pool_module, "groq_chat_completion", mock_groq_chat_completion)

    res = client.post(
        "/api/chat",
        json={"message": "What should I prioritize today?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "timestamp" in data
    assert "Hello Anas!" in data["reply"]

    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call["model"] in ("qwen/qwen3.8-27b", "llama-3.3-70b-versatile")
    system_msg = call["messages"][0]["content"]
    assert "intelligent personal buddy" in system_msg
    assert "time manager" in system_msg
    assert "business advisor" in system_msg
    assert "Urdu" in system_msg
    assert call["messages"][-1]["content"] == "What should I prioritize today?"
    assert call["messages"][-1]["role"] == "user"


def test_chat_endpoint_with_history_and_urdu(client, monkeypatch):
    captured_messages = []

    def mock_chat(messages, **kwargs):
        captured_messages.extend(messages)
        return "Walaikum Assalam Anas! Aaj ke 2 aham business deliverables list mein hain."

    monkeypatch.setattr(key_pool_module, "groq_chat_completion", mock_chat)

    res = client.post(
        "/api/chat",
        json={
            "message": "aaj mere kitne deliverables bache hain?",
            "history": [
                {"role": "user", "content": "Salam Jarvis"},
                {"role": "assistant", "content": "Walaikum Assalam Anas, main aapki kya madad karoon?"},
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["reply"] == "Walaikum Assalam Anas! Aaj ke 2 aham business deliverables list mein hain."
    assert "timestamp" in data

    # Check conversation history structure
    assert captured_messages[0]["role"] == "system"
    assert captured_messages[1] == {"role": "user", "content": "Salam Jarvis"}
    assert captured_messages[2] == {
        "role": "assistant",
        "content": "Walaikum Assalam Anas, main aapki kya madad karoon?",
    }
    assert captured_messages[3] == {"role": "user", "content": "aaj mere kitne deliverables bache hain?"}


def test_chat_endpoint_offline_fallback(client, monkeypatch):
    # Simulate network failure or offline outage
    def mock_fail(messages, **kwargs):
        raise ConnectionError("Network unreachable / offline")

    monkeypatch.setattr(key_pool_module, "groq_chat_completion", mock_fail)

    res = client.post(
        "/api/chat",
        json={"message": "Can you check my tasks offline?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "timestamp" in data
    assert "Offline" in data["reply"] or "Understood" in data["reply"]
    assert "Can you check my tasks offline?" in data["reply"]

