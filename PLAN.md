# Jarvis: Personal Buddy & Business Workflow Engine (Implementation Plan)

Handoff and status document. Read this and `AGENTS.md` first.

## Goal
24/7 personal accountability buddy, course-learning auditor, and business task engine for Anas (`Asia/Karachi`). Built on a standard **JS Frontend + Python Backend (FastAPI) + Native PostgreSQL Database** stack, plus a **Mobile App Installer** (1-Click PWA / QR Code on Desktop JS Frontend + `mobile/` Capacitor JS Android APK project). The user speaks or types tasks in mixed English and Roman-Urdu. Jarvis transcribes and extracts tasks via a 46-key rotating Groq pool (`whisper-large-v3-turbo` + `llama-3.3-70b-versatile`) with deterministic offline fallbacks, runs an Advisory Hard Routine Audit against the user's Fixed Weekly Routine, requires explicit user confirmation before scheduling or executing actions, and caches everything in an Offline-First JS client (`IndexedDB` + Service Worker) so alarms and reminders continue working when internet drops.

## Architecture & Standard 3-Step Workflow
- **Database (pgAdmin)**: `postgresql://jarvis:jarvis@localhost:5432/jarvis` (configured in `backend/.env`)
- **Backend (`backend/`)**:
  ```powershell
  cd c:\projects\jarvis\backend
  .\venv\Scripts\activate
  uvicorn main:app --reload --port 8000
  ```
- **Frontend (`frontend/`)**:
  ```powershell
  cd c:\projects\jarvis\frontend
  npm run dev
  ```

```
Server / Local Stack:
  Native PostgreSQL 16 in pgAdmin (postgresql://jarvis:jarvis@localhost:5432/jarvis, backend/.env)
  Python FastAPI Backend (backend/main.py -> jarvis/web.py on http://localhost:8000)
    ├── 46-Key Groq Pool (jarvis/key_pool.py -> llama-3.3-70b-versatile & whisper-large-v3-turbo)
    ├── Voice Capture & Mobile Installer (/api/voice/capture & /api/mobile/install-info)
    ├── Deterministic Time Parser (jarvis/timeparse.py -> Roman-Urdu & English)
    ├── Hard Routine Audit (jarvis/routine_audit.py -> Core vs. Overflow advisory split)
    ├── Nightly & Course Audit (jarvis/course_audit.py -> reflection organizer + 2-Q recall quiz)
    ├── Business & Small-Task Buddy (jarvis/business.py -> urgency ranker + draft/breakdown/SOP/research)
    └── Confirm-First Guardrails (jarvis/store.py & jarvis/actions.py)

Desktop JS Frontend (`frontend/` via `npm run dev`) & Mobile App (1-Click PWA + Capacitor Android APK in `mobile/`):
  JS Frontend (frontend/index.html, frontend/src/app.js, frontend/public/sw.js) + Capacitor Mobile Wrapper (mobile/)
  IndexedDB/LocalStorage Sync (GET /api/sync) + Browser/Phone Mic Recording (POST /api/voice/capture)
  5s Local Offline Timer -> Reminders & Strict Proof-of-Wake ("Anas, wake up!") loop
```

## Key Design Rules
1. The LLM only converts natural language to structured JSON. All date/time math is done by deterministic code in `jarvis/timeparse.py`.
2. Handle Roman-Urdu time words in `timeparse.py`: `kal`, `aaj`, `parson`, `tarson`, `subah`, `dopahar`, `sehpahar`, `shaam`, `maghrib`, `isha`, `raat`, `baje`, `agle hafte`, `derh`, `dhai`.
3. Every extracted or audited task goes through a confirmation step (`pending_confirmation` -> `confirmed`). Nothing is committed or executed without explicit user confirmation.
4. No email auto-sending, no Home Assistant, no smart-home features, and never modify `c:\projects\temp for atarion solutions budget`.

## Phases and Tasks

### Phase 0: Environment & Native PostgreSQL Setup
- [x] Python 3.11 environment and `requirements.txt` configured.
- [x] Native PostgreSQL 16 database & tables provisioned via `py -3.11 setup_postgres.py` (`DATABASE_URL`).
- [x] 46 Groq API keys wired via `jarvis/key_pool.py` from `c:\projects\halucination\Api_keys (1).xlsx` with automatic rate-limit rotation and offline fallback.

### Phase 1: Capture to Calendar (MVP)
- [x] `jarvis/config.py`: load `config.yaml`, `DATABASE_URL`, and Groq key pool settings.
- [x] `jarvis/watcher.py`: watch `inbox/` for audio files (`m4a`, `mp3`, `wav`, `ogg`).
- [x] `jarvis/stt.py`: speech-to-text wrapper with mixed Urdu/English vocabulary prompt and fallback.
- [x] `jarvis/extract.py`: structured task extraction with Pydantic validation and deterministic offline rule fallback.
- [x] `jarvis/timeparse.py`: deterministic Urdu & English datetime parser (including midnight `"12 baje raat"`, `"agle hafte <weekday>"`, compound/fractional durations, and prayer PM hints).
- [x] `jarvis/store.py`: Native PostgreSQL store (`DATABASE_URL`) with automatic local SQL-compatible test fallback, audit logs, and CalDAV sync helper.
- [x] `jarvis/web.py`: Python FastAPI confirmation dashboard, REST API, `/api/voice/capture`, and `/api/mobile/install-info`.
- [x] Comprehensive unit & integration tests in `tests/`.

### Phase 2: Conversation, Briefing & Strict Wake-Up Alarm
- [x] CLI entrypoint `jarvis/main.py` (`run`, `briefing`, `process`, `status`, `test-parse`).
- [x] Morning briefing summary spoken by TTS (`jarvis/briefing.py` + `jarvis/tts.py`).
- [x] `ntfy` push notification integration.
- [x] Strict Proof-of-Wake `"Anas, wake up!"` alarm state machine and verification endpoint (`/api/alarms/{id}/verify-wake`).

### Phase 3: PC Control (Confirm-First)
- [x] `jarvis/actions.py` whitelist: `open_app`, `open_folder`, `get_system_status`.
- [x] Confirmation guardrail (`user_confirmed=True` mandatory before execution) + audit logging in `action_logs`.
- [x] Test suite verifying unwhitelisted apps and unconfirmed calls are blocked.

### Phase 4: JS Frontend, Mobile App (PWA + Capacitor APK) & Proactive Accountability Engines
- [x] `jarvis/routine_audit.py`: Advisory Hard Routine Audit comparing daily tasks against Fixed Weekly Routine & True Free Hours (Core vs. Overflow split + accept structure or force-schedule all).
- [x] `jarvis/course_audit.py`: Nightly task accountability checklist, `"What I Learned Today"` structured note organizer, and 2-question quick recall quiz from yesterday's lesson.
- [x] `jarvis/business.py`: Business deliverable urgency scorer and Autonomous Small-Task Buddy (`draft`, `breakdown`, `sop`, `research`).
- [x] JS Frontend & Offline-First PWA (`static/sw.js`, `static/app.js`, `static/manifest.json`, `templates/index.html`) with `IndexedDB` / `localStorage` caching (`GET /api/sync`), in-browser voice recording (`POST /api/voice/capture`), and 1-Click Mobile App Installer modal (`GET /api/mobile/install-info`).
- [x] Standalone Capacitor JS Android APK project (`mobile/package.json`, `mobile/capacitor.config.json`, `mobile/www/index.html`, `mobile/www/mobile-bridge.js`, `mobile/build_apk.ps1`).
