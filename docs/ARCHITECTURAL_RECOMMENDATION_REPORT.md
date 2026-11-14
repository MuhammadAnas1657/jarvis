# Architectural Recommendation Report: Jarvis 24/7 Personal Buddy & Business Workflow Engine

**Target System**: `c:\projects\jarvis`  
**Timezone**: `Asia/Karachi` (PKT)  
**Tech Stack**: JS Frontend + Python Backend (FastAPI) + Native PostgreSQL 16 + Mobile App (1-Click PWA & Capacitor Android APK)

---

## 1. Executive Summary & Standard 3-Step Workflow

Jarvis is an always-on, voice- and text-driven personal accountability buddy, course-learning auditor, and autonomous business task worker built for Anas (`Asia/Karachi`). It runs on a clean, standard stack: a **JavaScript Frontend (`frontend/`)**, a **Python FastAPI Backend (`backend/`)**, a **Native PostgreSQL 16 Database in pgAdmin**, and a **46-key rotating Groq API pool**.

### Standard 3-Step Workflow
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

For mobile access and internet-drop resilience in Pakistan, Jarvis provides both a **1-Click Install / QR Code Mobile Installer** directly in the Desktop JS Frontend (`/api/mobile/install-info`) and a standalone **Capacitor JS Android APK project** (`mobile/`). All date/time math, routine conflict detection, and urgency scoring execute via 100% deterministic Python logic (`jarvis/timeparse.py`, `jarvis/routine_audit.py`, `jarvis/business.py`), while every task write and system action remains strictly gated behind explicit user confirmation.

---

## 2. Core Architectural Pillars

### 2.1 Database Layer: Native PostgreSQL 16 (`DATABASE_URL` + `setup_postgres.py`)
- **Native PostgreSQL Provisioning**: `py -3.11 setup_postgres.py` connects natively to a local or remote PostgreSQL 16 instance, creates the `jarvis` database if missing, and initializes all production tables via `DATABASE_URL` (`postgresql://jarvis:jarvis@localhost:5432/jarvis`).
- **Resilient Test & Local Adapter**: `jarvis/store.py` (`ReminderStore`) connects natively to PostgreSQL via `psycopg2`/`psycopg` when `DATABASE_URL` is reachable, and transparently falls back to a local SQL-compatible adapter during offline CI/unit testing so `pytest` runs cleanly without external daemon friction.
- **Core Schema**:
  - `reminders` & `action_logs`: Tasks (`pending_confirmation` $\rightarrow$ `confirmed` $\rightarrow$ `completed`) and audited system actions.
  - `weekly_routine`: Fixed routine blocks (`id`, `day_of_week`, `title`, `start_time`, `end_time`, `category`, `is_locked`).
  - `alarms`: Wake-up alarm state machine (`id`, `alarm_time`, `label`, `first_task_prompt`, `state` in `['scheduled', 'ringing', 'acknowledged', 'missed']`).
  - `courses` & `course_logs`: Course progress tracker and nightly learning reflections (`topic`, `raw_reflection`, `structured_notes`, `quiz_json`).
  - `business_deliverables` & `small_tasks`: Client deliverables ranked by urgency and autonomous background worker outputs (`draft`, `breakdown`, `sop`, `research`).

### 2.2 Compute & AI Layer: Python FastAPI Backend + 46 Rotating Groq API Keys
- **Zero Local GPU / Wake-on-LAN Dependency**: Runs on any standard Windows PC or Linux server with Python 3.11 and Native PostgreSQL.
- **Groq 46-Key Rotating Pool (`jarvis/key_pool.py`)**:
  - Loads all 46 Groq API keys from `c:\projects\halucination\Api_keys (1).xlsx` (or `GROQ_API_KEYS` env / `config.yaml`).
  - Thread-safe round-robin rotation (`get_next_key()`, `mark_rate_limited(key)`) with automatic HTTP 429 cooldown failover.
  - **LLM Inference**: `llama-3.3-70b-versatile` via `groq_chat_completion()` for JSON task extraction, course note structuring, recall quiz generation, and business drafting.
  - **Speech-to-Text (STT)**: `whisper-large-v3-turbo` via `groq_transcribe()` biased for mixed Roman-Urdu and English, exposed to the JS Frontend and mobile app via `POST /api/voice/capture`.
  - **Deterministic Offline Fallback**: If internet connectivity is unavailable, `key_pool.py` and the engines degrade gracefully to deterministic local rule extractors so core operations never crash.

### 2.3 JS Frontend & Dual Mobile App Installation (1-Click PWA + `mobile/` Capacitor APK)
- **Desktop & Mobile JS Frontend (`templates/index.html`, `static/app.js`, `static/sw.js`)**:
  - Caches the unified state snapshot (`GET /api/sync`) in `IndexedDB` / `localStorage`.
  - Includes a built-in **Browser/Phone Microphone Recorder** (`MediaRecorder` $\rightarrow$ `POST /api/voice/capture`) to speak Urdu/English tasks or nightly reflections directly from phone or desktop.
  - Includes a **Mobile App Installer Modal** powered by `GET /api/mobile/install-info` displaying the auto-detected LAN URL (`http://<lan_ip>:8000`), an instant QR code for phone pairing, a 1-Click `beforeinstallprompt` PWA installer button, and native APK build steps.
- **Capacitor JS Android APK Project (`mobile/`)**:
  - `mobile/package.json`, `mobile/capacitor.config.json`, `mobile/www/index.html`, `mobile/www/mobile-bridge.js`, and `mobile/build_apk.ps1` package the JS frontend into a standalone Android `.apk` (`com.anas.jarvis`).
  - Allows configuring the Python Backend URL in `localStorage`, syncs `/api/sync` into offline storage whenever online, and runs the 5-second reminder watchdog and 15-second repeating Proof-of-Wake voice alarm completely offline.

---

## 3. Proactive Accountability & Workflow Engines

```
┌──────────────────────────────────────────────────────────────────────────┐
│            PYTHON BACKEND (FastAPI + Native PostgreSQL 16)               │
│  • Provisioned via `py -3.11 setup_postgres.py` (DATABASE_URL)           │
│  • 46 Rotating Groq Keys (llama-3.3-70b-versatile + whisper-v3-turbo)    │
│  • Endpoints: /api/sync | /api/voice/capture | /api/mobile/install-info  │
│  • Deterministic Engines: timeparse | routine_audit | course | business  │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ HTTP/HTTPS + /api/sync Snapshot
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│      JS FRONTEND & MOBILE APP (1-Click PWA + `mobile/` Android APK)      │
│  • Service Worker (sw.js) + IndexedDB / LocalStorage Cache               │
│  • 5s Offline Watchdog Timer + Web SpeechSynthesis Loop                  │
│  • Mic Voice Capture | Proof-of-Wake | Routine Audit | Quiz | Buddy      │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Strict Proof-of-Wake Alarm ("Anas, wake up!")
- **Repeating Voice Loop**: When an alarm hits `alarm_time`, the JS client triggers a repeating 15-second voice synthesis loop: *"Anas, wake up! Your first task is [first_task_prompt]."*
- **Proof-of-Wake Verification (`POST /api/alarms/{id}/verify-wake`)**: Cannot be dismissed with a blind swipe. Remains in `ringing` state until the user speaks back or completes the on-screen first-task verification check (`acknowledged`). Alarms can also be managed via `DELETE /api/alarms/{id}`.

### 3.2 Hard Routine Audit (Advisory Mode — `jarvis/routine_audit.py`)
- **Fixed Weekly Routine & True Free Hours**: Compares proposed daily tasks against locked routine blocks (`weekly_routine`, manageable via `POST`/`DELETE /api/routine/weekly`).
- **Deterministic Conflict & Overload Math**: Computes `total_locked_minutes`, `true_free_minutes`, and `requested_minutes` (with a 15% buffer), flags exact time-slot overlaps, and splits tasks into **Core Schedule** vs. **Overflow Tasks**.
- **User Choice (`POST /api/routine/commit`)**: Advisory Mode lets the user choose **`[Accept Core Structure]`** (`mode="core_only"`) or **`[Force-Schedule All Today]`** (`mode="force_all"`), staging tasks behind the confirmation gate.

### 3.3 Deterministic Roman-Urdu & English Time Parser (`jarvis/timeparse.py`)
- Executes all date/time math deterministically in `Asia/Karachi`: relative days (`aaj`, `kal`, `parson`, `tarson`, `agle hafte <weekday>`), diurnal/prayer hints (`fajar`, `subah`, `dopahar`, `sehpahar`, `shaam`, `maghrib`, `isha`, `raat`, `"12 baje raat"` $\rightarrow$ `00:00`), and compound/fractional Urdu durations (`"1 ghanta 30 minute baad"`, `"derh"`, `"dhai"`).

### 3.4 Nightly Task & Course Learning Audit (`jarvis/course_audit.py`)
- Computes daily discipline score (`compute_daily_discipline_score`), structures `"What I Learned Today"` reflections into markdown notes, and generates an interactive 2-question recall quiz (`generate_recall_quiz`) from yesterday's lesson.

### 3.5 Business & Small-Task Buddy (`jarvis/business.py`)
- Deterministically ranks client deliverables by deadline proximity, effort, and impact (`score_deliverable`), and runs an autonomous background worker (`execute_small_task`) for `draft`, `breakdown`, `sop`, and `research`.

---

## 4. Security & Confirmation Guardrails (`AGENTS.md` Compliance)

1. **Mandatory User Confirmation**: No reminder is marked active and no PC/system action is executed without explicit user confirmation (`user_confirmed=True`).
2. **Deterministic Time Computation**: The LLM only extracts structured fields; `jarvis/timeparse.py` computes all timestamps.
3. **Strict Scope & Isolation**: No email auto-senders, no Home Assistant/smart-home integrations, `shell=False` subprocess isolation for whitelisted local actions, and zero modifications to `c:\projects\temp for atarion solutions budget`.
