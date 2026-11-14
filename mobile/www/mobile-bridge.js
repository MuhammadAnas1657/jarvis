/**
 * JARVIS 24/7 Buddy — Standalone Capacitor JS Mobile Bridge & Offline Engine (mobile/www/mobile-bridge.js)
 *
 * Capabilities:
 * 1. Configurable Python Backend Server URL saved in localStorage ('jarvis_backend_url').
 * 2. Automatic /api/sync caching into local IndexedDB ('jarvis_offline_pwa_db') & localStorage whenever online.
 * 3. 5-second Offline Reminder & Alarm Watchdog Timer + Capacitor LocalNotifications bridge.
 * 4. 15-second Repeating "Anas, wake up!" Proof-of-Wake Voice Alarm Loop (works with zero internet connection).
 * 5. Full 5-tab Offline-First Dashboard (Today & Hard Routine Audit, Fixed Weekly Routine, Strict Alarm,
 *    Nightly Course Audit & 2-Question Quiz, and Business & Small-Task Buddy).
 */

const LS_BACKEND_URL_KEY = 'jarvis_backend_url';
const IDB_NAME = 'jarvis_offline_pwa_db';
const IDB_VERSION = 1;
const IDB_STORE = 'sync_cache';
const LS_CACHE_KEY = 'jarvis_offline_sync_snapshot_v1';

const DEFAULT_OFFLINE_SEED = {
  reminders: [
    {
      id: 901,
      title: 'Morning Architecture Review & Client Priority Check',
      due_datetime: new Date(Date.now() + 30 * 60000).toISOString(),
      raw_due_text: 'in 30 minutes',
      priority: 'high',
      category: 'general',
      status: 'confirmed'
    }
  ],
  weekly_routine: [
    { id: 1, day_of_week: 'Daily', title: 'Sleep & Recovery', start_time: '23:00', end_time: '06:00', category: 'Sleep', is_locked: 1 },
    { id: 2, day_of_week: 'Daily', title: 'Fajr, Morning Prep & Planning', start_time: '06:00', end_time: '07:30', category: 'Spiritual', is_locked: 1 },
    { id: 3, day_of_week: 'Daily', title: 'Deep Client Engineering Block', start_time: '09:00', end_time: '13:00', category: 'Deep Work', is_locked: 1 }
  ],
  alarms: [
    {
      id: 1,
      alarm_time: '06:00',
      label: 'Anas Fajr & Deep Work Wake-Up',
      first_task_prompt: 'Complete Fajr prayer and review your #1 Core Client Deliverable',
      state: 'scheduled'
    }
  ],
  courses: [
    { id: 1, title: 'AI Systems & LLM Engineering', instructor: 'Self-Paced', total_modules: 12, completed_modules: 4, status: 'active' }
  ],
  course_logs: [],
  business_deliverables: [
    {
      id: 1,
      client_name: 'Core Client',
      title: 'Production FastAPI + Native PostgreSQL Deployment',
      deadline: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
      estimated_hours: 4.0,
      impact_score: 9,
      urgency_score: 92.5,
      status: 'pending'
    }
  ],
  small_tasks: []
};

let jarvisState = {
  online: navigator.onLine,
  backendUrl: '',
  lastSyncedAt: null,
  reminders: [],
  weekly_routine: [],
  alarms: [],
  courses: [],
  course_logs: [],
  business_deliverables: [],
  small_tasks: [],
  lastAuditResult: null,
  proposedAuditTasks: [
    { title: 'Deep Work: Client Architecture Deliverable', estimated_minutes: 90, preferred_time: '10:00', priority: 'high' },
    { title: 'AI Engineering Course Module Study', estimated_minutes: 60, preferred_time: '14:00', priority: 'normal' }
  ],
  activeRingingAlarm: null,
  wakeLoopIntervalId: null,
  notifiedReminderIds: new Set(),
  mediaRecorder: null,
  audioChunks: []
};

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* ============================================================================
   1. PYTHON BACKEND SERVER URL CONFIGURATION & FETCH BRIDGE
   ============================================================================ */

function getBackendServerUrl() {
  try {
    const saved = localStorage.getItem(LS_BACKEND_URL_KEY);
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/+$/, '');
    }
  } catch (e) {}

  if (window.location && /^https?:\/\//i.test(window.location.origin) && !window.location.origin.includes('localhost')) {
    return window.location.origin.replace(/\/+$/, '');
  }
  return 'http://192.168.1.100:8000';
}

function saveBackendServerUrl() {
  const input = document.getElementById('mobileBackendUrlInput');
  const raw = input ? input.value.trim().replace(/\/+$/, '') : '';
  const cleaned = raw || 'http://192.168.1.100:8000';
  try {
    localStorage.setItem(LS_BACKEND_URL_KEY, cleaned);
  } catch (e) {}
  jarvisState.backendUrl = cleaned;
  if (input) input.value = cleaned;

  const meta = document.getElementById('mobileSyncMetaText');
  if (meta) {
    meta.textContent = `Saved Backend URL: ${cleaned} • Syncing /api/sync to local IndexedDB...`;
  }
  syncAllData();
}

const nativeFetch = window.fetch.bind(window);
window.fetch = async function (resource, options = {}) {
  let url = typeof resource === 'string' ? resource : (resource && resource.url ? resource.url : String(resource));
  if (url.startsWith('/api/')) {
    const base = getBackendServerUrl();
    url = `${base}${url}`;
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 6000);
  try {
    const res = await nativeFetch(url, { ...options, signal: options.signal || controller.signal });
    clearTimeout(timeoutId);
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
};

/* ============================================================================
   2. INDEXEDDB + LOCALSTORAGE OFFLINE CACHE (/api/sync)
   ============================================================================ */

function openOfflineDB() {
  return new Promise((resolve) => {
    if (!('indexedDB' in window)) {
      return resolve(null);
    }
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
  });
}

async function saveSyncPayloadToCache(payload) {
  const snapshot = {
    id: 'latest',
    savedAt: new Date().toISOString(),
    backendUrl: getBackendServerUrl(),
    data: payload
  };
  try {
    localStorage.setItem(LS_CACHE_KEY, JSON.stringify(snapshot));
  } catch (e) {}

  try {
    const db = await openOfflineDB();
    if (db) {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).put(snapshot);
    }
  } catch (e) {}
}

async function loadSyncPayloadFromCache() {
  try {
    const db = await openOfflineDB();
    if (db) {
      const idbResult = await new Promise((resolve) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const req = tx.objectStore(IDB_STORE).get('latest');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
      });
      if (idbResult && idbResult.data) {
        return idbResult;
      }
    }
  } catch (e) {}

  try {
    const raw = localStorage.getItem(LS_CACHE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return null;
}

function updateConnectionStatusUI(isOnline, syncedAt) {
  jarvisState.online = isOnline;
  const badge = document.getElementById('connectionStatusBadge');
  const dot = document.getElementById('connectionStatusDot');
  const text = document.getElementById('connectionStatusText');
  const meta = document.getElementById('mobileSyncMetaText');

  if (badge && text) {
    if (isOnline) {
      badge.className = 'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold border border-emerald-500/40 bg-emerald-500/10 text-emerald-400';
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
      text.textContent = 'Online • Synced with Python + PostgreSQL';
    } else {
      badge.className = 'flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold border border-amber-500/40 bg-amber-500/10 text-amber-400';
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-400';
      text.textContent = 'Offline Mode • Running from Local IndexedDB';
    }
  }

  if (meta) {
    const stamp = syncedAt ? new Date(syncedAt).toLocaleTimeString() : 'Local Snapshot';
    meta.textContent = `${isOnline ? 'Connected to' : 'Offline Fallback from'} ${getBackendServerUrl()} • Last Sync: ${stamp} • 5s Watchdog Active`;
  }
}

async function syncAllData() {
  try {
    const res = await fetch('/api/sync', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    if (payload && !payload.offline) {
      applySyncPayload(payload);
      await saveSyncPayloadToCache(payload);
      updateConnectionStatusUI(true, payload.synced_at);
      return;
    }
    throw new Error('Offline payload');
  } catch (err) {
    const cached = await loadSyncPayloadFromCache();
    if (cached && cached.data) {
      applySyncPayload(cached.data);
      updateConnectionStatusUI(false, cached.savedAt);
    } else {
      applySyncPayload(DEFAULT_OFFLINE_SEED);
      await saveSyncPayloadToCache(DEFAULT_OFFLINE_SEED);
      updateConnectionStatusUI(false, new Date().toISOString());
    }
  }
}

function getCurrentPayloadSnapshot() {
  return {
    reminders: jarvisState.reminders,
    weekly_routine: jarvisState.weekly_routine,
    alarms: jarvisState.alarms,
    courses: jarvisState.courses,
    course_logs: jarvisState.course_logs,
    business_deliverables: jarvisState.business_deliverables,
    small_tasks: jarvisState.small_tasks,
    synced_at: new Date().toISOString()
  };
}

function applySyncPayload(payload) {
  jarvisState.reminders = payload.reminders || payload.tasks || [];
  jarvisState.weekly_routine = payload.weekly_routine || [];
  jarvisState.alarms = payload.alarms || [];
  jarvisState.courses = payload.courses || [];
  jarvisState.course_logs = payload.course_logs || [];
  jarvisState.business_deliverables = payload.business_deliverables || [];
  jarvisState.small_tasks = payload.small_tasks || [];
  jarvisState.lastSyncedAt = payload.synced_at || new Date().toISOString();

  renderAllSections();
}

/* ============================================================================
   3. 5-SECOND OFFLINE REMINDER WATCHDOG & 15-SECOND "Anas, wake up!" ALARM LOOP
   ============================================================================ */

async function fireCapacitorLocalNotification(title, body, id = 1001) {
  try {
    const cap = window.Capacitor;
    if (cap && cap.Plugins && cap.Plugins.LocalNotifications) {
      await cap.Plugins.LocalNotifications.schedule({
        notifications: [
          {
            title,
            body,
            id,
            schedule: { at: new Date(Date.now() + 250) }
          }
        ]
      });
      return;
    }
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(title, { body });
    }
  } catch (e) {}
}

function speakText(text) {
  try {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    }
  } catch (e) {}
}

function runLocalOfflineWatchdog() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const currentHHMM = `${hh}:${mm}`;

  // 1. Check offline-cached reminders for due items every 5 seconds
  const dueReminders = (jarvisState.reminders || []).filter((r) => {
    const st = String(r.status || '').toLowerCase();
    if (st !== 'confirmed' && st !== 'scheduled') return false;
    if (!r.due_datetime) return false;
    const dueTime = new Date(r.due_datetime);
    return !isNaN(dueTime.getTime()) && dueTime <= now && !jarvisState.notifiedReminderIds.has(r.id);
  });

  dueReminders.forEach((rem) => {
    jarvisState.notifiedReminderIds.add(rem.id);
    showDueReminderBanner(rem);
    fireCapacitorLocalNotification('Jarvis Reminder Due Now', rem.title, Number(rem.id) || 2001);
  });

  // 2. Check offline-cached alarms for matching HH:MM or ringing state
  const alarms = jarvisState.alarms || [];
  for (const alarm of alarms) {
    const alarmHHMM = String(alarm.alarm_time || '').slice(0, 5);
    if (alarm.state === 'ringing' || (alarm.state === 'scheduled' && alarmHHMM === currentHHMM)) {
      if (!jarvisState.activeRingingAlarm || jarvisState.activeRingingAlarm.id !== alarm.id) {
        alarm.state = 'ringing';
        startWakeUpLoop(alarm);
      }
      break;
    }
  }
}

function showDueReminderBanner(reminder) {
  const banner = document.getElementById('dueAlertBanner');
  const textEl = document.getElementById('dueAlertText');
  if (banner && textEl) {
    textEl.textContent = `DUE NOW: ${reminder.title} (${reminder.raw_due_text || reminder.due_datetime || 'Scheduled'})`;
    banner.classList.remove('hidden');
  }
  speakText(`Reminder due now: ${reminder.title}`);
}

function dismissDueAlertBanner() {
  const banner = document.getElementById('dueAlertBanner');
  if (banner) banner.classList.add('hidden');
}

function startWakeUpLoop(alarm) {
  jarvisState.activeRingingAlarm = alarm;
  const modal = document.getElementById('wakeModal');
  const promptEl = document.getElementById('wakeModalTaskPrompt');
  const timeEl = document.getElementById('wakeModalTime');

  const firstTask = alarm.first_task_prompt || alarm.label || 'Review your core schedule and start your first priority block';
  if (promptEl) promptEl.textContent = firstTask;
  if (timeEl) timeEl.textContent = alarm.alarm_time || 'NOW';
  if (modal) modal.classList.remove('hidden');

  fireCapacitorLocalNotification('Anas, wake up!', `First task: ${firstTask}`, 9999);

  const speakWakePhrase = () => {
    const phrase = `Anas, wake up! Your first task is ${firstTask}. Complete your proof of wake check now.`;
    speakText(phrase);
  };

  speakWakePhrase();
  if (jarvisState.wakeLoopIntervalId) {
    clearInterval(jarvisState.wakeLoopIntervalId);
  }
  // Repeat every 15 seconds until user completes Proof-of-Wake check
  jarvisState.wakeLoopIntervalId = setInterval(speakWakePhrase, 15000);
}

function stopWakeUpLoop() {
  if (jarvisState.wakeLoopIntervalId) {
    clearInterval(jarvisState.wakeLoopIntervalId);
    jarvisState.wakeLoopIntervalId = null;
  }
  try {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  } catch (e) {}
  jarvisState.activeRingingAlarm = null;
  const modal = document.getElementById('wakeModal');
  if (modal) modal.classList.add('hidden');
}

async function submitWakeVerification() {
  const alarm = jarvisState.activeRingingAlarm;
  const phraseInput = document.getElementById('wakeVerificationInput');
  const checkbox = document.getElementById('wakeFirstTaskCheck');
  const statusEl = document.getElementById('wakeVerifyStatus');

  const spokenOrTyped = phraseInput ? phraseInput.value.trim() : '';
  const firstTaskConfirmed = checkbox ? checkbox.checked : false;

  if (!spokenOrTyped && !firstTaskConfirmed) {
    if (statusEl) {
      statusEl.textContent = 'Please type/speak your wake phrase (e.g. "I am awake") or check the First-Task confirmation box.';
      statusEl.className = 'text-xs text-rose-400 font-semibold';
    }
    return;
  }

  try {
    if (alarm && alarm.id) {
      await fetch(`/api/alarms/${alarm.id}/verify-wake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spoken_phrase: spokenOrTyped || 'I am awake and starting first task',
          first_task_confirmed: true
        })
      });
    }
  } catch (e) {}

  if (alarm) alarm.state = 'acknowledged';
  stopWakeUpLoop();
  if (phraseInput) phraseInput.value = '';
  if (checkbox) checkbox.checked = false;
  await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
  renderAlarmsSection();
}

async function triggerTestWakeAlarm() {
  let targetAlarm = (jarvisState.alarms || [])[0];
  if (!targetAlarm) {
    targetAlarm = {
      id: Date.now(),
      alarm_time: '06:00',
      label: 'Anas Morning Deep Work Alarm',
      first_task_prompt: 'Start your #1 high-impact client deliverable & review routine blocks',
      state: 'ringing'
    };
    jarvisState.alarms.unshift(targetAlarm);
  } else {
    targetAlarm.state = 'ringing';
  }
  renderAlarmsSection();
  startWakeUpLoop(targetAlarm);
}

/* ============================================================================
   4. VOICE CAPTURE & DASHBOARD INTERACTIONS (ONLINE + OFFLINE FALLBACK)
   ============================================================================ */

async function toggleMobileVoiceCapture() {
  const btn = document.getElementById('mobileVoiceRecordBtn');
  const statusEl = document.getElementById('mobileCaptureStatus');

  if (jarvisState.mediaRecorder && jarvisState.mediaRecorder.state === 'recording') {
    jarvisState.mediaRecorder.stop();
    if (btn) btn.textContent = '🎤 Speak Task';
    return;
  }

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      jarvisState.audioChunks = [];
      const recorder = new MediaRecorder(stream);
      jarvisState.mediaRecorder = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) jarvisState.audioChunks.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(jarvisState.audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', blob, 'mobile_voice.webm');
        try {
          const res = await fetch('/api/voice/capture', { method: 'POST', body: formData });
          const data = await res.json();
          if (data && data.transcript) {
            const input = document.getElementById('quickCaptureInput');
            if (input) input.value = data.transcript;
          }
          await syncAllData();
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = 'Offline: Type task below to stage in local confirmation queue.';
            statusEl.classList.remove('hidden');
          }
        }
      };

      recorder.start();
      if (btn) btn.textContent = '⏹ Stop Recording';
      return;
    } catch (e) {}
  }

  // Fallback to Web Speech API if available
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    const rec = new SpeechRec();
    rec.lang = 'en-US';
    rec.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const input = document.getElementById('quickCaptureInput');
      if (input) input.value = transcript;
    };
    rec.start();
  }
}

async function submitQuickCapture() {
  const input = document.getElementById('quickCaptureInput');
  if (!input || !input.value.trim()) return;
  const text = input.value.trim();
  input.value = '';

  try {
    const res = await fetch('/api/reminders/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!res.ok) throw new Error('Stage failed');
    await syncAllData();
  } catch (e) {
    // Offline local staging fallback
    jarvisState.reminders.unshift({
      id: Date.now(),
      title: text,
      due_datetime: new Date(Date.now() + 3600000).toISOString(),
      raw_due_text: 'staged offline (+1h)',
      priority: 'normal',
      category: 'general',
      status: 'pending_confirmation'
    });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderRemindersSection();
  }
}

async function confirmReminderAction(id) {
  try {
    await fetch(`/api/reminders/${id}/confirm`, { method: 'POST' });
    await syncAllData();
  } catch (e) {
    const item = jarvisState.reminders.find((r) => r.id === id);
    if (item) item.status = 'confirmed';
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderRemindersSection();
  }
}

async function rejectReminderAction(id) {
  try {
    await fetch(`/api/reminders/${id}/reject`, { method: 'POST' });
    await syncAllData();
  } catch (e) {
    jarvisState.reminders = jarvisState.reminders.filter((r) => r.id !== id);
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderRemindersSection();
  }
}

async function completeReminderAction(id) {
  try {
    await fetch(`/api/reminders/${id}/done`, { method: 'POST' });
    await syncAllData();
  } catch (e) {
    const item = jarvisState.reminders.find((r) => r.id === id);
    if (item) item.status = 'done';
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderAllSections();
  }
}

/* ============================================================================
   5. RENDERING ALL 5 SECTIONS
   ============================================================================ */

function switchDashboardTab(tabName) {
  const tabs = ['today', 'routine', 'alarm', 'nightly', 'business'];
  tabs.forEach((t) => {
    const sec = document.getElementById(`section-${t}`);
    const btn = document.getElementById(`nav-btn-${t}`);
    if (sec) {
      if (t === tabName) sec.classList.remove('hidden');
      else sec.classList.add('hidden');
    }
    if (btn) {
      if (t === tabName) {
        btn.className = 'py-2.5 px-3 rounded-xl border bg-cyan-500/20 border-cyan-400 text-cyan-300 transition text-center';
      } else {
        btn.className = 'py-2.5 px-3 rounded-xl border border-transparent text-slate-400 hover:text-white transition text-center';
      }
    }
  });
}

function renderAllSections() {
  renderRemindersSection();
  renderProposedAuditInputList();
  renderWeeklyRoutineSection();
  renderAlarmsSection();
  renderNightlyAuditSection();
  renderBusinessSection();
}

function renderRemindersSection() {
  const pendingContainer = document.getElementById('pendingRemindersList');
  const confirmedContainer = document.getElementById('confirmedRemindersList');
  const pendingCountBadge = document.getElementById('pendingCountBadge');
  const confirmedCountBadge = document.getElementById('confirmedCountBadge');
  if (!pendingContainer || !confirmedContainer) return;

  const pending = (jarvisState.reminders || []).filter((r) => r.status === 'pending_confirmation');
  const confirmed = (jarvisState.reminders || []).filter((r) => r.status === 'confirmed' || r.status === 'scheduled');

  if (pendingCountBadge) pendingCountBadge.textContent = `${pending.length} Pending`;
  if (confirmedCountBadge) confirmedCountBadge.textContent = `${confirmed.length} Confirmed`;

  pendingContainer.innerHTML = pending.length === 0
    ? '<div class="text-xs text-slate-400 py-3 text-center">No tasks waiting for confirmation.</div>'
    : pending.map((r) => `
      <div class="p-3 rounded-xl bg-slate-900/90 border border-amber-500/30 flex items-center justify-between gap-2">
        <div>
          <div class="text-xs font-semibold text-white">${escapeHtml(r.title)}</div>
          <div class="text-[11px] text-slate-400">${escapeHtml(r.raw_due_text || r.due_datetime || 'Unscheduled')}</div>
        </div>
        <div class="flex gap-1.5">
          <button onclick="confirmReminderAction(${r.id})" class="btn-emerald px-2.5 py-1 rounded-lg bg-emerald-500 text-slate-950 text-xs font-bold">Confirm</button>
          <button onclick="rejectReminderAction(${r.id})" class="btn-rose px-2.5 py-1 rounded-lg bg-rose-500/20 text-rose-300 text-xs font-bold">Reject</button>
        </div>
      </div>
    `).join('');

  confirmedContainer.innerHTML = confirmed.length === 0
    ? '<div class="text-xs text-slate-400 py-3 text-center">No confirmed tasks cached yet.</div>'
    : confirmed.map((r) => `
      <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between gap-2">
        <div>
          <div class="text-xs font-semibold text-emerald-300">${escapeHtml(r.title)}</div>
          <div class="text-[11px] text-slate-400 font-mono">${escapeHtml(r.due_datetime || r.raw_due_text || 'Scheduled')}</div>
        </div>
        <button onclick="completeReminderAction(${r.id})" class="btn-slate px-2.5 py-1 rounded-lg text-xs">Done</button>
      </div>
    `).join('');
}

function addProposedAuditTask() {
  const titleEl = document.getElementById('auditTaskTitle');
  const minsEl = document.getElementById('auditTaskMinutes');
  const prefEl = document.getElementById('auditTaskPrefTime');
  const prioEl = document.getElementById('auditTaskPriority');
  if (!titleEl || !titleEl.value.trim()) return;

  jarvisState.proposedAuditTasks.push({
    title: titleEl.value.trim(),
    estimated_minutes: parseInt(minsEl ? minsEl.value : '60', 10) || 60,
    preferred_time: prefEl && prefEl.value.trim() ? prefEl.value.trim() : null,
    priority: prioEl ? prioEl.value : 'normal'
  });
  titleEl.value = '';
  renderProposedAuditInputList();
}

function removeProposedAuditTask(idx) {
  jarvisState.proposedAuditTasks.splice(idx, 1);
  renderProposedAuditInputList();
}

function renderProposedAuditInputList() {
  const listEl = document.getElementById('proposedAuditTasksList');
  if (!listEl) return;
  listEl.innerHTML = (jarvisState.proposedAuditTasks || []).map((t, idx) => `
    <div class="flex items-center justify-between px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-xs">
      <span class="text-slate-200 font-medium">${escapeHtml(t.title)} (${t.estimated_minutes}m • ${escapeHtml(t.priority)})</span>
      <button onclick="removeProposedAuditTask(${idx})" class="text-rose-400 text-xs">Remove</button>
    </div>
  `).join('');
}

async function runHardRoutineAudit() {
  try {
    const res = await fetch('/api/routine/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tasks: jarvisState.proposedAuditTasks, day_of_week: 'Daily' })
    });
    if (!res.ok) throw new Error('Offline audit fallback');
    jarvisState.lastAuditResult = await res.json();
  } catch (e) {
    // Deterministic offline Hard Routine Audit calculation
    const lockedMins = 13 * 60;
    const trueFreeMins = 24 * 60 - lockedMins;
    let used = 0;
    const core = [];
    const overflow = [];
    for (const t of jarvisState.proposedAuditTasks) {
      const buffered = Math.round((t.estimated_minutes || 60) * 1.15);
      if (used + buffered <= trueFreeMins) {
        used += buffered;
        core.push({ ...t, buffered_minutes: buffered });
      } else {
        overflow.push({ ...t, buffered_minutes: buffered, overflow_reason: 'Exceeds True Free Hours' });
      }
    }
    jarvisState.lastAuditResult = {
      advisory_mode: true,
      locked_minutes: lockedMins,
      true_free_minutes: trueFreeMins,
      true_free_hours: +(trueFreeMins / 60).toFixed(2),
      proposed_buffered_minutes: used,
      overloaded: overflow.length > 0,
      warnings: overflow.length > 0 ? ['Overload detected against Fixed Weekly Routine.'] : ['Schedule fits within True Free Hours (+15% buffer).'],
      core_schedule: core,
      overflow_tasks: overflow
    };
  }
  renderAuditResultPanel();
}

function renderAuditResultPanel() {
  const res = jarvisState.lastAuditResult;
  const panel = document.getElementById('auditResultPanel');
  if (!res || !panel) return;
  panel.classList.remove('hidden');

  const summary = document.getElementById('auditMetricsSummary');
  if (summary) {
    summary.innerHTML = `
      <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs">True Free: <strong class="text-emerald-400">${res.true_free_hours}h (${res.true_free_minutes}m)</strong></div>
      <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs">Buffered Demand: <strong class="text-cyan-300">${res.proposed_buffered_minutes}m</strong></div>
      <div class="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs">Core / Overflow: <strong>${(res.core_schedule || []).length} / ${(res.overflow_tasks || []).length}</strong></div>
    `;
  }

  const coreEl = document.getElementById('auditCoreScheduleList');
  if (coreEl) {
    coreEl.innerHTML = (res.core_schedule || []).map((t) => `
      <div class="p-2 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-xs text-white">
        ${escapeHtml(t.title)} (${t.buffered_minutes || t.estimated_minutes}m)
      </div>
    `).join('');
  }

  const overEl = document.getElementById('auditOverflowList');
  if (overEl) {
    overEl.innerHTML = (res.overflow_tasks || []).length === 0
      ? '<div class="text-xs text-slate-400">Zero overflow.</div>'
      : (res.overflow_tasks || []).map((t) => `
        <div class="p-2 rounded-lg bg-amber-950/30 border border-amber-500/30 text-xs text-amber-200">
          ${escapeHtml(t.title)} (${t.buffered_minutes || t.estimated_minutes}m)
        </div>
      `).join('');
  }
}

async function commitRoutinePlan(mode) {
  const res = jarvisState.lastAuditResult;
  if (!res) return;
  const confirmEl = document.getElementById('commitUserConfirmedCheck');
  if (confirmEl && !confirmEl.checked) return;

  try {
    await fetch('/api/routine/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode,
        user_confirmed: true,
        core_schedule: res.core_schedule || [],
        overflow_tasks: res.overflow_tasks || []
      })
    });
    await syncAllData();
  } catch (e) {
    const toCommit = mode === 'force_all'
      ? [...(res.core_schedule || []), ...(res.overflow_tasks || [])]
      : (res.core_schedule || []);
    toCommit.forEach((t, i) => {
      jarvisState.reminders.push({
        id: Date.now() + i,
        title: t.title,
        due_datetime: new Date(Date.now() + (i + 1) * 1800000).toISOString(),
        raw_due_text: t.preferred_time || 'Today',
        priority: t.priority || 'normal',
        status: 'confirmed'
      });
    });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderRemindersSection();
  }
}

function renderWeeklyRoutineSection() {
  const listEl = document.getElementById('weeklyRoutineList');
  const summaryEl = document.getElementById('weeklyTrueFreeSummary');
  if (!listEl) return;

  const blocks = jarvisState.weekly_routine || [];
  if (summaryEl) {
    summaryEl.textContent = `${blocks.length} Fixed Routine Blocks Cached Offline`;
  }

  listEl.innerHTML = blocks.map((b) => `
    <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between gap-2 text-xs">
      <div>
        <span class="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 font-mono mr-2">${escapeHtml(b.day_of_week)}</span>
        <strong class="text-white">${escapeHtml(b.title)}</strong>
      </div>
      <div class="flex items-center gap-2">
        <span class="font-mono text-slate-300">${escapeHtml(b.start_time)} - ${escapeHtml(b.end_time)}</span>
        <button onclick="deleteWeeklyRoutineBlock(${b.id})" class="text-rose-400 text-xs">Delete</button>
      </div>
    </div>
  `).join('');
}

async function addWeeklyRoutineBlock() {
  const day = document.getElementById('routineDayInput')?.value || 'Daily';
  const title = document.getElementById('routineTitleInput')?.value?.trim();
  const start = document.getElementById('routineStartInput')?.value || '09:00';
  const end = document.getElementById('routineEndInput')?.value || '11:00';
  const category = document.getElementById('routineCategoryInput')?.value || 'Core Routine';
  if (!title) return;

  try {
    await fetch('/api/routine/weekly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ day_of_week: day, title, start_time: start, end_time: end, category, is_locked: true })
    });
    await syncAllData();
  } catch (e) {
    jarvisState.weekly_routine.push({ id: Date.now(), day_of_week: day, title, start_time: start, end_time: end, category, is_locked: 1 });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderWeeklyRoutineSection();
  }
}

async function deleteWeeklyRoutineBlock(id) {
  try {
    await fetch(`/api/routine/weekly/${id}`, { method: 'DELETE' });
    await syncAllData();
  } catch (e) {
    jarvisState.weekly_routine = jarvisState.weekly_routine.filter((b) => b.id !== id);
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderWeeklyRoutineSection();
  }
}

function renderAlarmsSection() {
  const container = document.getElementById('alarmsListContainer');
  if (!container) return;
  const alarms = jarvisState.alarms || [];

  container.innerHTML = alarms.map((a) => `
    <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-800 flex items-center justify-between gap-2 text-xs">
      <div>
        <span class="text-base font-mono font-extrabold text-cyan-400 mr-2">${escapeHtml(a.alarm_time)}</span>
        <strong class="text-white">${escapeHtml(a.label)}</strong>
        <div class="text-[11px] text-slate-400">First Task: ${escapeHtml(a.first_task_prompt || 'Start priority task')} (${escapeHtml(a.state)})</div>
      </div>
      <div class="flex items-center gap-1.5">
        <button onclick='startWakeUpLoop(${JSON.stringify(a).replace(/'/g, "&#39;")})' class="btn-rose px-2.5 py-1 rounded-lg text-xs">Ring Now</button>
        <button onclick="deleteAlarmEntry(${a.id})" class="btn-slate px-2 py-1 rounded-lg text-xs text-rose-300">Delete</button>
      </div>
    </div>
  `).join('');
}

async function createAlarmEntry() {
  const alarm_time = document.getElementById('alarmTimeInput')?.value || '06:00';
  const label = document.getElementById('alarmLabelInput')?.value?.trim() || 'Anas Morning Wake-Up';
  const first_task_prompt = document.getElementById('alarmFirstTaskInput')?.value?.trim() || 'Start #1 Core Task';

  try {
    await fetch('/api/alarms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alarm_time, label, first_task_prompt, state: 'scheduled' })
    });
    await syncAllData();
  } catch (e) {
    jarvisState.alarms.unshift({ id: Date.now(), alarm_time, label, first_task_prompt, state: 'scheduled' });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderAlarmsSection();
  }
}

async function deleteAlarmEntry(id) {
  try {
    await fetch(`/api/alarms/${id}`, { method: 'DELETE' });
    await syncAllData();
  } catch (e) {
    jarvisState.alarms = jarvisState.alarms.filter((a) => a.id !== id);
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderAlarmsSection();
  }
}

function renderNightlyAuditSection() {
  const checklistEl = document.getElementById('nightlyTaskChecklist');
  if (!checklistEl) return;
  const active = (jarvisState.reminders || []).filter((r) => r.status === 'confirmed' || r.status === 'done');
  checklistEl.innerHTML = active.length === 0
    ? '<div class="text-xs text-slate-400">No confirmed tasks today.</div>'
    : active.map((r) => `
      <label class="flex items-center gap-2 p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-xs">
        <input type="checkbox" ${r.status === 'done' ? 'checked' : ''} onchange="completeReminderAction(${r.id})">
        <span class="text-white">${escapeHtml(r.title)}</span>
      </label>
    `).join('');
}

async function submitNightlyAudit() {
  const course_id = parseInt(document.getElementById('nightlyCourseSelect')?.value || '1', 10);
  const topic = document.getElementById('nightlyTopicInput')?.value?.trim() || 'Core Engineering Module';
  const raw_reflection = document.getElementById('nightlyReflectionInput')?.value?.trim() || 'Completed key lesson takeaways.';

  try {
    const res = await fetch('/api/nightly/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id, topic, raw_reflection, completed_ids: [], missed_ids: [] })
    });
    const data = await res.json();
    const notesEl = document.getElementById('nightlyStructuredNotesOutput');
    if (notesEl && data.course_entry) {
      notesEl.textContent = data.course_entry.structured_notes;
      notesEl.classList.remove('hidden');
    }
    const quizEl = document.getElementById('nightlyRecallQuizContainer');
    const questions = data.recall_quiz_from_previous_lesson || (data.course_entry && data.course_entry.quiz) || [];
    if (quizEl) {
      quizEl.innerHTML = questions.map((q, i) => `
        <div class="p-3 rounded-xl bg-slate-900 border border-cyan-500/30 text-xs space-y-1">
          <div class="font-bold text-cyan-300">Q${i + 1}: ${escapeHtml(q.question)}</div>
          <div class="text-slate-400">Expected Hint: ${escapeHtml(q.expected_answer_hint || 'Explain key concept & production application')}</div>
        </div>
      `).join('');
    }
  } catch (e) {}
}

function renderBusinessSection() {
  const delivEl = document.getElementById('businessDeliverablesList');
  const smallEl = document.getElementById('smallTasksStagedList');
  if (delivEl) {
    delivEl.innerHTML = (jarvisState.business_deliverables || []).map((d) => `
      <div class="p-3 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between text-xs">
        <div>
          <strong class="text-white">${escapeHtml(d.client_name)}: ${escapeHtml(d.title)}</strong>
          <div class="text-slate-400">Due: ${escapeHtml(d.deadline)} • Impact ${d.impact_score}/10</div>
        </div>
        <span class="px-2 py-1 rounded bg-cyan-500/15 text-cyan-300 font-mono">Urgency ${d.urgency_score || 85}</span>
      </div>
    `).join('');
  }
  if (smallEl) {
    smallEl.innerHTML = (jarvisState.small_tasks || []).map((st) => `
      <div class="p-3 rounded-xl bg-slate-900 border border-purple-500/30 text-xs space-y-1">
        <div class="font-bold text-purple-300 uppercase">${escapeHtml(st.task_type)}: ${escapeHtml(st.prompt)}</div>
        <pre class="text-[11px] text-slate-300 whitespace-pre-wrap font-mono">${escapeHtml(st.result_content)}</pre>
      </div>
    `).join('');
  }
}

async function addBusinessDeliverable() {
  const client_name = document.getElementById('bizClientInput')?.value?.trim();
  const title = document.getElementById('bizTitleInput')?.value?.trim();
  const deadline = document.getElementById('bizDeadlineInput')?.value || new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const estimated_hours = parseFloat(document.getElementById('bizHoursInput')?.value || '4');
  const impact_score = parseInt(document.getElementById('bizImpactInput')?.value || '8', 10);
  if (!client_name || !title) return;

  try {
    await fetch('/api/business/deliverables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_name, title, deadline, estimated_hours, impact_score })
    });
    await syncAllData();
  } catch (e) {
    jarvisState.business_deliverables.unshift({ id: Date.now(), client_name, title, deadline, estimated_hours, impact_score, urgency_score: impact_score * 10 });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderBusinessSection();
  }
}

async function runSmallTaskBuddy() {
  const task_type = document.getElementById('smallTaskTypeInput')?.value || 'draft';
  const prompt = document.getElementById('smallTaskPromptInput')?.value?.trim();
  if (!prompt) return;

  try {
    await fetch('/api/business/small-tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, task_type })
    });
    await syncAllData();
  } catch (e) {
    jarvisState.small_tasks.unshift({
      id: Date.now(),
      task_type,
      prompt,
      result_content: `# Offline Staged ${task_type.toUpperCase()}\n- Goal: ${prompt}\n- Status: Queued locally in IndexedDB`
    });
    await saveSyncPayloadToCache(getCurrentPayloadSnapshot());
    renderBusinessSection();
  }
}

/* ============================================================================
   6. BOOTSTRAP MOBILE BRIDGE
   ============================================================================ */

window.addEventListener('DOMContentLoaded', async () => {
  const urlInput = document.getElementById('mobileBackendUrlInput');
  const currentUrl = getBackendServerUrl();
  jarvisState.backendUrl = currentUrl;
  if (urlInput) urlInput.value = currentUrl;

  // Request Capacitor / Web notification permission quietly
  try {
    if (window.Capacitor?.Plugins?.LocalNotifications) {
      await window.Capacitor.Plugins.LocalNotifications.requestPermissions();
    }
  } catch (e) {}

  // Load local IndexedDB/localStorage cache immediately for instant 0ms mobile startup
  const cached = await loadSyncPayloadFromCache();
  if (cached && cached.data) {
    applySyncPayload(cached.data);
  } else {
    applySyncPayload(DEFAULT_OFFLINE_SEED);
  }

  // Sync live with Python Backend + Native PostgreSQL if reachable
  await syncAllData();

  // Start 5-second Offline Reminder & Alarm Watchdog Timer
  setInterval(runLocalOfflineWatchdog, 5000);
  // Auto-sync with backend every 25 seconds when online
  setInterval(() => {
    if (navigator.onLine) syncAllData();
  }, 25000);

  window.addEventListener('online', () => syncAllData());
  window.addEventListener('offline', () => updateConnectionStatusUI(false, jarvisState.lastSyncedAt));
});
