const STATIC_CACHE = 'recall-static-v1';
const DATA_CACHE   = 'recall-data-v1';
const CDN_CACHE    = 'recall-cdn-v1';
const ALL_CACHES   = [STATIC_CACHE, DATA_CACHE, CDN_CACHE];

const CDN_HOSTS = ['code.jquery.com', 'cdn.datatables.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

// ── Install：只預快取輕量靜態資源 ──────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(['./index.html', './manifest.json']))
      .then(() => self.skipWaiting())
  );
});

// ── Activate：清除舊版 cache ────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => !ALL_CACHES.includes(k)).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

function notifyClients(type) {
  self.clients.matchAll().then(clients =>
    clients.forEach(c => c.postMessage({ type }))
  );
}

// ── Fetch ───────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // ── data/data.json（可能帶有 ?t=timestamp cache-busting query）──
  // 以去除 query string 的正規化 URL 作為 cache key，確保快取可命中
  // 策略：network-first（回收資料每日更新，優先取最新），離線顯示快取並通知
  if (url.pathname.endsWith('data/data.json')) {
    const normalizedKey = new Request(url.origin + url.pathname);

    event.respondWith(
      caches.open(DATA_CACHE).then(async cache => {
        try {
          const response = await fetch(event.request);
          if (response.ok) cache.put(normalizedKey, response.clone());
          return response;
        } catch {
          const cached = await cache.match(normalizedKey);
          if (cached) {
            notifyClients('OFFLINE_MODE');
            return cached;
          }
          // 無快取且無網路：回傳空陣列讓頁面呈現無資料狀態
          return new Response('[]', {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        }
      })
    );
    return;
  }

  // ── CDN 資源（jQuery、DataTables、Google Fonts）：cache-first ──
  // 版本號固定的 CDN URL 不會變動，優先從快取回傳以支援離線
  if (CDN_HOSTS.some(h => url.hostname === h)) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok) {
            caches.open(CDN_CACHE).then(c => c.put(event.request, response.clone()));
          }
          return response;
        }).catch(() => new Response('', { status: 503 }));
      })
    );
    return;
  }

  // ── 同源靜態資源：network-first + cache fallback ────────────────
  if (url.origin === self.location.origin) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response.ok) {
            caches.open(STATIC_CACHE).then(c => c.put(event.request, response.clone()));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
