"""PostgreSQL primary database store with transparent local SQL fallback for Jarvis."""

import json
import logging
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore

from jarvis.config import ADMIN_POSTGRES_URL, CalDAVConfig, DEFAULT_POSTGRES_URL, load_config, load_dotenv_files
from jarvis.timeparse import DEFAULT_TIMEZONE

logger = logging.getLogger(__name__)

VALID_ALARM_STATES = {"scheduled", "ringing", "acknowledged", "missed"}


POSTGRES_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        original_transcript TEXT DEFAULT '',
        raw_due_text TEXT DEFAULT '',
        due_datetime TEXT,
        priority TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'pending_review',
        clarification_question TEXT,
        recommendation TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        caldav_uid TEXT,
        notified INTEGER DEFAULT 0
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks (status, due_datetime);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks (created_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS action_logs (
        id SERIAL PRIMARY KEY,
        action_name TEXT NOT NULL,
        parameters TEXT,
        status TEXT NOT NULL,
        result TEXT,
        timestamp TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS briefings (
        id SERIAL PRIMARY KEY,
        briefing_text TEXT NOT NULL,
        audio_path TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS weekly_routine (
        id SERIAL PRIMARY KEY,
        day_of_week TEXT NOT NULL,
        title TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        category TEXT DEFAULT 'fixed',
        is_locked BOOLEAN DEFAULT TRUE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alarms (
        id SERIAL PRIMARY KEY,
        alarm_time TEXT NOT NULL,
        label TEXT NOT NULL,
        first_task_prompt TEXT DEFAULT '',
        state TEXT DEFAULT 'scheduled'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS courses (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        instructor TEXT DEFAULT '',
        total_modules INTEGER DEFAULT 1,
        completed_modules INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS course_logs (
        id SERIAL PRIMARY KEY,
        course_id INTEGER,
        log_date TEXT NOT NULL,
        topic TEXT NOT NULL,
        raw_reflection TEXT DEFAULT '',
        structured_notes TEXT DEFAULT '',
        quiz_json TEXT DEFAULT '[]'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS business_deliverables (
        id SERIAL PRIMARY KEY,
        client_name TEXT NOT NULL,
        title TEXT NOT NULL,
        deadline TEXT,
        estimated_hours DOUBLE PRECISION DEFAULT 1.0,
        impact_score INTEGER DEFAULT 5,
        status TEXT DEFAULT 'pending'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS small_tasks (
        id SERIAL PRIMARY KEY,
        prompt TEXT NOT NULL,
        task_type TEXT NOT NULL,
        result_content TEXT DEFAULT '',
        status TEXT DEFAULT 'pending_review',
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS routine_completions (
        id SERIAL PRIMARY KEY,
        routine_id INTEGER NOT NULL,
        date_str TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        completed_at TEXT,
        UNIQUE(routine_id, date_str)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'project',
        goal TEXT DEFAULT '',
        total_hours REAL DEFAULT 4.0,
        session_minutes INTEGER DEFAULT 60,
        priority TEXT DEFAULT 'medium',
        deadline TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


SQLITE_DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        original_transcript TEXT DEFAULT '',
        raw_due_text TEXT DEFAULT '',
        due_datetime TEXT,
        priority TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'pending_review',
        clarification_question TEXT,
        recommendation TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        caldav_uid TEXT,
        notified INTEGER DEFAULT 0
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks (status, due_datetime);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks (created_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_name TEXT NOT NULL,
        parameters TEXT,
        status TEXT NOT NULL,
        result TEXT,
        timestamp TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS briefings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        briefing_text TEXT NOT NULL,
        audio_path TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS weekly_routine (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_of_week TEXT NOT NULL,
        title TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        category TEXT DEFAULT 'fixed',
        is_locked INTEGER DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alarms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alarm_time TEXT NOT NULL,
        label TEXT NOT NULL,
        first_task_prompt TEXT DEFAULT '',
        state TEXT DEFAULT 'scheduled'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        instructor TEXT DEFAULT '',
        total_modules INTEGER DEFAULT 1,
        completed_modules INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS course_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER,
        log_date TEXT NOT NULL,
        topic TEXT NOT NULL,
        raw_reflection TEXT DEFAULT '',
        structured_notes TEXT DEFAULT '',
        quiz_json TEXT DEFAULT '[]'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS business_deliverables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_name TEXT NOT NULL,
        title TEXT NOT NULL,
        deadline TEXT,
        estimated_hours REAL DEFAULT 1.0,
        impact_score INTEGER DEFAULT 5,
        status TEXT DEFAULT 'pending'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS small_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prompt TEXT NOT NULL,
        task_type TEXT NOT NULL,
        result_content TEXT DEFAULT '',
        status TEXT DEFAULT 'pending_review',
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS routine_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        routine_id INTEGER NOT NULL,
        date_str TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        completed_at TEXT,
        UNIQUE(routine_id, date_str)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'project',
        goal TEXT DEFAULT '',
        total_hours REAL DEFAULT 4.0,
        session_minutes INTEGER DEFAULT 60,
        priority TEXT DEFAULT 'medium',
        deadline TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


def _is_postgres_url(value: Optional[str]) -> bool:
    if not value:
        return False
    val = str(value).strip().lower()
    return val.startswith("postgresql://") or val.startswith("postgres://")


class TaskStore:
    """
    Unified store supporting PostgreSQL via DATABASE_URL (`psycopg2`) in production,
    with automatic transparent fallback to a local SQL-compatible adapter when the
    PostgreSQL daemon is unreachable during offline development or CI unit tests.
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        database_url: Optional[str] = None,
    ):
        cfg = load_config()
        self.database_url: Optional[str] = None
        self.db_path: Path = cfg.get_abs_db_path()
        self.backend: str = "sqlite_compat"

        if _is_postgres_url(str(db_path) if db_path else None):
            self.database_url = str(db_path)
        elif database_url and _is_postgres_url(database_url):
            self.database_url = database_url
        elif db_path is not None:
            self.db_path = Path(db_path).resolve()
        else:
            load_dotenv_files()
            candidate_url = os.environ.get("DATABASE_URL") or cfg.get_database_url() or DEFAULT_POSTGRES_URL
            if _is_postgres_url(candidate_url):
                self.database_url = candidate_url

        if self.database_url and self._can_connect_postgres(self.database_url):
            self.backend = "postgres"
        elif (
            db_path is None
            and database_url is None
            and _is_postgres_url(os.environ.get("POSTGRES_ADMIN_URL") or ADMIN_POSTGRES_URL)
            and self._can_connect_postgres(os.environ.get("POSTGRES_ADMIN_URL") or ADMIN_POSTGRES_URL)
        ):
            self.database_url = os.environ.get("POSTGRES_ADMIN_URL") or ADMIN_POSTGRES_URL
            self.backend = "postgres"
        else:
            self.backend = "sqlite_compat"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @staticmethod
    def _can_connect_postgres(url: str) -> bool:
        if psycopg2 is None:
            return False
        try:
            conn = psycopg2.connect(url, connect_timeout=1)
            conn.close()
            return True
        except Exception as exc:
            logger.debug("PostgreSQL server not reachable at %s (%s); using local SQL adapter.", url, exc)
            return False

    def _get_pg_connection(self):
        return psycopg2.connect(self.database_url, connect_timeout=5)

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _get_connection(self):
        if self.backend == "postgres":
            return self._get_pg_connection()
        return self._get_sqlite_connection()

    @staticmethod
    def _adapt_query(query: str, backend: str) -> str:
        if backend == "postgres":
            return query.replace("?", "%s")
        return query

    def _execute_insert(self, query: str, params: Sequence[Any] = ()) -> int:
        if self.backend == "postgres":
            pg_query = self._adapt_query(query.strip().rstrip(";"), "postgres") + " RETURNING id;"
            with self._get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_query, tuple(params))
                    row = cur.fetchone()
                    conn.commit()
                    return int(row[0]) if row else 0
        else:
            with self._get_sqlite_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                conn.commit()
                return int(cur.lastrowid or 0)

    def _execute_write(self, query: str, params: Sequence[Any] = ()) -> int:
        if self.backend == "postgres":
            pg_query = self._adapt_query(query, "postgres")
            with self._get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_query, tuple(params))
                    count = cur.rowcount
                    conn.commit()
                    return count
        else:
            with self._get_sqlite_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                conn.commit()
                return cur.rowcount

    def _fetch_one(self, query: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        if self.backend == "postgres":
            pg_query = self._adapt_query(query, "postgres")
            with self._get_pg_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(pg_query, tuple(params))
                    row = cur.fetchone()
                    return dict(row) if row else None
        else:
            with self._get_sqlite_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                row = cur.fetchone()
                return dict(row) if row else None

    def _fetch_all(self, query: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        if self.backend == "postgres":
            pg_query = self._adapt_query(query, "postgres")
            with self._get_pg_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(pg_query, tuple(params))
                    return [dict(row) for row in cur.fetchall()]
        else:
            with self._get_sqlite_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, tuple(params))
                return [dict(row) for row in cur.fetchall()]

    def _init_db(self) -> None:
        if self.backend == "postgres":
            with self._get_pg_connection() as conn:
                with conn.cursor() as cur:
                    for stmt in POSTGRES_DDL_STATEMENTS:
                        cur.execute(stmt)
                conn.commit()
        else:
            with self._get_sqlite_connection() as conn:
                cur = conn.cursor()
                for stmt in SQLITE_DDL_STATEMENTS:
                    cur.execute(stmt)

                # Auto-migrate legacy columns if opening an older database
                cur.execute("PRAGMA table_info(tasks);")
                existing_cols = {row["name"] for row in cur.fetchall()}
                if "clarification_question" not in existing_cols:
                    cur.execute("ALTER TABLE tasks ADD COLUMN clarification_question TEXT;")
                if "recommendation" not in existing_cols:
                    cur.execute("ALTER TABLE tasks ADD COLUMN recommendation TEXT;")
                conn.commit()

    # =========================================================================
    # Tasks & Reminders (Full backward compatibility for TaskStore/ReminderStore)
    # =========================================================================

    @staticmethod
    def _enrich_task_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        enriched = dict(row)
        enriched["confirmed"] = enriched.get("status") in ("confirmed", "scheduled", "completed")
        return enriched

    @staticmethod
    def _normalize_due(due_val: Optional[Union[datetime, str]]) -> Optional[str]:
        if due_val is None:
            return None
        if isinstance(due_val, datetime):
            return due_val.isoformat()
        return str(due_val)

    def add_task(
        self,
        title: str,
        description: str = "",
        original_transcript: str = "",
        raw_due_text: str = "",
        due_datetime: Optional[Union[datetime, str]] = None,
        priority: str = "normal",
        status: str = "pending_review",
        clarification_question: Optional[str] = None,
        recommendation: Optional[str] = None,
        caldav_uid: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        if due_datetime is None:
            due_datetime = kwargs.get("due_iso") or kwargs.get("due_time") or kwargs.get("due_at")
        if "confirmed" in kwargs and kwargs["confirmed"] is True and status == "pending_review":
            status = "confirmed"

        due_iso = self._normalize_due(due_datetime)

        return self._execute_insert(
            """
            INSERT INTO tasks (
                title, description, original_transcript, raw_due_text,
                due_datetime, priority, status, clarification_question, recommendation,
                created_at, updated_at, caldav_uid
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                original_transcript,
                raw_due_text,
                due_iso,
                priority,
                status,
                clarification_question,
                recommendation,
                now_iso,
                now_iso,
                caldav_uid,
            ),
        )

    def add_reminder(
        self,
        title: str,
        due_datetime: Optional[Union[datetime, str]] = None,
        priority: str = "normal",
        status: str = "pending_review",
        description: str = "",
        original_transcript: str = "",
        raw_due_text: str = "",
        clarification_question: Optional[str] = None,
        recommendation: Optional[str] = None,
        caldav_uid: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        return self.add_task(
            title=title,
            description=description,
            original_transcript=original_transcript,
            raw_due_text=raw_due_text,
            due_datetime=due_datetime,
            priority=priority,
            status=status,
            clarification_question=clarification_question,
            recommendation=recommendation,
            caldav_uid=caldav_uid,
            **kwargs,
        )

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._enrich_task_row(row)

    def get_reminder(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        return self.get_task(reminder_id)

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if status:
            rows = self._fetch_all(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        else:
            rows = self._fetch_all(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [self._enrich_task_row(r) for r in rows if r is not None]

    def list_reminders(
        self,
        status: Optional[str] = None,
        include_pending: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if status:
            return self.list_tasks(status=status, limit=limit)
        if not include_pending:
            rows = self._fetch_all(
                "SELECT * FROM tasks WHERE status != 'pending_review' ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [self._enrich_task_row(r) for r in rows if r is not None]
        return self.list_tasks(limit=limit)

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        return self.list_tasks(status="pending_review")

    def get_today_tasks(self, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        target = target_date or datetime.now(DEFAULT_TIMEZONE).date()
        date_str = target.isoformat()
        rows = self._fetch_all(
            """
            SELECT * FROM tasks
            WHERE status IN ('confirmed', 'scheduled')
              AND due_datetime LIKE ?
            ORDER BY due_datetime ASC
            """,
            (f"{date_str}%",),
        )
        return [self._enrich_task_row(r) for r in rows if r is not None]

    def update_task_status(self, task_id: int, status: str) -> bool:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        count = self._execute_write(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso, task_id),
        )
        return count > 0

    def update_status(self, reminder_id: int, status: str) -> bool:
        return self.update_task_status(reminder_id, status)

    def confirm_reminder(self, reminder_id: int) -> bool:
        return self.update_task_status(reminder_id, "confirmed")

    def confirm_task(self, task_id: int) -> bool:
        return self.update_task_status(task_id, "confirmed")

    def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_datetime: Optional[Union[datetime, str]] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        clarification_question: Optional[str] = None,
        recommendation: Optional[str] = None,
    ) -> bool:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        fields = ["updated_at = ?"]
        params: List[Any] = [now_iso]

        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if due_datetime is not None:
            fields.append("due_datetime = ?")
            params.append(self._normalize_due(due_datetime))
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
        return self._execute_write(query, params) > 0

    def delete_task(self, task_id: int) -> bool:
        return self._execute_write("DELETE FROM tasks WHERE id = ?", (task_id,)) > 0

    def delete_reminder(self, reminder_id: int) -> bool:
        return self.delete_task(reminder_id)

    def log_action(
        self,
        action_name: str,
        parameters: Optional[Union[Dict[str, Any], str]] = None,
        status: str = "executed",
        result: Optional[str] = None,
    ) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        if isinstance(parameters, str):
            params_str = parameters
        else:
            params_str = json.dumps(parameters or {})
        return self._execute_insert(
            """
            INSERT INTO action_logs (action_name, parameters, status, result, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (action_name, params_str, status, result, now_iso),
        )

    def get_action_logs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self._fetch_all(
                "SELECT * FROM action_logs WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        else:
            rows = self._fetch_all(
                "SELECT * FROM action_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        results = []
        for r in rows:
            item = dict(r)
            raw_params = item.get("parameters")
            if isinstance(raw_params, str):
                try:
                    item["parameters_dict"] = json.loads(raw_params)
                except Exception:
                    item["parameters_dict"] = {}
            results.append(item)
        return results

    def list_action_logs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.get_action_logs(limit=limit, status=status)

    def log_briefing(self, briefing_text: str, audio_path: Optional[str] = None) -> int:
        now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
        return self._execute_insert(
            "INSERT INTO briefings (briefing_text, audio_path, created_at) VALUES (?, ?, ?)",
            (briefing_text, audio_path, now_iso),
        )

    def sync_to_caldav(self, task_id: int, caldav_cfg: Optional[CalDAVConfig] = None) -> bool:
        """Sync confirmed task to Radicale CalDAV server if reachable."""
        task = self.get_task(task_id)
        if not task:
            return False

        try:
            import caldav

            cfg = caldav_cfg or load_config().caldav
            client = caldav.DAVClient(url=cfg.url, username=cfg.user, password=cfg.password)
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
            return False
        return False

    # =========================================================================
    # 1. Fixed Weekly Routine (`weekly_routine`)
    # =========================================================================

    @staticmethod
    def _normalize_routine_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row)
        d["is_locked"] = bool(d.get("is_locked", True))
        return d

    def add_routine_block(
        self,
        day_of_week: Union[str, int],
        title: str,
        start_time: str,
        end_time: str,
        category: str = "fixed",
        is_locked: bool = True,
    ) -> int:
        locked_val = bool(is_locked) if self.backend == "postgres" else (1 if is_locked else 0)
        return self._execute_insert(
            """
            INSERT INTO weekly_routine (day_of_week, title, start_time, end_time, category, is_locked)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(day_of_week), title, start_time, end_time, category, locked_val),
        )

    add_weekly_routine = add_routine_block

    def get_routine_block(self, block_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetch_one("SELECT * FROM weekly_routine WHERE id = ?", (block_id,))
        return self._normalize_routine_row(row)

    def list_weekly_routine(self, day_of_week: Optional[Union[str, int]] = None) -> List[Dict[str, Any]]:
        if day_of_week is not None:
            day_str = str(day_of_week).strip()
            rows = self._fetch_all(
                """
                SELECT * FROM weekly_routine
                WHERE LOWER(day_of_week) IN (LOWER(?), 'daily', 'all', 'everyday')
                ORDER BY start_time ASC, id ASC
                """,
                (day_str,),
            )
        else:
            rows = self._fetch_all("SELECT * FROM weekly_routine ORDER BY day_of_week ASC, start_time ASC, id ASC")
        return [self._normalize_routine_row(r) for r in rows if r is not None]

    get_weekly_routine = list_weekly_routine
    list_routine_blocks = list_weekly_routine

    def update_routine_block(
        self,
        block_id: int,
        day_of_week: Optional[Union[str, int]] = None,
        title: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        category: Optional[str] = None,
        is_locked: Optional[bool] = None,
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []
        if day_of_week is not None:
            fields.append("day_of_week = ?")
            params.append(str(day_of_week))
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if start_time is not None:
            fields.append("start_time = ?")
            params.append(start_time)
        if end_time is not None:
            fields.append("end_time = ?")
            params.append(end_time)
        if category is not None:
            fields.append("category = ?")
            params.append(category)
        if is_locked is not None:
            fields.append("is_locked = ?")
            params.append(bool(is_locked) if self.backend == "postgres" else (1 if is_locked else 0))

        if not fields:
            return False
        params.append(block_id)
        return self._execute_write(f"UPDATE weekly_routine SET {', '.join(fields)} WHERE id = ?", params) > 0

    def delete_routine_block(self, block_id: int) -> bool:
        return self._execute_write("DELETE FROM weekly_routine WHERE id = ?", (block_id,)) > 0

    def delete_weekly_routine_block(self, block_id: int) -> bool:
        return self.delete_routine_block(block_id)

    delete_weekly_routine = delete_routine_block

    # =========================================================================
    # 1b. Daily Routine Completions & Free Slot Calculations
    # =========================================================================

    def mark_routine_completion(self, routine_id: int, date_str: str, completed: bool = True) -> bool:
        """Mark or unmark a routine block as completed for a specific date."""
        if completed:
            now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
            if self.backend == "postgres":
                query = """
                INSERT INTO routine_completions (routine_id, date_str, status, completed_at)
                VALUES (?, ?, 'completed', ?)
                ON CONFLICT (routine_id, date_str)
                DO UPDATE SET status = 'completed', completed_at = EXCLUDED.completed_at
                """
            else:
                query = """
                INSERT OR REPLACE INTO routine_completions (routine_id, date_str, status, completed_at)
                VALUES (?, ?, 'completed', ?)
                """
            return self._execute_write(query, (int(routine_id), str(date_str).strip(), now_iso)) > 0
        else:
            return self._execute_write(
                "DELETE FROM routine_completions WHERE routine_id = ? AND date_str = ?",
                (int(routine_id), str(date_str).strip()),
            ) > 0

    def list_routine_completions(self, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """List completions for a specific date or all dates."""
        if date_str:
            rows = self._fetch_all("SELECT * FROM routine_completions WHERE date_str = ?", (str(date_str).strip(),))
        else:
            rows = self._fetch_all("SELECT * FROM routine_completions ORDER BY date_str DESC, id DESC")
        return [dict(r) for r in rows if r is not None]

    def get_free_slots_for_day(
        self,
        day_of_week: str,
        day_start: str = "06:00",
        day_end: str = "23:00",
    ) -> List[Dict[str, Any]]:
        """Deterministically calculate all free time slots for a given day."""
        def _to_mins(t: str) -> int:
            parts = str(t).strip().split(":")
            return int(parts[0]) * 60 + int(parts[1][:2])

        def _to_hhmm(m: int) -> str:
            return f"{m // 60:02d}:{m % 60:02d}"

        def _to_12h(m: int) -> str:
            h = (m // 60) % 24
            mins = m % 60
            am_pm = "AM" if h < 12 else "PM"
            h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
            return f"{h12}:{mins:02d} {am_pm}"

        day_start_m = _to_mins(day_start)
        day_end_m = _to_mins(day_end)

        blocks = self.list_weekly_routine(day_of_week=day_of_week)
        intervals = []
        for b in blocks:
            try:
                s = _to_mins(b.get("start_time", "00:00"))
                e = _to_mins(b.get("end_time", "00:00"))
                if s < e:
                    intervals.append((max(day_start_m, s), min(day_end_m, e)))
            except Exception:
                continue

        # Merge overlapping/adjacent intervals
        merged = []
        for s, e in sorted(intervals, key=lambda x: x[0]):
            if not merged or s > merged[-1][1]:
                merged.append((s, e))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))

        free_slots = []
        curr = day_start_m
        for s, e in merged:
            if s > curr and (s - curr) >= 30:
                diff = s - curr
                free_slots.append({
                    "start": _to_hhmm(curr),
                    "end": _to_hhmm(s),
                    "start_12h": _to_12h(curr),
                    "end_12h": _to_12h(s),
                    "duration_minutes": diff,
                    "duration_hours": round(diff / 60.0, 1),
                    "label": f"{_to_12h(curr)} – {_to_12h(s)} ({round(diff / 60.0, 1)} hrs free)",
                })
            curr = max(curr, e)

        if curr < day_end_m and (day_end_m - curr) >= 30:
            diff = day_end_m - curr
            free_slots.append({
                "start": _to_hhmm(curr),
                "end": _to_hhmm(day_end_m),
                "start_12h": _to_12h(curr),
                "end_12h": _to_12h(day_end_m),
                "duration_minutes": diff,
                "duration_hours": round(diff / 60.0, 1),
                "label": f"{_to_12h(curr)} – {_to_12h(day_end_m)} ({round(diff / 60.0, 1)} hrs free)",
            })

        return free_slots


    # =========================================================================
    # 2. Strict Proof-of-Wake Alarms (`alarms`)
    # =========================================================================

    def add_alarm(
        self,
        alarm_time: str,
        label: str = "Anas, wake up!",
        first_task_prompt: str = "",
        state: str = "scheduled",
    ) -> int:
        if state not in VALID_ALARM_STATES:
            raise ValueError(f"Invalid alarm state '{state}'. Must be one of {sorted(VALID_ALARM_STATES)}")
        return self._execute_insert(
            """
            INSERT INTO alarms (alarm_time, label, first_task_prompt, state)
            VALUES (?, ?, ?, ?)
            """,
            (alarm_time, label, first_task_prompt, state),
        )

    create_alarm = add_alarm

    def get_alarm(self, alarm_id: int) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM alarms WHERE id = ?", (alarm_id,))

    def list_alarms(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        if state:
            return self._fetch_all("SELECT * FROM alarms WHERE state = ? ORDER BY alarm_time ASC, id DESC", (state,))
        return self._fetch_all("SELECT * FROM alarms ORDER BY alarm_time ASC, id DESC")

    get_alarms = list_alarms

    def update_alarm_state(self, alarm_id: int, state: str) -> bool:
        if state not in VALID_ALARM_STATES:
            raise ValueError(f"Invalid alarm state '{state}'. Must be one of {sorted(VALID_ALARM_STATES)}")
        return self._execute_write("UPDATE alarms SET state = ? WHERE id = ?", (state, alarm_id)) > 0

    def update_alarm(
        self,
        alarm_id: int,
        alarm_time: Optional[str] = None,
        label: Optional[str] = None,
        first_task_prompt: Optional[str] = None,
        state: Optional[str] = None,
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []
        if alarm_time is not None:
            fields.append("alarm_time = ?")
            params.append(alarm_time)
        if label is not None:
            fields.append("label = ?")
            params.append(label)
        if first_task_prompt is not None:
            fields.append("first_task_prompt = ?")
            params.append(first_task_prompt)
        if state is not None:
            if state not in VALID_ALARM_STATES:
                raise ValueError(f"Invalid alarm state '{state}'. Must be one of {sorted(VALID_ALARM_STATES)}")
            fields.append("state = ?")
            params.append(state)
        if not fields:
            return False
        params.append(alarm_id)
        return self._execute_write(f"UPDATE alarms SET {', '.join(fields)} WHERE id = ?", params) > 0

    def acknowledge_alarm(self, alarm_id: int) -> bool:
        return self.update_alarm_state(alarm_id, "acknowledged")

    def delete_alarm(self, alarm_id: int) -> bool:
        return self._execute_write("DELETE FROM alarms WHERE id = ?", (alarm_id,)) > 0

    # =========================================================================
    # 3. Courses (`courses`) & 4. Course Learning Logs (`course_logs`)
    # =========================================================================

    def add_course(
        self,
        title: str,
        instructor: str = "",
        total_modules: int = 10,
        completed_modules: int = 0,
        status: str = "active",
    ) -> int:
        return self._execute_insert(
            """
            INSERT INTO courses (title, instructor, total_modules, completed_modules, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, instructor, int(total_modules), int(completed_modules), status),
        )

    create_course = add_course

    def get_course(self, course_id: int) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM courses WHERE id = ?", (course_id,))

    def list_courses(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return self._fetch_all("SELECT * FROM courses WHERE status = ? ORDER BY id DESC", (status,))
        return self._fetch_all("SELECT * FROM courses ORDER BY id DESC")

    get_courses = list_courses

    def update_course(
        self,
        course_id: int,
        title: Optional[str] = None,
        instructor: Optional[str] = None,
        total_modules: Optional[int] = None,
        completed_modules: Optional[int] = None,
        status: Optional[str] = None,
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if instructor is not None:
            fields.append("instructor = ?")
            params.append(instructor)
        if total_modules is not None:
            fields.append("total_modules = ?")
            params.append(int(total_modules))
        if completed_modules is not None:
            fields.append("completed_modules = ?")
            params.append(int(completed_modules))
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if not fields:
            return False
        params.append(course_id)
        return self._execute_write(f"UPDATE courses SET {', '.join(fields)} WHERE id = ?", params) > 0

    update_course_progress = update_course

    def delete_course(self, course_id: int) -> bool:
        return self._execute_write("DELETE FROM courses WHERE id = ?", (course_id,)) > 0

    @staticmethod
    def _enrich_course_log_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        d = dict(row)
        raw_quiz = d.get("quiz_json", "[]")
        if isinstance(raw_quiz, str):
            try:
                d["quiz"] = json.loads(raw_quiz)
            except Exception:
                d["quiz"] = []
        else:
            d["quiz"] = raw_quiz
        return d

    def add_course_log(
        self,
        course_id: Optional[int] = None,
        topic: str = "",
        raw_reflection: str = "",
        structured_notes: str = "",
        quiz_json: Union[str, List[Any], Dict[str, Any]] = "[]",
        log_date: Optional[str] = None,
    ) -> int:
        date_val = log_date or datetime.now(DEFAULT_TIMEZONE).date().isoformat()
        if not isinstance(quiz_json, str):
            quiz_str = json.dumps(quiz_json)
        else:
            quiz_str = quiz_json

        return self._execute_insert(
            """
            INSERT INTO course_logs (course_id, log_date, topic, raw_reflection, structured_notes, quiz_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (course_id, date_val, topic, raw_reflection, structured_notes, quiz_str),
        )

    create_course_log = add_course_log
    log_course_session = add_course_log

    def get_course_log(self, log_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetch_one("SELECT * FROM course_logs WHERE id = ?", (log_id,))
        return self._enrich_course_log_row(row)

    def list_course_logs(self, course_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if course_id is not None:
            rows = self._fetch_all(
                "SELECT * FROM course_logs WHERE course_id = ? ORDER BY id DESC LIMIT ?",
                (course_id, limit),
            )
        else:
            rows = self._fetch_all("SELECT * FROM course_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [self._enrich_course_log_row(r) for r in rows if r is not None]

    get_course_logs = list_course_logs

    def get_latest_course_log(self, course_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        logs = self.list_course_logs(course_id=course_id, limit=1)
        return logs[0] if logs else None

    def delete_course_log(self, log_id: int) -> bool:
        return self._execute_write("DELETE FROM course_logs WHERE id = ?", (log_id,)) > 0

    # =========================================================================
    # 5. Business Deliverables (`business_deliverables`)
    # =========================================================================

    def add_business_deliverable(
        self,
        client_name: str,
        title: str,
        deadline: Optional[str] = None,
        estimated_hours: float = 1.0,
        impact_score: int = 5,
        status: str = "pending",
    ) -> int:
        return self._execute_insert(
            """
            INSERT INTO business_deliverables (
                client_name, title, deadline, estimated_hours, impact_score, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (client_name, title, deadline, float(estimated_hours), int(impact_score), status),
        )

    add_deliverable = add_business_deliverable
    create_business_deliverable = add_business_deliverable

    def get_business_deliverable(self, deliverable_id: int) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM business_deliverables WHERE id = ?", (deliverable_id,))

    get_deliverable = get_business_deliverable

    def list_business_deliverables(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return self._fetch_all(
                "SELECT * FROM business_deliverables WHERE status = ? ORDER BY impact_score DESC, deadline ASC, id DESC",
                (status,),
            )
        return self._fetch_all(
            "SELECT * FROM business_deliverables ORDER BY impact_score DESC, deadline ASC, id DESC"
        )

    get_business_deliverables = list_business_deliverables
    list_deliverables = list_business_deliverables

    def update_business_deliverable(
        self,
        deliverable_id: int,
        client_name: Optional[str] = None,
        title: Optional[str] = None,
        deadline: Optional[str] = None,
        estimated_hours: Optional[float] = None,
        impact_score: Optional[int] = None,
        status: Optional[str] = None,
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []
        if client_name is not None:
            fields.append("client_name = ?")
            params.append(client_name)
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if deadline is not None:
            fields.append("deadline = ?")
            params.append(deadline)
        if estimated_hours is not None:
            fields.append("estimated_hours = ?")
            params.append(float(estimated_hours))
        if impact_score is not None:
            fields.append("impact_score = ?")
            params.append(int(impact_score))
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if not fields:
            return False
        params.append(deliverable_id)
        return self._execute_write(f"UPDATE business_deliverables SET {', '.join(fields)} WHERE id = ?", params) > 0

    update_deliverable = update_business_deliverable

    def update_deliverable_status(self, deliverable_id: int, status: str) -> bool:
        return self.update_business_deliverable(deliverable_id, status=status)

    def delete_business_deliverable(self, deliverable_id: int) -> bool:
        return self._execute_write("DELETE FROM business_deliverables WHERE id = ?", (deliverable_id,)) > 0

    delete_deliverable = delete_business_deliverable

    # =========================================================================
    # 6. Autonomous Small-Task Buddy (`small_tasks`)
    # =========================================================================

    def add_small_task(
        self,
        prompt: str,
        task_type: str = "draft",
        result_content: str = "",
        status: str = "pending_review",
        created_at: Optional[str] = None,
    ) -> int:
        created_val = created_at or datetime.now(DEFAULT_TIMEZONE).isoformat()
        return self._execute_insert(
            """
            INSERT INTO small_tasks (prompt, task_type, result_content, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt, task_type, result_content, status, created_val),
        )

    create_small_task = add_small_task

    def get_small_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        return self._fetch_one("SELECT * FROM small_tasks WHERE id = ?", (task_id,))

    def list_small_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        if status:
            return self._fetch_all(
                "SELECT * FROM small_tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        return self._fetch_all("SELECT * FROM small_tasks ORDER BY id DESC LIMIT ?", (limit,))

    get_small_tasks = list_small_tasks

    def update_small_task(
        self,
        task_id: int,
        status: Optional[str] = None,
        result_content: Optional[str] = None,
    ) -> bool:
        fields: List[str] = []
        params: List[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if result_content is not None:
            fields.append("result_content = ?")
            params.append(result_content)
        if not fields:
            return False
        params.append(task_id)
        return self._execute_write(f"UPDATE small_tasks SET {', '.join(fields)} WHERE id = ?", params) > 0

    update_small_task_status = update_small_task

    def confirm_small_task(self, task_id: int) -> bool:
        return self.update_small_task(task_id, status="confirmed")

    def delete_small_task(self, task_id: int) -> bool:
        return self._execute_write("DELETE FROM small_tasks WHERE id = ?", (task_id,)) > 0

    # =========================================================================
    # Offline PWA Sync Payload Helper
    # =========================================================================

    def add_project(
        self,
        title: str,
        category: str = "project",
        goal: str = "",
        total_hours: float = 4.0,
        session_minutes: int = 60,
        priority: str = "medium",
        deadline: Optional[str] = None,
        status: str = "active",
    ) -> int:
        now = datetime.now(DEFAULT_TIMEZONE).isoformat()
        cat = "learning" if str(category).lower().strip() == "learning" else "project"
        return self._execute_insert(
            """
            INSERT INTO projects (
                title, category, goal, total_hours, session_minutes,
                priority, deadline, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                cat,
                goal.strip(),
                float(total_hours),
                int(session_minutes),
                priority.lower().strip(),
                deadline,
                status,
                now,
                now,
            ),
        )

    def list_projects(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category.lower().strip())
        if status:
            clauses.append("status = ?")
            params.append(status.lower().strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetch_all(
            f"SELECT * FROM projects {where} ORDER BY id DESC",
            tuple(params),
        )
        return [dict(r) for r in rows if r is not None]

    def update_project_status(self, project_id: int, status: str) -> bool:
        now = datetime.now(DEFAULT_TIMEZONE).isoformat()
        return (
            self._execute_write(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                (status.lower().strip(), now, int(project_id)),
            )
            > 0
        )

    def delete_project(self, project_id: int) -> bool:
        return self._execute_write("DELETE FROM projects WHERE id = ?", (int(project_id),)) > 0

    def propose_project_slots(
        self,
        total_hours: float = 4.0,
        session_minutes: int = 60,
        preferred_days: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Deterministically allocate weekday free slots for a project or learning goal
        using get_free_slots_for_day() without invoking any LLM for time math.
        """
        days = preferred_days or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        needed_mins = max(30, int(round(float(total_hours) * 60)))
        chunk_mins = max(30, min(180, int(session_minutes)))

        def _to_mins(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m[:2])

        def _to_hhmm(m: int) -> str:
            return f"{m // 60:02d}:{m % 60:02d}"

        def _to_12h(m: int) -> str:
            h = (m // 60) % 24
            mins = m % 60
            am_pm = "AM" if h < 12 else "PM"
            h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
            return f"{h12}:{mins:02d} {am_pm}"

        proposals: List[Dict[str, Any]] = []
        remaining = needed_mins
        for day in days:
            if remaining <= 0:
                break
            slots = self.get_free_slots_for_day(day)
            # Prefer evening/larger free slots first
            sorted_slots = sorted(slots, key=lambda s: s["duration_minutes"], reverse=True)
            for slot in sorted_slots:
                if remaining <= 0:
                    break
                s_min = _to_mins(slot["start"])
                e_min = _to_mins(slot["end"])
                alloc = min(chunk_mins, remaining, e_min - s_min)
                if alloc < 30:
                    continue
                end_alloc = s_min + alloc
                proposals.append(
                    {
                        "day": day,
                        "start": _to_hhmm(s_min),
                        "end": _to_hhmm(end_alloc),
                        "duration_minutes": alloc,
                        "label": f"{day} {_to_12h(s_min)} – {_to_12h(end_alloc)} ({alloc} min)",
                    }
                )
                remaining -= alloc
        return proposals

    def get_sync_payload(self) -> Dict[str, Any]:
        """Return full offline-cache payload for the PWA IndexedDB/localStorage sync."""
        tasks = self.list_tasks(limit=200)
        return {
            "reminders": tasks,
            "tasks": tasks,
            "weekly_routine": self.list_weekly_routine(),
            "routine_completions": self.list_routine_completions(),
            "projects": self.list_projects(),
            "alarms": self.list_alarms(),
            "courses": self.list_courses(),
            "course_logs": self.list_course_logs(limit=50),
            "business_deliverables": self.list_business_deliverables(),
            "small_tasks": self.list_small_tasks(limit=50),
            "backend": self.backend,
            "synced_at": datetime.now(DEFAULT_TIMEZONE).isoformat(),
        }


class ReminderStore(TaskStore):
    """Alias/subclass of TaskStore providing all ReminderStore and TaskStore interfaces."""

    pass
