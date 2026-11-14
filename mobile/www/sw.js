/* JARVIS Offline-First Service Worker for Internet-Drop Resilience */
const CACHE_NAME = 'jarvis-pwa-cache-v8';
const CORE_ASSETS = [
  '/',
  '/manifest.json',
  '/static/manifest.json',
  '/static/app.js',
  '/static/icon.svg',
  '/static/logo.png',
  '/static/jarvis-logo-dark.png',
  '/static/jarvis-logo-light.png',
  '/static/jarvis-emblem.png',
  '/static/jarvis-emblem-dark.png',
  '/static/jarvis-emblem-light.png',
  '/static/tailwind.js',
  '/icon.svg',
  '/sw.js',
  '/static/sw.js'
];

const API_SYNC_CACHE = 'jarvis-api-sync-v8';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(CORE_ASSETS).catch(() => {
        // Ignore individual asset failure during install
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== API_SYNC_CACHE) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle GET requests in service worker cache
  if (request.method !== 'GET') {
    return;
  }

  // Network-first with offline cache fallback for /api/sync and other GET API endpoints
  if (url.pathname.startsWith('/api/') || url.pathname === '/reminders') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const cloned = response.clone();
            caches.open(API_SYNC_CACHE).then((cache) => {
              cache.put(request, cloned);
            });
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (cached) {
            return cached;
          }
          return new Response(
            JSON.stringify({
              offline: true,
              status: 'offline_cache_fallback',
              reminders: [],
              weekly_routine: [],
              alarms: [],
              courses: [],
              business_deliverables: [],
              small_tasks: []
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' }
            }
          );
        })
    );
    return;
  }

  // Stale-while-revalidate for static assets & dashboard shell
  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      const fetchPromise = fetch(request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const cloned = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, cloned);
            });
          }
          return networkResponse;
        })
        .catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});

// Listen for messages from the foreground app (e.g. alarm trigger or local notification)
self.addEventListener('message', (event) => {
  if (!event.data) return;
  if (event.data.type === 'TRIGGER_NOTIFICATION') {
    const title = event.data.title || 'JARVIS Alert';
    const body = event.data.body || 'Scheduled task or alarm is due now.';
    if (self.registration && self.registration.showNotification) {
      self.registration.showNotification(title, {
        body,
        icon: '/static/icon.svg',
  '/static/logo.png',
  '/static/tailwind.js',
        tag: event.data.tag || 'jarvis-alert',
        renotify: true,
        requireInteraction: true
      }).catch(() => {});
    }
  }
});
