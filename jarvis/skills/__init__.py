"""Modular JARVIS Slash-Skills registry (/automation, /schedule, /browser, /swarm, /goal, /plugin, /learn)."""

from typing import Any, Dict, List


JARVIS_SKILLS: List[Dict[str, Any]] = [
    {
        "command": "/schedule",
        "name": "Smart Scheduler",
        "description": "Schedule tasks, projects, or learnings into deterministic weekday free slots.",
        "example": "/schedule Complete FastAPI assignment on Monday free slot",
        "enabled": True,
    },
    {
        "command": "/automation",
        "name": "Recurring Automation",
        "description": "Create repeating reminders (every 30m/1h) or daily alarms (e.g. 12:00 AM, 3:50 PM).",
        "example": "/automation remind me every 30 minutes to drink water",
        "enabled": True,
    },
    {
        "command": "/goal",
        "name": "Goal Completion Tracker",
        "description": "Track multi-session projects and keep nudging until 100% completed.",
        "example": "/goal Finish React Native portfolio project in 8 hours",
        "enabled": True,
    },
    {
        "command": "/learn",
        "name": "Learning & Reflection",
        "description": "Add a learning topic, schedule study blocks, and log daily takeaways.",
        "example": "/learn System Design — 1 hour daily on weekdays",
        "enabled": True,
    },
    {
        "command": "/swarm",
        "name": "Multi-Agent Swarm",
        "description": "Break down a complex objective across Planner, Auditor, and Executor roles.",
        "example": "/swarm Plan my semester project milestones and weekday schedule",
        "enabled": True,
    },
    {
        "command": "/browser",
        "name": "Browser & Web Helper",
        "description": "Confirm-first opening of research URLs or web workflows on your machine.",
        "example": "/browser Open FastAPI WebSocket docs",
        "enabled": True,
    },
    {
        "command": "/plugin",
        "name": "Skills & Plugins",
        "description": "Inspect or toggle active JARVIS capabilities and modules.",
        "example": "/plugin list active skills",
        "enabled": True,
    },
]


def list_skills() -> List[Dict[str, Any]]:
    return JARVIS_SKILLS
