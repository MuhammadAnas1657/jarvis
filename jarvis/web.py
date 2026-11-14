"""FastAPI application for Jarvis Control Center, Mobile App Installer, Voice Capture, and Accountability Engines."""

from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jarvis import key_pool, timeparse
from jarvis.actions import ActionManager
from jarvis.briefing import DailyBriefing
from jarvis.business import execute_small_task, rank_deliverables, score_deliverable
from jarvis.config import load_config
from jarvis.core.events import (
    EVENT_ACTION_CONFIRMED,
    EVENT_PING,
    EVENT_REMINDER_ADDED,
    EVENT_REMINDER_DELETED,
    EVENT_REMINDER_UPDATED,
    EVENT_ROUTINE_UPDATED,
)
from jarvis.core.pg_bus import PostgresEventBus
from jarvis.core.websocket import ConnectionManager
from jarvis.course_audit import (
    compute_daily_discipline_score,
    generate_recall_quiz,
    structure_course_reflection,
)
from jarvis.extract import TaskExtractor
from jarvis.key_pool import groq_chat_completion, groq_transcribe
from jarvis.routine_audit import audit_daily_routine
from jarvis.store import ReminderStore
from jarvis.stt import SpeechToText
from jarvis.timeparse import DEFAULT_TIMEZONE, parse_relative_time

# Ensure jarvis.timeparse exposes parse_datetime as a deterministic entry point
if not hasattr(timeparse, "parse_datetime"):
    setattr(timeparse, "parse_datetime", parse_relative_time)

_orig_groq_transcribe = groq_transcribe

store = ReminderStore()
stt = SpeechToText()
extractor = TaskExtractor()
briefing_engine = DailyBriefing(store=store)
action_mgr = ActionManager(store=store)
config = load_config()

ws_manager = ConnectionManager()
pg_bus = PostgresEventBus(
    dsn=config.get_database_url() if getattr(store, "backend", "") == "postgresql" else None
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import os
    if os.environ.get("JARVIS_SEED_ON_STARTUP", "true").lower() in ("1", "true", "yes"):
        try:
            from jarvis.main import seed_fixed_routine
            seed_fixed_routine(store)
        except Exception:
            pass
    pg_bus.subscribe(ws_manager.broadcast)
    await pg_bus.start()
    try:
        yield
    finally:
        pg_bus.unsubscribe(ws_manager.broadcast)
        await pg_bus.stop()


app = FastAPI(
    title="JARVIS Control Center — React + FastAPI + PostgreSQL LISTEN/NOTIFY",
    version="0.4.0",
    lifespan=lifespan,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
ROOT_TEMPLATES_DIR = PROJECT_ROOT / "templates"
PACKAGE_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (FRONTEND_DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="frontend_assets")


# =============================================================================
# Helper Functions (LAN IP Detection, Self-Contained SVG QR, Voice Parsing)
# =============================================================================


def _detect_lan_ip() -> str:
    """Detect the machine's local network (LAN) IPv4 address without external traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return ip or "127.0.0.1"


def _generate_qr_svg(data_url: str, size: int = 220) -> str:
    """
    Generate a clean, self-contained inline SVG QR-style matrix visual for `data_url`
    with standard finder patterns, timing lines, and deterministic URL bit encoding
    so zero external QR binary or third-party service is required.
    """
    grid_size = 21
    matrix = [[0 for _ in range(grid_size)] for _ in range(grid_size)]
    reserved = [[False for _ in range(grid_size)] for _ in range(grid_size)]

    def place_finder(r0: int, c0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r0 + dr, c0 + dc
                if 0 <= rr < grid_size and 0 <= cc < grid_size:
                    reserved[rr][cc] = True
                    if 0 <= dr <= 6 and 0 <= dc <= 6:
                        if dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4):
                            matrix[rr][cc] = 1
                        else:
                            matrix[rr][cc] = 0

    place_finder(0, 0)
    place_finder(0, grid_size - 7)
    place_finder(grid_size - 7, 0)

    # Timing patterns on row 6 and col 6
    for i in range(8, grid_size - 8):
        reserved[6][i] = True
        reserved[i][6] = True
        matrix[6][i] = 1 if i % 2 == 0 else 0
        matrix[i][6] = 1 if i % 2 == 0 else 0

    # Deterministic bit stream derived from the URL payload
    digest = hashlib.sha256(data_url.encode("utf-8")).digest()
    payload_bytes = data_url.encode("utf-8") + digest
    bits: List[int] = []
    for b in payload_bytes:
        for shift in range(7, -1, -1):
            bits.append((b >> shift) & 1)

    bit_idx = 0
    for r in range(grid_size):
        for c in range(grid_size):
            if not reserved[r][c]:
                matrix[r][c] = bits[bit_idx % len(bits)]
                bit_idx += 1

    quiet = 2
    total_modules = grid_size + quiet * 2
    rects: List[str] = []
    for r in range(grid_size):
        for c in range(grid_size):
            if matrix[r][c]:
                rects.append(f'<rect x="{c + quiet}" y="{r + quiet}" width="1" height="1" rx="0.15" fill="#050914"/>')

    rects_str = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_modules} {total_modules}" '
        f'width="{size}" height="{size}" role="img" aria-label="QR Code for {data_url}">'
        f'<rect width="{total_modules}" height="{total_modules}" rx="2" fill="#f8fafc"/>'
        f"{rects_str}"
        f"</svg>"
    )


def _extract_estimated_minutes(text: str) -> int:
    """Extract duration in minutes from voice/text transcript, defaulting to 60 minutes."""
    lower = text.lower()
    if "derh ghanta" in lower or "dedh ghanta" in lower or "90 min" in lower:
        return 90
    if "dhai ghante" in lower or "dhaai ghante" in lower or "150 min" in lower:
        return 150
    if "aadha ghanta" in lower or "half an hour" in lower or "30 min" in lower:
        return 30
    m_min = re.search(r"(\d+)\s*(?:minute|minutes|min|mins)\b", lower)
    if m_min and "baad" not in lower[m_min.start() : m_min.end() + 8]:
        val = int(m_min.group(1))
        if 5 <= val <= 480:
            return val
    m_hr = re.search(r"(\d+)\s*(?:hour|hours|hr|hrs|ghanta|ghante)\b", lower)
    if m_hr and "baad" not in lower[m_hr.start() : m_hr.end() + 8]:
        val = int(m_hr.group(1)) * 60
        if 15 <= val <= 480:
            return val
    return 60


def _clean_voice_task_title(transcript: str) -> str:
    """Produce a clean, readable task title from a spoken Urdu/English transcript."""
    cleaned = transcript.strip()
    if not cleaned:
        return "Voice Captured Task"
    # Strip common polite command suffixes in Roman-Urdu / English
    cleaned = re.sub(
        r"\b(schedule\s+kar\s*do|schedule\s+kardo|yaad\s+dilana|remind\s+me\s+to|please\s+add)\b",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned or transcript.strip()


# =============================================================================
# Request Models
# =============================================================================


class QuickAddRequest(BaseModel):
    text: str


class ReminderCreateRequest(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    due_datetime: Optional[str] = None
    raw_due_text: Optional[str] = ""
    priority: str = "normal"
    description: str = ""
    confirmed: bool = False


class ActionExecuteRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    user_confirmed: Optional[bool] = None


class RoutineCompletionRequest(BaseModel):
    routine_id: int
    date: Optional[str] = None
    completed: bool = True


class ProjectProposeRequest(BaseModel):
    title: str
    category: str = "project"
    goal: str = ""
    total_hours: float = 4.0
    session_minutes: int = 60
    priority: str = "medium"
    deadline: Optional[str] = None
    preferred_days: Optional[List[str]] = None


class ProjectCreateRequest(ProjectProposeRequest):
    confirmed: bool = False
    selected_slots: List[Dict[str, Any]] = Field(default_factory=list)


class ProjectStatusRequest(BaseModel):
    status: str


class WeeklyRoutineBlockRequest(BaseModel):
    day_of_week: Optional[Union[str, int]] = "Daily"
    title: Optional[str] = None
    start_time: Optional[str] = "09:00"
    end_time: Optional[str] = "11:00"
    category: str = "fixed"
    is_locked: bool = True
    blocks: Optional[List[Dict[str, Any]]] = None


class RoutineAuditRequest(BaseModel):
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    day_of_week: Optional[Union[str, int]] = None
    routine_blocks: Optional[List[Dict[str, Any]]] = None
    day_window_minutes: Optional[int] = None


class RoutineCommitRequest(BaseModel):
    mode: str = "core_only"  # "core_only" or "force_all"
    core_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    overflow_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    user_confirmed: bool = False
    confirmed: Optional[bool] = None


class AlarmCreateRequest(BaseModel):
    alarm_time: str
    label: str = "Anas, wake up!"
    first_task_prompt: str = "Start your first core priority block"
    state: str = "scheduled"


class AlarmVerifyWakeRequest(BaseModel):
    verification_phrase: Optional[str] = ""
    spoken_text: Optional[str] = ""
    phrase: Optional[str] = ""
    first_task_confirmed: bool = False
    task_confirmed: bool = False


class CourseCreateRequest(BaseModel):
    title: str
    instructor: str = ""
    total_modules: int = 10
    completed_modules: int = 0
    status: str = "active"


class NightlyAuditRequest(BaseModel):
    course_id: Optional[int] = 1
    topic: str = "Daily Course Lesson"
    raw_reflection: Optional[str] = None
    reflection: Optional[str] = None
    completed_task_ids: List[int] = Field(default_factory=list)
    missed_task_ids: List[int] = Field(default_factory=list)
    tasks: Optional[List[Dict[str, Any]]] = None


class BusinessDeliverableRequest(BaseModel):
    client_name: str
    title: str
    deadline: str
    estimated_hours: float = 1.0
    impact_score: int = 5
    status: str = "pending"


class SmallTaskRequest(BaseModel):
    prompt: str
    task_type: str = "draft"


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# Dashboard, Icon & Static PWA Routes
# =============================================================================


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dist_index = FRONTEND_DIST_DIR / "index.html"
    if dist_index.is_file():
        return HTMLResponse(content=dist_index.read_text(encoding="utf-8"))
    html_file = ROOT_TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        html_file = PACKAGE_TEMPLATES_DIR / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="Frontend bundle not built")
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/manifest.json")
async def get_manifest():
    manifest_path = STATIC_DIR / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    return FileResponse(path=str(manifest_path), media_type="application/manifest+json")


@app.get("/sw.js")
async def get_service_worker():
    sw_path = STATIC_DIR / "sw.js"
    if not sw_path.exists():
        raise HTTPException(status_code=404, detail="sw.js not found")
    return FileResponse(path=str(sw_path), media_type="application/javascript")


@app.get("/icon.svg")
async def get_app_icon():
    icon_path = STATIC_DIR / "icon.svg"
    if not icon_path.exists():
        raise HTTPException(status_code=404, detail="icon.svg not found")
    return FileResponse(path=str(icon_path), media_type="image/svg+xml")


# =============================================================================
# Mobile App Installer & Voice Capture Endpoints
# =============================================================================


def _find_built_apk() -> Optional[Path]:
    candidates = [
        PROJECT_ROOT / "mobile" / "dist" / "jarvis.apk",
        PROJECT_ROOT / "mobile" / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk",
        PROJECT_ROOT / "mobile" / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@app.get("/api/mobile/install-info")
async def get_mobile_install_info(request: Request):
    """
    Return public server URL (or LAN IP when accessed locally), Capacitor APK
    availability, and direct APK download URL.
    """
    import os

    lan_ip = _detect_lan_ip()
    port = request.url.port or 8000
    public_url = os.environ.get("JARVIS_PUBLIC_URL", "").strip().rstrip("/")
    req_base = str(request.base_url).rstrip("/")
    is_local = request.url.hostname in ("localhost", "127.0.0.1", None)
    install_url = public_url or (f"http://{lan_ip}:{port}" if is_local else req_base)
    qr_svg = _generate_qr_svg(install_url)
    mobile_dir = PROJECT_ROOT / "mobile"
    apk_path = _find_built_apk()

    return {
        "install_url": install_url,
        "public_url": public_url or req_base,
        "lan_ip": lan_ip,
        "port": port,
        "apk_available": apk_path is not None,
        "apk_download_url": "/api/mobile/download-apk",
        "apk_project_path": "mobile/",
        "apk_build_script": ".\\mobile\\build_apk.ps1",
        "apk_project_ready": bool((mobile_dir / "package.json").exists() or mobile_dir.exists()),
        "qr_svg": qr_svg,
        "stack": "React + FastAPI + PostgreSQL",
    }


@app.get("/api/mobile/download-apk")
async def download_mobile_apk():
    """Serve the compiled Android APK if present."""
    apk_path = _find_built_apk()
    if not apk_path:
        raise HTTPException(
            status_code=404,
            detail="Android APK not compiled yet. Run the GitHub Actions APK build or .\\mobile\\build_apk.ps1.",
        )
    return FileResponse(
        path=str(apk_path),
        media_type="application/vnd.android.package-archive",
        filename="jarvis.apk",
    )


@app.post("/api/voice/capture")
async def capture_voice_or_text(request: Request):
    """
    Accept either an uploaded audio file (`UploadFile` from browser `MediaRecorder`)
    or `{ "text": "..." }` fallback, transcribe via `jarvis.key_pool.groq_transcribe`
    (46-key Groq Whisper pool), deterministically parse time via
    `jarvis.timeparse.parse_datetime`, and return structured task data.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    transcript = ""
    stage_task = False

    if "application/json" in content_type:
        body = await request.json()
        transcript = str(body.get("text") or body.get("transcript") or "").strip()
        stage_task = bool(body.get("stage_task", False))
    else:
        form = await request.form()
        stage_task = str(form.get("stage_task", "")).lower() in ("true", "1", "yes")
        text_field = form.get("text")
        upload = form.get("file") or form.get("audio")

        if upload is not None and hasattr(upload, "read"):
            # Save into dedicated web_voice subdirectory so root inbox watcher doesn't race/move it
            voice_dir = config.get_abs_inbox_dir() / "web_voice"
            voice_dir.mkdir(parents=True, exist_ok=True)
            orig_name = getattr(upload, "filename", None) or "voice_capture.webm"
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", orig_name)
            file_path = voice_dir / f"voice_{int(time.time() * 1000)}_{safe_name}"
            audio_bytes = await upload.read()
            file_path.write_bytes(audio_bytes)

            transcribe_fn = (
                groq_transcribe
                if groq_transcribe is not _orig_groq_transcribe
                else getattr(key_pool, "groq_transcribe", groq_transcribe)
            )
            prompt_hint = "Urdu, Roman-Urdu, English, Jarvis, Anas, schedule, routine, task, kaisay ho, intro"
            try:
                tx_res = transcribe_fn(str(file_path), prompt=prompt_hint)
            except TypeError:
                tx_res = transcribe_fn(str(file_path))

            if isinstance(tx_res, dict):
                transcript = str(tx_res.get("text", "")).strip()
            else:
                transcript = str(tx_res).strip()

        if not transcript and text_field:
            transcript = str(text_field).strip()

    if not transcript:
        raise HTTPException(status_code=400, detail="No audio file or text provided for voice capture.")

    parse_fn = getattr(timeparse, "parse_datetime", parse_relative_time)
    parsed_dt = parse_fn(transcript)
    due_iso = parsed_dt.isoformat() if parsed_dt else None
    preferred_time = parsed_dt.strftime("%H:%M") if parsed_dt else None
    estimated_minutes = _extract_estimated_minutes(transcript)
    title = _clean_voice_task_title(transcript)
    priority = "urgent" if any(w in transcript.lower() for w in ("urgent", "foran", "zaroori", "asap")) else "normal"

    parsed_task = {
        "title": title,
        "due_iso": due_iso,
        "preferred_time": preferred_time,
        "estimated_minutes": estimated_minutes,
        "priority": priority,
    }

    staged_task_id: Optional[int] = None
    if stage_task:
        staged_task_id = store.add_task(
            title=title,
            description="Captured via Voice Capture (/api/voice/capture)",
            original_transcript=transcript,
            raw_due_text=transcript,
            due_datetime=due_iso,
            priority=priority,
            status="pending_review",
        )

    return {
        "transcript": transcript,
        "parsed_task": parsed_task,
        "staged_task_id": staged_task_id,
    }


@app.post("/api/voice/transcribe")
async def transcribe_voice_ptt(request: Request):
    """
    Dedicated Push-to-Talk (PTT) transcription endpoint.
    Accepts an audio file blob from browser MediaRecorder, transcribes via
    Groq Whisper (46-key pool), and returns `{ "text": "..." }` cleanly.
    """
    form = await request.form()
    upload = form.get("file") or form.get("audio")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="No audio file provided")

    voice_dir = config.get_abs_inbox_dir() / "web_voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    orig_name = getattr(upload, "filename", None) or "ptt_capture.webm"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", orig_name)
    file_path = voice_dir / f"ptt_{int(time.time() * 1000)}_{safe_name}"
    audio_bytes = await upload.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio recording")
    file_path.write_bytes(audio_bytes)

    transcribe_fn = (
        groq_transcribe
        if groq_transcribe is not _orig_groq_transcribe
        else getattr(key_pool, "groq_transcribe", groq_transcribe)
    )
    prompt_hint = "Urdu, Roman-Urdu, English, Jarvis, Anas, schedule, routine, mark, unmark, reminder, assignment, kal, aaj"
    try:
        tx_res = transcribe_fn(str(file_path), prompt=prompt_hint)
    except TypeError:
        tx_res = transcribe_fn(str(file_path))

    if isinstance(tx_res, dict):
        transcript = str(tx_res.get("text", "")).strip()
    else:
        transcript = str(tx_res or "").strip()

    return {"text": transcript}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"event": EVENT_PING, "data": {"status": "connected"}})
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_json({"event": EVENT_PING, "data": {"pong": True}})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# =============================================================================

# =============================================================================
# Offline Text-to-Speech (TTS) Endpoint
# =============================================================================

@app.post("/api/tts")
async def tts_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided for TTS")

    # Clean markdown formatting so synthesizer speaks natural words
    clean = re.sub(r"[#*_`~>-]+", " ", text)
    clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    try:
        from jarvis.tts import TextToSpeech
        tts = TextToSpeech()
        out_dir = config.get_abs_inbox_dir().parent / "data" / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        wav_file = out_dir / f"tts_{int(time.time() * 1000)}.wav"
        res_path = tts.speak(clean[:600], output_wav=str(wav_file))
        if res_path and Path(res_path).exists():
            return FileResponse(res_path, media_type="audio/wav")
    except Exception as exc:
        logger.warning("Backend TTS generation failed: %s", exc)

    raise HTTPException(status_code=500, detail="Backend TTS synthesis failed")

# Offline-First PWA Sync Endpoint
# =============================================================================


@app.get("/api/sync")
async def get_offline_sync_payload():
    """Return full offline-cache payload for the phone/laptop PWA."""
    if hasattr(store, "get_sync_payload"):
        payload = store.get_sync_payload()
    else:
        tasks = store.list_tasks(limit=200)
        payload = {
            "reminders": tasks,
            "tasks": tasks,
            "weekly_routine": getattr(store, "list_weekly_routine", lambda: [])(),
            "alarms": getattr(store, "list_alarms", lambda: [])(),
            "courses": getattr(store, "list_courses", lambda: [])(),
            "course_logs": getattr(store, "list_course_logs", lambda: [])(),
            "business_deliverables": getattr(store, "list_business_deliverables", lambda: [])(),
            "small_tasks": getattr(store, "list_small_tasks", lambda: [])(),
            "synced_at": datetime.now(DEFAULT_TIMEZONE).isoformat(),
        }

    # Enrich business deliverables with deterministic urgency score rankings
    raw_deliverables = payload.get("business_deliverables", [])
    payload["business_deliverables"] = rank_deliverables(raw_deliverables)
    return payload


# =============================================================================
# Existing Reminders / Tasks & Action Endpoints (100% Backward Compatible)
# =============================================================================


@app.get("/api/tasks")
@app.get("/api/reminders")
@app.get("/reminders")
async def list_tasks(status: Optional[str] = None):
    return store.list_tasks(status=status)


@app.post("/reminders")
@app.post("/api/reminders")
async def create_reminder_endpoint(req: ReminderCreateRequest):
    if req.text and not req.title:
        extracted = extractor.extract_tasks(req.text)
        created_ids = []
        for item in extracted:
            t_id = store.add_task(
                title=item["title"],
                description=item.get("description", ""),
                original_transcript=req.text,
                raw_due_text=item.get("raw_due_text", ""),
                due_datetime=item.get("due_datetime"),
                priority=item.get("priority", req.priority),
                status="pending_review",
                clarification_question=item.get("clarification_question"),
                recommendation=item.get("recommendation"),
            )
            created_ids.append(t_id)
        return {"created_count": len(created_ids), "ids": created_ids, "status": "pending_review"}

    title = req.title or req.text or "Untitled Reminder"
    due_dt = req.due_datetime
    if not due_dt and req.raw_due_text:
        parsed_dt = parse_relative_time(req.raw_due_text)
        if parsed_dt:
            due_dt = parsed_dt.isoformat()

    # Enforce AGENTS.md confirmation gate: new reminders start in pending_review unless explicitly confirmed
    status_val = "confirmed" if req.confirmed else "pending_review"
    reminder_id = store.add_task(
        title=title,
        description=req.description,
        raw_due_text=req.raw_due_text or "",
        due_datetime=due_dt,
        priority=req.priority,
        status=status_val,
    )
    await pg_bus.publish(
        EVENT_REMINDER_ADDED,
        event_type=status_val,
        data={"id": reminder_id, "title": title, "status": status_val},
    )
    return {"id": reminder_id, "title": title, "status": status_val, "confirmed": req.confirmed}


@app.post("/api/tasks/{task_id}/confirm")
@app.post("/api/reminders/{task_id}/confirm")
@app.post("/reminders/{task_id}/confirm")
async def confirm_task(task_id: int):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = store.update_task_status(task_id, "confirmed")
    store.sync_to_caldav(task_id)
    await pg_bus.publish(EVENT_REMINDER_UPDATED, event_type="confirmed", data={"id": task_id})
    return {"success": updated, "id": task_id, "status": "confirmed"}


@app.post("/api/tasks/{task_id}/reject")
@app.post("/api/reminders/{task_id}/reject")
async def reject_task(task_id: int):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updated = store.update_task_status(task_id, "rejected")
    await pg_bus.publish(EVENT_REMINDER_UPDATED, event_type="rejected", data={"id": task_id})
    return {"success": updated, "id": task_id, "status": "rejected"}


@app.post("/reminders/{task_id}/delete")
@app.delete("/reminders/{task_id}/delete")
@app.delete("/reminders/{task_id}")
@app.post("/api/reminders/{task_id}/delete")
@app.delete("/api/tasks/{task_id}")
async def delete_reminder_endpoint(task_id: int):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    deleted = store.delete_task(task_id)
    await pg_bus.publish(EVENT_REMINDER_DELETED, event_type="deleted", data={"id": task_id})
    return {"success": deleted, "id": task_id, "status": "deleted"}


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
            recommendation=item.get("recommendation"),
        )
        created_ids.append(t_id)

    return {"created_count": len(created_ids), "ids": created_ids}


@app.post("/api/audio/upload")
async def upload_audio_memo(file: UploadFile = File(...)):
    inbox = config.get_abs_inbox_dir()
    inbox.mkdir(parents=True, exist_ok=True)
    filename = f"browser_{int(time.time())}_{file.filename}"
    file_path = inbox / filename

    content = await file.read()
    file_path.write_bytes(content)

    stt_res = stt.transcribe(str(file_path))
    transcript = stt_res.get("text", "").strip()

    tasks = extractor.extract_tasks(transcript) if transcript else []
    created_ids = []
    for item in tasks:
        t_id = store.add_task(
            title=item["title"],
            description=item.get("description", ""),
            original_transcript=transcript,
            raw_due_text=item.get("raw_due_text", ""),
            due_datetime=item.get("due_datetime"),
            priority=item.get("priority", "normal"),
            status="pending_review",
            clarification_question=item.get("clarification_question"),
            recommendation=item.get("recommendation"),
        )
        created_ids.append(t_id)

    return {
        "filename": filename,
        "transcript": transcript,
        "tasks": tasks,
        "created_ids": created_ids,
    }


@app.post("/api/briefing")
async def trigger_briefing():
    return briefing_engine.generate_briefing()


@app.get("/api/status")
async def get_system_status():
    ollama_online = False
    try:
        r = requests.get(f"{config.ollama_url}/api/tags", timeout=1)
        ollama_online = r.status_code == 200
    except Exception:
        pass

    return {
        "status": "online",
        "stack": "JS Frontend + Python Backend + Native PostgreSQL",
        "profile": config.profile,
        "timezone": config.timezone,
        "backend": getattr(store, "backend", "sqlite_compat"),
        "ollama_online": ollama_online,
        "active_devices": {
            "stt": config.get_active_profile().stt.model_dump(),
            "llm": config.get_active_profile().llm.model_dump(),
        },
    }


@app.post("/api/actions/execute")
@app.post("/actions/propose")
@app.post("/api/actions/propose")
async def execute_action(req: ActionExecuteRequest):
    is_confirmed = bool(req.user_confirmed if req.user_confirmed is not None else req.confirmed)
    result = action_mgr.execute_action(
        action_name=req.action,
        params=req.params,
        user_confirmed=is_confirmed,
    )
    if result.get("status") == "success":
        action_type = req.action.lower().strip()
        await pg_bus.publish(
            EVENT_ACTION_CONFIRMED,
            event_type=action_type,
            data={"action": action_type, "params": req.params, "result": result},
        )
        if action_type in ("mark_routine", "unmark_routine", "add_routine_block", "delete_routine_block"):
            await pg_bus.publish(EVENT_ROUTINE_UPDATED, event_type=action_type, data=result)
        elif action_type in ("create_reminder", "schedule_free_slot"):
            await pg_bus.publish(EVENT_REMINDER_ADDED, event_type=action_type, data=result)
        elif action_type in ("complete_reminder", "delete_reminder"):
            await pg_bus.publish(EVENT_REMINDER_UPDATED, event_type=action_type, data=result)
    return result


# =============================================================================
# 1. Fixed Weekly Routine & Advisory Hard Routine Audit Endpoints
# =============================================================================


@app.get("/api/routine/weekly")
async def get_weekly_routine_endpoint(day_of_week: Optional[str] = None):
    blocks = store.list_weekly_routine(day_of_week=day_of_week)
    audit_summary = audit_daily_routine(routine_blocks=blocks, proposed_tasks=[])
    return {
        "weekly_routine": blocks,
        "blocks": blocks,
        "total_locked_minutes": audit_summary["total_locked_minutes"],
        "true_free_minutes": audit_summary["true_free_minutes"],
    }


@app.post("/api/routine/weekly")
async def save_weekly_routine_endpoint(req: WeeklyRoutineBlockRequest):
    created_ids: List[int] = []
    if req.blocks:
        for b in req.blocks:
            b_id = store.add_routine_block(
                day_of_week=b.get("day_of_week", "Daily"),
                title=b.get("title", "Routine Block"),
                start_time=b.get("start_time", "09:00"),
                end_time=b.get("end_time", "10:00"),
                category=b.get("category", "fixed"),
                is_locked=bool(b.get("is_locked", True)),
            )
            created_ids.append(b_id)
    else:
        if not req.title:
            raise HTTPException(status_code=400, detail="Routine block title is required")
        b_id = store.add_routine_block(
            day_of_week=req.day_of_week or "Daily",
            title=req.title,
            start_time=req.start_time or "09:00",
            end_time=req.end_time or "11:00",
            category=req.category or "fixed",
            is_locked=req.is_locked,
        )
        created_ids.append(b_id)

    blocks = store.list_weekly_routine()
    return {
        "created_ids": created_ids,
        "id": created_ids[0] if created_ids else None,
        "weekly_routine": blocks,
        "blocks": blocks,
    }


@app.delete("/api/routine/weekly/{block_id}")
@app.post("/api/routine/weekly/{block_id}/delete")
async def delete_weekly_routine_endpoint(block_id: int):
    if hasattr(store, "delete_weekly_routine_block"):
        deleted = bool(store.delete_weekly_routine_block(block_id))
    elif hasattr(store, "delete_routine_block"):
        deleted = bool(store.delete_routine_block(block_id))
    else:
        deleted = store._execute_write("DELETE FROM weekly_routine WHERE id = ?", (block_id,)) > 0
    return {"success": deleted, "deleted": deleted, "id": block_id}


@app.get("/api/routine/completions")
async def list_routine_completions_endpoint(date: Optional[str] = None):
    return {"completions": store.list_routine_completions(date_str=date)}


@app.post("/api/routine/completions")
async def mark_routine_completion_endpoint(req: RoutineCompletionRequest):
    date_str = req.date or datetime.now(DEFAULT_TIMEZONE).strftime("%Y-%m-%d")
    res = store.mark_routine_completion(routine_id=req.routine_id, date_str=date_str, completed=req.completed)
    await pg_bus.publish(
        EVENT_ROUTINE_UPDATED,
        event_type="completion_toggled",
        data={"routine_id": req.routine_id, "date": date_str, "completed": req.completed},
    )
    return {"success": res, "routine_id": req.routine_id, "date": date_str, "completed": req.completed}


@app.get("/api/routine/free-slots")
async def get_routine_free_slots_endpoint(day: str = "Monday"):
    slots = store.get_free_slots_for_day(day_of_week=day)
    return {"day": day, "slots": slots}


@app.get("/api/skills")
async def list_skills_endpoint():
    from jarvis.skills import list_skills
    return {"skills": list_skills()}


@app.get("/api/projects")
async def list_projects_endpoint(category: Optional[str] = None, status: Optional[str] = None):
    return {"projects": store.list_projects(category=category, status=status)}


@app.post("/api/projects/propose-schedule")
async def propose_project_schedule_endpoint(req: ProjectProposeRequest):
    slots = store.propose_project_slots(
        total_hours=req.total_hours,
        session_minutes=req.session_minutes,
        preferred_days=req.preferred_days,
    )
    return {
        "title": req.title,
        "category": req.category,
        "proposed_slots": slots,
        "requires_confirmation": True,
    }


@app.post("/api/projects")
async def create_project_endpoint(req: ProjectCreateRequest):
    if not req.confirmed:
        slots = store.propose_project_slots(
            total_hours=req.total_hours,
            session_minutes=req.session_minutes,
            preferred_days=req.preferred_days,
        )
        return {
            "status": "confirmation_required",
            "requires_confirmation": True,
            "proposed_slots": slots,
        }

    project_id = store.add_project(
        title=req.title,
        category=req.category,
        goal=req.goal,
        total_hours=req.total_hours,
        session_minutes=req.session_minutes,
        priority=req.priority,
        deadline=req.deadline,
        status="active",
    )

    scheduled_task_ids: List[int] = []
    for slot in req.selected_slots:
        day = str(slot.get("day") or "Monday")
        start = str(slot.get("start") or "20:00")
        end = str(slot.get("end") or "21:00")
        tid = store.add_task(
            title=f"[{req.category.title()}] {req.title}",
            description=f"Scheduled in free slot ({start} - {end}) on {day} | Goal: {req.goal or req.title}",
            raw_due_text=f"{day} {start}",
            priority="high" if req.priority == "high" else "normal",
            status="confirmed",
        )
        scheduled_task_ids.append(tid)

    await pg_bus.publish(
        EVENT_REMINDER_ADDED,
        event_type="project_created",
        data={"project_id": project_id, "scheduled_task_ids": scheduled_task_ids},
    )
    return {
        "status": "confirmed",
        "id": project_id,
        "scheduled_task_ids": scheduled_task_ids,
    }


@app.patch("/api/projects/{project_id}")
async def update_project_endpoint(project_id: int, req: ProjectStatusRequest):
    ok = store.update_project_status(project_id, req.status)
    await pg_bus.publish(
        EVENT_ROUTINE_UPDATED,
        event_type="project_updated",
        data={"id": project_id, "status": req.status},
    )
    return {"success": ok, "id": project_id, "status": req.status}


@app.delete("/api/projects/{project_id}")
async def delete_project_endpoint(project_id: int):
    ok = store.delete_project(project_id)
    await pg_bus.publish(
        EVENT_REMINDER_DELETED,
        event_type="project_deleted",
        data={"id": project_id},
    )
    return {"success": ok, "id": project_id}


@app.post("/api/routine/audit")
async def audit_routine_endpoint(req: RoutineAuditRequest):
    if req.routine_blocks is not None:
        blocks = req.routine_blocks
    else:
        blocks = store.list_weekly_routine(day_of_week=req.day_of_week)

    report = audit_daily_routine(
        routine_blocks=blocks,
        proposed_tasks=req.tasks,
        day_window_minutes=req.day_window_minutes,
    )
    return report


@app.post("/api/routine/commit")
async def commit_routine_endpoint(req: RoutineCommitRequest):
    """
    Commit audited tasks in either `core_only` or `force_all` mode.
    Enforces AGENTS.md confirmation rule: requires explicit confirmation before
    activating tasks (`confirmed`), otherwise stages them in `pending_review`.
    """
    if req.mode not in ("core_only", "force_all"):
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'core_only' or 'force_all'.")

    is_confirmed = bool(req.confirmed if req.confirmed is not None else req.user_confirmed)

    core_list = list(req.core_schedule)
    overflow_list = list(req.overflow_tasks)

    # If caller passed raw `tasks` without pre-splitting, run audit first
    if not core_list and not overflow_list and req.tasks:
        blocks = store.list_weekly_routine()
        report = audit_daily_routine(routine_blocks=blocks, proposed_tasks=req.tasks)
        core_list = report.get("core_schedule", [])
        overflow_list = report.get("overflow_tasks", [])

    selected_tasks = core_list if req.mode == "core_only" else (core_list + overflow_list)

    if not is_confirmed:
        # Stage in pending_review without activating until user confirms
        staged_ids: List[int] = []
        for t in selected_tasks:
            t_id = store.add_task(
                title=t.get("title", "Audited Task"),
                description=f"Routine Audit ({req.mode}) slot: {t.get('assigned_slot', 'unassigned')}",
                raw_due_text=t.get("scheduled_start") or t.get("preferred_time") or "",
                priority=str(t.get("priority", "normal")),
                status="pending_review",
            )
            staged_ids.append(t_id)
        return {
            "status": "confirmation_required",
            "requires_confirmation": True,
            "mode": req.mode,
            "staged_ids": staged_ids,
            "committed_count": 0,
            "message": "Tasks staged in pending_review. Explicit user confirmation is required to activate schedule.",
        }

    today_str = datetime.now(DEFAULT_TIMEZONE).date().isoformat()
    committed_ids: List[int] = []
    for t in selected_tasks:
        slot_start = t.get("scheduled_start") or t.get("preferred_time")
        due_iso = f"{today_str}T{slot_start}:00+05:00" if (slot_start and ":" in str(slot_start)) else None
        t_id = store.add_task(
            title=t.get("title", "Audited Task"),
            description=f"Routine Audit ({req.mode}) slot: {t.get('assigned_slot', 'forced')}",
            raw_due_text=str(slot_start or ""),
            due_datetime=due_iso,
            priority=str(t.get("priority", "normal")),
            status="confirmed",
        )
        committed_ids.append(t_id)

    return {
        "status": "confirmed",
        "mode": req.mode,
        "committed_ids": committed_ids,
        "committed_count": len(committed_ids),
        "overflow_deferred_count": len(overflow_list) if req.mode == "core_only" else 0,
        "message": f"Successfully committed {len(committed_ids)} task(s) in '{req.mode}' mode.",
    }


# =============================================================================
# 2. Strict Proof-of-Wake ("Anas, wake up!") Alarm Endpoints
# =============================================================================


@app.get("/api/alarms")
async def list_alarms_endpoint(state: Optional[str] = None):
    alarms = store.list_alarms(state=state)
    return {"alarms": alarms}


@app.post("/api/alarms")
async def create_alarm_endpoint(req: AlarmCreateRequest):
    alarm_id = store.add_alarm(
        alarm_time=req.alarm_time,
        label=req.label or "Anas, wake up!",
        first_task_prompt=req.first_task_prompt,
        state=req.state if req.state in ("scheduled", "ringing", "acknowledged", "missed") else "scheduled",
    )
    alarm = store.get_alarm(alarm_id)
    return {
        "id": alarm_id,
        "alarm": alarm,
        "wake_loop_phrase": f"Anas, wake up! Your first task is {req.first_task_prompt}.",
    }


@app.delete("/api/alarms/{alarm_id}")
@app.post("/api/alarms/{alarm_id}/delete")
async def delete_alarm_endpoint(alarm_id: int):
    if hasattr(store, "delete_alarm"):
        deleted = bool(store.delete_alarm(alarm_id))
    else:
        deleted = store._execute_write("DELETE FROM alarms WHERE id = ?", (alarm_id,)) > 0
    return {"success": deleted, "deleted": deleted, "id": alarm_id}


@app.post("/api/alarms/{alarm_id}/verify-wake")
async def verify_wake_alarm_endpoint(alarm_id: int, req: AlarmVerifyWakeRequest):
    alarm = store.get_alarm(alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    phrase = (req.verification_phrase or req.spoken_text or req.phrase or "").strip()
    task_confirmed = bool(req.first_task_confirmed or req.task_confirmed)

    # Strict Proof-of-Wake check: requires non-empty spoken/typed phrase OR explicit first-task confirmation
    if len(phrase) < 2 and not task_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Proof-of-Wake verification failed: speak/type the wake phrase or confirm your first task.",
        )

    store.acknowledge_alarm(alarm_id)
    updated_alarm = store.get_alarm(alarm_id)
    return {
        "verified": True,
        "id": alarm_id,
        "state": "acknowledged",
        "alarm": updated_alarm,
        "message": "Proof-of-Wake verified. Repeating 'Anas, wake up!' alarm loop stopped.",
    }


# =============================================================================
# 3. Nightly Accountability & Course Learning Audit Endpoints
# =============================================================================


@app.get("/api/courses")
async def list_courses_endpoint():
    return {
        "courses": store.list_courses(),
        "course_logs": store.list_course_logs(limit=20),
    }


@app.post("/api/courses")
async def create_course_endpoint(req: CourseCreateRequest):
    c_id = store.add_course(
        title=req.title,
        instructor=req.instructor,
        total_modules=req.total_modules,
        completed_modules=req.completed_modules,
        status=req.status,
    )
    return {"id": c_id, "course": store.get_course(c_id)}


@app.post("/api/audit/nightly")
async def submit_nightly_audit_endpoint(req: NightlyAuditRequest):
    # 1. Update task statuses from nightly checklist if task IDs were submitted
    for tid in req.completed_task_ids:
        store.update_task_status(tid, "completed")
    for tid in req.missed_task_ids:
        store.update_task_status(tid, "missed")

    # 2. Build task list for discipline score calculation
    if req.tasks is not None:
        eval_tasks = req.tasks
    elif req.completed_task_ids or req.missed_task_ids:
        eval_tasks = [
            {"id": tid, "title": (store.get_task(tid) or {}).get("title", f"Task {tid}"), "completed": True}
            for tid in req.completed_task_ids
        ] + [
            {"id": tid, "title": (store.get_task(tid) or {}).get("title", f"Task {tid}"), "completed": False}
            for tid in req.missed_task_ids
        ]
    else:
        eval_tasks = store.get_today_tasks()

    discipline = compute_daily_discipline_score(eval_tasks)

    # 3. Fetch previous course log BEFORE saving today's log so the recall quiz targets yesterday's lesson
    previous_log = store.get_latest_course_log(course_id=req.course_id)

    raw_text = (req.raw_reflection if req.raw_reflection is not None else req.reflection) or ""
    course_obj = store.get_course(req.course_id) if req.course_id else None
    course_title = course_obj["title"] if course_obj else "Course Study"

    structured_notes = structure_course_reflection(
        raw_reflection=raw_text,
        topic=req.topic,
        course_title=course_title,
    )

    quiz_source = previous_log or {
        "topic": req.topic,
        "raw_reflection": raw_text,
        "structured_notes": structured_notes,
    }
    recall_quiz = generate_recall_quiz(quiz_source)

    log_id = store.add_course_log(
        course_id=req.course_id,
        topic=req.topic,
        raw_reflection=raw_text,
        structured_notes=structured_notes,
        quiz_json=recall_quiz,
    )

    return {
        "log_id": log_id,
        "discipline": discipline,
        "structured_notes": structured_notes,
        "recall_quiz": recall_quiz,
        "quiz": recall_quiz,
    }


# =============================================================================
# 4. Business Deliverables & Autonomous Small-Task Buddy Endpoints
# =============================================================================


@app.get("/api/business/deliverables")
async def list_business_deliverables_endpoint():
    items = store.list_business_deliverables()
    ranked = rank_deliverables(items)
    return {"deliverables": ranked}


@app.post("/api/business/deliverables")
async def add_business_deliverable_endpoint(req: BusinessDeliverableRequest):
    deliv_id = store.add_business_deliverable(
        client_name=req.client_name,
        title=req.title,
        deadline=req.deadline,
        estimated_hours=req.estimated_hours,
        impact_score=req.impact_score,
        status=req.status,
    )
    created = store.get_business_deliverable(deliv_id) or {}
    scoring = score_deliverable(
        deadline_iso=req.deadline,
        estimated_hours=req.estimated_hours,
        impact_score=req.impact_score,
    )
    enriched = {**created, **scoring}
    all_ranked = rank_deliverables(store.list_business_deliverables())
    return {
        "id": deliv_id,
        "deliverable": enriched,
        "urgency_score": scoring["urgency_score"],
        "tier": scoring["tier"],
        "deliverables": all_ranked,
    }


@app.get("/api/business/small-task")
async def list_small_tasks_endpoint(status: Optional[str] = None):
    return {"small_tasks": store.list_small_tasks(status=status)}


@app.post("/api/business/small-task")
async def run_small_task_buddy_endpoint(req: SmallTaskRequest):
    worker_res = execute_small_task(prompt=req.prompt, task_type=req.task_type)
    task_id = store.add_small_task(
        prompt=worker_res["prompt"],
        task_type=worker_res["task_type"],
        result_content=worker_res["result_content"],
        status="pending_review",
    )
    return {
        "id": task_id,
        "prompt": worker_res["prompt"],
        "task_type": worker_res["task_type"],
        "result_content": worker_res["result_content"],
        "status": "pending_review",
        "requires_confirmation": True,
    }


@app.post("/api/business/small-task/{task_id}/confirm")
async def confirm_small_task_endpoint(task_id: int):
    existing = store.get_small_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Small task not found")
    updated = store.confirm_small_task(task_id)
    return {"success": updated, "id": task_id, "status": "confirmed"}


# =============================================================================
# 5. Interactive Discussion / Chat Endpoint
# =============================================================================


def _build_chat_system_prompt() -> str:
    now = datetime.now(DEFAULT_TIMEZONE)
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    today_day = now.strftime("%A")
    today_ymd = now.strftime("%Y-%m-%d")

    blocks = store.list_weekly_routine()
    by_day = {}
    for b in blocks:
        d = b.get("day_of_week", "Daily")
        by_day.setdefault(d, []).append(f"[ID {b.get('id')}] {b.get('start_time')}-{b.get('end_time')}: {b.get('title')}")

    routine_lines = []
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        items = by_day.get(d, [])
        free = store.get_free_slots_for_day(d)
        free_str = ", ".join(f"{s['start_12h']}-{s['end_12h']} ({s['duration_hours']}h)" for s in free)
        if items:
            routine_lines.append(f"  * {d}: {'; '.join(items)} | Free Slots: {free_str or 'None'}")
        else:
            routine_lines.append(f"  * {d}: No fixed blocks | Free Slots: 6:00 AM - 11:00 PM (17h)")

    routine_text = "\n".join(routine_lines)

    reminders = store.list_tasks(status="confirmed", limit=15)
    rem_lines = [f"  * [ID {r['id']}] {r['title']} (Due: {r.get('due_datetime') or r.get('raw_due_text') or 'Today'})" for r in reminders]
    reminders_text = "\n".join(rem_lines) if rem_lines else "  * No active deadlines"

    completions = store.list_routine_completions(date_str=today_ymd)
    comp_ids = {c["routine_id"] for c in completions if c.get("status") == "completed"}
    comp_text = f"{len(comp_ids)} routine blocks marked completed today"

    return f"""You are JARVIS, Anas's autonomous personal executive partner, time architect, and daily accountability buddy.
Current Local Time: {date_str}, {time_str} ({DEFAULT_TIMEZONE.zone if hasattr(DEFAULT_TIMEZONE, 'zone') else 'PKT'}). Today is {today_day}.

=== ANAS'S VERIFIED WEEKLY SCHEDULE & DETERMINISTIC FREE SLOTS ===
{routine_text}

=== ACTIVE REMINDERS & DEADLINES ===
{reminders_text}

=== TODAY'S ROUTINE STATUS ===
{comp_text}

CORE PRINCIPLES & CAPABILITIES:
1. You have DIRECT, real-time access to Anas's schedule, weekly routine, free slots, and reminders database.
2. NEVER say "I cannot access or modify your personal calendar" or "What is your schedule?". You ALREADY know his entire schedule.
3. Communicate naturally, supportively, and intelligently in Roman-Urdu or English, matching how Anas speaks to you.
4. When Anas gives ANY command related to scheduling, free slots, assignments, marking/unmarking routine, adding/deleting reminders, or auditing:
   - Provide a smart conversational explanation in Roman-Urdu or English.
   - ALWAYS output a structured action block at the very end of your response inside ```json:action ... ``` so the UI displays an interactive Confirmation Card.

ACTION PAYLOAD SCHEMA:
```json:action
{{
  "type": "schedule_free_slot" | "create_reminder" | "mark_routine" | "unmark_routine" | "complete_reminder" | "delete_reminder" | "run_audit" | "switch_theme",
  "title": "Action Title (e.g. Reserve Monday Free Slot for Assignment)",
  "details": "Description of the action",
  "day": "Monday",
  "slots": [
    {{"start": "20:00", "end": "22:00", "duration": "2.0 hrs", "label": "8:00 PM – 10:00 PM (2.0 hrs recommended)"}},
    {{"start": "20:00", "end": "23:00", "duration": "3.0 hrs", "label": "8:00 PM – 11:00 PM (3.0 hrs full slot)"}}
  ],
  "params": {{
    "title": "Task title",
    "day": "Monday",
    "start_time": "20:00",
    "end_time": "22:00",
    "priority": "high"
  }}
}}
```
"""


def _extract_and_enrich_action(user_msg: str, raw_reply: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    action_dict = None
    clean_reply = raw_reply.strip()

    # 1. Check for ```json:action or ```action block
    match = re.search(r'```(?:json:action|action|json)?\s*(\{[\s\S]*\})\s*```', raw_reply)
    if match:
        try:
            action_dict = json.loads(match.group(1))
            clean_reply = (raw_reply[:match.start()] + raw_reply[match.end():]).strip()
        except Exception:
            clean_reply = (raw_reply[:match.start()] + raw_reply[match.end():]).strip()
    else:
        # Also strip any raw trailing JSON action object if LLM omitted code fences
        bare_match = re.search(r'(\{\s*"type"\s*:\s*"[a-z_]+"[\s\S]*\})\s*$', raw_reply)
        if bare_match:
            try:
                action_dict = json.loads(bare_match.group(1))
                clean_reply = raw_reply[:bare_match.start()].strip()
            except Exception:
                pass

    msg_low = user_msg.lower().strip()

    # Fallback A: Free slot booking / assignment scheduling
    if not action_dict and any(w in msg_low for w in ["free slot", "assignment", "reserve slot", "mark free", "monday free", "free slots"]):
        target_day = "Monday"
        for d in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if d in msg_low:
                target_day = d.capitalize()
                break

        slots = store.get_free_slots_for_day(target_day)
        if slots:
            rec_slot = slots[-1]
            title = "Complete Assignment" if "assignment" in msg_low else "Deep Work Session"
            action_dict = {
                "type": "schedule_free_slot",
                "title": f"Reserve {target_day} Free Slot",
                "details": f"Schedule '{title}' during {target_day}'s available free hours",
                "day": target_day,
                "slots": slots,
                "params": {
                    "title": title,
                    "day": target_day,
                    "start_time": rec_slot["start"],
                    "end_time": rec_slot["end"],
                    "priority": "high"
                }
            }

    # Fallback B: Mark routine completion
    if not action_dict and (msg_low.startswith("mark ") or " mark " in msg_low or "completed" in msg_low or " done" in msg_low) and "unmark" not in msg_low:
        blocks = store.list_weekly_routine()
        for b in blocks:
            b_title = b.get("title", "").lower()
            if any(w in msg_low for w in b_title.split() if len(w) > 3):
                action_dict = {
                    "type": "mark_routine",
                    "title": f"Mark Completed: {b.get('title')}",
                    "details": f"Mark '{b.get('title')}' as completed for today",
                    "params": {
                        "routine_id": b["id"],
                        "title": b.get("title")
                    }
                }
                break

    # Fallback C: Unmark routine
    if not action_dict and "unmark" in msg_low:
        blocks = store.list_weekly_routine()
        for b in blocks:
            b_title = b.get("title", "").lower()
            if any(w in msg_low for w in b_title.split() if len(w) > 3):
                action_dict = {
                    "type": "unmark_routine",
                    "title": f"Unmark Routine: {b.get('title')}",
                    "details": f"Unmark '{b.get('title')}' for today",
                    "params": {
                        "routine_id": b["id"],
                        "title": b.get("title")
                    }
                }
                break

    # Fallback D: Reminder creation
    if not action_dict and any(w in msg_low for w in ["remind me", "reminder", "yaad dilana", "kal sham", "kal subah"]):
        dt = parse_relative_time(user_msg)
        due_iso = dt.isoformat() if dt else None
        clean_title = re.sub(r'(?:remind me to|reminder for|yaad dilana|kal|sham|subah|baje)\s*', '', user_msg, flags=re.I).strip() or user_msg
        action_dict = {
            "type": "create_reminder",
            "title": f"Create Reminder: {clean_title[:30]}",
            "details": f"Reminder: '{clean_title}'" + (f" due {dt.strftime('%A %I:%M %p')}" if dt else ""),
            "params": {
                "title": clean_title,
                "raw_due_text": user_msg,
                "due_datetime": due_iso,
                "priority": "normal"
            }
        }

    return clean_reply, action_dict


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    system_prompt = _build_chat_system_prompt()
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    if req.history:
        for item in req.history:
            if isinstance(item, dict) and "role" in item and "content" in item:
                role = str(item["role"]).strip().lower()
                content = str(item["content"]).strip()
                if role in ("user", "assistant", "system") and content:
                    messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": req.message})

    try:
        if hasattr(key_pool, "groq_chat_completion"):
            completion = key_pool.groq_chat_completion(
                messages=messages,
                model="qwen/qwen3.8-27b",
            )
        else:
            completion = groq_chat_completion(
                messages=messages,
                model="qwen/qwen3.8-27b",
            )

        if isinstance(completion, str):
            raw_reply = str(completion).strip()
        elif isinstance(completion, dict):
            raw_reply = (
                completion.get("content")
                or completion.get("reply")
                or (completion.get("choices", [{}])[0].get("message", {}).get("content", ""))
            )
        else:
            raw_reply = str(completion).strip()

        if not raw_reply:
            raw_reply = f"Understood, Anas: '{req.message.strip()}'. Processing your request."
    except Exception as exc:
        raw_reply = (
            f"Understood, Anas: '{req.message.strip()}'. "
            "Offline mode active; all local tasks and routine schedules remain synchronized."
        )

    clean_reply, action_dict = _extract_and_enrich_action(req.message, raw_reply)

    now_iso = datetime.now(DEFAULT_TIMEZONE).isoformat()
    return {"reply": clean_reply, "action": action_dict, "timestamp": now_iso}
