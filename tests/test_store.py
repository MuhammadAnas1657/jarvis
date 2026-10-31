"""Unit tests for Jarvis TaskStore."""

from datetime import datetime, timedelta
import tempfile
import pytest
from jarvis.store import TaskStore
from jarvis.timeparse import DEFAULT_TIMEZONE


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_jarvis.db"
    return TaskStore(db_path=str(db_file))


def test_add_and_get_task(temp_store):
    due = datetime.now(DEFAULT_TIMEZONE) + timedelta(days=1)
    task_id = temp_store.add_task(
        title="Submit Atarion Budget",
        description="Verify calculations",
        original_transcript="kal submit atarion budget",
        raw_due_text="kal",
        due_datetime=due,
        priority="high"
    )

    task = temp_store.get_task(task_id)
    assert task is not None
    assert task["id"] == task_id
    assert task["title"] == "Submit Atarion Budget"
    assert task["priority"] == "high"
    assert task["status"] == "pending_review"


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


def test_action_log(temp_store):
    log_id = temp_store.log_action("open_app", {"app": "notepad"}, "executed", "PID 1234")
    assert log_id > 0

