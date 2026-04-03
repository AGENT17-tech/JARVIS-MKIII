const CACHE = 'jarvis-mobile-v2';
const OFFLINE_URL = '/mobile';
const CACHE_URLS = [OFFLINE_URL, '/mobile/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(CACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }
  // Network-first for API calls — return offline sentinel on failure
  if (e.request.url.includes('/chat') || e.request.url.includes('/health')) {
    e.respondWith(fetch(e.request).catch(() =>
      new Response('{"error":"offline"}', { headers: { 'Content-Type': 'application/json' } })
    ));
    return;
  }
  // Cache-first for static assets
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});

// ── Push notification handler ─────────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = { title: 'JARVIS', body: 'Alert from JARVIS' };
  try { data = e.data.json(); } catch {}
  e.waitUntil(
    self.registration.showNotification(data.title || 'JARVIS', {
      body:    data.body  || '',
      icon:    data.icon  || '/mobile/manifest.json',
      badge:   '/mobile/manifest.json',
      vibrate: [200, 100, 200],
      data:    { url: self.location.origin + '/mobile' },
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data?.url || '/mobile'));
});
