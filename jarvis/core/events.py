"""Real-time event definitions for JARVIS WebSocket + PostgreSQL LISTEN/NOTIFY bus."""

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class JarvisEvent(BaseModel):
    event: str
    type: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


EVENT_ACTION_CONFIRMED = "action_confirmed"
EVENT_ROUTINE_UPDATED = "routine_updated"
EVENT_REMINDER_ADDED = "reminder_added"
EVENT_REMINDER_UPDATED = "reminder_updated"
EVENT_REMINDER_DELETED = "reminder_deleted"
EVENT_PING = "ping"
