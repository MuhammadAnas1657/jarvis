"""Nightly Accountability & Course Learning Audit engine for Jarvis.

Provides:
1. `compute_daily_discipline_score(tasks)`: Evaluates completed vs. missed/pending tasks.
2. `structure_course_reflection(raw_reflection, topic="", course_title="")`: Structures a user's
   voice/text "What I Learned Today" reflection into clean markdown takeaways (using
   `jarvis.key_pool.groq_chat_completion` when available with a deterministic fallback).
3. `generate_recall_quiz(yesterday_log)`: Generates a 2-question quick recall quiz based on
   yesterday's course log so the user is quizzed every night on what they learned.
"""

import json
import re
from typing import Any, Dict, List, Optional, Union


COMPLETED_STATUSES = {"completed", "done", "acknowledged", "finished"}
MISSED_STATUSES = {"missed", "failed", "skipped", "overdue"}


def compute_daily_discipline_score(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministically evaluate today's completed vs. missed/pending tasks.

    Supports task dicts with either `completed: bool` or `status: str`.
    """
    if not tasks:
        return {
            "total_tasks": 0,
            "completed_count": 0,
            "missed_count": 0,
            "pending_count": 0,
            "score_pct": 100.0,
            "score": 100.0,
            "grade": "A",
            "completed_titles": [],
            "missed_titles": [],
            "summary": "No tasks scheduled for today.",
        }

    completed_titles: List[str] = []
    missed_titles: List[str] = []
    pending_count = 0

    for t in tasks:
        title = str(t.get("title") or t.get("name") or "Untitled Task")
        is_done = False
        is_missed = False

        if "completed" in t and isinstance(t["completed"], bool):
            is_done = t["completed"]
            is_missed = not is_done
        else:
            status = str(t.get("status", "")).lower().strip()
            if status in COMPLETED_STATUSES:
                is_done = True
            elif status in MISSED_STATUSES:
                is_missed = True
            else:
                # In a nightly audit, uncompleted confirmed/scheduled tasks count as missed unless marked pending
                is_missed = True
                pending_count += 1

        if is_done:
            completed_titles.append(title)
        elif is_missed:
            missed_titles.append(title)

    total = len(tasks)
    comp_cnt = len(completed_titles)
    miss_cnt = len(missed_titles)
    score_pct = round((comp_cnt / total) * 100.0, 1) if total > 0 else 100.0

    if score_pct >= 90:
        grade = "A"
    elif score_pct >= 75:
        grade = "B"
    elif score_pct >= 60:
        grade = "C"
    elif score_pct >= 40:
        grade = "D"
    else:
        grade = "F"

    summary = f"Completed {comp_cnt}/{total} tasks ({score_pct}% - Grade {grade})."
    if missed_titles:
        summary += f" Missed: {', '.join(missed_titles[:3])}."

    return {
        "total_tasks": total,
        "completed_count": comp_cnt,
        "missed_count": miss_cnt,
        "pending_count": pending_count,
        "score_pct": score_pct,
        "score": score_pct,
        "grade": grade,
        "completed_titles": completed_titles,
        "missed_titles": missed_titles,
        "summary": summary,
    }


def _try_groq_chat(messages: List[Dict[str, str]]) -> Optional[str]:
    """Attempt calling `jarvis.key_pool.groq_chat_completion` if available and online."""
    try:
        from jarvis import key_pool
        fn = getattr(key_pool, "groq_chat_completion", None)
        if callable(fn):
            res = fn(messages)
            if isinstance(res, dict):
                # Handle OpenAI/Groq style dict or custom dict
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


def _extract_sentences(text: str) -> List[str]:
    cleaned = re.sub(r'\s+', ' ', (text or "").strip())
    if not cleaned:
        return []
    parts = [p.strip(" -•*\t") for p in re.split(r'(?<=[.!?])\s+|\n+|;\s+', cleaned) if p.strip(" -•*\t")]
    return parts if parts else [cleaned]


def structure_course_reflection(
    raw_reflection: str,
    topic: str = "",
    course_title: str = "",
    use_llm: bool = True,
) -> str:
    """
    Structure a user's voice/text 'What I Learned Today' reflection into clean Markdown takeaways.
    Uses `jarvis.key_pool.groq_chat_completion` when available and falls back to a deterministic
    structured Markdown extractor.
    """
    cleaned = (raw_reflection or "").strip()
    header_title = topic.strip() or course_title.strip() or "Daily Course Reflection"

    if not cleaned:
        return f"### {header_title}\n\n- **Key Takeaway**: No reflection notes provided today.\n"

    if use_llm:
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert technical study assistant. Convert the user's raw voice/text "
                    "reflection on what they learned today into concise, high-signal Markdown notes "
                    "with sections: '### Key Takeaways', '### Core Concepts', and '### Actionable Next Step'."
                ),
            },
            {
                "role": "user",
                "content": f"Course/Topic: {header_title}\nRaw Reflection:\n{cleaned}",
            },
        ]
        llm_out = _try_groq_chat(prompt_messages)
        # Only use LLM output if it contains actual structured markdown and is not a generic offline stub
        if (
            llm_out
            and ("#" in llm_out or "-" in llm_out or "*" in llm_out)
            and "offline fallback" not in llm_out.lower()
        ):
            return llm_out.strip()

    # Deterministic structured Markdown extractor fallback
    sentences = _extract_sentences(cleaned)
    bullets = "\n".join(f"- {s}" for s in sentences)

    # Extract key terms (capitalized technical words or quoted terms or words > 5 chars)
    words = re.findall(r'\b[A-Za-z][A-Za-z0-9_-]{3,}\b', cleaned)
    stop_words = {
        "today", "learned", "about", "course", "module", "video", "lecture", "watched",
        "studied", "understand", "understood", "because", "which", "their", "there",
        "where", "would", "could", "should", "these", "those", "after", "before",
    }
    key_terms: List[str] = []
    for w in words:
        lw = w.lower()
        if lw not in stop_words and lw not in [k.lower() for k in key_terms]:
            key_terms.append(w)
        if len(key_terms) >= 5:
            break

    concepts_line = ", ".join(f"`{k}`" for k in key_terms) if key_terms else "`Core Fundamentals`"
    first_point = sentences[0] if sentences else cleaned
    practice_target = key_terms[0] if key_terms else "today's concept"

    md = (
        f"### {header_title} — Structured Takeaways\n\n"
        f"#### Key Takeaways\n"
        f"{bullets}\n\n"
        f"#### Core Concepts Covered\n"
        f"- Focus Areas: {concepts_line}\n"
        f"- Primary Insight: {first_point}\n\n"
        f"#### Next Practice Step\n"
        f"- Apply {practice_target} in a hands-on exercise before the next module."
    )
    return md


def generate_recall_quiz(
    yesterday_log: Optional[Union[Dict[str, Any], str]],
    use_llm: bool = False,
) -> List[Dict[str, str]]:
    """
    Generate a 2-question quick recall quiz based on yesterday's course log.

    Accepts either a dict (`{"topic": ..., "raw_reflection": ..., "structured_notes": ...}`)
    or a plain string reflection.
    Returns a list of 2 question dicts: `[{"question": ..., "expected_answer": ..., "topic": ...}, ...]`.
    """
    if not yesterday_log:
        return [
            {
                "question": "What was the single most important concept you studied in your previous session?",
                "expected_answer": "Summarize the main concept and how it works in practice.",
                "topic": "General Recall",
            },
            {
                "question": "How can you apply your last lesson to an active project or deliverable this week?",
                "expected_answer": "Identify one concrete task or workflow where this knowledge applies.",
                "topic": "Practical Application",
            },
        ]

    if isinstance(yesterday_log, str):
        topic = "Previous Lesson"
        raw_text = yesterday_log.strip()
        notes_text = ""
    else:
        topic = str(yesterday_log.get("topic") or yesterday_log.get("course_title") or "Previous Lesson").strip()
        raw_text = str(yesterday_log.get("raw_reflection") or "").strip()
        notes_text = str(yesterday_log.get("structured_notes") or "").strip()

        # If quiz_json is already stored and valid with 2 questions, we can still generate fresh or parse
    source_text = raw_text or notes_text or topic
    sentences = _extract_sentences(source_text)

    first_fact = sentences[0] if sentences else f"Core principles of {topic}"
    second_fact = sentences[1] if len(sentences) > 1 else f"Practical implementation of {topic} ({first_fact})"

    # Extract a primary concept keyword for targeted recall
    words = [
        w for w in re.findall(r'\b[A-Za-z][A-Za-z0-9_-]{3,}\b', source_text)
        if w.lower() not in {"today", "learned", "about", "course", "module", "watched", "studied"}
    ]
    focus_term = words[0] if words else topic

    q1 = {
        "question": f"In yesterday's lesson on '{topic}', explain the core mechanism behind {focus_term} and your main takeaway.",
        "expected_answer": first_fact,
        "topic": topic,
    }
    q2 = {
        "question": f"How does '{focus_term}' apply in practice, or what was the second key detail you noted in '{topic}'?",
        "expected_answer": second_fact,
        "topic": topic,
    }
    return [q1, q2]


def run_nightly_audit(
    today_tasks: List[Dict[str, Any]],
    raw_reflection: str,
    topic: str = "",
    course_title: str = "",
    yesterday_log: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """Convenience helper combining discipline score, structured course notes, and 2-question recall quiz."""
    discipline = compute_daily_discipline_score(today_tasks)
    structured_notes = structure_course_reflection(raw_reflection, topic=topic, course_title=course_title)
    recall_quiz = generate_recall_quiz(yesterday_log or {"topic": topic or course_title, "raw_reflection": raw_reflection})
    return {
        "discipline": discipline,
        "structured_notes": structured_notes,
        "recall_quiz": recall_quiz,
    }
