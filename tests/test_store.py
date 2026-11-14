"""Unit tests for Jarvis ReminderStore/TaskStore (PostgreSQL + local SQL adapter) and 46-key GroqKeyPool."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from jarvis.config import DEFAULT_GROQ_XLSX_PATH, load_config
from jarvis.key_pool import (
    GroqKeyPool,
    groq_chat_completion,
    groq_transcribe,
    load_keys_from_xlsx,
)
from jarvis.store import POSTGRES_DDL_STATEMENTS, ReminderStore, TaskStore
from jarvis.timeparse import DEFAULT_TIMEZONE


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_jarvis.db"
    return ReminderStore(db_path=str(db_file))


def test_add_and_get_task_and_reminder_compat(temp_store):
    due = datetime.now(DEFAULT_TIMEZONE) + timedelta(days=1)
    task_id = temp_store.add_task(
        title="Submit Atarion Budget",
        description="Verify calculations",
        original_transcript="kal submit atarion budget",
        raw_due_text="kal",
        due_datetime=due,
        priority="high",
    )

    task = temp_store.get_task(task_id)
    assert task is not None
    assert task["id"] == task_id
    assert task["title"] == "Submit Atarion Budget"
    assert task["priority"] == "high"
    assert task["status"] == "pending_review"
    assert task["confirmed"] is False

    # Test ReminderStore aliases
    rem_id = temp_store.add_reminder(
        title="Call Vendor",
        due_datetime=due,
        priority="urgent",
    )
    rem = temp_store.get_reminder(rem_id)
    assert rem is not None
    assert rem["title"] == "Call Vendor"
    assert temp_store.confirm_reminder(rem_id) is True

    confirmed_rem = temp_store.get_reminder(rem_id)
    assert confirmed_rem["status"] == "confirmed"
    assert confirmed_rem["confirmed"] is True

    all_rems = temp_store.list_reminders()
    assert len(all_rems) >= 2

    assert temp_store.update_status(rem_id, "completed") is True
    assert temp_store.get_reminder(rem_id)["status"] == "completed"

    assert temp_store.delete_reminder(rem_id) is True
    assert temp_store.get_reminder(rem_id) is None


def test_update_status(temp_store):
    task_id = temp_store.add_task(title="Review PR")
    assert temp_store.update_task_status(task_id, "confirmed") is True

    task = temp_store.get_task(task_id)
    assert task["status"] == "confirmed"


def test_list_pending(temp_store):
    temp_store.add_task(title="Task 1", status="pending_review")
    temp_store.add_task(title="Task 2", status="confirmed")
    temp_store.add_task(title="Task 3", status="pending_review")

    pending = temp_store.get_pending_tasks()
    assert len(pending) == 2


def test_action_log_and_get_action_logs(temp_store):
    log_id = temp_store.log_action("open_app", {"app": "notepad"}, "executed", "PID 1234")
    assert log_id > 0

    logs = temp_store.get_action_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["action_name"] == "open_app"
    assert logs[0]["parameters_dict"]["app"] == "notepad"
    assert logs[0]["status"] == "executed"


def test_weekly_routine_crud(temp_store):
    block_id = temp_store.add_routine_block(
        day_of_week="Monday",
        title="Deep Work Block",
        start_time="09:00",
        end_time="12:00",
        category="work",
        is_locked=True,
    )
    assert block_id > 0

    daily_id = temp_store.add_routine_block(
        day_of_week="daily",
        title="Morning Exercise",
        start_time="07:00",
        end_time="08:00",
        category="health",
        is_locked=True,
    )
    assert daily_id > 0

    monday_blocks = temp_store.list_weekly_routine(day_of_week="Monday")
    assert len(monday_blocks) == 2
    assert monday_blocks[0]["title"] == "Morning Exercise"
    assert monday_blocks[1]["title"] == "Deep Work Block"
    assert monday_blocks[1]["is_locked"] is True

    assert temp_store.update_routine_block(block_id, end_time="12:30", is_locked=False) is True
    updated = temp_store.get_routine_block(block_id)
    assert updated["end_time"] == "12:30"
    assert updated["is_locked"] is False

    assert temp_store.delete_weekly_routine_block(block_id) is True
    assert temp_store.get_routine_block(block_id) is None
    assert temp_store.delete_routine_block(daily_id) is True
    assert temp_store.get_routine_block(daily_id) is None


def test_alarms_crud_and_states(temp_store):
    alarm_id = temp_store.add_alarm(
        alarm_time="06:30",
        label="Anas, wake up!",
        first_task_prompt="Review today's Core Routine and complete Fajr + 15m planning",
        state="scheduled",
    )
    assert alarm_id > 0

    alarm = temp_store.get_alarm(alarm_id)
    assert alarm["state"] == "scheduled"
    assert alarm["label"] == "Anas, wake up!"

    for valid_state in ["ringing", "acknowledged", "missed", "scheduled"]:
        assert temp_store.update_alarm_state(alarm_id, valid_state) is True
        assert temp_store.get_alarm(alarm_id)["state"] == valid_state

    with pytest.raises(ValueError):
        temp_store.update_alarm_state(alarm_id, "invalid_state")

    assert temp_store.acknowledge_alarm(alarm_id) is True
    assert temp_store.get_alarm(alarm_id)["state"] == "acknowledged"

    assert temp_store.delete_alarm(alarm_id) is True
    assert temp_store.get_alarm(alarm_id) is None


def test_courses_and_course_logs_crud(temp_store):
    course_id = temp_store.add_course(
        title="Distributed Systems Engineering",
        instructor="Dr. Martin Kleppmann",
        total_modules=12,
        completed_modules=3,
        status="active",
    )
    assert course_id > 0

    course = temp_store.get_course(course_id)
    assert course["title"] == "Distributed Systems Engineering"
    assert course["completed_modules"] == 3

    assert temp_store.update_course(course_id, completed_modules=4) is True
    assert temp_store.get_course(course_id)["completed_modules"] == 4

    quiz_sample = [
        {"question": "What is linearizability?", "expected_answer": "Strongest single-object consistency model."},
        {"question": "How does Raft elect a leader?", "expected_answer": "Randomized election timeouts and majority vote."},
    ]
    log_id = temp_store.add_course_log(
        course_id=course_id,
        log_date="2026-11-12",
        topic="Consensus & Raft",
        raw_reflection="Learned how Raft handles split votes using randomized timeouts.",
        structured_notes="- Raft uses term numbers\n- Randomized timeouts prevent split votes",
        quiz_json=quiz_sample,
    )
    assert log_id > 0

    log_entry = temp_store.get_course_log(log_id)
    assert log_entry["topic"] == "Consensus & Raft"
    assert len(log_entry["quiz"]) == 2
    assert log_entry["quiz"][0]["question"] == "What is linearizability?"

    latest = temp_store.get_latest_course_log(course_id=course_id)
    assert latest is not None
    assert latest["id"] == log_id

    assert temp_store.delete_course_log(log_id) is True
    assert temp_store.delete_course(course_id) is True


def test_business_deliverables_and_small_tasks_crud(temp_store):
    deliv_id = temp_store.add_business_deliverable(
        client_name="Atarion Solutions",
        title="Q4 Cloud Architecture Proposal",
        deadline="2026-11-15T18:00:00+05:00",
        estimated_hours=4.5,
        impact_score=9,
        status="pending",
    )
    assert deliv_id > 0

    delivs = temp_store.list_business_deliverables()
    assert len(delivs) == 1
    assert delivs[0]["client_name"] == "Atarion Solutions"
    assert delivs[0]["impact_score"] == 9

    assert temp_store.update_business_deliverable(deliv_id, status="in_progress", impact_score=10) is True
    assert temp_store.get_business_deliverable(deliv_id)["status"] == "in_progress"

    st_id = temp_store.add_small_task(
        prompt="Draft SOP for weekly VPS PostgreSQL backups",
        task_type="sop",
        result_content="### SOP: PostgreSQL Backup\n1. Run pg_dump...",
        status="pending_review",
    )
    assert st_id > 0

    st = temp_store.get_small_task(st_id)
    assert st["task_type"] == "sop"
    assert st["status"] == "pending_review"

    assert temp_store.confirm_small_task(st_id) is True
    assert temp_store.get_small_task(st_id)["status"] == "confirmed"

    sync_data = temp_store.get_sync_payload()
    assert "reminders" in sync_data
    assert "weekly_routine" in sync_data
    assert "alarms" in sync_data
    assert "courses" in sync_data
    assert "business_deliverables" in sync_data
    assert "small_tasks" in sync_data

    assert temp_store.delete_business_deliverable(deliv_id) is True
    assert temp_store.delete_small_task(st_id) is True


def test_postgres_adapter_execution_when_connected():
    """Verify PostgreSQL DDL and %s / RETURNING id execution path when DATABASE_URL connects."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (42,)
    mock_cursor.rowcount = 1
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("jarvis.store.psycopg2") as mock_pg:
        mock_pg.connect.return_value = mock_conn
        store = ReminderStore(database_url="postgresql://jarvis:jarvis@localhost:5432/jarvis")
        assert store.backend == "postgres"

        new_id = store.add_alarm("06:00", "Anas, wake up!", "First task")
        assert new_id == 42

        executed_sqls = [call.args[0] for call in mock_cursor.execute.call_args_list]
        assert any("CREATE TABLE IF NOT EXISTS weekly_routine" in sql for sql in executed_sqls)
        assert any("RETURNING id" in sql and "%s" in sql for sql in executed_sqls)


def test_setup_postgres_script_creates_db_and_tables():
    """Verify setup_postgres.py connects to postgres maintenance DB, creates jarvis DB, and initializes tables."""
    import setup_postgres

    maint_url, target_db = setup_postgres.build_maintenance_url(
        "postgresql://postgres:postgres@localhost:5432/jarvis"
    )
    assert maint_url == "postgresql://postgres:postgres@localhost:5432/postgres"
    assert target_db == "jarvis"

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with patch("setup_postgres.psycopg2") as mock_pg_setup, patch("jarvis.store.psycopg2") as mock_pg_store:
        mock_pg_setup.connect.return_value = mock_conn
        mock_pg_store.connect.return_value = mock_conn

        result = setup_postgres.ensure_postgres_database(
            "postgresql://postgres:postgres@localhost:5432/jarvis"
        )
        assert result["ok"] is True
        assert result["backend"] == "postgres"
        assert result["database"] == "jarvis"
        assert "weekly_routine" in result["tables"]
        assert "alarms" in result["tables"]


def test_key_pool_loads_46_keys_and_rotates(monkeypatch):
    if not DEFAULT_GROQ_XLSX_PATH:
        pytest.skip("GROQ_KEYS_XLSX_PATH not configured")
    xlsx_file = Path(DEFAULT_GROQ_XLSX_PATH)
    assert xlsx_file.exists(), f"Expected Groq keys Excel file at {xlsx_file}"

    keys = load_keys_from_xlsx(xlsx_file)
    assert len(keys) == 46
    assert all(k.startswith("gsk_") for k in keys)
    assert len(set(keys)) == 46

    pool = GroqKeyPool(xlsx_path=xlsx_file, cooldown_seconds=30.0)
    assert len(pool.keys) == 46

    # Verify round-robin rotation across all 46 keys
    visited = [pool.get_next_key() for _ in range(46)]
    assert visited == pool.keys
    assert pool.get_next_key() == pool.keys[0]

    # Verify rate-limit cooldown skips the rate-limited key
    first_key = pool.get_next_key()
    pool.mark_rate_limited(first_key, cooldown_seconds=60.0)
    assert pool.is_rate_limited(first_key) is True
    assert pool.available_key_count() == 45

    next_cycle = [pool.get_next_key() for _ in range(45)]
    assert first_key not in next_cycle

    # Verify HTTP 429 triggers automatic rotation to the next key
    call_count = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        call_count["n"] += 1
        resp = MagicMock()
        if call_count["n"] == 1:
            resp.status_code = 429
            return resp
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Rotated key success!"}}]
        }
        return resp

    monkeypatch.delenv("GROQ_OFFLINE_MODE", raising=False)
    with patch("jarvis.key_pool.requests.post", side_effect=fake_post):
        res = pool.chat_completion("Test prompt")
        assert str(res) == "Rotated key success!"
        assert res.get("content") == "Rotated key success!"
        assert res.get("offline_fallback") is False
        assert call_count["n"] == 2

    # Verify deterministic offline fallback when internet is unavailable
    monkeypatch.setenv("GROQ_OFFLINE_MODE", "1")
    offline_res = groq_chat_completion("Learned Raft leader election today", json_mode=True)
    assert offline_res.get("offline_fallback") is True
    assert "takeaways" in str(offline_res) or "summary" in str(offline_res)

    offline_stt = groq_transcribe("nonexistent_memo.wav")
    assert offline_stt.get("offline_fallback") is True
    assert "Offline voice memo" in str(offline_stt)
