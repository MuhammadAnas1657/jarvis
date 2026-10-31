"""Daily and boot-time briefing engine with spoken clarification recommendations."""

from datetime import datetime
from typing import Dict, Any, Optional
import requests

from jarvis.config import load_config
from jarvis.store import TaskStore
from jarvis.timeparse import DEFAULT_TIMEZONE
from jarvis.tts import TextToSpeech


class DailyBriefing:
    def __init__(self, store: Optional[TaskStore] = None):
        self.store = store or TaskStore()
        self.tts = TextToSpeech()
        self.config = load_config()

    def generate_briefing(self) -> Dict[str, Any]:
        """Generate spoken briefing summary of today's schedule and pending voice items."""
        now = datetime.now(DEFAULT_TIMEZONE)
        today_tasks = self.store.get_today_tasks()
        pending_tasks = self.store.get_pending_tasks()

        greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 17 else "Good evening")
        lines = [f"{greeting}, sir. Jarvis system is online."]

        # 1. Today's agenda
        if today_tasks:
            lines.append(f"You have {len(today_tasks)} item{'s' if len(today_tasks) > 1 else ''} scheduled for today:")
            for idx, task in enumerate(today_tasks, 1):
                time_str = ""
                if task.get("due_datetime"):
                    try:
                        dt = datetime.fromisoformat(task["due_datetime"])
                        time_str = f" at {dt.strftime('%I:%M %p')}"
                    except Exception:
                        pass
                lines.append(f"{idx}. {task['title']}{time_str}.")
        else:
            lines.append("You have no scheduled tasks on your calendar for today.")

        # 2. Pending voice items & recommendations
        if pending_tasks:
            lines.append(f"There {'are' if len(pending_tasks) > 1 else 'is'} {len(pending_tasks)} voice memo{'s' if len(pending_tasks) > 1 else ''} awaiting your review.")
            
            # Highlight top clarification question if any
            with_clarifications = [t for t in pending_tasks if t.get("clarification_question")]
            if with_clarifications:
                first = with_clarifications[0]
                lines.append(f"For '{first['title']}', {first['clarification_question']}")

        briefing_text = " ".join(lines)

        # Generate audio safely via TTS
        audio_path = self.tts.speak(briefing_text)

        # Log into database
        briefing_id = self.store.log_briefing(briefing_text, audio_path)

        # Send ntfy notification if configured
        self._send_ntfy(briefing_text)

        return {
            "id": briefing_id,
            "text": briefing_text,
            "audio_path": audio_path,
            "scheduled_count": len(today_tasks),
            "pending_count": len(pending_tasks),
            "timestamp": now.isoformat()
        }

    def _send_ntfy(self, text: str):
        try:
            cfg = self.config.ntfy
            url = f"{cfg.url.rstrip('/')}/{cfg.topic}"
            requests.post(
                url,
                data=text.encode("utf-8"),
                headers={"Title": "Jarvis Morning Briefing", "Priority": "default"},
                timeout=3
            )
        except Exception:
            pass
