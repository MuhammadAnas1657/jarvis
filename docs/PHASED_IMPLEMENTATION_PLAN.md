# Phased Implementation Plan: Jarvis 24/7 Personal Buddy & Business Workflow Engine

**Target Workspace**: `c:\projects\jarvis`  
**Stack**: JS Frontend + Python 3.11 Backend (FastAPI) + Native PostgreSQL 16 + Groq 46-Key Pool + Mobile App (PWA & Capacitor APK)

---

## 1. Phase Progression Summary

| Phase | Scope | Status |
| :--- | :--- | :--- |
| **Phase 1** | Capture to Calendar MVP (`config`, `watcher`, `stt`, `extract`, `timeparse`, `store`, `web`) | `[x] Completed` |
| **Phase 2** | CLI Entrypoints, Morning Briefing, TTS & Push Notifications (`main`, `briefing`, `tts`) | `[x] Completed` |
| **Phase 3** | Confirm-First PC Control & Guardrails (`actions.py` whitelist + audit log) | `[x] Completed` |
| **Phase 4** | Native PostgreSQL 16 (`setup_postgres.py`), 46-Key Groq Pool (`key_pool.py`) & Hardened `timeparse.py` | `[x] Completed` |
| **Phase 5** | Hard Routine Audit (`routine_audit.py`), Nightly Course Audit (`course_audit.py`) & Business Buddy (`business.py`) | `[x] Completed` |
| **Phase 6** | JS Frontend, Voice Capture (`/api/voice/capture`), 1-Click Mobile Installer & Capacitor Android APK (`mobile/`) | `[x] Completed` |

---

## 2. Detailed Phase Deliverables

### Phases 1–3: Core Foundation & Safety Guardrails (`[x] Completed`)
- **Capture & Extraction**: Voice/text ingestion (`jarvis/watcher.py`, `jarvis/stt.py`, `jarvis/extract.py`) with Pydantic schema validation and zero-cloud heuristic fallback.
- **Confirm-First Store & Action Whitelist**: `jarvis/store.py` and `jarvis/actions.py` enforce `pending_confirmation` staging for tasks and `user_confirmed=True` with `shell=False` for whitelisted applications (`notepad`, `calc`, `explorer`, `code`, etc.).

### Phase 4: Native PostgreSQL 16 Backend, 46-Key Groq Rotation & Timeparse Hardening (`[x] Completed`)
1. **Native PostgreSQL 16 Setup (`setup_postgres.py`)**:
   - `py -3.11 setup_postgres.py` connects to native PostgreSQL (`postgresql://jarvis:jarvis@localhost:5432/jarvis` or `DATABASE_URL`), creates the `jarvis` database if missing, initializes all tables via `ReminderStore`, and verifies read/write health.
2. **`jarvis/key_pool.py`**:
   - Loads 46 Groq API keys from `c:\projects\halucination\Api_keys (1).xlsx` (with `GROQ_API_KEYS` env and `config.yaml` support).
   - Thread-safe round-robin key rotation (`get_next_key()`, `mark_rate_limited(key)`) with automatic cooldown on HTTP 429.
   - Exposes `groq_chat_completion(messages, model="llama-3.3-70b-versatile")` and `groq_transcribe(audio_path, model="whisper-large-v3-turbo")` with offline fallback.
3. **`jarvis/store.py` & `jarvis/config.py` (`config.yaml`)**:
   - Connects natively to PostgreSQL via `DATABASE_URL` (`postgresql://...`) while providing a seamless local SQL-compatible fallback adapter when PostgreSQL is not running locally during unit tests.
   - Provides schema and CRUD methods (including delete methods `delete_routine_block` and `delete_alarm`) for `weekly_routine`, `alarms`, `courses`, `course_logs`, `business_deliverables`, and `small_tasks`.
4. **`jarvis/timeparse.py` & `tests/test_timeparse.py`**:
   - Handles `"12 baje raat"` / `"aadhi raat"` $\rightarrow$ `00:00:00` (midnight), named weekdays with `"agle hafte"`, compound durations (`"1 ghanta 30 minute baad"`), fractional Urdu durations (`"derh"`, `"dhai"`), and prayer PM hints (`"isha"`, `"maghrib"`).

### Phase 5: Routine Audit, Nightly Course Audit & Business Buddy (`[x] Completed`)
1. **`jarvis/routine_audit.py` (Hard Routine Audit — Advisory Mode)**:
   - Compares proposed daily tasks against locked `weekly_routine` blocks, calculating `total_locked_minutes`, `true_free_minutes`, `requested_minutes` (with 15% buffer), and exact overlaps.
   - Splits tasks into `core_schedule` and `overflow_tasks` (`advisory_mode: True`) so the user can accept the core plan or force-schedule all tasks today.
2. **`jarvis/course_audit.py` (Nightly Task & Course Learning Audit)**:
   - Computes daily discipline score (`compute_daily_discipline_score`), organizes `"What I Learned Today"` reflections into markdown notes, and generates a 2-question recall quiz (`generate_recall_quiz`).
3. **`jarvis/business.py` (Business Deliverables & Small-Task Buddy)**:
   - Scores deliverable urgency (`score_deliverable`) and runs autonomous small tasks (`execute_small_task` for `draft`, `breakdown`, `sop`, and `research`) staged for user review.

### Phase 6: JS Frontend, Voice Capture & Mobile App (PWA + Capacitor APK) (`[x] Completed`)
1. **Python FastAPI Endpoints (`jarvis/web.py`)**:
   - `GET /api/sync`: Full offline cache snapshot (`reminders`, `weekly_routine`, `alarms`, `courses`, `business_deliverables`, `small_tasks`).
   - `GET /api/mobile/install-info`: Returns LAN IP, `lan_url` (`http://<lan_ip>:8000`), PWA manifest info, and Android APK build instructions for the Frontend QR/1-Click Installer.
   - `POST /api/voice/capture`: Accepts browser/mobile recorded audio (`wav`/`webm`/`ogg`/`m4a`), transcribes via `groq_transcribe()` (`whisper-large-v3-turbo`), extracts tasks, and stages them as `pending_confirmation`.
   - `GET`/`POST`/`DELETE /api/routine/weekly` & `POST /api/routine/audit` & `POST /api/routine/commit`: Manage weekly routine blocks and run Advisory Hard Routine Audit.
   - `POST`/`DELETE /api/alarms` & `POST /api/alarms/{id}/verify-wake`: Manage alarms and verify Proof-of-Wake.
   - `POST /api/audit/nightly`, `POST /api/business/deliverables`, `POST /api/business/small-task`: Nightly audit quiz and Business Buddy endpoints.
2. **JS Frontend (`templates/index.html`, `static/app.js`, `static/sw.js`, `static/manifest.json`)**:
   - Responsive dark-mode JS dashboard with `IndexedDB` / `localStorage` offline sync, browser microphone voice recorder, interactive 2-question quiz checker, routine/alarm deletion, 1-Click Mobile App & QR Code installer modal, and 5-second local watchdog timer for reminders and the 15-second repeating `"Anas, wake up!"` voice loop.
3. **Capacitor JS Mobile App Project (`mobile/`)**:
   - `mobile/package.json`, `mobile/capacitor.config.json`, `mobile/www/index.html`, `mobile/www/mobile-bridge.js`, `mobile/build_apk.ps1`, and `mobile/README.md` provide a complete Android `.apk` wrapper with configurable backend URL and full offline alarm/reminder resilience.

---

## 3. Standard 3-Step Workflow & Verification Commands

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

### Additional Verification & Mobile APK Commands

```powershell
# 1. Initialize / verify Native PostgreSQL 16 database & tables in pgAdmin
py -3.11 setup_postgres.py

# 2. Run the complete unit and integration test suite
py -3.11 -m pytest -v

# 3. Verify FastAPI JS Frontend, Voice Capture & Mobile Installer endpoints
py -3.11 -m pytest tests/test_web.py -v

# 4. Build standalone Android APK (optional, inside mobile/)
cd c:\projects\jarvis\mobile
.\build_apk.ps1
```
