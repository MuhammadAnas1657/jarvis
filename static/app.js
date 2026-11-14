/**
 * JARVIS 24/7 Personal Accountability & Autonomous Business Buddy
 * Single-Page Client Application Engine
 * Supports:
 *  - 1-Click Multi-Theme System (White Neumorphic, Stark Cyan HUD, Cyberpunk Neon)
 *  - Dynamic 7-Font Selection Engine
 *  - Live HUD Digital Clock & System Telemetry
 *  - Interactive Discussion & Chat Window with Jarvis (POST /api/chat + Groq LLaMA-3.3 70B)
 *  - Arc Reactor Voice Recording & Temporal Extraction Matrix
 *  - 6-Tab Complete Accountability & Business Suite
 *  - 100% Offline Resilience (Service Worker + IndexedDB + LocalStorage)
 */

const IDB_NAME = 'jarvis_offline_pwa_db';
const IDB_VERSION = 1;
const IDB_STORE = 'sync_cache';
const LS_CACHE_KEY = 'jarvis_offline_sync_snapshot_v1';
const CHAT_STORAGE_KEY = 'jarvis_neural_chat_history_v2';
const CONFIGURED_API_URL = (typeof window !== 'undefined' && window.JARVIS_API_URL) ? window.JARVIS_API_URL : '';

// Transparent API URL resolver: proxies /api/* or direct backend fallback
const _origFetch = typeof window !== 'undefined' && window.fetch ? window.fetch.bind(window) : null;
if (_origFetch && typeof window !== 'undefined') {
  window.fetch = async (input, init) => {
    const urlStr = typeof input === 'string' ? input : (input && input.url ? input.url : String(input));
    const isBackendRoute = urlStr.startsWith('/api/') || urlStr.startsWith('/reminders') || urlStr.startsWith('/actions');
    try {
      const res = await _origFetch(input, init);
      if (isBackendRoute && res.status === 503 && window.location.port !== '8000') {
        const directTarget = (CONFIGURED_API_URL || 'http://localhost:8000').replace(/\/+$/, '') + urlStr;
        return await _origFetch(directTarget, init);
      }
      return res;
    } catch (err) {
      if (isBackendRoute && window.location.port !== '8000') {
        const directTarget = (CONFIGURED_API_URL || 'http://localhost:8000').replace(/\/+$/, '') + urlStr;
        return await _origFetch(directTarget, init);
      }
      throw err;
    }
  };
}

let deferredInstallPrompt = null;
let activeMediaRecorder = null;
let recordedAudioChunks = [];
let activeVoiceTarget = null;
let arcMediaRecorder = null;
let arcAudioChunks = [];
let arcIsRecording = false;
let chatHistory = [];

let jarvisState = {
  online: typeof navigator !== 'undefined' ? navigator.onLine : true,
  lastSyncedAt: null,
  reminders: [],
  weekly_routine: [],
  alarms: [],
  courses: [],
  course_logs: [],
  business_deliverables: [],
  small_tasks: [],
  lastAuditResult: null,
  lastRecallQuiz: [],
  proposedAuditTasks: [],
  routine_completions: [],
  activeRingingAlarm: null,
  wakeLoopIntervalId: null,
  notifiedReminderIds: new Set(),
  lastDisciplineScore: 85
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
   RADIAL DISCIPLINE GAUGE & COGNITIVE EQUALIZER ENGINE
   ============================================================================ */

let cachedDisciplineScore = 85;
function updateDisciplineGauge(score) {
  cachedDisciplineScore = score;
  const valueEl = document.getElementById('disciplineScoreValue');
  const badgeEl = document.getElementById('nightlyDisciplineScoreBadge');
  const circleEl = document.getElementById('disciplineGaugeCircle');

  const validScore = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));

  if (valueEl) valueEl.textContent = `${validScore}%`;
  if (badgeEl) badgeEl.textContent = `${validScore}%`;

  if (circleEl) {
    const circumference = 339.29; // 2 * Math.PI * 54
    const offset = circumference - (validScore / 100) * circumference;
    circleEl.style.strokeDashoffset = offset;
    
    // Choose clean accent color based on score
    if (validScore >= 80) {
      circleEl.setAttribute('stroke', '#2563eb'); // Modern Royal Blue
    } else if (validScore >= 50) {
      circleEl.setAttribute('stroke', '#0ea5e9'); // Sky Blue
    } else {
      circleEl.setAttribute('stroke', '#f59e0b'); // Amber
    }
  }
}
function startEqualizerAnimation(stream) {
  const bars = [
    document.getElementById('eqBar1'),
    document.getElementById('eqBar2'),
    document.getElementById('eqBar3'),
    document.getElementById('eqBar4'),
    document.getElementById('eqBar5')
  ];

  if (stream && (window.AudioContext || window.webkitAudioContext)) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      eqAudioContext = new AudioCtx();
      const source = eqAudioContext.createMediaStreamSource(stream);
      eqAnalyser = eqAudioContext.createAnalyser();
      eqAnalyser.fftSize = 32;
      source.connect(eqAnalyser);
      eqDataArray = new Uint8Array(eqAnalyser.frequencyBinCount);

      function updateRealtimeEQ() {
        if (!eqAnalyser) return;
        eqAnalyser.getByteFrequencyData(eqDataArray);
        for (let i = 0; i < 5; i++) {
          const val = eqDataArray[i * 2] || 0;
          const pct = Math.max(20, Math.min(100, Math.round((val / 255) * 100)));
          if (bars[i]) bars[i].style.height = `${pct}%`;
        }
        if (eqAnimInterval) {
          requestAnimationFrame(updateRealtimeEQ);
        }
      }
      eqAnimInterval = true;
      requestAnimationFrame(updateRealtimeEQ);
      return;
    } catch (e) {
      console.warn('WebAudio equalizer fallback to simulated pulse:', e);
    }
  }

  // Fallback pulse loop for browsers or headless audio
  if (typeof eqAnimInterval === 'number') clearInterval(eqAnimInterval);
  eqAnimInterval = setInterval(() => {
    bars.forEach((bar) => {
      if (bar) {
        const rand = Math.floor(Math.random() * 65) + 35;
        bar.style.height = `${rand}%`;
      }
    });
  }, 100);
}

function stopEqualizerAnimation() {
  if (typeof eqAnimInterval === 'number') {
    clearInterval(eqAnimInterval);
  }
  eqAnimInterval = null;
  if (eqAudioContext && eqAudioContext.state !== 'closed') {
    eqAudioContext.close().catch(() => {});
    eqAudioContext = null;
  }
  eqAnalyser = null;
  eqDataArray = null;

  const idleHeights = [65, 85, 45, 75, 90];
  for (let i = 1; i <= 5; i++) {
    const bar = document.getElementById(`eqBar${i}`);
    if (bar) bar.style.height = `${idleHeights[i - 1]}%`;
  }
}

/* ============================================================================
   1. THEME SWITCHING & DYNAMIC FONT SYSTEM
   ============================================================================ */

function applyTheme(theme) {
  const isDark = (theme !== 'white');
  const root = document.documentElement;
  root.classList.remove('theme-white', 'theme-dark', 'dark');
  root.classList.add(isDark ? 'theme-dark' : 'theme-white');
  if (isDark) root.classList.add('dark');
  localStorage.setItem('jarvis_theme_mode', isDark ? 'dark' : 'white');
  const on = "px-3 py-1.5 rounded-lg text-xs font-bold transition-all bg-[var(--hud-accent)] text-white";
  const off = "px-3 py-1.5 rounded-lg text-xs font-medium transition-all text-[var(--text-muted)]";
  const w = document.getElementById('theme-btn-white'), d = document.getElementById('theme-btn-dark');
  if (w && d) { w.className = isDark ? off : on; d.className = isDark ? on : off; }
  if (typeof updateDisciplineGauge === 'function') updateDisciplineGauge(cachedDisciplineScore || 85);
}
function applyFont(bodyFont = 'Inter', displayFont = 'Plus Jakarta Sans') {
  document.documentElement.style.setProperty('--font-family-current', `'Inter', 'Plus Jakarta Sans', sans-serif`);
  document.documentElement.style.setProperty('--font-display-current', `'Inter', sans-serif`);
  localStorage.setItem('jarvis_body_font', 'Inter');
  localStorage.setItem('jarvis_display_font', 'Plus Jakarta Sans');
  document.documentElement.style.setProperty('--font-family-current', `'${bodyFont}', sans-serif`);
  document.documentElement.style.setProperty('--font-display-current', `'${displayFont}', monospace`);
  localStorage.setItem('jarvis_body_font', bodyFont);
  localStorage.setItem('jarvis_display_font', displayFont);

  const badge = document.getElementById('activeFontBadge');
  if (badge) badge.textContent = `${bodyFont} / ${displayFont}`;

  const fontOptions = {
    'Rajdhani': 'font-opt-rajdhani',
    'Orbitron': 'font-opt-orbitron',
    'Chakra Petch': 'font-opt-chakra',
    'JetBrains Mono': 'font-opt-jetbrains',
    'Plus Jakarta Sans': 'font-opt-jakarta',
    'Share Tech Mono': 'font-opt-sharetech',
    'Inter': 'font-opt-inter'
  };

  Object.entries(fontOptions).forEach(([fontName, btnId]) => {
    const el = document.getElementById(btnId);
    if (el) {
      if (fontName === bodyFont) {
        el.classList.add('border-[var(--hud-accent)]', 'bg-[var(--hud-accent)]/15');
      } else {
        el.classList.remove('border-[var(--hud-accent)]', 'bg-[var(--hud-accent)]/15');
      }
    }
  });
}

/* ============================================================================
   2. LIVE HUD DIGITAL CLOCK & TELEMETRY
   ============================================================================ */

function updateClock() {
  const now = new Date();
  const clockEl = document.getElementById('hudClock');
  const dateEl = document.getElementById('hudDate');
  if (clockEl) {
    clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: true });
  }
  if (dateEl) {
    dateEl.textContent = now.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  }
}

async function updateTelemetryUI() {
  try {
    const res = await fetch('/api/actions/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'get_system_status', confirmed: true })
    });
    if (res.ok) {
      const data = await res.json();
      if (data && data.stats) {
        const cpuEl = document.getElementById('statCpu');
        const ramEl = document.getElementById('statRam');
        const diskEl = document.getElementById('statDisk');
        if (cpuEl) cpuEl.textContent = `${data.stats.cpu_percent}%`;
        if (ramEl) ramEl.textContent = `${data.stats.ram_used_gb} / ${data.stats.ram_total_gb} GB`;
        if (diskEl) diskEl.textContent = `${data.stats.disk_free_gb} GB`;
      }
    }
  } catch (e) {
    // Non-blocking telemetry
  }
}

/* ============================================================================
   3. TAB 1: INTERACTIVE DISCUSSION & COMMAND CHAT ENGINE (ChatGPT Style)
   ============================================================================ */

const JARVIS_LOGO_DARK = '/static/jarvis-logo-dark.png';
const JARVIS_LOGO_LIGHT = '/static/jarvis-logo-light.png';
const JARVIS_EMBLEM_DARK = '/static/jarvis-emblem-dark.png';
const JARVIS_EMBLEM_LIGHT = '/static/jarvis-emblem-light.png';
const JARVIS_LOGO_SRC = JARVIS_LOGO_DARK;
const CHATS_KEY = 'jarvis_chats_v2';
let chats = [];
let activeChatId = null;

function chatNowTime() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function loadChats() {
  try {
    const raw = localStorage.getItem(CHATS_KEY) || localStorage.getItem('jarvis_chats_v1') || '[]';
    chats = JSON.parse(raw) || [];
  } catch (e) {
    chats = [];
  }
}

function writeChats() {
  try {
    localStorage.setItem(CHATS_KEY, JSON.stringify(chats.slice(0, 100)));
  } catch (e) {}
}

function persistChats() {
  if (!activeChatId) activeChatId = 'c_' + Date.now();
  let c = chats.find(x => x.id === activeChatId);
  if (!c) {
    c = { id: activeChatId, title: 'New Chat', messages: [], updated: Date.now() };
    chats.unshift(c);
  }
  c.messages = (chatHistory || []).slice(-200);
  const firstUserMsg = (chatHistory || []).find(m => m.role === 'user');
  if (firstUserMsg && (!c.title || c.title === 'New Chat' || c.title === 'Discussion with Jarvis')) {
    c.title = firstUserMsg.content.slice(0, 45);
  }
  c.updated = Date.now();
  chats.sort((a, b) => (b.updated || 0) - (a.updated || 0));
  writeChats();
  renderChatList();
  updateHeaderChatTitle();
}

function updateHeaderChatTitle() {
  const titleEl = document.getElementById('currentChatTitle');
  if (!titleEl) return;
  const c = chats.find(x => x.id === activeChatId);
  titleEl.textContent = (c && c.title && c.title !== 'New Chat') ? c.title : 'Discussion with Jarvis';
}

function initChat() {
  loadChats();
  const savedActiveId = localStorage.getItem('jarvis_active_chat_id');
  if (savedActiveId && chats.some(x => x.id === savedActiveId)) {
    openChat(savedActiveId);
  } else if (chats.length > 0) {
    openChat(chats[0].id);
  } else {
    newChat();
  }

  // Keyboard shortcut Ctrl+K or Cmd+K for new chat
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      newChat();
    }
  });
}

function closeMobileChatSidebar() {
  if (window.innerWidth < 768) {
    const sb = document.getElementById('chatSidebar');
    const bd = document.getElementById('chatSidebarBackdrop');
    if (sb) sb.classList.add('hidden');
    if (bd) bd.classList.add('hidden');
  }
}

function newChat() {
  activeChatId = 'c_' + Date.now();
  localStorage.setItem('jarvis_active_chat_id', activeChatId);
  chatHistory = [];
  renderChatMessages();
  renderChatList();
  updateHeaderChatTitle();
  closeMobileChatSidebar();
  const input = document.getElementById('chatInput');
  if (input) input.focus();
}

function openChat(id) {
  const c = chats.find(x => x.id === id);
  if (!c) return;
  activeChatId = id;
  localStorage.setItem('jarvis_active_chat_id', id);
  chatHistory = (c.messages || []).slice();
  renderChatMessages();
  renderChatList();
  updateHeaderChatTitle();
  closeMobileChatSidebar();
  const input = document.getElementById('chatInput');
  if (input) input.focus();
}

function deleteChat(id, ev) {
  if (ev) ev.stopPropagation();
  if (!confirm('Delete this conversation?')) return;
  chats = chats.filter(x => x.id !== id);
  writeChats();
  if (id === activeChatId) {
    if (chats.length > 0) openChat(chats[0].id);
    else newChat();
  } else {
    renderChatList();
  }
}

function renameChat(id, ev) {
  if (ev) ev.stopPropagation();
  const c = chats.find(x => x.id === id);
  if (!c) return;
  const newTitle = prompt('Rename conversation:', c.title || '');
  if (newTitle && newTitle.trim()) {
    c.title = newTitle.trim();
    writeChats();
    renderChatList();
    if (id === activeChatId) updateHeaderChatTitle();
  }
}

function clearAllChats() {
  if (!confirm('Are you sure you want to delete ALL chat history? This cannot be undone.')) return;
  chats = [];
  writeChats();
  newChat();
}

function toggleChatSidebar() {
  const sb = document.getElementById('chatSidebar');
  const bd = document.getElementById('chatSidebarBackdrop');
  if (!sb) return;
  if (window.innerWidth < 768) {
    const isHidden = sb.classList.contains('hidden');
    if (isHidden) {
      sb.classList.remove('hidden');
      if (bd) bd.classList.remove('hidden');
    } else {
      sb.classList.add('hidden');
      if (bd) bd.classList.add('hidden');
    }
  } else {
    sb.classList.toggle('md:hidden');
    sb.classList.toggle('md:flex');
  }
}

function renderChatList() {
  const el = document.getElementById('chatList');
  const countBadge = document.getElementById('chatCountBadge');
  if (countBadge) {
    countBadge.textContent = `${chats.length} chat${chats.length === 1 ? '' : 's'}`;
  }
  if (!el) return;

  const q = ((document.getElementById('chatSearch') || {}).value || '').toLowerCase().trim();
  const filtered = chats.filter(c => {
    if (!q) return true;
    const matchTitle = (c.title || '').toLowerCase().includes(q);
    const matchMsg = (c.messages || []).some(m => (m.content || '').toLowerCase().includes(q));
    return matchTitle || matchMsg;
  });

  if (!filtered.length) {
    el.innerHTML = `
      <div class="text-center py-8 px-3 text-[var(--text-muted)] space-y-1">
        <div class="text-xs font-semibold">No chats found</div>
        <div class="text-[10px]">Start a conversation or adjust your search</div>
      </div>
    `;
    return;
  }

  const oneDay = 86400000;
  const startToday = new Date().setHours(0, 0, 0, 0);
  const getCategory = (ts) => {
    if (!ts) return 'Older';
    if (ts >= startToday) return 'Today';
    if (ts >= startToday - oneDay) return 'Yesterday';
    if (ts >= startToday - 7 * oneDay) return 'Previous 7 Days';
    if (ts >= startToday - 30 * oneDay) return 'Previous 30 Days';
    return 'Older';
  };

  let html = '';
  let lastCategory = '';

  filtered.forEach(c => {
    const cat = getCategory(c.updated);
    if (cat !== lastCategory) {
      html += `<div class="text-[10px] uppercase font-bold text-[var(--text-muted)] pt-3 pb-1 px-1.5">${cat}</div>`;
      lastCategory = cat;
    }
    const isActive = (c.id === activeChatId);
    const safeTitle = escapeHtml(c.title || 'New Chat');

    html += `
      <div onclick="openChat('${c.id}')"
           class="group flex items-center justify-between gap-2 px-3 py-2 rounded-xl cursor-pointer text-xs transition duration-150 ${
             isActive 
               ? 'bg-[var(--hud-accent)] text-white font-semibold shadow-sm' 
               : 'text-[var(--text-sub)] hover:bg-[var(--chip-bg)]'
           }">
        <span class="truncate flex-1 text-left">${safeTitle}</span>
        <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button onclick="renameChat('${c.id}', event)" class="px-1 text-[10px] ${isActive ? 'text-white/80 hover:text-white' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'}" title="Rename">
            Edit
          </button>
          <button onclick="deleteChat('${c.id}', event)" class="px-1 text-[10px] ${isActive ? 'text-white/80 hover:text-white' : 'text-[var(--text-muted)] hover:text-rose-500'}" title="Delete">
            x
          </button>
        </div>
      </div>
    `;
  });

  el.innerHTML = html;
}

function renderChatMessages() {
  const container = document.getElementById('chatMessagesContainer');
  if (!container) return;

  if (!chatHistory || chatHistory.length === 0) {
    container.innerHTML = `
      <div class="h-full flex flex-col items-center justify-center text-center p-6 space-y-4 max-w-md mx-auto my-auto">
        <div class="flex items-center justify-center mb-1 select-none">
          <img src="/static/jarvis-logo-dark.png" alt="JARVIS - Your Personal AI Agent" class="hidden dark:block h-20 w-auto object-contain select-none">
          <img src="/static/jarvis-logo-light.png" alt="JARVIS - Your Personal AI Agent" class="block dark:hidden h-20 w-auto object-contain select-none">
        </div>
        <div>
          <h3 class="text-base font-bold text-[var(--text-main)]">How can I help you today, Anas?</h3>
          <p class="text-xs text-[var(--text-muted)] mt-1">Autonomous Business Buddy &bull; 24/7 Accountability Partner</p>
        </div>
        <div class="grid grid-cols-1 gap-2 w-full pt-2">
          <button onclick="sendChatMessage('Mera schedule aur high impact tasks review karo')" class="p-2.5 rounded-xl hud-raised hover:hud-inset text-xs text-left text-[var(--text-sub)] transition">
            "Mera schedule aur high impact tasks review karo"
          </button>
          <button onclick="sendChatMessage('Tomorrow deep work routine block stage karo')" class="p-2.5 rounded-xl hud-raised hover:hud-inset text-xs text-left text-[var(--text-sub)] transition">
            "Tomorrow deep work routine block stage karo"
          </button>
          <button onclick="sendChatMessage('Draft polite client follow-up update')" class="p-2.5 rounded-xl hud-raised hover:hud-inset text-xs text-left text-[var(--text-sub)] transition">
            "Draft polite client follow-up update"
          </button>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = chatHistory.map((msg, idx) => {
    const isAnas = msg.role === 'user';
    const timeStr = msg.timestamp || chatNowTime();
    const safeContent = escapeHtml(msg.content);

    if (isAnas) {
      return `
        <div class="flex items-start justify-end gap-2.5">
          <div class="max-w-[80%] rounded-2xl rounded-tr-none p-3.5 text-xs font-medium space-y-1 shadow-md" style="background: var(--chat-anas-bg); color: var(--chat-anas-text); border: 1px solid var(--hud-border);">
            <div class="text-[10px] opacity-80 font-mono-code uppercase font-bold flex items-center justify-between gap-2">
              <span>Anas</span>
              <span>${timeStr}</span>
            </div>
            <div class="whitespace-pre-wrap leading-relaxed">${safeContent}</div>
          </div>
          <div class="w-8 h-8 rounded-xl flex items-center justify-center font-bold text-xs bg-blue-600 text-white shadow-sm flex-shrink-0">
            A
          </div>
        </div>
      `;
    } else {
      return `
        <div class="flex items-start gap-2.5">
          <div class="w-7 h-7 flex-shrink-0 flex items-center justify-center pt-0.5 select-none">
            <img src="/static/jarvis-emblem-dark.png" alt="JARVIS" class="hidden dark:block w-7 h-7 object-contain select-none">
            <img src="/static/jarvis-emblem-light.png" alt="JARVIS" class="block dark:hidden w-7 h-7 object-contain select-none">
          </div>
          <div class="max-w-[85%] rounded-2xl rounded-tl-none p-3.5 text-xs border border-[var(--hud-border)] shadow-md space-y-1.5" style="background: var(--chat-jarvis-bg); box-shadow: var(--chat-jarvis-shadow);">
            <div class="flex items-center justify-between gap-3 text-[10px] text-[var(--text-muted)] font-mono-code">
              <span class="font-bold text-[var(--hud-accent)] uppercase">JARVIS &bull; ${timeStr}</span>
              <div class="flex items-center gap-2">
                <button onclick="copyChatMessageText(${idx})" class="hover:text-[var(--hud-accent)] text-[var(--text-muted)] text-[10px] transition" title="Copy text">Copy</button>
                <button onclick="speakChatMessageText(${idx})" class="hover:text-[var(--hud-accent)] text-[var(--text-muted)] text-[10px] transition" title="Speak reply aloud">Listen</button>
              </div>
            </div>
            <div class="text-[var(--text-main)] whitespace-pre-wrap leading-relaxed">${safeContent}</div>
            ${renderActionCardHtml(msg.action, idx)}
          </div>
        </div>
      `;
    }
  }).join('');

  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage(customText, wasVoiceInput = false) {
  const input = document.getElementById('chatInput');
  const text = (customText || (input ? input.value : '')).trim();
  if (!text) return;

  if (input) input.value = '';

  const nowTime = chatNowTime();
  chatHistory.push({
    role: 'user',
    content: text,
    timestamp: nowTime
  });
  renderChatMessages();
  persistChats();

  // Display typing indicator
  const indicator = document.getElementById('chatTypingIndicator');
  if (indicator) indicator.classList.remove('hidden');

  const historyPayload = chatHistory.slice(-10).map(m => ({
    role: m.role,
    content: m.content
  }));

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: historyPayload })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const replyText = data.reply || "Understood, Anas. Request noted.";
    const replyTime = data.timestamp ? new Date(data.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : nowTime;

    chatHistory.push({
      role: 'assistant',
      content: replyText,
      timestamp: replyTime,
      action: data.action || null
    });

    // Auto-Voice speaking power: Speak response aloud if autoVoiceReply is ON or user used Mic
    if (autoVoiceReply || wasVoiceInput) {
      speakText(replyText);
    }
  } catch (err) {
    const fallbackReply = `Jarvis (Offline Fallback): Understood, Anas. "${text}". Local tasks and offline schedules remain synchronized.`;
    chatHistory.push({
      role: 'assistant',
      content: fallbackReply,
      timestamp: nowTime
    });
    if (autoVoiceReply || wasVoiceInput) {
      speakText(fallbackReply);
    }
  } finally {
    if (indicator) indicator.classList.add('hidden');
    persistChats();
    renderChatMessages();
  }
}

function sendQuickPrompt(promptText) {
  sendChatMessage(promptText);
}

function saveChatHistory() {
  persistChats();
}

function clearChatHistory() {
  chatHistory = [];
  persistChats();
  renderChatMessages();
}

function copyChatMessageText(idx) {
  if (chatHistory[idx] && chatHistory[idx].content) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(chatHistory[idx].content);
    }
  }
}

function speakChatMessageText(idx) {
  if (chatHistory[idx] && chatHistory[idx].content) {
    speakText(chatHistory[idx].content);
  }
}

async function toggleChatMic() {
  const statusEl = document.getElementById('chatMicStatus');
  const btn = document.getElementById('chatMicBtn');
  const input = document.getElementById('chatInput');

  // If currently active, stop listening
  if (activeSpeechRecognizer) {
    try { activeSpeechRecognizer.stop(); } catch (e) {}
    activeSpeechRecognizer = null;
    if (btn) btn.classList.remove('bg-rose-500', 'text-white', 'animate-pulse');
    if (statusEl) {
      statusEl.textContent = 'Voice captured. Processing...';
      setTimeout(() => statusEl.classList.add('hidden'), 2500);
    }
    return;
  }

  if (activeMediaRecorder && activeMediaRecorder.state === 'recording') {
    if (statusEl) statusEl.textContent = 'Finishing recording & transcribing...';
    try { activeMediaRecorder.requestData(); } catch (e) {}
    activeMediaRecorder.stop();
    return;
  }

  // METHOD 1: Real-time Web Speech API (Instant, live words streaming on Chrome, Edge, Android)
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    try {
      const recognition = new SpeechRec();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      recognition.lang = 'en-US';

      activeSpeechRecognizer = recognition;
      let finalTranscript = '';

      recognition.onstart = () => {
        if (btn) btn.classList.add('bg-rose-500', 'text-white', 'animate-pulse');
        if (statusEl) {
          statusEl.textContent = 'Listening live... Speak in Urdu or English now.';
          statusEl.classList.remove('hidden');
        }
      };

      recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const trans = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += trans;
          } else {
            interim += trans;
          }
        }
        const currentSpoken = finalTranscript || interim;
        if (input && currentSpoken) {
          input.value = currentSpoken;
        }
        if (statusEl) {
          statusEl.textContent = 'Hearing: "' + currentSpoken + '"';
        }
      };

      recognition.onerror = (event) => {
        console.warn("SpeechRecognition error, falling back to MediaRecorder Whisper:", event.error);
        activeSpeechRecognizer = null;
        if (btn) btn.classList.remove('bg-rose-500', 'text-white', 'animate-pulse');
        if (event.error !== 'no-speech') {
          startMediaRecorderFallback();
        } else {
          if (statusEl) {
            statusEl.textContent = 'No speech detected. Click Mic and speak again.';
            setTimeout(() => statusEl.classList.add('hidden'), 3500);
          }
        }
      };

      recognition.onend = () => {
        activeSpeechRecognizer = null;
        if (btn) btn.classList.remove('bg-rose-500', 'text-white', 'animate-pulse');
        const textToSend = (input ? input.value : finalTranscript).trim();
        if (textToSend) {
          if (statusEl) {
            statusEl.textContent = 'Transcribed: "' + textToSend + '"';
            setTimeout(() => statusEl.classList.add('hidden'), 3000);
          }
          sendChatMessage(textToSend, true);
        } else {
          if (statusEl) {
            statusEl.textContent = 'Ready.';
            setTimeout(() => statusEl.classList.add('hidden'), 2000);
          }
        }
      };

      recognition.start();
      return;
    } catch (e) {
      console.warn("SpeechRecognition start failed, using MediaRecorder fallback", e);
    }
  }

  // METHOD 2: Fallback to MediaRecorder + Groq Whisper Pool
  startMediaRecorderFallback();
}

async function startMediaRecorderFallback() {
  const statusEl = document.getElementById('chatMicStatus');
  const btn = document.getElementById('chatMicBtn');
  const input = document.getElementById('chatInput');

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedAudioChunks = [];
    activeMediaRecorder = new MediaRecorder(stream);

    activeMediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedAudioChunks.push(e.data);
    };

    activeMediaRecorder.onstop = async () => {
      stopEqualizerAnimation();
      if (statusEl) {
        statusEl.textContent = 'Transcribing voice via Groq Whisper...';
        statusEl.classList.remove('hidden');
      }
      try {
        const audioBlob = new Blob(recordedAudioChunks, { type: 'audio/webm' });
        if (audioBlob.size < 1000) {
          if (statusEl) {
            statusEl.textContent = 'Recording was too short. Hold mic, speak, then click again.';
            setTimeout(() => statusEl.classList.add('hidden'), 3500);
          }
          return;
        }

        const formData = new FormData();
        formData.append('file', audioBlob, 'chat_voice.webm');
        const res = await fetch('/api/voice/capture', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        const text = (data.transcript || '').trim();
        if (text && !text.startsWith('Offline voice memo')) {
          if (input) input.value = text;
          sendChatMessage(text, true);
        } else if (text) {
          if (input) {
            input.value = text;
            input.focus();
          }
          if (statusEl) {
            statusEl.textContent = 'Transcribed with fallback. Check text and send.';
            setTimeout(() => statusEl.classList.add('hidden'), 4000);
          }
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = 'Voice capture error: ' + err.message;
      } finally {
        if (btn) btn.classList.remove('bg-rose-500', 'text-white', 'animate-pulse');
        stream.getTracks().forEach(t => t.stop());
        setTimeout(() => { if (statusEl) statusEl.classList.add('hidden'); }, 3000);
      }
    };

    activeMediaRecorder.start(250);
    startEqualizerAnimation(stream);
    if (statusEl) {
      statusEl.textContent = 'Listening (Whisper)... Speak now, click Mic again when done.';
      statusEl.classList.remove('hidden');
    }
    if (btn) btn.classList.add('bg-rose-500', 'text-white', 'animate-pulse');
  } catch (err) {
    alert("Microphone permission denied: " + err.message);
  }
}

/* ============================================================================
   4. ARC REACTOR VOICE CORE & SPOKEN BRIEFING
   ============================================================================ */

async function toggleMicRecording() {
  if (!arcIsRecording) {
    startArcRecording();
  } else {
    stopArcRecording();
  }
}

async function startArcRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    arcMediaRecorder = new MediaRecorder(stream);
    arcAudioChunks = [];

    arcMediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) arcAudioChunks.push(e.data);
    };

    arcMediaRecorder.onstop = async () => {
      stopEqualizerAnimation();
      const audioBlob = new Blob(arcAudioChunks, { type: 'audio/webm' });
      await uploadArcAudio(audioBlob);
      stream.getTracks().forEach(t => t.stop());
    };

    arcMediaRecorder.start();
    arcIsRecording = true;
    startEqualizerAnimation(stream);

    const core = document.getElementById('reactorCore');
    if (core) core.classList.add('reactor-recording');
    const coreText = document.getElementById('reactorCoreText');
    if (coreText) coreText.textContent = "RECORDING";
    const statusText = document.getElementById('reactorStatusText');
    if (statusText) statusText.textContent = "LISTENING... TAP CORE AGAIN TO TRANSMIT";
    const wave = document.getElementById('arcWaveContainer');
    if (wave) {
      wave.classList.remove('hidden');
      wave.classList.add('flex');
    }
  } catch (err) {
    alert("Microphone permission denied or not supported by browser.");
  }
}

function stopArcRecording() {
  if (arcMediaRecorder && arcIsRecording) {
    arcMediaRecorder.stop();
    arcIsRecording = false;
    stopEqualizerAnimation();
    const core = document.getElementById('reactorCore');
    if (core) core.classList.remove('reactor-recording');
    const coreText = document.getElementById('reactorCoreText');
    if (coreText) coreText.textContent = "";
    const statusText = document.getElementById('reactorStatusText');
    if (statusText) statusText.textContent = "PROCESSING AUDIO INFERENCE...";
    const wave = document.getElementById('arcWaveContainer');
    if (wave) {
      wave.classList.remove('flex');
      wave.classList.add('hidden');
    }
  }
}

async function uploadArcAudio(blob) {
  const formData = new FormData();
  formData.append("file", blob, `voice_memo_${Date.now()}.webm`);

  try {
    const res = await fetch('/api/voice/capture', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    const statusText = document.getElementById('reactorStatusText');
    if (statusText) statusText.textContent = `CAPTURED: "${data.transcript || 'Audio received'}"`;
    await syncAllData();
  } catch (err) {
    console.error("Arc upload error:", err);
  }
}

async function triggerBriefing() {
  try {
    const res = await fetch('/api/briefing', { method: 'POST' });
    const data = await res.json();
    const text = data.briefing || data.text || data.briefing_text || "All schedules and business deliverables are in order, Anas.";
    speakText(text);
  } catch (e) {
    speakText("Offline briefing: All tasks and schedules remain synchronized locally.");
  }
}

function fillExample(text) {
  const input = document.getElementById('quickCaptureInput');
  if (input) input.value = text;
}

/* ============================================================================
   5. SERVICE WORKER, PWA INSTALL PROMPT & MOBILE INSTALLER MODAL
   ============================================================================ */

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  const statusEl = document.getElementById('oneClickInstallStatus');
  if (statusEl) {
    statusEl.textContent = 'Ready for instant 1-Click Native Installation!';
  }
});

async function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register('/sw.js');
    } catch (err) {
      try {
        await navigator.serviceWorker.register('/static/sw.js');
      } catch (e) {
        console.warn('ServiceWorker registration fallback:', e);
      }
    }
  }
}

async function openMobileInstallModal() {
  const modal = document.getElementById('mobileInstallModal');
  if (modal) modal.classList.remove('hidden');

  const qrContainer = document.getElementById('mobileQrContainer');
  const urlInput = document.getElementById('mobileInstallUrlInput');
  const apkPathEl = document.getElementById('mobileApkPathText');

  try {
    const res = await fetch('/api/mobile/install-info');
    if (res.ok) {
      const info = await res.json();
      if (urlInput && info.install_url) {
        urlInput.value = info.install_url;
      }
      if (qrContainer && info.qr_svg) {
        qrContainer.innerHTML = info.qr_svg;
      }
      if (apkPathEl && info.apk_project_path) {
        apkPathEl.textContent = info.apk_project_path;
      }
      return;
    }
  } catch (err) {
    // Fallback offline client-side SVG QR rendering
  }

  const fallbackUrl = window.location.origin || 'http://127.0.0.1:8000';
  if (urlInput) urlInput.value = fallbackUrl;
  if (qrContainer) {
    qrContainer.innerHTML = generateClientQrSvg(fallbackUrl);
  }
}

function closeMobileInstallModal() {
  const modal = document.getElementById('mobileInstallModal');
  if (modal) modal.classList.add('hidden');
}

function generateClientQrSvg(urlText) {
  const encoded = encodeURIComponent(urlText);
  return `
    <div class="flex flex-col items-center justify-center p-3 text-center">
      <svg class="w-40 h-40 text-slate-900" viewBox="0 0 100 100" fill="currentColor">
        <rect x="10" y="10" width="25" height="25" fill="#0f172a" rx="4"/>
        <rect x="65" y="10" width="25" height="25" fill="#0f172a" rx="4"/>
        <rect x="10" y="65" width="25" height="25" fill="#0f172a" rx="4"/>
        <rect x="17" y="17" width="11" height="11" fill="#ffffff" rx="2"/>
        <rect x="72" y="17" width="11" height="11" fill="#ffffff" rx="2"/>
        <rect x="17" y="72" width="11" height="11" fill="#ffffff" rx="2"/>
        <rect x="45" y="45" width="12" height="12" fill="#00f0ff" rx="2"/>
        <rect x="42" y="15" width="6" height="16" fill="#0f172a"/>
        <rect x="42" y="68" width="8" height="14" fill="#0f172a"/>
        <rect x="65" y="48" width="15" height="8" fill="#0f172a"/>
        <rect x="15" y="45" width="14" height="8" fill="#0f172a"/>
      </svg>
      <span class="text-[10px] text-slate-600 font-mono-code mt-2 break-all max-w-[200px]">${urlText}</span>
    </div>
  `;
}

async function triggerOneClickMobileInstall() {
  const statusEl = document.getElementById('oneClickInstallStatus');
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    if (statusEl) statusEl.textContent = `Installation outcome: ${outcome}`;
    deferredInstallPrompt = null;
  } else {
    if (statusEl) {
      statusEl.textContent = 'To install: Tap your browser Share/Menu icon and select "Add to Home Screen".';
    }
  }
}

function copyMobileInstallUrl() {
  const urlInput = document.getElementById('mobileInstallUrlInput');
  const statusEl = document.getElementById('copyInstallUrlStatus');
  if (urlInput) {
    navigator.clipboard.writeText(urlInput.value).then(() => {
      if (statusEl) {
        statusEl.classList.remove('hidden');
        setTimeout(() => statusEl.classList.add('hidden'), 3500);
      }
    });
  }
}

/* ============================================================================
   6. VOICE CAPTURE WITH GROQ WHISPER & ROMAN-URDU/ENGLISH FALLBACK
   ============================================================================ */

async function toggleVoiceRecording(targetSection) {
  const btn = targetSection === 'task'
    ? document.getElementById('voiceRecordBtnTask')
    : document.getElementById('voiceRecordBtnCourse');
  const statusEl = targetSection === 'task'
    ? document.getElementById('voiceRecordStatusTask')
    : document.getElementById('voiceRecordStatusCourse');

  if (activeMediaRecorder && activeMediaRecorder.state === 'recording') {
    activeMediaRecorder.stop();
    return;
  }

  activeVoiceTarget = targetSection;
  recordedAudioChunks = [];

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    activeMediaRecorder = new MediaRecorder(stream);

    activeMediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        recordedAudioChunks.push(e.data);
      }
    };

    activeMediaRecorder.onstop = async () => {
      stopEqualizerAnimation();
      if (statusEl) statusEl.textContent = 'Transcribing voice via Groq Whisper...';
      try {
        const audioBlob = new Blob(recordedAudioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('file', audioBlob, `voice_${Date.now()}.webm`);
        formData.append('target', targetSection);

        const res = await fetch('/api/voice/capture', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        applyCapturedVoiceResult(data, targetSection);
      } catch (err) {
        console.error('Audio upload error, trying browser speech recognition fallback:', err);
        fallbackSpeechRecognition(targetSection);
      } finally {
        if (statusEl) statusEl.classList.add('hidden');
        if (btn) btn.classList.remove('bg-rose-500', 'text-white', 'animate-pulse');
        stream.getTracks().forEach((track) => track.stop());
      }
    };

    activeMediaRecorder.start();
    startEqualizerAnimation(stream);
    if (statusEl) {
      statusEl.textContent = 'Listening to voice... Click record button again to finish.';
      statusEl.classList.remove('hidden');
    }
    if (btn) {
      btn.classList.add('bg-rose-500', 'text-white', 'animate-pulse');
    }
  } catch (err) {
    fallbackSpeechRecognition(targetSection);
  }
}

function fallbackSpeechRecognition(targetSection) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert('Voice input not supported on this browser. Please type directly.');
    return;
  }

  const rec = new SpeechRec();
  rec.lang = 'ur-PK';
  rec.continuous = false;
  rec.interimResults = false;

  const statusEl = targetSection === 'task'
    ? document.getElementById('voiceRecordStatusTask')
    : document.getElementById('voiceRecordStatusCourse');

  if (statusEl) {
    statusEl.textContent = 'Listening via browser speech recognition...';
    statusEl.classList.remove('hidden');
  }

  rec.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    applyCapturedVoiceResult({ transcript }, targetSection);
    if (statusEl) statusEl.classList.add('hidden');
  };

  rec.onerror = (e) => {
    if (statusEl) {
      statusEl.textContent = 'Voice error: ' + (e.error || 'Check microphone');
      setTimeout(() => statusEl.classList.add('hidden'), 4000);
    }
  };

  rec.start();
}

function applyCapturedVoiceResult(data, targetSection) {
  const transcript = data.transcript || '';
  if (targetSection === 'task') {
    const input = document.getElementById('quickCaptureInput');
    if (input) input.value = transcript;
    if (data.created_ids && data.created_ids.length > 0) {
      syncAllData();
    }
  } else if (targetSection === 'course') {
    const input = document.getElementById('nightlyReflectionInput');
    if (input) {
      input.value = input.value ? input.value + ' ' + transcript : transcript;
    }
  }
}

/* ============================================================================
   7. OFFLINE INDEXEDDB & SYNCHRONIZATION ENGINE
   ============================================================================ */

function openOfflineDB() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      resolve(null);
      return;
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

async function saveSnapshotToOfflineStorage(data) {
  try {
    localStorage.setItem(LS_CACHE_KEY, JSON.stringify(data));
  } catch (e) {}

  const db = await openOfflineDB();
  if (!db) return;
  try {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).put({ id: 'latest_snapshot', data, timestamp: Date.now() });
  } catch (e) {}
}

async function loadSnapshotFromOfflineStorage() {
  const db = await openOfflineDB();
  if (db) {
    try {
      const p = new Promise((resolve) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const req = tx.objectStore(IDB_STORE).get('latest_snapshot');
        req.onsuccess = () => resolve(req.result ? req.result.data : null);
        req.onerror = () => resolve(null);
      });
      const data = await p;
      if (data) return data;
    } catch (e) {}
  }

  try {
    const ls = localStorage.getItem(LS_CACHE_KEY);
    if (ls) return JSON.parse(ls);
  } catch (e) {}
  return null;
}

function updateConnectionStatusUI(isOnline) {
  jarvisState.online = isOnline;
  const badge = document.getElementById('connectionStatusBadge');
  const dot = document.getElementById('connectionStatusDot');
  const text = document.getElementById('connectionStatusText');

  if (isOnline) {
    if (badge) badge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border border-emerald-500/40 bg-emerald-500/10 text-emerald-400';
    if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse';
    if (text) text.textContent = 'Online — Synced with Native PostgreSQL';
  } else {
    if (badge) badge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border border-amber-500/40 bg-amber-500/10 text-amber-400';
    if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-400';
    if (text) text.textContent = 'Offline Mode — Running from Local Device Cache';
  }
}

async function syncAllData() {
  try {
    const res = await fetch('/api/sync');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    applySyncPayload(data);
    await saveSnapshotToOfflineStorage(data);
    updateConnectionStatusUI(true);
    await updateTelemetryUI();
  } catch (err) {
    updateConnectionStatusUI(false);
    const cached = await loadSnapshotFromOfflineStorage();
    if (cached) {
      applySyncPayload(cached);
    }
  }
}

function applySyncPayload(payload) {
  jarvisState.reminders = payload.reminders || [];
  jarvisState.weekly_routine = payload.weekly_routine || [];
  jarvisState.routine_completions = payload.routine_completions || [];
  jarvisState.alarms = payload.alarms || [];
  jarvisState.courses = payload.courses || [];
  jarvisState.course_logs = payload.course_logs || [];
  jarvisState.business_deliverables = payload.business_deliverables || [];
  jarvisState.small_tasks = payload.small_tasks || [];
  jarvisState.lastSyncedAt = payload.synced_at || new Date().toISOString();

  renderAllSections();
}

function renderAllSections() {
  renderRemindersSection();
  renderWeeklyRoutineSection();
  renderDeadlinesCalendar();
  renderAlarmsSection();
  renderNightlyAuditSection();
  renderBusinessSection();
  renderProposedAuditInputList();
}

/* ============================================================================
   8. 5-SECOND LOCAL OFFLINE WATCHDOG & DUE NOTIFICATIONS
   ============================================================================ */

function runLocalOfflineWatchdog() {
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  const currentTimeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  // 1. Reminders Due Watchdog
  const confirmedReminders = jarvisState.reminders.filter((r) => r.status === 'confirmed' || r.status === 'scheduled');
  for (const reminder of confirmedReminders) {
    if (!reminder.due_datetime) continue;
    const dueDate = new Date(reminder.due_datetime);
    const isDue = Math.abs(now - dueDate) < 60000;
    if (isDue && !jarvisState.notifiedReminderIds.has(reminder.id)) {
      jarvisState.notifiedReminderIds.add(reminder.id);
      showDueReminderBanner(reminder);
      speakText(`Reminder: ${reminder.title}`);
    }
  }

  // 2. Proof-of-Wake Alarms Watchdog
  const activeAlarms = jarvisState.alarms.filter((a) => a.is_active);
  for (const alarm of activeAlarms) {
    if (alarm.alarm_time === currentTimeStr && !jarvisState.activeRingingAlarm) {
      startWakeUpLoop(alarm);
      break;
    }
  }
}

function showDueReminderBanner(reminder) {
  const banner = document.getElementById('dueAlertBanner');
  const text = document.getElementById('dueAlertText');
  if (banner && text) {
    text.textContent = `Due Reminder: "${reminder.title}" (Due: ${new Date(reminder.due_datetime).toLocaleTimeString()})`;
    banner.classList.remove('hidden');
  }
}

function dismissDueAlertBanner() {
  const banner = document.getElementById('dueAlertBanner');
  if (banner) banner.classList.add('hidden');
}

// =============================================================================
// SPEECH SYNTHESIS (SPEAKING POWER) & LIVE LISTENING ENGINE
// =============================================================================

let autoVoiceReply = localStorage.getItem('jarvis_auto_voice') !== 'false';
let isSpeaking = false;
let currentSpeechAudio = null;
let activeSpeechRecognizer = null;
let speechWatchdogInterval = null;

function toggleAutoVoiceReply() {
  autoVoiceReply = !autoVoiceReply;
  localStorage.setItem('jarvis_auto_voice', autoVoiceReply ? 'true' : 'false');
  updateAutoVoiceBtn();
}

function updateAutoVoiceBtn() {
  const btn = document.getElementById('voiceAutoReplyBtn');
  if (!btn) return;
  if (autoVoiceReply) {
    btn.textContent = 'Voice: ON';
    btn.className = 'px-2.5 h-10 text-[11px] font-bold shrink-0 rounded-xl hud-inset text-emerald-400 border border-emerald-400/40 transition flex items-center justify-center';
  } else {
    btn.textContent = 'Voice: MUTE';
    btn.className = 'px-2.5 h-10 text-[11px] font-bold shrink-0 rounded-xl hud-raised text-[var(--text-muted)] transition flex items-center justify-center';
  }
}

function cleanSpeechText(t) {
  if (!t) return '';
  return t
    .replace(/###+/g, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, '')
    .replace(/[-*•]\s+/g, '. ')
    .replace(/\s+/g, ' ')
    .trim();
}

function updateSpeakingIndicator(speaking) {
  isSpeaking = speaking;
  const banner = document.getElementById('voiceSpeakingBanner');
  if (banner) {
    if (speaking) banner.classList.remove('hidden');
    else banner.classList.add('hidden');
  }
}

function stopSpeaking() {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try { window.speechSynthesis.cancel(); } catch (e) {}
  }
  if (speechWatchdogInterval) {
    clearInterval(speechWatchdogInterval);
    speechWatchdogInterval = null;
  }
  if (currentSpeechAudio) {
    try {
      currentSpeechAudio.pause();
      currentSpeechAudio.currentTime = 0;
    } catch (e) {}
    currentSpeechAudio = null;
  }
  updateSpeakingIndicator(false);
}

function speakText(rawText) {
  if (!rawText) return;
  const clean = cleanSpeechText(rawText);
  if (!clean) return;

  stopSpeaking();

  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    // Delay slightly to bypass Chromium cancel() race condition
    setTimeout(() => {
      try {
        const utterance = new SpeechSynthesisUtterance(clean);
        utterance.rate = 1.05;
        utterance.pitch = 1.0;

        const voices = window.speechSynthesis.getVoices() || [];
        const preferred = voices.find(v =>
          v.name.includes('Natural') ||
          v.name.includes('Google UK English Male') ||
          v.name.includes('Microsoft David') ||
          v.name.includes('Microsoft Mark') ||
          v.lang.startsWith('en')
        );
        if (preferred) utterance.voice = preferred;

        utterance.onstart = () => {
          updateSpeakingIndicator(true);
        };
        utterance.onend = () => {
          updateSpeakingIndicator(false);
          if (speechWatchdogInterval) {
            clearInterval(speechWatchdogInterval);
            speechWatchdogInterval = null;
          }
        };
        utterance.onerror = (err) => {
          console.warn("SpeechSynthesis error, trying backend TTS fallback", err);
          updateSpeakingIndicator(false);
          speakViaBackendTTS(clean);
        };

        window.speechSynthesis.speak(utterance);

        // Chromium watchdog to prevent 15-second speech silence bug
        if (speechWatchdogInterval) clearInterval(speechWatchdogInterval);
        speechWatchdogInterval = setInterval(() => {
          if (window.speechSynthesis.speaking) {
            window.speechSynthesis.pause();
            window.speechSynthesis.resume();
          } else {
            clearInterval(speechWatchdogInterval);
            speechWatchdogInterval = null;
          }
        }, 10000);

      } catch (err) {
        speakViaBackendTTS(clean);
      }
    }, 60);
  } else {
    speakViaBackendTTS(clean);
  }
}

async function speakViaBackendTTS(cleanText) {
  try {
    updateSpeakingIndicator(true);
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: cleanText })
    });
    if (!res.ok) throw new Error("TTS endpoint returned " + res.status);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    currentSpeechAudio = new Audio(url);
    currentSpeechAudio.onended = () => {
      updateSpeakingIndicator(false);
      URL.revokeObjectURL(url);
      currentSpeechAudio = null;
    };
    currentSpeechAudio.onerror = () => {
      updateSpeakingIndicator(false);
      currentSpeechAudio = null;
    };
    await currentSpeechAudio.play();
  } catch (err) {
    updateSpeakingIndicator(false);
    console.warn("Backend TTS playback failed:", err);
  }
}

/* ============================================================================
   9. TAB 3: STRICT PROOF-OF-WAKE ALARM ("Anas, wake up!" 15s VOICE LOOP)
   ============================================================================ */

function startWakeUpLoop(alarm) {
  jarvisState.activeRingingAlarm = alarm;

  const modal = document.getElementById('wakeModal');
  const modalTime = document.getElementById('wakeModalTime');
  const modalTask = document.getElementById('wakeModalTaskPrompt');

  if (modalTime) modalTime.textContent = alarm.alarm_time || '06:00';
  if (modalTask) modalTask.textContent = alarm.first_task_prompt || 'Start Scheduled Routine Block';
  if (modal) modal.classList.remove('hidden');

  const voicePhrase = `Anas, wake up! Your first scheduled task is: ${alarm.first_task_prompt || 'ready'}.`;
  speakText(voicePhrase);

  if (jarvisState.wakeLoopIntervalId) clearInterval(jarvisState.wakeLoopIntervalId);
  jarvisState.wakeLoopIntervalId = setInterval(() => {
    if (jarvisState.activeRingingAlarm) {
      speakText(voicePhrase);
    } else {
      clearInterval(jarvisState.wakeLoopIntervalId);
      jarvisState.wakeLoopIntervalId = null;
    }
  }, 15000);
}

function stopWakeUpLoop() {
  if (jarvisState.wakeLoopIntervalId) {
    clearInterval(jarvisState.wakeLoopIntervalId);
    jarvisState.wakeLoopIntervalId = null;
  }
  jarvisState.activeRingingAlarm = null;
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  const modal = document.getElementById('wakeModal');
  if (modal) modal.classList.add('hidden');
}

async function submitWakeVerification() {
  const input = document.getElementById('wakeVerificationInput');
  const check = document.getElementById('wakeFirstTaskCheck');
  const statusEl = document.getElementById('wakeVerifyStatus');
  const phrase = (input ? input.value : '').trim();
  const confirmed = check ? check.checked : false;

  if (!jarvisState.activeRingingAlarm) {
    stopWakeUpLoop();
    return;
  }

  const alarmId = jarvisState.activeRingingAlarm.id;
  try {
    const res = await fetch(`/api/alarms/${alarmId}/verify-wake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        verification_phrase: phrase,
        first_task_confirmed: confirmed
      })
    });
    const data = await res.json();
    if (data.success) {
      stopWakeUpLoop();
      speakText('Wake verification confirmed. Have a productive day, Anas.');
      if (input) input.value = '';
      if (check) check.checked = false;
      await syncAllData();
    } else {
      if (statusEl) {
        statusEl.textContent = data.message || 'Verification failed. Repeat required phrase.';
      }
    }
  } catch (err) {
    if (confirmed || phrase.length > 3) {
      stopWakeUpLoop();
      speakText('Offline wake verification accepted. Welcome, Anas.');
    } else {
      if (statusEl) statusEl.textContent = 'Type a verification phrase or check the confirmation box.';
    }
  }
}

function triggerTestWakeAlarm() {
  const testAlarm = jarvisState.alarms[0] || {
    id: 9999,
    alarm_time: 'Now',
    label: 'Test Wake-Up Alarm',
    first_task_prompt: 'Review Routine & Start Priority Block'
  };
  startWakeUpLoop(testAlarm);
}

function renderAlarmsSection() {
  const container = document.getElementById('alarmsListContainer');
  if (!container) return;

  const alarms = jarvisState.alarms || [];
  if (alarms.length === 0) {
    container.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-6 text-center font-mono-code">No strict alarms configured. Set one above.</div>`;
    return;
  }

  container.innerHTML = alarms
    .map(
      (a) => `
    <div class="p-3.5 rounded-2xl hud-inset flex items-center justify-between gap-3 border border-[var(--hud-border-dim)]">
      <div class="space-y-0.5">
        <div class="flex items-center gap-2">
          <span class="text-base font-bold font-hud-clock text-[var(--hud-accent)]">${escapeHtml(a.alarm_time)}</span>
          <span class="text-xs font-semibold text-[var(--text-main)]">${escapeHtml(a.label || 'Alarm')}</span>
          <span class="text-[10px] px-2 py-0.5 rounded-full ${a.is_active ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-slate-800 text-slate-500'} font-mono-code">
            ${a.is_active ? 'ACTIVE' : 'MUTED'}
          </span>
        </div>
        <div class="text-xs text-[var(--text-muted)] font-mono-code">Spoken Task: "${escapeHtml(a.first_task_prompt || 'Wake up and begin task')}"</div>
      </div>
      <div class="flex items-center gap-2">
        <button onclick="startWakeUpLoop(jarvisState.alarms.find(x => x.id === ${a.id}))" class="px-3 py-1.5 rounded-xl hud-inset hover:border-[var(--hud-accent)] text-xs text-[var(--hud-accent)] font-hud-clock font-bold transition">
          Test Loop
        </button>
        <button onclick="toggleAlarmStatus(${a.id}, ${!a.is_active})" class="px-3 py-1.5 rounded-xl hud-inset hover:border-[var(--hud-accent)] text-xs text-[var(--text-sub)] transition">
          ${a.is_active ? 'Disable' : 'Enable'}
        </button>
        <button onclick="deleteAlarmEntry(${a.id})" class="px-2.5 py-1.5 rounded-xl hud-inset hover:border-rose-400 text-xs text-rose-300 transition" title="Delete Alarm">
          
        </button>
      </div>
    </div>
  `
    )
    .join('');
}

async function createAlarmEntry() {
  const time = document.getElementById('alarmTimeInput')?.value || '06:00';
  const label = document.getElementById('alarmLabelInput')?.value.trim() || 'Anas Strict Wake-Up';
  const first_task_prompt = document.getElementById('alarmFirstTaskInput')?.value.trim() || 'Review Today\'s Schedule';

  await fetch('/api/alarms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alarm_time: time, label, first_task_prompt })
  });

  document.getElementById('alarmLabelInput').value = '';
  document.getElementById('alarmFirstTaskInput').value = '';
  await syncAllData();
}

async function deleteAlarmEntry(id) {
  await fetch(`/api/alarms/${id}`, { method: 'DELETE' });
  await syncAllData();
}

async function toggleAlarmStatus(id, newStatus) {
  await fetch('/api/alarms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, is_active: newStatus })
  });
  await syncAllData();
}

/* ============================================================================
   10. TAB 2: REMINDERS & PENDING CONFIRMATION GATE
   ============================================================================ */

function renderRemindersSection() {
  const pendingEl = document.getElementById('pendingRemindersList');
  const confirmedEl = document.getElementById('confirmedRemindersList');
  const pendingBadge = document.getElementById('pendingCountBadge');
  const confirmedBadge = document.getElementById('confirmedCountBadge');

  const pending = jarvisState.reminders.filter((r) => r.status === 'pending_review');
  const confirmed = jarvisState.reminders.filter((r) => r.status === 'confirmed' || r.status === 'scheduled');

  if (pendingBadge) pendingBadge.textContent = `${pending.length} Pending`;
  if (confirmedBadge) confirmedBadge.textContent = `${confirmed.length} Confirmed`;

  if (pendingEl) {
    if (pending.length === 0) {
      pendingEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-8 text-center font-mono-code">No tasks staged for confirmation. Speak or type above to add.</div>`;
    } else {
      pendingEl.innerHTML = pending
        .map(
          (t) => `
        <div class="p-3.5 rounded-2xl hud-inset border border-amber-500/30 space-y-2.5">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="text-xs font-bold text-[var(--text-main)] font-hud-clock">${escapeHtml(t.title)}</div>
              <div class="text-[11px] text-[var(--text-muted)] font-mono-code mt-0.5">Time: ${escapeHtml(t.raw_due_text || 'Unspecified')}</div>
            </div>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 uppercase font-mono-code">
              ${escapeHtml(t.priority || 'Normal')}
            </span>
          </div>
          ${t.original_transcript ? `<div class="text-[11px] text-[var(--text-muted)] italic font-mono-code">"${escapeHtml(t.original_transcript)}"</div>` : ''}
          <div class="flex items-center gap-2 pt-1 border-t border-[var(--hud-border-dim)]">
            <button onclick="confirmPendingTask(${t.id})" class="px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition font-hud-clock">
              Confirm & Schedule
            </button>
            <button onclick="rejectPendingTask(${t.id})" class="px-3 py-1.5 rounded-xl hud-inset hover:border-rose-400 text-xs text-rose-300 transition">
              Reject
            </button>
          </div>
        </div>
      `
        )
        .join('');
    }
  }

  if (confirmedEl) {
    if (confirmed.length === 0) {
      confirmedEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-8 text-center font-mono-code">No confirmed schedule items for today.</div>`;
    } else {
      confirmedEl.innerHTML = confirmed
        .map(
          (t) => `
        <div class="p-3.5 rounded-2xl hud-inset border border-[var(--hud-border-dim)] flex items-center justify-between gap-3">
          <div class="space-y-0.5">
            <div class="text-xs font-bold text-[var(--text-main)] font-hud-clock">${escapeHtml(t.title)}</div>
            <div class="text-[11px] text-[var(--text-muted)] font-mono-code">
              Due: ${t.due_datetime ? new Date(t.due_datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Today'}
              &bull; Priority: <span class="uppercase text-[var(--hud-accent)]">${escapeHtml(t.priority || 'Normal')}</span>
            </div>
          </div>
          <button onclick="deleteConfirmedTask(${t.id})" class="px-2.5 py-1.5 rounded-xl hud-inset hover:border-rose-400 text-xs text-rose-300 transition" title="Delete Task">
            x
          </button>
        </div>
      `
        )
        .join('');
    }
  }
}

async function submitQuickCapture() {
  const input = document.getElementById('quickCaptureInput');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  await fetch('/reminders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: text,
      raw_due_text: text,
      priority: 'normal'
    })
  });

  input.value = '';
  await syncAllData();
}

async function captureVoiceTextToAuditAndStage() {
  const input = document.getElementById('quickCaptureInput');
  const text = input ? input.value.trim() : '';
  if (!text) return;

  await fetch('/api/tasks/quick-add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });

  input.value = '';
  await syncAllData();
}

async function confirmPendingTask(id) {
  await fetch(`/api/tasks/${id}/confirm`, { method: 'POST' });
  await syncAllData();
}

async function rejectPendingTask(id) {
  await fetch(`/api/tasks/${id}/reject`, { method: 'POST' });
  await syncAllData();
}

async function deleteConfirmedTask(id) {
  await fetch(`/reminders/${id}/delete`, { method: 'POST' });
  await syncAllData();
}

/* ============================================================================
   11. TAB 2: ADVISORY HARD ROUTINE AUDIT (routine_audit.py)
   ============================================================================ */

function renderProposedAuditInputList() {
  const listEl = document.getElementById('proposedAuditTasksList');
  if (!listEl) return;

  listEl.innerHTML = jarvisState.proposedAuditTasks
    .map(
      (task, idx) => `
    <div class="p-2.5 rounded-xl hud-inset flex items-center justify-between gap-3 text-xs border border-[var(--hud-border-dim)]">
      <div class="flex items-center gap-2">
        <span class="w-5 h-5 rounded-full bg-[var(--hud-accent)]/20 text-[var(--hud-accent)] flex items-center justify-center font-bold text-[10px] font-mono-code">${idx + 1}</span>
        <span class="font-semibold text-[var(--text-main)]">${escapeHtml(task.title)}</span>
        <span class="text-[var(--text-muted)] font-mono-code">(${task.estimated_minutes}m &bull; ${escapeHtml(task.preferred_time || 'flexible')})</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-[var(--text-muted)] font-mono-code uppercase">${escapeHtml(task.priority)}</span>
        <button onclick="removeProposedAuditTask(${idx})" class="text-rose-400 hover:text-rose-300 font-bold px-1.5">x</button>
      </div>
    </div>
  `
    )
    .join('');
}

function addProposedAuditTask() {
  const title = document.getElementById('auditTaskTitle')?.value.trim();
  const dueDate = document.getElementById('auditTaskDueDate')?.value || '';
  const minutes = parseInt(document.getElementById('auditTaskMinutes')?.value || '60', 10);
  const preferred_time = document.getElementById('auditTaskPrefTime')?.value.trim();
  const priority = document.getElementById('auditTaskPriority')?.value || 'normal';

  if (!title) return;

  jarvisState.proposedAuditTasks.push({
    title,
    due_date: dueDate || toLocalDateStr(new Date()),
    estimated_minutes: isNaN(minutes) ? 60 : minutes,
    preferred_time: preferred_time || undefined,
    priority
  });

  document.getElementById('auditTaskTitle').value = '';
  renderProposedAuditInputList();
  renderWeeklyRoutineSection();
  renderDeadlinesCalendar();
}

function removeProposedAuditTask(idx) {
  jarvisState.proposedAuditTasks.splice(idx, 1);
  renderProposedAuditInputList();
  renderWeeklyRoutineSection();
  renderDeadlinesCalendar();
}

async function runHardRoutineAudit() {
  const panel = document.getElementById('auditResultPanel');
  if (panel) panel.classList.remove('hidden');

  try {
    const res = await fetch('/api/routine/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        day_of_week: 'Tuesday',
        proposed_tasks: jarvisState.proposedAuditTasks
      })
    });
    const report = await res.json();
    jarvisState.lastAuditResult = report;
    renderAuditReportUI(report);
  } catch (err) {
    console.error('Audit run error:', err);
  }
}

function renderAuditReportUI(report) {
  const summaryEl = document.getElementById('auditMetricsSummary');
  const warningsEl = document.getElementById('auditWarningsList');
  const coreEl = document.getElementById('auditCoreScheduleList');
  const overflowEl = document.getElementById('auditOverflowList');

  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="p-3.5 rounded-2xl hud-inset space-y-1">
        <span class="text-[10px] text-[var(--text-muted)] font-mono-code uppercase">TRUE FREE WAKING HOURS</span>
        <div class="text-base font-bold font-hud-clock text-emerald-400">${(report.true_free_minutes / 60).toFixed(1)} hrs (${report.true_free_minutes}m)</div>
      </div>
      <div class="p-3.5 rounded-2xl hud-inset space-y-1">
        <span class="text-[10px] text-[var(--text-muted)] font-mono-code uppercase">PROPOSED EFFORT (+15% BUFFER)</span>
        <div class="text-base font-bold font-hud-clock text-[var(--hud-accent)]">${(report.total_requested_minutes_with_buffer / 60).toFixed(1)} hrs</div>
      </div>
      <div class="p-3.5 rounded-2xl hud-inset space-y-1">
        <span class="text-[10px] text-[var(--text-muted)] font-mono-code uppercase">SURPLUS / DEFICIT</span>
        <div class="text-base font-bold font-hud-clock ${report.is_over_capacity ? 'text-rose-400' : 'text-emerald-400'}">
          ${report.is_over_capacity ? `DEFICIT -${(report.capacity_gap_minutes / 60).toFixed(1)}h` : `SURPLUS +${((report.true_free_minutes - report.total_requested_minutes_with_buffer) / 60).toFixed(1)}h`}
        </div>
      </div>
    `;
  }

  if (warningsEl) {
    if (report.warnings && report.warnings.length > 0) {
      warningsEl.innerHTML = report.warnings
        .map(
          (w) => `
        <div class="p-2.5 rounded-xl bg-amber-500/15 border border-amber-400/40 text-amber-200 text-xs font-mono-code">
           ${escapeHtml(w)}
        </div>
      `
        )
        .join('');
    } else {
      warningsEl.innerHTML = `
        <div class="p-2.5 rounded-xl bg-emerald-500/15 border border-emerald-400/40 text-emerald-200 text-xs font-mono-code">
           All proposed tasks fit safely within your True Free Hours.
        </div>
      `;
    }
  }

  if (coreEl) {
    coreEl.innerHTML = (report.core_schedule || [])
      .map(
        (c) => `
      <div class="p-2.5 rounded-xl hud-inset text-xs space-y-1 border border-[var(--hud-border-dim)]">
        <div class="font-bold text-[var(--text-main)] font-hud-clock">${escapeHtml(c.task.title)}</div>
        <div class="text-[11px] text-[var(--text-muted)] font-mono-code">${c.scheduled_start} – ${c.scheduled_end} (${c.task.estimated_minutes}m + ${c.allocated_buffer_minutes}m buffer)</div>
      </div>
    `
      )
      .join('');
  }

  if (overflowEl) {
    if ((report.overflow_tasks || []).length === 0) {
      overflowEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] font-mono-code py-4">No overflow tasks.</div>`;
    } else {
      overflowEl.innerHTML = (report.overflow_tasks || [])
        .map(
          (o) => `
        <div class="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs space-y-1">
          <div class="font-bold text-amber-200 font-hud-clock">${escapeHtml(o.title)} (${o.estimated_minutes}m)</div>
          <div class="text-[11px] text-amber-300 font-mono-code">Deferred to overflow pool to protect sleep & routine</div>
        </div>
      `
        )
        .join('');
    }
  }
}

async function commitRoutinePlan(mode) {
  const userConfirmed = document.getElementById('commitUserConfirmedCheck')?.checked ?? true;
  if (!jarvisState.lastAuditResult) return;

  const res = await fetch('/api/routine/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plan_mode: mode,
      user_confirmed: userConfirmed,
      audit_report: jarvisState.lastAuditResult
    })
  });

  const data = await res.json();
  const statusEl = document.getElementById('commitRoutineStatus');
  if (statusEl) {
    statusEl.textContent = data.message || `Committed (${mode}) with ${data.committed_count || 0} tasks.`;
    statusEl.classList.remove('hidden');
  }
  await syncAllData();
}

/* ============================================================================
   12. TAB 2: FIXED WEEKLY ROUTINE & TRUE FREE CAPACITY BAR
   ============================================================================ */

const WEEKDAYS_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
let calendarViewYear = new Date().getFullYear();
let calendarViewMonth = new Date().getMonth();
let calendarSelectedDate = null;

function toLocalDateStr(d) {
  const dt = d instanceof Date ? d : new Date(d);
  if (isNaN(dt.getTime())) return '';
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, '0');
  const day = String(dt.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getWeekDatesMap() {
  const now = new Date();
  const jsDay = now.getDay(); // 0=Sun..6=Sat
  const diffToMonday = jsDay === 0 ? -6 : 1 - jsDay;
  const monday = new Date(now);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(now.getDate() + diffToMonday);

  const map = {};
  WEEKDAYS_ORDER.forEach((name, idx) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + idx);
    map[name] = {
      dateStr: toLocalDateStr(d),
      displayDate: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      isToday: toLocalDateStr(d) === toLocalDateStr(now)
    };
  });
  return map;
}

function collectAllDeadlines() {
  const todayStr = toLocalDateStr(new Date());
  const items = [];

  (jarvisState.reminders || []).forEach((r) => {
    if (r.status === 'rejected' || r.status === 'completed') return;
    if (!r.due_datetime) return;
    const dateStr = toLocalDateStr(new Date(r.due_datetime));
    if (!dateStr) return;
    items.push({
      id: r.id,
      source: 'reminder',
      title: r.title,
      dateStr,
      timeStr: new Date(r.due_datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      priority: r.priority || 'normal',
      status: r.status || 'pending_review'
    });
  });

  (jarvisState.proposedAuditTasks || []).forEach((t, idx) => {
    items.push({
      id: `audit_${idx}`,
      auditIdx: idx,
      source: 'staged',
      title: t.title,
      dateStr: t.due_date || todayStr,
      timeStr: t.preferred_time ? `${t.preferred_time} (${t.estimated_minutes || 60}m)` : `${t.estimated_minutes || 60}m`,
      priority: t.priority || 'normal',
      status: 'staged'
    });
  });

  return items;
}

function quickStageForDay(dateStr) {
  const dueInput = document.getElementById('auditTaskDueDate');
  const titleInput = document.getElementById('auditTaskTitle');
  if (dueInput) dueInput.value = dateStr;
  if (titleInput) {
    titleInput.focus();
    titleInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function renderWeeklyRoutineSection() {
  const matrixEl = document.getElementById('sevenDayRoutineMatrix');
  const listEl = document.getElementById('weeklyRoutineList');
  const freeHoursEl = document.getElementById('weeklyTrueFreeSummary');

  const blocks = jarvisState.weekly_routine || [];
  let lockedMins = 0;
  blocks.forEach((b) => {
    const [sh, sm] = String(b.start_time || '00:00').split(':').map(Number);
    const [eh, em] = String(b.end_time || '00:00').split(':').map(Number);
    if (!isNaN(sh) && !isNaN(eh)) {
      const diff = eh * 60 + (em || 0) - (sh * 60 + (sm || 0));
      lockedMins += diff > 0 ? diff : 0;
    }
  });

  if (freeHoursEl) {
    const wakingMins = 16 * 60;
    const freeMins = Math.max(0, wakingMins - lockedMins);
    freeHoursEl.textContent = `${(freeMins / 60).toFixed(1)}h free`;
  }
  updateTrueFreeHoursBar(lockedMins);

  if (matrixEl) {
    const weekMap = getWeekDatesMap();
    const allExtraWork = collectAllDeadlines();

    matrixEl.innerHTML = WEEKDAYS_ORDER.map((dayName) => {
      const info = weekMap[dayName];
      const dayBlocks = blocks
        .filter((b) => {
          const d = (b.day_of_week || 'Daily').toLowerCase();
          return d === dayName.toLowerCase() || d === 'daily' || d === 'all';
        })
        .sort((a, b) => String(a.start_time || '').localeCompare(String(b.start_time || '')));

      let dayMins = 0;
      dayBlocks.forEach((b) => {
        const [sh, sm] = String(b.start_time || '00:00').split(':').map(Number);
        const [eh, em] = String(b.end_time || '00:00').split(':').map(Number);
        if (!isNaN(sh) && !isNaN(eh)) {
          const diff = eh * 60 + (em || 0) - (sh * 60 + (sm || 0));
          dayMins += diff > 0 ? diff : 0;
        }
      });

      // Parallel Extra Work: items due ON this day OR accumulated/carryover due TILL this day
      const extraTillDay = allExtraWork.filter((item) => item.dateStr && item.dateStr <= info.dateStr);

      const routineHtml = dayBlocks.length === 0
        ? `<div class="text-xs text-[var(--text-muted)] py-4 text-center font-mono">No fixed routine blocks for ${dayName}.</div>`
        : dayBlocks.map((b) => {
            const isCompleted = (jarvisState.routine_completions || []).some(
              c => Number(c.routine_id) === Number(b.id) && c.date_str === info.dateStr && c.status === 'completed'
            );
            return `
              <div class="p-2.5 rounded-xl hud-inset border ${isCompleted ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-[var(--hud-border-dim)]'} flex items-center justify-between gap-2 transition-all">
                <div class="flex items-center gap-2.5 min-w-0">
                  <input type="checkbox"
                         onchange="toggleRoutineCompletion(${b.id}, '${info.dateStr}', this.checked)"
                         ${isCompleted ? 'checked' : ''}
                         class="w-4 h-4 rounded text-emerald-500 cursor-pointer accent-emerald-500 shrink-0"
                         title="Mark/Unmark completed">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span class="text-[10px] font-mono px-2 py-0.5 rounded ${isCompleted ? 'bg-emerald-500/15 text-emerald-400' : 'bg-blue-500/15 text-blue-600 dark:text-cyan-400'} font-bold">${escapeHtml(b.start_time)} – ${escapeHtml(b.end_time)}</span>
                      <span class="text-xs font-bold ${isCompleted ? 'line-through text-emerald-400/80' : 'text-[var(--text-main)]'} truncate">${escapeHtml(b.title)}</span>
                      ${isCompleted ? '<span class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">Done</span>' : ''}
                    </div>
                    <div class="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">${escapeHtml(b.category || 'Fixed')} ${String(b.day_of_week || '').toLowerCase() === 'daily' ? '&bull; Daily' : ''}</div>
                  </div>
                </div>
                <button onclick="deleteWeeklyRoutineBlock(${b.id})" class="px-2 py-1 rounded-lg hud-raised hover:text-rose-500 text-xs text-[var(--text-muted)] transition shrink-0" title="Delete Block">x</button>
              </div>
            `;
          }).join('');

      const extraHtml = extraTillDay.length === 0
        ? `<div class="text-xs text-[var(--text-muted)] py-4 text-center font-mono">No extra work due till ${dayName}.</div>`
        : extraTillDay.map((item) => {
          const isExactDay = item.dateStr === info.dateStr;
          const badgeClass = isExactDay
            ? 'bg-amber-500/15 text-amber-500'
            : 'bg-rose-500/15 text-rose-400';
          const badgeText = isExactDay ? `Due ${dayName.slice(0, 3)}` : `Carryover (${item.dateStr})`;
          const actionBtn = item.source === 'reminder'
            ? (item.status === 'pending_review'
                ? `<button onclick="confirmPendingTask(${item.id})" class="px-2 py-1 rounded-lg bg-emerald-500/20 text-emerald-400 text-[10px] font-bold hover:bg-emerald-500/30 transition shrink-0">Confirm</button>`
                : `<button onclick="deleteConfirmedTask(${item.id})" class="px-2 py-1 rounded-lg hud-raised hover:text-rose-500 text-xs text-[var(--text-muted)] transition shrink-0" title="Remove">x</button>`)
            : `<button onclick="removeProposedAuditTask(${item.auditIdx})" class="px-2 py-1 rounded-lg hud-raised hover:text-rose-500 text-xs text-[var(--text-muted)] transition shrink-0" title="Remove">x</button>`;

          return `
            <div class="p-2.5 rounded-xl hud-inset border border-[var(--hud-border-dim)] flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="text-[10px] font-mono px-1.5 py-0.5 rounded ${badgeClass} font-bold">${badgeText}</span>
                  <span class="text-xs font-bold text-[var(--text-main)] truncate">${escapeHtml(item.title)}</span>
                </div>
                <div class="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">${escapeHtml(item.timeStr)} &bull; ${escapeHtml(item.priority)} &bull; ${escapeHtml(item.status)}</div>
              </div>
              ${actionBtn}
            </div>
          `;
        }).join('');

      return `
        <div class="p-3 sm:p-4 rounded-2xl hud-inset border ${info.isToday ? 'border-blue-500/50 ring-1 ring-blue-500/30' : 'border-[var(--hud-border-dim)]'}">
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <!-- Tile 1: Fixed Routine -->
            <div class="hud-card p-3.5 rounded-xl space-y-2.5">
              <div class="flex items-center justify-between pb-2 border-b border-[var(--hud-border-dim)]">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-sm text-[var(--text-main)]">${dayName}</span>
                  <span class="text-[10px] font-mono text-[var(--text-muted)]">${info.displayDate}</span>
                  ${info.isToday ? '<span class="text-[9px] font-mono px-2 py-0.5 rounded-full bg-blue-600 text-white font-bold uppercase">Today</span>' : ''}
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-[10px] font-mono font-bold text-blue-600 dark:text-cyan-400">${(dayMins / 60).toFixed(1)}h Fixed</span>
                  <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500">${Math.max(0, 16 - dayMins / 60).toFixed(1)}h Free</span>
                </div>
              </div>
              <div class="space-y-2 max-h-56 overflow-y-auto pr-1">${routineHtml}</div>
            </div>

            <!-- Tile 2 (Parallel): Extra Work & Deadlines Till Day -->
            <div class="hud-card p-3.5 rounded-xl space-y-2.5">
              <div class="flex items-center justify-between pb-2 border-b border-[var(--hud-border-dim)]">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-sm text-[var(--text-main)]">Extra Work Till ${dayName.slice(0, 3)}</span>
                  <span class="text-[10px] font-mono px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-500 font-bold">${extraTillDay.length} item${extraTillDay.length === 1 ? '' : 's'}</span>
                </div>
                <button onclick="quickStageForDay('${info.dateStr}')" class="px-2 py-1 rounded-lg hud-raised hover:hud-inset text-[10px] font-bold text-[var(--hud-accent)] transition">+ Add</button>
              </div>
              <div class="space-y-2 max-h-56 overflow-y-auto pr-1">${extraHtml}</div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  if (listEl) {
    listEl.innerHTML = '';
  }
}

function changeCalendarMonth(delta) {
  calendarViewMonth += delta;
  if (calendarViewMonth < 0) {
    calendarViewMonth = 11;
    calendarViewYear -= 1;
  } else if (calendarViewMonth > 11) {
    calendarViewMonth = 0;
    calendarViewYear += 1;
  }
  renderDeadlinesCalendar();
}

function jumpCalendarToday() {
  const now = new Date();
  calendarViewYear = now.getFullYear();
  calendarViewMonth = now.getMonth();
  calendarSelectedDate = toLocalDateStr(now);
  renderDeadlinesCalendar();
}

function selectCalendarDate(dateStr) {
  calendarSelectedDate = dateStr;
  renderDeadlinesCalendar();
}

function renderDeadlinesCalendar() {
  const gridEl = document.getElementById('calendarGrid');
  const labelEl = document.getElementById('calendarMonthLabel');
  if (!gridEl) return;

  const todayStr = toLocalDateStr(new Date());
  if (!calendarSelectedDate) calendarSelectedDate = todayStr;

  const monthDate = new Date(calendarViewYear, calendarViewMonth, 1);
  if (labelEl) {
    labelEl.textContent = monthDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }

  const allItems = collectAllDeadlines();
  const byDate = {};
  let overdueCount = 0;
  let dueTodayCount = 0;
  let upcomingCount = 0;

  allItems.forEach((item) => {
    if (!byDate[item.dateStr]) byDate[item.dateStr] = [];
    byDate[item.dateStr].push(item);
    if (item.dateStr < todayStr) overdueCount += 1;
    else if (item.dateStr === todayStr) dueTodayCount += 1;
    else upcomingCount += 1;
  });

  const ovEl = document.getElementById('calOverdueCount');
  const tdEl = document.getElementById('calDueTodayCount');
  const upEl = document.getElementById('calUpcomingCount');
  if (ovEl) ovEl.textContent = String(overdueCount);
  if (tdEl) tdEl.textContent = String(dueTodayCount);
  if (upEl) upEl.textContent = String(upcomingCount);

  const firstWeekday = (monthDate.getDay() + 6) % 7; // Mon=0..Sun=6
  const daysInMonth = new Date(calendarViewYear, calendarViewMonth + 1, 0).getDate();

  let cellsHtml = '';
  for (let i = 0; i < firstWeekday; i++) {
    cellsHtml += `<div class="h-11 sm:h-12 rounded-lg opacity-25"></div>`;
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const dStr = `${calendarViewYear}-${String(calendarViewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayItems = byDate[dStr] || [];
    const isToday = dStr === todayStr;
    const isSelected = dStr === calendarSelectedDate;

    let ringClass = 'hud-inset border border-transparent hover:border-[var(--hud-accent)]';
    if (isSelected) {
      ringClass = 'bg-blue-600 text-white border border-blue-400 shadow-md';
    } else if (isToday) {
      ringClass = 'hud-raised border-2 border-blue-500 text-[var(--text-main)]';
    }

    const dotColor = dStr < todayStr ? 'bg-rose-400' : (dStr === todayStr ? 'bg-amber-400' : 'bg-cyan-400');
    const badgeHtml = dayItems.length > 0
      ? `<span class="mt-0.5 inline-flex items-center gap-0.5 text-[9px] font-mono font-bold ${isSelected ? 'text-white' : 'text-[var(--hud-accent)]'}"><span class="w-1.5 h-1.5 rounded-full ${dotColor}"></span>${dayItems.length}</span>`
      : '';

    cellsHtml += `
      <button onclick="selectCalendarDate('${dStr}')" class="h-11 sm:h-12 rounded-lg p-1 flex flex-col items-center justify-center transition ${ringClass}">
        <span class="text-xs font-bold leading-none">${day}</span>
        ${badgeHtml}
      </button>
    `;
  }

  gridEl.innerHTML = cellsHtml;

  const selTitle = document.getElementById('selectedDateTitle');
  const selBadge = document.getElementById('selectedDateCountBadge');
  const selList = document.getElementById('selectedDateDeadlinesList');
  const selItems = byDate[calendarSelectedDate] || [];

  if (selTitle) selTitle.textContent = `Deadlines & Work for ${calendarSelectedDate}`;
  if (selBadge) selBadge.textContent = `${selItems.length} item${selItems.length === 1 ? '' : 's'}`;
  if (selList) {
    if (selItems.length === 0) {
      selList.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-3 text-center font-mono">No due dates or deadlines on ${calendarSelectedDate}.</div>`;
    } else {
      selList.innerHTML = selItems.map((it) => `
        <div class="p-2.5 rounded-xl hud-inset border border-[var(--hud-border-dim)] flex items-center justify-between gap-2">
          <div class="min-w-0">
            <div class="text-xs font-bold text-[var(--text-main)] truncate">${escapeHtml(it.title)}</div>
            <div class="text-[10px] font-mono text-[var(--text-muted)]">${escapeHtml(it.timeStr)} &bull; ${escapeHtml(it.priority)} &bull; ${escapeHtml(it.status)}</div>
          </div>
          <span class="text-[9px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-cyan-400 uppercase font-bold shrink-0">${escapeHtml(it.source)}</span>
        </div>
      `).join('');
    }
  }
}

async function submitReminderForm() {
  const titleEl = document.getElementById('reminderTitleInput');
  const dateEl = document.getElementById('reminderDateInput');
  const timeEl = document.getElementById('reminderTimeInput');
  const prioEl = document.getElementById('reminderPriorityInput');

  const title = titleEl ? titleEl.value.trim() : '';
  if (!title) return;

  const dateVal = dateEl ? dateEl.value : '';
  const timeVal = timeEl ? timeEl.value : '';
  const priority = prioEl ? prioEl.value : 'normal';
  const rawDue = [dateVal, timeVal].filter(Boolean).join(' ') || title;

  await fetch('/reminders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      raw_due_text: rawDue,
      priority
    })
  });

  if (titleEl) titleEl.value = '';
  await syncAllData();
}

async function loadSettingsMobileInfo() {
  const qrEl = document.getElementById('settingsMobileQrContainer');
  const urlEl = document.getElementById('settingsMobileUrlInput');
  const apkEl = document.getElementById('settingsApkPathText');
  if (!qrEl && !urlEl) return;

  try {
    const res = await fetch('/api/mobile/install-info');
    if (res.ok) {
      const info = await res.json();
      if (urlEl && info.install_url) urlEl.value = info.install_url;
      if (qrEl && info.qr_svg) qrEl.innerHTML = info.qr_svg;
      if (apkEl && info.apk_project_path) apkEl.textContent = info.apk_project_path;
      return;
    }
  } catch (e) {
    // Fallback offline SVG QR
  }

  const fallbackUrl = window.location.origin || 'http://127.0.0.1:8000';
  if (urlEl) urlEl.value = fallbackUrl;
  if (qrEl) qrEl.innerHTML = generateClientQrSvg(fallbackUrl);
}

function copySettingsMobileUrl() {
  const urlInput = document.getElementById('settingsMobileUrlInput');
  const statusEl = document.getElementById('settingsCopyUrlStatus');
  if (urlInput) {
    navigator.clipboard.writeText(urlInput.value).then(() => {
      if (statusEl) {
        statusEl.classList.remove('hidden');
        setTimeout(() => statusEl.classList.add('hidden'), 3000);
      }
    });
  }
}

function updateTrueFreeHoursBar(lockedMins) {
  const wakingMins = 16 * 60;
  const freeMins = Math.max(0, wakingMins - lockedMins);
  const freeHours = (freeMins / 60).toFixed(1);
  const percent = Math.min(100, Math.max(0, Math.round((freeMins / wakingMins) * 100)));

  const textEl = document.getElementById('trueFreeHoursText');
  const barEl = document.getElementById('trueFreeProgressBar');
  const routineEl = document.getElementById('statRoutineHours');
  const summaryEl = document.getElementById('weeklyTrueFreeSummary');

  if (textEl) textEl.textContent = `${freeHours} hrs`;
  if (barEl) barEl.style.width = `${percent}%`;
  if (routineEl) routineEl.textContent = `${(lockedMins / 60).toFixed(1)}h`;
  if (summaryEl) summaryEl.textContent = `${freeHours}h free / ${(lockedMins / 60).toFixed(1)}h routine`;
}

async function addWeeklyRoutineBlock() {
  const day = document.getElementById('routineDayInput')?.value || 'Daily';
  const title = document.getElementById('routineTitleInput')?.value.trim();
  const start_time = document.getElementById('routineStartInput')?.value || '09:00';
  const end_time = document.getElementById('routineEndInput')?.value || '11:00';
  const category = document.getElementById('routineCategoryInput')?.value.trim() || 'Core Routine';

  if (!title) return;

  await fetch('/api/routine/weekly', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      day_of_week: day,
      title,
      start_time,
      end_time,
      category
    })
  });

  document.getElementById('routineTitleInput').value = '';
  await syncAllData();
}

async function deleteWeeklyRoutineBlock(id) {
  await fetch(`/api/routine/weekly/${id}`, { method: 'DELETE' });
  await syncAllData();
}

/* ============================================================================
   13. TAB 5: NIGHTLY AUDIT & ACTIVE RECALL QUIZ
   ============================================================================ */

function renderNightlyAuditSection() {
  const checklistEl = document.getElementById('nightlyTaskChecklist');
  const scoreBadge = document.getElementById('nightlyDisciplineScoreBadge');
  const courseSelect = document.getElementById('nightlyCourseSelect');

  updateDisciplineGauge(jarvisState.lastDisciplineScore || 85);

  const tasks = jarvisState.reminders.filter((r) => r.status === 'confirmed' || r.status === 'scheduled');
  if (checklistEl) {
    if (tasks.length === 0) {
      checklistEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] col-span-2 py-4 font-mono-code">No tasks scheduled for today's audit.</div>`;
    } else {
      checklistEl.innerHTML = tasks
        .map(
          (t, idx) => `
        <label class="p-3 rounded-2xl hud-inset border border-[var(--hud-border-dim)] flex items-center justify-between gap-3 text-xs cursor-pointer">
          <div class="flex items-center gap-2.5">
            <input type="checkbox" data-task-id="${t.id}" class="rounded text-[var(--hud-accent)]">
            <span class="font-semibold text-[var(--text-main)] font-hud-clock">${escapeHtml(t.title)}</span>
          </div>
          <span class="text-[10px] text-[var(--text-muted)] font-mono-code">${t.due_datetime ? new Date(t.due_datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Today'}</span>
        </label>
      `
        )
        .join('');
    }
  }

  if (courseSelect && jarvisState.courses.length > 0) {
    courseSelect.innerHTML = jarvisState.courses
      .map((c) => `<option value="${c.id}">${escapeHtml(c.title)} (${escapeHtml(c.category || 'General')})</option>`)
      .join('');
  }
}

async function submitNightlyAudit() {
  const course_id = parseInt(document.getElementById('nightlyCourseSelect')?.value || '1', 10);
  const topic = document.getElementById('nightlyTopicInput')?.value.trim() || 'Daily Learning';
  const reflection = document.getElementById('nightlyReflectionInput')?.value.trim();

  const checkboxes = document.querySelectorAll('#nightlyTaskChecklist input[type="checkbox"]');
  const completed_ids = [];
  checkboxes.forEach((cb) => {
    if (cb.checked) {
      completed_ids.push(parseInt(cb.getAttribute('data-task-id'), 10));
    }
  });

  const res = await fetch('/api/audit/nightly', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      course_id,
      topic,
      raw_notes: reflection,
      completed_task_ids: completed_ids
    })
  });

  const data = await res.json();
  const discScore = data.discipline_score !== undefined ? data.discipline_score : 100;
  updateDisciplineGauge(discScore);

  const notesEl = document.getElementById('nightlyStructuredNotesOutput');
  if (notesEl && data.course_log && data.course_log.structured_summary) {
    notesEl.textContent = data.course_log.structured_summary;
    notesEl.classList.remove('hidden');
  }

  if (data.recall_quiz && data.recall_quiz.length > 0) {
    jarvisState.lastRecallQuiz = data.recall_quiz;
    renderRecallQuizUI();
  }

  await syncAllData();
}

async function generateActiveRecallQuizNow() {
  const container = document.getElementById('nightlyRecallQuizContainer');
  if (container) {
    container.innerHTML = `
      <div class="p-4 rounded-2xl hud-inset text-xs font-mono text-center text-blue-600 dark:text-cyan-400 animate-pulse">
        Generating active recall quiz questions via Groq LLaMA-3.3 70B...
      </div>
    `;
  }

  try {
    const course_id = parseInt(document.getElementById('nightlyCourseSelect')?.value || '1', 10);
    const topic = document.getElementById('nightlyTopicInput')?.value.trim() || 'Core Engineering Principles';
    const notes = document.getElementById('nightlyReflectionInput')?.value.trim() || 'Transformer architectures, KV cache retention, and deterministic execution pipelines.';

    const res = await fetch('/api/audit/nightly', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        course_id,
        topic,
        raw_notes: notes,
        completed_task_ids: []
      })
    });

    if (res.ok) {
      const data = await res.json();
      if (data.recall_quiz && data.recall_quiz.length > 0) {
        jarvisState.lastRecallQuiz = data.recall_quiz;
        if (data.discipline_score !== undefined) {
          updateDisciplineGauge(data.discipline_score);
        }
      }
    }
  } catch (err) {
    console.warn('Quiz generation fetch fallback:', err);
  }

  if (!jarvisState.lastRecallQuiz || jarvisState.lastRecallQuiz.length === 0) {
    jarvisState.lastRecallQuiz = [
      {
        question: "In transformer attention mechanisms, what is the primary benefit of the Key-Value (KV) cache?",
        options: [
          "It avoids recomputing keys and values for earlier tokens during autoregressive decoding",
          "It compresses model weights into 8-bit integer representations",
          "It eliminates the need for positional embeddings in multi-head attention",
          "It replaces backpropagation with direct gradient descent"
        ],
        correct_option_index: 0
      },
      {
        question: "Why must temporal task scheduling and date computation run deterministically rather than relying on LLM outputs?",
        options: [
          "LLMs can hallucinate dates, timezones, and day offsets; deterministic code guarantees strict calendar accuracy",
          "Deterministic code requires GPU acceleration",
          "LLMs cannot parse numbers higher than 60",
          "Deterministic algorithms reduce network bandwidth by 90%"
        ],
        correct_option_index: 0
      }
    ];
  }

  renderRecallQuizUI();
}

function renderRecallQuizUI() {
  const quizContainer = document.getElementById('nightlyRecallQuizContainer');
  if (!quizContainer) return;

  if (!jarvisState.lastRecallQuiz || jarvisState.lastRecallQuiz.length === 0) {
    quizContainer.innerHTML = `
      <div class="p-4 rounded-2xl hud-inset text-xs text-[var(--text-muted)] text-center font-mono-code">
        No active recall quiz. Click 'Refresh Quiz' or submit daily reflection to generate retention questions.
      </div>
    `;
    return;
  }

  quizContainer.innerHTML = jarvisState.lastRecallQuiz
    .map(
      (q, idx) => `
    <div class="p-3.5 rounded-2xl hud-inset border border-[var(--hud-border-dim)] space-y-2 text-xs">
      <div class="font-bold text-[var(--hud-accent)] font-hud-clock flex items-center gap-2">
        <span class="w-5 h-5 rounded-full hud-raised flex items-center justify-center text-[10px] text-blue-600 dark:text-cyan-400 font-mono font-bold">${idx + 1}</span>
        <span>${escapeHtml(q.question)}</span>
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
        ${(q.options || [])
          .map(
            (opt, oIdx) => `
          <button onclick="checkRecallQuizAnswer(${idx}, ${oIdx})" id="quiz-opt-${idx}-${oIdx}" class="p-2.5 rounded-xl hud-inset hover:hud-raised text-left text-xs transition flex items-center gap-2">
            <span class="w-4 h-4 rounded-full border border-[var(--hud-border)] flex items-center justify-center text-[9px] shrink-0 font-mono font-bold">${String.fromCharCode(65 + oIdx)}</span>
            <span>${escapeHtml(opt)}</span>
          </button>
        `
          )
          .join('')}
      </div>
      <div id="quiz-feedback-${idx}" class="hidden text-xs font-mono-code pt-1"></div>
    </div>
  `
    )
    .join('');
}

function checkRecallQuizAnswer(qIdx, oIdx) {
  const quiz = jarvisState.lastRecallQuiz[qIdx];
  if (!quiz) return;

  const isCorrect = oIdx === quiz.correct_option_index;
  const feedbackEl = document.getElementById(`quiz-feedback-${qIdx}`);
  const btnEl = document.getElementById(`quiz-opt-${qIdx}-${oIdx}`);

  if (feedbackEl) {
    feedbackEl.textContent = isCorrect ? ' Correct! Recall verified.' : 'x Incorrect. Review structured takeaways.';
    feedbackEl.className = isCorrect ? 'text-xs font-mono-code pt-1 text-emerald-400' : 'text-xs font-mono-code pt-1 text-rose-400';
    feedbackEl.classList.remove('hidden');
  }

  if (btnEl) {
    if (isCorrect) btnEl.classList.add('border-emerald-400', 'bg-emerald-500/20');
    else btnEl.classList.add('border-rose-400', 'bg-rose-500/20');
  }
}

/* ============================================================================
   14. TAB 4: BUSINESS BUDDY & AUTONOMOUS SMALL-TASK WORKER
   ============================================================================ */

function renderBusinessSection() {
  const bizListEl = document.getElementById('businessDeliverablesList');
  const smallTasksEl = document.getElementById('smallTasksStagedList');

  const deliverables = jarvisState.business_deliverables || [];
  if (bizListEl) {
    if (deliverables.length === 0) {
      bizListEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-6 text-center font-mono-code">No client deliverables ranked yet.</div>`;
    } else {
      bizListEl.innerHTML = deliverables
        .map(
          (d) => `
        <div class="p-3.5 rounded-2xl hud-inset border border-[var(--hud-border-dim)] space-y-2">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="text-xs font-bold text-[var(--text-main)] font-hud-clock">${escapeHtml(d.title)}</div>
              <div class="text-[11px] text-[var(--text-muted)] font-mono-code">Client: <span class="text-[var(--hud-accent)]">${escapeHtml(d.client_name)}</span> &bull; Due: ${escapeHtml(d.deadline)}</div>
            </div>
            <div class="text-right">
              <span class="text-xs font-mono-code px-2 py-0.5 rounded-full ${d.urgency_score > 60 ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'}">
                Urgency: ${(d.urgency_score || 0).toFixed(0)}
              </span>
            </div>
          </div>
          <div class="flex items-center justify-between text-[11px] text-[var(--text-muted)] font-mono-code pt-1 border-t border-[var(--hud-border-dim)]">
            <span>Est: ${d.estimated_hours}h &bull; Impact: ${d.impact_score}/10</span>
            <span class="uppercase text-[10px] text-emerald-400">${escapeHtml(d.status || 'Active')}</span>
          </div>
        </div>
      `
        )
        .join('');
    }
  }

  const smallTasks = jarvisState.small_tasks || [];
  if (smallTasksEl) {
    if (smallTasks.length === 0) {
      smallTasksEl.innerHTML = `<div class="text-xs text-[var(--text-muted)] py-6 text-center font-mono-code">No small tasks currently prepared. Run worker above.</div>`;
    } else {
      smallTasksEl.innerHTML = smallTasks
        .map(
          (st) => `
        <div class="p-4 rounded-2xl hud-inset border border-purple-500/30 space-y-2.5 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-bold text-purple-300 uppercase font-mono-code text-[11px]">${escapeHtml(st.task_type)}</span>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-[var(--text-muted)] font-mono-code">${escapeHtml(st.status || 'prepared')}</span>
          </div>
          <div class="text-[var(--text-main)] font-medium leading-relaxed">${escapeHtml(st.prompt)}</div>
          ${st.staged_output ? `<pre class="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-purple-200 whitespace-pre-wrap font-mono-code max-h-48 overflow-y-auto">${escapeHtml(st.staged_output)}</pre>` : ''}
          <div class="flex items-center justify-end gap-2 pt-1">
            <button onclick="confirmSmallTaskToRoutine(${st.id})" class="px-3 py-1.5 rounded-xl bg-purple-500 hover:bg-purple-400 text-slate-950 font-bold text-xs font-hud-clock transition">
              Stage to Routine / Confirm
            </button>
          </div>
        </div>
      `
        )
        .join('');
    }
  }
}

async function addBusinessDeliverable() {
  const client_name = document.getElementById('bizClientInput')?.value.trim() || 'Internal Client';
  const title = document.getElementById('bizTitleInput')?.value.trim();
  const deadline = document.getElementById('bizDeadlineInput')?.value || new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const estimated_hours = parseFloat(document.getElementById('bizHoursInput')?.value || '4') || 4.0;
  const impact_score = parseInt(document.getElementById('bizImpactInput')?.value || '8', 10) || 8;

  if (!title) return;

  await fetch('/api/business/deliverables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_name,
      title,
      deadline,
      estimated_hours,
      impact_score
    })
  });

  document.getElementById('bizTitleInput').value = '';
  await syncAllData();
}

async function runSmallTaskBuddy() {
  const task_type = document.getElementById('smallTaskTypeInput')?.value || 'draft';
  const prompt = document.getElementById('smallTaskPromptInput')?.value.trim();
  if (!prompt) return;

  await fetch('/api/business/small-task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, task_type })
  });

  document.getElementById('smallTaskPromptInput').value = '';
  await syncAllData();
}

async function confirmSmallTaskToRoutine(id) {
  await fetch(`/api/business/small-task/${id}/confirm`, { method: 'POST' });
  await syncAllData();
}

/* ============================================================================
   15. 6-TAB DASHBOARD NAVIGATION ENGINE
   ============================================================================ */

function switchDashboardTab(tabKey) {
  let target = tabKey;
  if (tabKey === 'today' || tabKey === 'command') target = 'chat';
  if (tabKey === 'weekly') target = 'routine';
  if (tabKey === 'alarm') target = 'reminders';

  const tabConfigs = [
    { key: 'chat', secId: 'section-chat', btnId: 'nav-btn-chat', legacyBtnId: 'nav-btn-today' },
    { key: 'routine', secId: 'section-routine', btnId: 'nav-btn-routine', legacyBtnId: 'nav-btn-routine' },
    { key: 'reminders', secId: 'section-reminders', btnId: 'nav-btn-reminders', legacyBtnId: 'nav-btn-alarm' },
    { key: 'settings', secId: 'section-settings', btnId: 'nav-btn-settings', legacyBtnId: null }
  ];

  tabConfigs.forEach((conf) => {
    const sec = document.getElementById(conf.secId);
    const btn = document.getElementById(conf.btnId);
    const legacyBtn = conf.legacyBtnId ? document.getElementById(conf.legacyBtnId) : null;

    if (conf.key === target) {
      if (sec) sec.classList.remove('hidden');
      if (btn) {
        btn.classList.add('tab-active');
        btn.classList.remove('border-transparent', 'text-[var(--text-muted)]');
      }
      if (legacyBtn) {
        legacyBtn.classList.add('tab-active');
      }
    } else {
      if (sec) sec.classList.add('hidden');
      if (btn) {
        btn.classList.remove('tab-active');
        btn.classList.add('border-transparent', 'text-[var(--text-muted)]');
      }
      if (legacyBtn) {
        legacyBtn.classList.remove('tab-active');
      }
    }
  });

  if (target === 'routine') {
    renderDeadlinesCalendar();
    renderWeeklyRoutineSection();
    renderProposedAuditInputList();
  } else if (target === 'reminders') {
    renderRemindersSection();
  } else if (target === 'settings') {
    loadSettingsMobileInfo();
    updateTelemetryUI();
  }
}

/* ============================================================================
   16. UI TEMPLATE ACTION ALIASES & COMPATIBILITY BINDINGS
   ============================================================================ */

function handleQuickChatChip(text) {
  sendChatMessage(text);
}

async function executeQuickCaptureText() {
  await submitQuickCapture();
}

async function addAlarmRecord() {
  await createAlarmEntry();
}

function stageAuditTaskFromInputs() {
  addProposedAuditTask();
}

async function runAdvisoryAudit() {
  await runHardRoutineAudit();
}

async function commitAuditedRoutine() {
  await commitRoutinePlan('strict');
}

async function stageSmallTask() {
  await runSmallTaskBuddy();
}

async function submitNightlyReflection() {
  await submitNightlyAudit();
}

async function triggerPwaInstallPrompt() {
  await triggerOneClickMobileInstall();
}

function triggerSimulatedAlarm() {
  triggerTestWakeAlarm();
}

async function toggleChatVoiceRecording() {
  await toggleChatMic();
}

async function toggleTaskVoiceRecording() {
  await toggleVoiceRecording('task');
}

async function toggleCourseVoiceRecording() {
  await toggleVoiceRecording('course');
}

async function toggleArcReactorVoice() {
  await toggleMicRecording();
}

/* ============================================================================
   17. BOOTSTRAP ON LOAD
   ============================================================================ */

window.addEventListener('online', () => syncAllData());
window.addEventListener('offline', () => updateConnectionStatusUI(false));

document.addEventListener('DOMContentLoaded', async () => {
  await registerServiceWorker();

  // Load Saved Theme (Default to authentic White Neumorphic matching Image 1-3)
  applyTheme(localStorage.getItem('jarvis_theme_mode') || 'dark');

  // Load Saved Font
  const savedBodyFont = 'Inter';
  const savedDisplayFont = 'Plus Jakarta Sans';
  applyFont(savedBodyFont, savedDisplayFont);

  // Start Live HUD Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Initialize Chat Hub
  initChat();

  // Initialize Discipline Gauge
  updateDisciplineGauge(85);

  // Load Remote & Offline Data
  await syncAllData();

  // 5-Second Local Offline Watchdog Timer for reminders & alarms
  setInterval(runLocalOfflineWatchdog, 5000);

  // Periodic Background Sync (30s)
  setInterval(syncAllData, 30000);
});

// =============================================================================
// GLOBAL EXPOSURES: Guarantee all HTML onclick handlers work across all browsers
// =============================================================================

/* ============================================================================
   INTERACTIVE CHAT ACTION CARDS & ROUTINE COMPLETION ENGINE
   ============================================================================ */

function renderActionCardHtml(action, idx) {
  if (!action) return '';

  if (action.status === 'confirmed') {
    return `
      <div class="mt-2.5 p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs flex items-center justify-between gap-2 animate-fadeIn">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-sm font-bold">✓</span>
          <div class="min-w-0">
            <div class="font-bold truncate">${escapeHtml(action.title || 'Action Confirmed')}</div>
            <div class="text-[10px] opacity-80 font-mono">${escapeHtml(action.details || '')}</div>
          </div>
        </div>
        <span class="text-[9px] font-mono uppercase bg-emerald-500/25 px-2 py-0.5 rounded font-bold shrink-0">Committed</span>
      </div>
    `;
  }

  if (action.status === 'dismissed' || action.status === 'cancelled') {
    return `
      <div class="mt-2 p-2 rounded-lg hud-inset text-[11px] text-[var(--text-muted)] italic">
        Action cancelled.
      </div>
    `;
  }

  let slotsHtml = '';
  if (action.slots && action.slots.length > 0) {
    const selectedStart = (action.params && action.params.start_time) || action.slots[0].start;
    slotsHtml = `
      <div class="space-y-1.5 pt-1">
        <div class="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Select Time Slot:</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          ${action.slots.map(s => {
            const isSel = s.start === selectedStart;
            return `
              <button type="button"
                      onclick="selectActionSlot(${idx}, '${s.start}', '${s.end}', '${escapeHtml(s.label)}')"
                      class="px-2.5 py-1.5 rounded-lg text-left text-xs font-mono transition border ${isSel ? 'bg-blue-600 text-white border-blue-400 shadow-sm' : 'hud-raised text-[var(--text-main)] hover:border-blue-400'}">
                <div class="font-bold leading-tight">${s.label}</div>
              </button>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  return `
    <div class="mt-3 p-3.5 rounded-xl hud-inset border border-blue-500/30 bg-[var(--hud-panel)] space-y-2.5 select-none shadow-sm">
      <div class="flex items-center justify-between gap-2 pb-1.5 border-b border-[var(--hud-border-dim)]">
        <div class="flex items-center gap-2 font-bold text-xs text-[var(--text-main)]">
          <span class="text-sm">⚡</span>
          <span>${escapeHtml(action.title || 'Action Required')}</span>
        </div>
        <span class="text-[9px] font-mono uppercase px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 font-bold shrink-0">Confirmation Card</span>
      </div>
      <p class="text-[11px] text-[var(--text-muted)] leading-relaxed">${escapeHtml(action.details || '')}</p>

      ${slotsHtml}

      <div class="flex items-center gap-2 pt-2 border-t border-[var(--hud-border-dim)]">
        <button type="button" onclick="executeChatAction(${idx})" class="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs uppercase tracking-wider transition shadow-sm flex items-center gap-1.5">
          <span>✓ Confirm &amp; Execute</span>
        </button>
        <button type="button" onclick="dismissChatAction(${idx})" class="px-2.5 py-1.5 rounded-lg hud-raised hover:hud-inset text-xs font-semibold text-[var(--text-muted)] hover:text-rose-400 transition">
          Cancel
        </button>
      </div>
    </div>
  `;
}

function selectActionSlot(idx, start, end, label) {
  if (!chatHistory[idx] || !chatHistory[idx].action) return;
  const action = chatHistory[idx].action;
  if (!action.params) action.params = {};
  action.params.start_time = start;
  action.params.end_time = end;
  if (label) {
    action.details = `Selected slot: ${label}`;
  }
  persistChats();
  renderChatMessages();
}

function dismissChatAction(idx) {
  if (!chatHistory[idx] || !chatHistory[idx].action) return;
  chatHistory[idx].action.status = 'cancelled';
  persistChats();
  renderChatMessages();
}

async function executeChatAction(idx) {
  if (!chatHistory[idx] || !chatHistory[idx].action) return;
  const action = chatHistory[idx].action;

  try {
    const res = await fetch('/api/actions/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: action.type,
        params: action.params || {},
        user_confirmed: true
      })
    });

    if (res.ok) {
      action.status = 'confirmed';
      persistChats();
      renderChatMessages();
      await syncAllData();

      if (action.type === 'switch_theme' && action.params && action.params.theme) {
        applyTheme(action.params.theme);
      }
    } else {
      alert('Action execution failed. Please check server logs.');
    }
  } catch (err) {
    alert(`Error executing action: ${err.message}`);
  }
}

async function toggleRoutineCompletion(routineId, dateStr, completed) {
  try {
    await fetch('/api/routine/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        routine_id: routineId,
        date: dateStr,
        completed: completed
      })
    });
    await syncAllData();
  } catch (err) {
    console.error('Failed to toggle routine completion:', err);
  }
}

if (typeof window !== 'undefined') {
  window.toggleAutoVoiceReply = toggleAutoVoiceReply;
  window.stopSpeaking = stopSpeaking;
  window.speakText = speakText;

  window.renameChat = renameChat;
  window.clearAllChats = clearAllChats;
  window.toggleChatSidebar = toggleChatSidebar;
  window.copyChatMessageText = copyChatMessageText;

  window.applyTheme = applyTheme;
  window.applyFont = applyFont;
  window.switchDashboardTab = switchDashboardTab;
  window.sendChatMessage = sendChatMessage;
  window.clearChatHistory = clearChatHistory;
window.newChat = newChat;
window.openChat = openChat;
window.deleteChat = deleteChat;
window.renderChatList = renderChatList;
  window.handleQuickChatChip = handleQuickChatChip;
  window.toggleChatVoiceRecording = toggleChatVoiceRecording;
  window.toggleTaskVoiceRecording = toggleTaskVoiceRecording;
  window.toggleCourseVoiceRecording = toggleCourseVoiceRecording;
  window.toggleArcReactorVoice = toggleArcReactorVoice;
  window.openMobileInstallModal = openMobileInstallModal;
  window.closeMobileInstallModal = closeMobileInstallModal;
  window.copyMobileInstallUrl = copyMobileInstallUrl;
  window.triggerPwaInstallPrompt = triggerPwaInstallPrompt;
  window.triggerSimulatedAlarm = triggerSimulatedAlarm;
  window.submitWakeVerification = submitWakeVerification;
  window.addAlarmRecord = addAlarmRecord;
  window.deleteAlarmEntry = deleteAlarmEntry;
  window.toggleAlarmStatus = toggleAlarmStatus;
  window.runAdvisoryAudit = runAdvisoryAudit;
  window.stageAuditTaskFromInputs = stageAuditTaskFromInputs;
  window.removeProposedAuditTask = removeProposedAuditTask;
  window.commitAuditedRoutine = commitAuditedRoutine;
  window.addWeeklyRoutineBlock = addWeeklyRoutineBlock;
  window.deleteWeeklyRoutineBlock = deleteWeeklyRoutineBlock;
  window.submitNightlyReflection = submitNightlyReflection;
  window.generateActiveRecallQuizNow = generateActiveRecallQuizNow;
  window.checkRecallQuizAnswer = checkRecallQuizAnswer;
  window.addBusinessDeliverable = addBusinessDeliverable;
  window.stageSmallTask = stageSmallTask;
  window.confirmPendingTask = confirmPendingTask;
  window.rejectPendingTask = rejectPendingTask;
  window.deleteConfirmedTask = deleteConfirmedTask;
  window.speakChatMessageText = speakChatMessageText;
  window.triggerBriefing = triggerBriefing;
  window.syncAllData = syncAllData;
  window.changeCalendarMonth = changeCalendarMonth;
  window.jumpCalendarToday = jumpCalendarToday;
  window.selectCalendarDate = selectCalendarDate;
  window.quickStageForDay = quickStageForDay;
  window.submitReminderForm = submitReminderForm;
  window.loadSettingsMobileInfo = loadSettingsMobileInfo;
  window.copySettingsMobileUrl = copySettingsMobileUrl;
  window.renderActionCardHtml = renderActionCardHtml;
  window.selectActionSlot = selectActionSlot;
  window.dismissChatAction = dismissChatAction;
  window.executeChatAction = executeChatAction;
  window.toggleRoutineCompletion = toggleRoutineCompletion;
}
