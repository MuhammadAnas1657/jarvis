"""Business Deliverables Urgency Scorer & Autonomous Small-Task Buddy for Jarvis.

Provides:
1. `score_deliverable(deadline_iso, estimated_hours, impact_score, now=None)`:
   Deterministic urgency scorer that calculates urgency index, slack hours, risk tier,
   and recommended action.
2. `rank_deliverables(deliverables, now=None)`:
   Sorts client deliverables by urgency score descending.
3. `execute_small_task(prompt, task_type="draft")`:
   Autonomous Small-Task Worker supporting `draft`, `breakdown`, `sop`, and `research`
   via `jarvis.key_pool.groq_chat_completion` with a rich deterministic structured fallback
   and `requires_confirmation: True` per AGENTS.md.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from jarvis.timeparse import DEFAULT_TIMEZONE, parse_relative_time


SUPPORTED_TASK_TYPES = {"draft", "breakdown", "sop", "research"}


def _parse_deadline(deadline_iso: str, base_now: datetime) -> datetime:
    if not deadline_iso or not str(deadline_iso).strip():
        return base_now
    s = str(deadline_iso).strip()
    try:
        # Handle 'Z' suffix for Python 3.10/3.11 compatibility
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=DEFAULT_TIMEZONE)
        else:
            dt = dt.astimezone(DEFAULT_TIMEZONE)
        return dt
    except Exception:
        pass

    # Fallback to deterministic timeparse
    parsed = parse_relative_time(s, base_dt=base_now)
    if parsed:
        return parsed
    return base_now


def score_deliverable(
    deadline_iso: str,
    estimated_hours: float,
    impact_score: int,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Deterministically calculate the urgency score of a business/client deliverable.

    Parameters:
    - deadline_iso: ISO datetime or date string (e.g. '2026-11-14T18:00:00+05:00' or '2026-11-14')
    - estimated_hours: estimated effort in hours (>= 0.25)
    - impact_score: business/client impact on a 1..10 scale
    - now: optional reference datetime (defaults to current time in Asia/Karachi)
    """
    ref_now = now.astimezone(DEFAULT_TIMEZONE) if (now and now.tzinfo) else (
        now.replace(tzinfo=DEFAULT_TIMEZONE) if now else datetime.now(DEFAULT_TIMEZONE)
    )
    deadline_dt = _parse_deadline(deadline_iso, ref_now)

    est_hrs = max(0.25, float(estimated_hours or 1.0))
    impact = max(1, min(10, int(impact_score or 5)))

    hours_remaining = (deadline_dt - ref_now).total_seconds() / 3600.0
    slack_hours = round(hours_remaining - est_hrs, 2)

    # Time pressure component (0..60 points)
    if hours_remaining <= 0:
        # Overdue
        time_pressure = 60.0 + min(20.0, abs(hours_remaining) * 0.5)
    else:
        # Ratio of effort to remaining time + proximity decay
        effort_density = min(3.0, est_hrs / max(1.0, hours_remaining))
        proximity = 48.0 / (hours_remaining + 12.0)
        time_pressure = min(60.0, (effort_density * 25.0) + (proximity * 35.0))

    # Impact component (0..40 points)
    impact_points = impact * 4.0

    urgency_score = round(min(100.0, time_pressure + impact_points), 2)

    if hours_remaining <= 0 or slack_hours < 0 or urgency_score >= 80.0:
        tier = "critical"
    elif urgency_score >= 60.0 or hours_remaining <= 24.0:
        tier = "high"
    elif urgency_score >= 35.0 or hours_remaining <= 72.0:
        tier = "medium"
    else:
        tier = "low"

    return {
        "urgency_score": urgency_score,
        "score": urgency_score,
        "tier": tier,
        "hours_remaining": round(hours_remaining, 2),
        "slack_hours": slack_hours,
        "estimated_hours": est_hrs,
        "impact_score": impact,
        "is_overdue": hours_remaining < 0,
        "at_risk": slack_hours < 0,
    }


def rank_deliverables(
    deliverables: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Score and sort a list of business deliverables by urgency_score descending."""
    ranked: List[Dict[str, Any]] = []
    for item in deliverables or []:
        metrics = score_deliverable(
            deadline_iso=str(item.get("deadline", "")),
            estimated_hours=float(item.get("estimated_hours", 1.0)),
            impact_score=int(item.get("impact_score", 5)),
            now=now,
        )
        ranked.append({**item, **metrics})
    ranked.sort(key=lambda x: (-x["urgency_score"], x["hours_remaining"]))
    return ranked


def _try_groq_worker(messages: List[Dict[str, str]]) -> Optional[str]:
    """Attempt calling `jarvis.key_pool.groq_chat_completion` if available and online."""
    try:
        from jarvis import key_pool
        fn = getattr(key_pool, "groq_chat_completion", None)
        if callable(fn):
            res = fn(messages)
            if isinstance(res, dict):
                if "content" in res and isinstance(res["content"], str):
                    return res["content"]
                choices = res.get("choices")
                if choices and isinstance(choices, list):
                    msg = choices[0].get("message", {})
                    if isinstance(msg, dict) and msg.get("content"):
                        return str(msg["content"])
            elif isinstance(res, str) and res.strip():
                return res
    except Exception:
        pass
    return None


def _deterministic_small_task_fallback(prompt: str, task_type: str) -> str:
    topic = (prompt or "Untitled Business Request").strip()
    if task_type == "draft":
        return (
            f"### Draft Communication: {topic}\n\n"
            f"**Subject:** Update & Next Steps — {topic}\n\n"
            f"Hi Team / Client,\n\n"
            f"Following up on **{topic}**. Here is the current status and proposed plan:\n"
            f"1. **Objective**: Deliver {topic} on schedule with full quality verification.\n"
            f"2. **Current Progress**: Core requirements and scope have been structured.\n"
            f"3. **Next Steps**: Please review and confirm the deliverables below so we can proceed.\n\n"
            f"Best regards,\nAnas"
        )
    if task_type == "breakdown":
        return (
            f"### Project Breakdown: {topic}\n\n"
            f"1. **Phase 1 — Discovery & Scope (20% effort)**\n"
            f"   - Define acceptance criteria and constraints for: {topic}\n"
            f"   - Confirm dependencies and resources\n"
            f"2. **Phase 2 — Core Execution (50% effort)**\n"
            f"   - Build and validate the primary deliverable\n"
            f"   - Run internal quality check against client requirements\n"
            f"3. **Phase 3 — Review & Handover (30% effort)**\n"
            f"   - Package final artifacts, documentation, and walkthrough\n"
            f"   - Obtain user/client sign-off"
        )
    if task_type == "sop":
        return (
            f"### Standard Operating Procedure (SOP): {topic}\n\n"
            f"**Purpose:** Establish a repeatable, error-free workflow for {topic}.\n\n"
            f"#### Prerequisites\n"
            f"- Required access credentials, workspace files, and checklist verified.\n\n"
            f"#### Step-by-Step Procedure\n"
            f"1. **Preparation**: Open project tracker and verify input specifications for {topic}.\n"
            f"2. **Execution**: Follow the standardized implementation checklist and log outputs.\n"
            f"3. **Quality Gate**: Verify output accuracy, formatting, and edge cases.\n"
            f"4. **Completion**: Archive artifacts and mark deliverable status after confirmation."
        )
    # research (or any custom type)
    return (
        f"### Research Brief: {topic}\n\n"
        f"#### Executive Summary\n"
        f"- Structured analysis and decision matrix for **{topic}**.\n\n"
        f"#### Key Findings & Considerations\n"
        f"- **Core Requirement**: Align architecture, cost, and reliability around {topic}.\n"
        f"- **Trade-offs**: Balance execution speed against long-term maintainability.\n"
        f"- **Recommended Action**: Prototype the highest-leverage component first and validate metrics."
    )


def execute_small_task(
    prompt: str,
    task_type: str = "draft",
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    Autonomous Small-Task Buddy worker supporting `draft`, `breakdown`, `sop`, and `research`.

    Uses `jarvis.key_pool.groq_chat_completion` when available and falls back to a deterministic
    structured generator. Never executes side-effect actions without confirmation (`status='pending_review'`).
    """
    norm_type = (task_type or "draft").lower().strip()
    if norm_type not in SUPPORTED_TASK_TYPES:
        norm_type = "draft"

    clean_prompt = (prompt or "").strip() or "General business task"

    system_prompts = {
        "draft": "You are an executive assistant. Write a concise, professional client/team draft based on the user's prompt.",
        "breakdown": "You are a senior technical project manager. Break the user's project into clear milestones, sub-tasks, and time estimates.",
        "sop": "You are an operations architect. Write a clear, step-by-step Standard Operating Procedure (SOP) with prerequisites, steps, and verification checks.",
        "research": "You are a technical & business research analyst. Provide a high-signal research brief with Executive Summary, Key Options, Trade-offs, and Recommendation.",
    }

    content: Optional[str] = None
    source = "deterministic_fallback"

    if use_llm:
        messages = [
            {"role": "system", "content": system_prompts[norm_type]},
            {"role": "user", "content": clean_prompt},
        ]
        llm_out = _try_groq_worker(messages)
        if (
            llm_out
            and len(llm_out.strip()) > 20
            and "offline fallback" not in llm_out.lower()
        ):
            content = llm_out.strip()
            source = "groq_key_pool"

    if not content:
        content = _deterministic_small_task_fallback(clean_prompt, norm_type)

    return {
        "prompt": clean_prompt,
        "task_type": norm_type,
        "result_content": content,
        "content": content,
        "source": source,
        "status": "pending_review",
        "requires_confirmation": True,
    }
