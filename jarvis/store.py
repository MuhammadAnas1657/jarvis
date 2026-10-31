"""SQLite task database, optimization indexes, and CalDAV sync manager for Jarvis."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from jarvis.config import CalDAVConfig, load_config
from jarvis.timeparse import DEFAULT_TIMEZONE


class TaskStore:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            cfg = load_config()
            self.db_path = cfg.get_abs_db_path()
        else:
            self.db_path = Path(db_path).resolve()

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        # Performance tuning: WAL mode for concurrent reads and writes
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    original_transcript TEXT,
                    raw_due_text TEXT,
                    due_datetime TEXT,
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'pending_review',
                    clarification_question TEXT,
                    recommendation TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    caldav_uid TEXT,
                    notified INTEGER DEFAULT 0
                )
            """)

            # Auto-migrate columns for existing databases
            cursor.execute("PRAGMA table_info(tasks);")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "clarification_question" not in existing_cols:
                cursor.execute("ALTER TABLE tasks ADD COLUMN clarification_question TEXT;")
            if "recommendation" not in existing_cols:
                cursor.execute("ALTER TABLE tasks ADD COLUMN recommendation TEXT;")
            # Create composite indexes for high-speed queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status_due 
                ON tasks (status, due_datetime);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created 
                ON tasks (created_at DESC);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_name TEXT NOT NULL,
                    parameters TEXT,
                    status TEXT NOT NULL,
                    result TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS briefings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    briefing_text TEXT NOT NULL,
                    audio_path TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def add_task(
        self,
        title: str,
        description: str = "",
        original_transcript: str = "",
        raw_due_text: str = "",
        due_datetime: Optional[datetime] = None,
        priority: str = "normal",
        status: str = "pending_review",
        clarification_question: Optional[str] = None,
        recommendation: Optional[str] = None,
        caldav_uid: Optional[str] = None
    ) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        due_iso = due_datetime.isoformat() if due_datetime else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (
                    title, description, original_transcript, raw_due_text,
                    due_datetime, priority, status, clarification_question, recommendation,
                    created_at, updated_at, caldav_uid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, description, original_transcript, raw_due_text,
                due_iso, priority, status, clarification_question, recommendation,
                now_iso, now_iso, caldav_uid
            ))
            conn.commit()
            return cursor.lastrowid

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        return self.list_tasks(status="pending_review")

    def get_today_tasks(self, target_date: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        target = target_date or datetime.now(DEFAULT_TIMEZONE).date()
        date_str = target.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tasks 
                WHERE status IN ('confirmed', 'scheduled')
                  AND due_datetime LIKE ?
                ORDER BY due_datetime ASC
            """, (f"{date_str}%",))
            return [dict(row) for row in cursor.fetchall()]

    def update_task_status(self, task_id: int, status: str) -> bool:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (status, now_iso, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_datetime: Optional[datetime] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        clarification_question: Optional[str] = None,
        recommendation: Optional[str] = None
    ) -> bool:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        fields = ["updated_at = ?"]
        params = [now_iso]

        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if due_datetime is not None:
            fields.append("due_datetime = ?")
            params.append(due_datetime.isoformat())
        if priority is not None:
            fields.append("priority = ?")
            params.append(priority)
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if clarification_question is not None:
            fields.append("clarification_question = ?")
            params.append(clarification_question)
        if recommendation is not None:
            fields.append("recommendation = ?")
            params.append(recommendation)

        params.append(task_id)
        query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def log_action(
        self,
        action_name: str,
        parameters: Dict[str, Any],
        status: str,
        result: Optional[str] = None
    ) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        params_str = json.dumps(parameters)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO action_logs (action_name, parameters, status, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (action_name, params_str, status, result, now_iso))
            conn.commit()
            return cursor.lastrowid

    def log_briefing(self, briefing_text: str, audio_path: Optional[str] = None) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO briefings (briefing_text, audio_path, created_at)
                VALUES (?, ?, ?)
            """, (briefing_text, audio_path, now_iso))
            conn.commit()
            return cursor.lastrowid

    def sync_to_caldav(self, task_id: int, caldav_cfg: Optional[CalDAVConfig] = None) -> bool:
        """
        Sync confirmed task to Radicale CalDAV server if reachable.
        Handles temporary network outages without blocking or raising.
        """
        task = self.get_task(task_id)
        if not task:
            return False

        try:
            import caldav
            cfg = caldav_cfg or load_config().caldav
            client = caldav.DAVClient(
                url=cfg.url,
                username=cfg.user,
                password=cfg.password
            )
            principal = client.principal()
            calendars = principal.calendars()
            if calendars:
                cal = calendars[0]
                due_line = ""
                if task.get("due_datetime"):
                    try:
                        clean_dt = datetime.fromisoformat(task["due_datetime"]).strftime("%Y%m%dT%H%M%SZ")
                        due_line = f"DUE:{clean_dt}\n"
                    except Exception:
                        pass

                vtodo = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Jarvis Assistant//PK
BEGIN:VTODO
UID:jarvis-task-{task['id']}
SUMMARY:{task['title']}
DESCRIPTION:{task.get('description', '')}
STATUS:NEEDS-ACTION
PRIORITY:{1 if task.get('priority') == 'urgent' else 5}
{due_line}END:VTODO
END:VCALENDAR"""
                cal.add_todo(vtodo)
                return True
        except Exception:
            # CalDAV server temporarily offline; SQLite remains trusted local source of truth
            return False
        return False
