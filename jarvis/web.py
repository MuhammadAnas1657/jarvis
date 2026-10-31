"""FastAPI application for Jarvis Control Center and Review Queue."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from jarvis.actions import ActionManager
from jarvis.briefing import DailyBriefing
from jarvis.config import load_config
from jarvis.extract import TaskExtractor
from jarvis.store import TaskStore


app = FastAPI(title="JARVIS Control Center", version="0.1.0")

store = TaskStore()
extractor = TaskExtractor()
briefing_engine = DailyBriefing(store=store)
action_mgr = ActionManager(store=store)
config = load_config()

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class QuickAddRequest(BaseModel):
    text: str


class ActionExecuteRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}
    confirmed: bool = False


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    html_file = TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None):
    return store.list_tasks(status=status)


@app.post("/api/tasks/{task_id}/confirm")
async def confirm_task(task_id: int):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = store.update_task_status(task_id, "confirmed")
    # Trigger CalDAV sync in background or best effort
    store.sync_to_caldav(task_id)
    return {"success": updated, "id": task_id, "status": "confirmed"}


@app.post("/api/tasks/{task_id}/reject")
async def reject_task(task_id: int):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = store.update_task_status(task_id, "rejected")
    return {"success": updated, "id": task_id, "status": "rejected"}


@app.post("/api/tasks/quick-add")
async def quick_add_task(req: QuickAddRequest):
    extracted = extractor.extract_tasks(req.text)
    created_ids = []
    for item in extracted:
        t_id = store.add_task(
            title=item["title"],
            description=item.get("description", ""),
            original_transcript=req.text,
            raw_due_text=item.get("raw_due_text", ""),
            due_datetime=item.get("due_datetime"),
            priority=item.get("priority", "normal"),
            status="pending_review",
            clarification_question=item.get("clarification_question"),
            recommendation=item.get("recommendation")
        )
        created_ids.append(t_id)

    return {"created_count": len(created_ids), "ids": created_ids}


@app.post("/api/briefing")
async def trigger_briefing():
    result = briefing_engine.generate_briefing()
    return result


@app.get("/api/status")
async def get_system_status():
    ollama_online = False
    try:
        r = requests.get(f"{config.ollama_url}/api/tags", timeout=1)
        ollama_online = (r.status_code == 200)
    except Exception:
        pass

    return {
        "status": "online",
        "profile": config.profile,
        "timezone": config.timezone,
        "ollama_online": ollama_online,
        "active_devices": {
            "stt": config.get_active_profile().stt.model_dump(),
            "llm": config.get_active_profile().llm.model_dump()
        }
    }


@app.post("/api/actions/execute")
async def execute_action(req: ActionExecuteRequest):
    result = action_mgr.execute_action(
        action_name=req.action,
        params=req.params,
        user_confirmed=req.confirmed
    )
    return result
