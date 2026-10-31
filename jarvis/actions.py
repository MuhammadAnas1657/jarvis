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

        else:
            res = f"Denied: Unknown action '{action_name}'"
            self.store.log_action(action_name, params, "rejected", res)
            return {"status": "error", "message": res}
