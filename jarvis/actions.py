"""Whitelisted and confirmation-guarded PC automation actions for Jarvis."""

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

from jarvis.store import TaskStore

# Strict system application map with absolute paths when possible
SYSTEM_ROOT = Path(os.environ.get("SystemRoot", "C:\\Windows"))
ALLOWED_APPLICATIONS = {
    "notepad": SYSTEM_ROOT / "System32" / "notepad.exe",
    "calc": SYSTEM_ROOT / "System32" / "calc.exe",
    "calculator": SYSTEM_ROOT / "System32" / "calc.exe",
    "explorer": SYSTEM_ROOT / "explorer.exe",
    "taskmgr": SYSTEM_ROOT / "System32" / "Taskmgr.exe",
    "code": "code",
    "vscode": "code",
    "chrome": "chrome",
    "edge": "msedge"
}

ALLOWED_FOLDER_ROOTS = [
    Path("C:\\projects").resolve(),
    Path(os.environ.get("USERPROFILE", "C:\\Users")).resolve()
]


class ActionManager:
    def __init__(self, store: Optional[TaskStore] = None):
        self.store = store or TaskStore()

    def get_system_status(self) -> Dict[str, Any]:
        """Read current CPU, RAM, and disk utilization securely."""
        cpu_pct = psutil.cpu_percent(interval=0.1) if psutil and hasattr(psutil, "cpu_percent") else 0
        mem = psutil.virtual_memory() if psutil and hasattr(psutil, "virtual_memory") else None
        disk = psutil.disk_usage("C:\\") if psutil and hasattr(psutil, "disk_usage") else None

        return {
            "cpu_percent": cpu_pct,
            "ram_used_gb": round(mem.used / (1024**3), 2) if mem else 0,
            "ram_total_gb": round(mem.total / (1024**3), 2) if mem else 0,
            "ram_percent": mem.percent if mem else 0,
            "disk_free_gb": round(disk.free / (1024**3), 2) if disk else 0
        }

    def execute_action(
        self,
        action_name: str,
        params: Dict[str, Any],
        user_confirmed: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a whitelisted action with strict security boundaries.
        Requires explicit user_confirmed=True.
        """
        if not user_confirmed:
            return {
                "status": "confirmation_required",
                "message": f"Action '{action_name}' requires explicit user confirmation in the UI.",
                "action": action_name,
                "params": params
            }

        action_clean = action_name.lower().strip()

        if action_clean == "open_app":
            app_key = str(params.get("app", "")).lower().strip()
            if app_key not in ALLOWED_APPLICATIONS:
                res = f"Denied: Application '{app_key}' is not in the whitelist."
                self.store.log_action(action_name, params, "rejected", res)
                return {"status": "error", "message": res}

            target_exec = ALLOWED_APPLICATIONS[app_key]
            exec_str = str(target_exec)

            # If absolute path, verify existence
            if isinstance(target_exec, Path) and not target_exec.exists():
                # Fallback to binary name
                exec_str = target_exec.name

            try:
                proc = subprocess.Popen([exec_str], shell=False)
                res = f"Launched {exec_str} (PID: {proc.pid})"
                self.store.log_action(action_name, params, "executed", res)
                return {"status": "success", "message": res, "pid": proc.pid}
            except Exception as e:
                res = f"Failed to launch {exec_str}: {e}"
                self.store.log_action(action_name, params, "failed", res)
                return {"status": "error", "message": res}

        elif action_clean == "open_folder":
            raw_path = str(params.get("path", "")).strip()
            if not raw_path:
                return {"status": "error", "message": "Missing path parameter"}

            target_path = Path(raw_path).resolve()
            if not target_path.exists() or not target_path.is_dir():
                res = f"Denied: Directory does not exist: {raw_path}"
                self.store.log_action(action_name, params, "rejected", res)
                return {"status": "error", "message": res}

            # Enforce folder boundary check
            is_allowed_root = any(
                target_path == root or root in target_path.parents
                for root in ALLOWED_FOLDER_ROOTS
            )
            if not is_allowed_root:
                res = f"Denied: Path {target_path} is outside allowed directories."
                self.store.log_action(action_name, params, "rejected", res)
                return {"status": "error", "message": res}

            try:
                subprocess.Popen(["explorer.exe", str(target_path)], shell=False)
                res = f"Opened folder: {target_path}"
                self.store.log_action(action_name, params, "executed", res)
                return {"status": "success", "message": res}
            except Exception as e:
                res = f"Failed to open folder: {e}"
                self.store.log_action(action_name, params, "failed", res)
                return {"status": "error", "message": res}

        elif action_clean == "get_system_status":
            stats = self.get_system_status()
            self.store.log_action(action_name, params, "executed", "Retrieved system stats")
            return {"status": "success", "stats": stats}

        elif action_clean == "schedule_free_slot":
            title = str(params.get("title") or "Scheduled Task").strip()
            day = str(params.get("day") or "Today").strip()
            start_time = str(params.get("start_time") or "20:00").strip()
            end_time = str(params.get("end_time") or "22:00").strip()
            target_date = str(params.get("target_date") or "").strip()
            priority = str(params.get("priority") or "high").strip()

            due_dt = f"{target_date}T{start_time}:00" if target_date else None
            task_id = self.store.add_task(
                title=title,
                description=f"Scheduled in free slot ({start_time} - {end_time}) on {day}",
                raw_due_text=f"{day} {start_time}",
                due_datetime=due_dt,
                priority=priority,
                status="confirmed"
            )
            msg = f"Scheduled '{title}' for {day} ({start_time} – {end_time})"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "task_id": task_id}

        elif action_clean == "create_reminder":
            title = str(params.get("title") or "Reminder").strip()
            raw_due = str(params.get("raw_due_text") or "").strip()
            due_dt = params.get("due_datetime")
            priority = str(params.get("priority") or "normal").strip()

            task_id = self.store.add_task(
                title=title,
                description=str(params.get("description") or ""),
                raw_due_text=raw_due,
                due_datetime=due_dt,
                priority=priority,
                status="confirmed"
            )
            msg = f"Created reminder '{title}'" + (f" due {raw_due}" if raw_due else "")
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "task_id": task_id}

        elif action_clean == "mark_routine":
            routine_id = int(params.get("routine_id", 0))
            date_str = str(params.get("date") or "").strip()
            title = str(params.get("title") or "Routine block")
            if not date_str:
                from datetime import datetime
                from jarvis.timeparse import DEFAULT_TIMEZONE
                date_str = datetime.now(DEFAULT_TIMEZONE).strftime("%Y-%m-%d")

            self.store.mark_routine_completion(routine_id=routine_id, date_str=date_str, completed=True)
            msg = f"Marked '{title}' as completed for {date_str}"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "routine_id": routine_id, "date": date_str}

        elif action_clean == "unmark_routine":
            routine_id = int(params.get("routine_id", 0))
            date_str = str(params.get("date") or "").strip()
            title = str(params.get("title") or "Routine block")
            if not date_str:
                from datetime import datetime
                from jarvis.timeparse import DEFAULT_TIMEZONE
                date_str = datetime.now(DEFAULT_TIMEZONE).strftime("%Y-%m-%d")

            self.store.mark_routine_completion(routine_id=routine_id, date_str=date_str, completed=False)
            msg = f"Unmarked '{title}' for {date_str}"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "routine_id": routine_id, "date": date_str}

        elif action_clean == "complete_reminder":
            task_id = int(params.get("task_id", 0))
            self.store.update_task_status(task_id, "completed")
            msg = f"Marked reminder #{task_id} as completed"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "task_id": task_id}

        elif action_clean == "delete_reminder":
            task_id = int(params.get("task_id", 0))
            self.store.delete_task(task_id)
            msg = f"Deleted reminder #{task_id}"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "task_id": task_id}

        elif action_clean == "add_routine_block":
            b_id = self.store.add_routine_block(
                day_of_week=params.get("day_of_week", "Daily"),
                title=params.get("title", "Routine Block"),
                start_time=params.get("start_time", "09:00"),
                end_time=params.get("end_time", "10:00"),
                category=params.get("category", "fixed"),
                is_locked=True
            )
            msg = f"Added routine block '{params.get('title')}' for {params.get('day_of_week')}"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "block_id": b_id}

        elif action_clean == "delete_routine_block":
            b_id = int(params.get("block_id", 0))
            self.store.delete_routine_block(b_id)
            msg = f"Deleted routine block #{b_id}"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "block_id": b_id}

        elif action_clean == "run_audit":
            from jarvis.routine_audit import audit_daily_routine
            blocks = self.store.list_weekly_routine(day_of_week=params.get("day_of_week", "Monday"))
            audit_res = audit_daily_routine(routine_blocks=blocks, proposed_tasks=[])
            msg = f"Audit complete: {audit_res.get('total_locked_minutes', 0)/60:.1f}h locked, {audit_res.get('true_free_minutes', 0)/60:.1f}h free"
            self.store.log_action(action_name, params, "executed", msg)
            return {"status": "success", "message": msg, "audit": audit_res}

        else:
            res = f"Denied: Unknown action '{action_name}'"
            self.store.log_action(action_name, params, "rejected", res)
            return {"status": "error", "message": res}
