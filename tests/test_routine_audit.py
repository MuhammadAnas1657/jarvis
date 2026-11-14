"""Unit tests for Advisory Hard Routine Audit, Nightly Course Audit, and Business Buddy."""

from datetime import datetime
import pytest

from jarvis.routine_audit import audit_daily_routine, RoutineAuditor
from jarvis.course_audit import (
    compute_daily_discipline_score,
    structure_course_reflection,
    generate_recall_quiz,
    run_nightly_audit,
)
from jarvis.business import (
    score_deliverable,
    rank_deliverables,
    execute_small_task,
)
from jarvis.timeparse import DEFAULT_TIMEZONE


def test_routine_audit_clean_fit_and_free_minutes():
    # Waking window 06:00 to 22:00 = 960 mins.
    # Locked routine: 09:00-17:00 Office (480 mins) + 18:00-19:00 Gym (60 mins) = 540 locked mins.
    # True free minutes = 960 - 540 = 420 mins.
    routine_blocks = [
        {"title": "Deep Work / Job", "start_time": "09:00", "end_time": "17:00", "is_locked": True},
        {"title": "Gym Session", "start_time": "18:00", "end_time": "19:00", "is_locked": True},
    ]
    proposed_tasks = [
        {"title": "Course Study Module 1", "estimated_minutes": 60, "preferred_time": "19:30", "priority": 1},
        {"title": "Client Invoice Review", "estimated_minutes": 40, "preferred_time": "07:00", "priority": 2},
    ]

    report = audit_daily_routine(routine_blocks, proposed_tasks)

    assert report["total_locked_minutes"] == 540
    assert report["true_free_minutes"] == 420
    # 100 raw mins * 1.15 = 115 mins
    assert report["requested_minutes"] == 115
    assert report["is_overloaded"] is False
    assert report["advisory_mode"] is True
    assert len(report["core_schedule"]) == 2
    assert len(report["overflow_tasks"]) == 0
    assert report["warnings"] == []


def test_routine_audit_overload_and_overlap_warnings():
    # Locked routine leaves only 120 mins free in a 600-min custom window
    routine_blocks = [
        {"title": "Client Sprint", "start_time": "08:00", "end_time": "16:00", "is_locked": True},
    ]
    proposed_tasks = [
        # Overlaps 08:00-16:00 locked block!
        {"title": "Call Supplier", "estimated_minutes": 45, "preferred_time": "10:00", "priority": 1},
        {"title": "Write Architecture Doc", "estimated_minutes": 60, "preferred_time": None, "priority": 2},
        # Exceeds remaining free time (120 mins free vs 165 * 1.15 = 190 requested)
        {"title": "Refactor Legacy Module", "estimated_minutes": 60, "preferred_time": None, "priority": 3},
    ]

    report = audit_daily_routine(
        routine_blocks=routine_blocks,
        proposed_tasks=proposed_tasks,
        day_window_minutes=600,  # 480 locked -> 120 true free minutes
        day_start="08:00",
        day_end="18:00",
    )

    assert report["total_locked_minutes"] == 480
    assert report["true_free_minutes"] == 120
    assert report["is_overloaded"] is True
    assert report["advisory_mode"] is True
    # Should have conflict warning for 10:00 and overload warning
    assert any("Conflict" in w for w in report["warnings"])
    assert any("Overload" in w for w in report["warnings"])
    assert len(report["core_schedule"]) >= 1
    assert len(report["overflow_tasks"]) >= 1


def test_course_audit_discipline_notes_and_recall_quiz():
    tasks = [
        {"title": "Morning LeetCode", "status": "completed"},
        {"title": "PostgreSQL Indexing Lecture", "status": "completed"},
        {"title": "Cold Outreach Drafts", "status": "missed"},
    ]
    score = compute_daily_discipline_score(tasks)
    assert score["total_tasks"] == 3
    assert score["completed_count"] == 2
    assert score["missed_count"] == 1
    assert score["score_pct"] == 66.7
    assert score["grade"] == "C"

    raw_reflection = (
        "Today I learned how PostgreSQL B-tree and GIN indexes speed up JSONB queries. "
        "I also practiced writing partial indexes for active reminders."
    )
    notes_md = structure_course_reflection(
        raw_reflection,
        topic="PostgreSQL Indexing",
        use_llm=False,
    )
    assert "### PostgreSQL Indexing" in notes_md
    assert "Key Takeaways" in notes_md
    assert "B-tree" in notes_md

    yesterday_log = {
        "topic": "Docker Compose Networking",
        "raw_reflection": (
            "Containers on a custom bridge network resolve each other by service name. "
            "Volumes persist PostgreSQL data across container restarts."
        ),
    }
    quiz = generate_recall_quiz(yesterday_log)
    assert isinstance(quiz, list)
    assert len(quiz) == 2
    assert "Docker Compose Networking" in quiz[0]["question"]
    assert quiz[0]["expected_answer"]
    assert quiz[1]["expected_answer"]

    combined = run_nightly_audit(tasks, raw_reflection, topic="PostgreSQL Indexing", yesterday_log=yesterday_log)
    assert "discipline" in combined
    assert "structured_notes" in combined
    assert len(combined["recall_quiz"]) == 2


def test_business_urgency_scorer_and_small_task_buddy():
    ref_now = datetime(2026, 11, 13, 12, 0, 0, tzinfo=DEFAULT_TIMEZONE)

    # Deliverable 1: Due in 4 hours, takes 3 hours, impact 9 -> Critical urgency
    urgent_score = score_deliverable(
        deadline_iso="2026-11-13T16:00:00+05:00",
        estimated_hours=3.0,
        impact_score=9,
        now=ref_now,
    )
    # Deliverable 2: Due in 10 days, takes 2 hours, impact 4 -> Low/Medium urgency
    relaxed_score = score_deliverable(
        deadline_iso="2026-11-23T18:00:00+05:00",
        estimated_hours=2.0,
        impact_score=4,
        now=ref_now,
    )

    assert urgent_score["urgency_score"] > relaxed_score["urgency_score"]
    assert urgent_score["tier"] == "critical"

    ranked = rank_deliverables(
        [
            {"title": "Low Priority Blog", "deadline": "2026-11-23T18:00:00+05:00", "estimated_hours": 2, "impact_score": 4},
            {"title": "Production Hotfix", "deadline": "2026-11-13T16:00:00+05:00", "estimated_hours": 3, "impact_score": 9},
        ],
        now=ref_now,
    )
    assert ranked[0]["title"] == "Production Hotfix"

    # Test all 4 small-task types with deterministic fallback
    for t_type in ("draft", "breakdown", "sop", "research"):
        res = execute_small_task(f"Onboarding workflow for {t_type}", task_type=t_type, use_llm=False)
        assert res["task_type"] == t_type
        assert res["status"] == "pending_review"
        assert res["requires_confirmation"] is True
        assert len(res["result_content"]) > 40
