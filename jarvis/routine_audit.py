"""Advisory Hard Routine Audit engine for Jarvis.

Compares proposed daily tasks against a user's Fixed Weekly Routine blocks,
deterministically computes locked vs. true free minutes, adds a 15% transition buffer,
flags time-slot overlaps and capacity overloads, and splits tasks into Core vs. Overflow
while preserving Advisory Mode (allowing either Core structure or Force-Schedule All Today).
"""

from datetime import datetime, time, timedelta
import math
from typing import Any, Dict, List, Optional, Tuple
from jarvis.timeparse import parse_relative_time, DEFAULT_TIMEZONE


DEFAULT_WAKING_MINUTES = 16 * 60  # 16 waking hours (960 mins), or configurable up to 1440
DEFAULT_DAY_START = "06:00"
DEFAULT_DAY_END = "22:00"
TRANSITION_BUFFER_RATIO = 0.15


def _parse_hhmm(val: Optional[str]) -> Optional[int]:
    """Convert 'HH:MM' or 'HH:MM:SS' or ISO datetime string or Urdu phrase into minutes from midnight."""
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    # Direct HH:MM or HH:MM:SS
    parts = s.split(":")
    if len(parts) in (2, 3) and parts[0].strip().isdigit() and parts[1].strip()[:2].isdigit():
        h = int(parts[0].strip())
        m = int(parts[1].strip()[:2])
        if 0 <= h <= 24 and 0 <= m < 60:
            return h * 60 + m

    # ISO datetime string
    try:
        dt = datetime.fromisoformat(s)
        return dt.hour * 60 + dt.minute
    except Exception:
        pass

    # Fallback to deterministic timeparse
    dt = parse_relative_time(s)
    if dt:
        return dt.hour * 60 + dt.minute

    return None


def _format_hhmm(minutes_from_midnight: int) -> str:
    """Format minutes from midnight as 'HH:MM'."""
    m = max(0, min(24 * 60, int(minutes_from_midnight)))
    if m == 24 * 60:
        return "23:59"
    return f"{m // 60:02d}:{m % 60:02d}"


def _priority_rank(priority: Any) -> int:
    """Normalize priority (int or str) so higher urgency sorts first (smaller rank number = higher priority)."""
    if isinstance(priority, int):
        return priority
    if isinstance(priority, str):
        p = priority.lower().strip()
        mapping = {
            "urgent": 1,
            "critical": 1,
            "high": 2,
            "normal": 3,
            "medium": 3,
            "low": 4,
        }
        if p.isdigit():
            return int(p)
        return mapping.get(p, 3)
    return 3


def _merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [sorted_iv[0]]
    for start, end in sorted_iv[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def audit_daily_routine(
    routine_blocks: List[Dict[str, Any]],
    proposed_tasks: List[Dict[str, Any]],
    day_window_minutes: Optional[int] = None,
    day_start: str = DEFAULT_DAY_START,
    day_end: str = DEFAULT_DAY_END,
    transition_buffer: float = TRANSITION_BUFFER_RATIO,
) -> Dict[str, Any]:
    """
    Perform a deterministic Advisory Hard Routine Audit.

    Parameters:
    - routine_blocks: list of dicts `{"title": str, "start_time": "HH:MM", "end_time": "HH:MM", "is_locked": True}`
    - proposed_tasks: list of dicts `{"title": str, "estimated_minutes": int, "preferred_time": Optional[str], "priority": int|str}`
    - day_window_minutes: total minutes in the day window (if None, computed from day_start..day_end, or 1440 if blocks span 24h)
    """
    win_start = _parse_hhmm(day_start)
    win_end = _parse_hhmm(day_end)
    if win_start is None:
        win_start = 6 * 60
    if win_end is None or win_end <= win_start:
        win_end = 22 * 60

    locked_intervals: List[Tuple[int, int, str]] = []
    raw_intervals: List[Tuple[int, int]] = []

    for block in routine_blocks or []:
        is_locked = block.get("is_locked", True)
        if not is_locked:
            continue
        b_title = block.get("title", "Routine Block")
        s_min = _parse_hhmm(block.get("start_time"))
        e_min = _parse_hhmm(block.get("end_time"))
        if s_min is None or e_min is None:
            continue
        if e_min <= s_min:
            # Handle overnight block (e.g., 23:00 to 06:00) by splitting at midnight
            locked_intervals.append((s_min, 24 * 60, b_title))
            locked_intervals.append((0, e_min, b_title))
            raw_intervals.append((s_min, 24 * 60))
            raw_intervals.append((0, e_min))
            win_start = 0
            win_end = 24 * 60
        else:
            locked_intervals.append((s_min, e_min, b_title))
            raw_intervals.append((s_min, e_min))
            if s_min < win_start:
                win_start = s_min
            if e_min > win_end:
                win_end = e_min

    merged_locked = _merge_intervals(raw_intervals)
    total_locked_minutes = sum(e - s for s, e in merged_locked)

    if day_window_minutes is not None:
        total_window = day_window_minutes
    else:
        # If locked blocks include sleep or span beyond waking window, use 24h (1440), else waking window
        total_window = max(win_end - win_start, total_locked_minutes)

    true_free_minutes = max(0, total_window - total_locked_minutes)

    # Compute free slots inside [win_start, win_end]
    free_slots: List[ List[int] ] = []
    cursor = win_start
    for s, e in merged_locked:
        if e <= win_start or s >= win_end:
            continue
        clamped_s = max(win_start, s)
        clamped_e = min(win_end, e)
        if clamped_s > cursor:
            free_slots.append([cursor, clamped_s])
        cursor = max(cursor, clamped_e)
    if cursor < win_end:
        free_slots.append([cursor, win_end])

    # If day_window_minutes was explicitly provided and differs from sum of free_slots,
    # ensure free_slots reflect available capacity
    warnings: List[str] = []

    raw_task_minutes = 0
    normalized_tasks: List[Dict[str, Any]] = []
    for idx, t in enumerate(proposed_tasks or []):
        est = int(t.get("estimated_minutes") or t.get("duration_minutes") or 30)
        est = max(1, est)
        raw_task_minutes += est
        pref_str = t.get("preferred_time") or t.get("due_time") or t.get("start_time")
        pref_min = _parse_hhmm(pref_str) if pref_str else None
        buffered_est = int(math.ceil(est * (1.0 + transition_buffer)))

        # Check overlap with locked blocks if preferred_time is specified
        overlap_block: Optional[str] = None
        if pref_min is not None:
            task_end = pref_min + est
            for ls, le, ltitle in locked_intervals:
                if pref_min < le and task_end > ls:
                    overlap_block = f"{ltitle} ({_format_hhmm(ls)}-{_format_hhmm(le)})"
                    warnings.append(
                        f"Conflict: '{t.get('title', 'Task')}' at {_format_hhmm(pref_min)} overlaps locked routine '{overlap_block}'."
                    )
                    break

        normalized_tasks.append({
            **t,
            "_idx": idx,
            "title": t.get("title", f"Task {idx + 1}"),
            "estimated_minutes": est,
            "buffered_minutes": buffered_est,
            "preferred_time": pref_str,
            "_pref_min": pref_min,
            "_priority_rank": _priority_rank(t.get("priority", 3)),
            "conflict_with": overlap_block,
        })

    requested_minutes = int(math.ceil(raw_task_minutes * (1.0 + transition_buffer))) if raw_task_minutes > 0 else 0

    # Sort tasks by priority rank ascending (1 = highest priority), then original index
    sorted_tasks = sorted(normalized_tasks, key=lambda x: (x["_priority_rank"], x["_idx"]))

    core_schedule: List[Dict[str, Any]] = []
    overflow_tasks: List[Dict[str, Any]] = []
    used_free_minutes = 0

    # Copy free slots for mutable allocation
    available_slots = [[s, e] for s, e in free_slots]

    for task in sorted_tasks:
        needed = task["buffered_minutes"]
        est = task["estimated_minutes"]
        pref_min = task["_pref_min"]

        if used_free_minutes + needed > true_free_minutes:
            overflow_item = {
                k: v for k, v in task.items() if not k.startswith("_")
            }
            overflow_item["reason"] = "Exceeds today's true free hours (including 15% transition buffer)."
            overflow_tasks.append(overflow_item)
            continue

        # Try to place in preferred slot if no conflict and fits in an available slot
        assigned_start: Optional[int] = None
        assigned_end: Optional[int] = None

        if pref_min is not None and not task["conflict_with"]:
            for slot in available_slots:
                if slot[0] <= pref_min and (pref_min + needed) <= slot[1]:
                    assigned_start = pref_min
                    assigned_end = pref_min + est
                    # Split or shrink slot
                    old_end = slot[1]
                    slot[1] = pref_min
                    if pref_min + needed < old_end:
                        available_slots.append([pref_min + needed, old_end])
                    available_slots.sort(key=lambda x: x[0])
                    break

        # Otherwise place into earliest available free slot that fits `needed` (or `est`)
        if assigned_start is None:
            for slot in available_slots:
                slot_len = slot[1] - slot[0]
                if slot_len >= needed:
                    assigned_start = slot[0]
                    assigned_end = slot[0] + est
                    slot[0] += needed
                    break
                elif slot_len >= est:
                    assigned_start = slot[0]
                    assigned_end = slot[0] + est
                    slot[0] += est
                    break

        if assigned_start is not None and assigned_end is not None:
            used_free_minutes += needed
            scheduled_item = {
                k: v for k, v in task.items() if not k.startswith("_")
            }
            scheduled_item["scheduled_start"] = _format_hhmm(assigned_start)
            scheduled_item["scheduled_end"] = _format_hhmm(assigned_end)
            scheduled_item["assigned_slot"] = f"{_format_hhmm(assigned_start)}-{_format_hhmm(assigned_end)}"
            core_schedule.append(scheduled_item)
        else:
            overflow_item = {
                k: v for k, v in task.items() if not k.startswith("_")
            }
            overflow_item["reason"] = "No contiguous free slot large enough between fixed routine blocks."
            overflow_tasks.append(overflow_item)

    is_overloaded = (requested_minutes > true_free_minutes) or (len(overflow_tasks) > 0)
    if requested_minutes > true_free_minutes:
        deficit = requested_minutes - true_free_minutes
        warnings.append(
            f"Overload warning: Requested {requested_minutes} mins (incl. 15% buffer) exceeds True Free Time ({true_free_minutes} mins) by {deficit} mins."
        )

    return {
        "is_overloaded": is_overloaded,
        "warnings": warnings,
        "total_locked_minutes": total_locked_minutes,
        "true_free_minutes": true_free_minutes,
        "raw_requested_minutes": raw_task_minutes,
        "requested_minutes": requested_minutes,
        "total_requested_minutes": requested_minutes,
        "core_tasks": core_schedule,
        "core_schedule": core_schedule,
        "overflow_tasks": overflow_tasks,
        "advisory_mode": True,
        "options": ["core_only", "force_all"],
    }


class RoutineAuditor:
    """Object-oriented wrapper around `audit_daily_routine` for FastAPI and pipeline integration."""

    def __init__(self, day_start: str = DEFAULT_DAY_START, day_end: str = DEFAULT_DAY_END):
        self.day_start = day_start
        self.day_end = day_end

    def audit(
        self,
        routine_blocks: List[Dict[str, Any]],
        proposed_tasks: List[Dict[str, Any]],
        day_window_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        return audit_daily_routine(
            routine_blocks=routine_blocks,
            proposed_tasks=proposed_tasks,
            day_window_minutes=day_window_minutes,
            day_start=self.day_start,
            day_end=self.day_end,
        )
