const VERSION      = 'v4';  // v4：CDN 升級 jQuery 3.7.1 / DataTables 1.13.8 並加 SRI，清舊版 CDN 快取
const STATIC_CACHE = 'recall-static-' + VERSION;
const DATA_CACHE   = 'recall-data-'   + VERSION;
const CDN_CACHE    = 'recall-cdn-'    + VERSION;
const ALL_CACHES   = [STATIC_CACHE, DATA_CACHE, CDN_CACHE];
const CACHE_PREFIX = 'recall-';  // 僅管理本專案自己的 cache

const CDN_HOSTS = ['code.jquery.com', 'cdn.datatables.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

// ── Install：只預快取輕量靜態資源 ──────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(['./index.html', './manifest.json']))
      .then(() => self.skipWaiting())
  );
});

// ── Activate：只清除本專案自己的舊版 cache ─────────────────────────
// CR-12：Cache Storage 為 origin-wide，同 origin（liangrxdev.github.io）尚有其他專案。
// 僅刪除 recall- 前綴且不在現行清單的 cache，避免誤刪其他應用的離線資源。
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k.startsWith(CACHE_PREFIX) && !ALL_CACHES.includes(k))
            .map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// CR-09：回傳 Promise，讓呼叫端可 await 確保通知送達後才結束 respondWith
function notifyClients(type) {
  return self.clients.matchAll().then(clients =>
    clients.forEach(c => c.postMessage({ type }))
  );
}

// ── data/data.json：network-first，離線退快取 ──────────────────────
// 策略：優先取最新；離線時若有快取則回傳並通知 OFFLINE_MODE；
// 離線且無快取時回傳 503（絕不以空陣列偽裝成功 — CR-06）。
async function handleData(request) {
  const url = new URL(request.url);
  // 以去除 query string 的正規化 URL 作為 cache key，確保 ?t=timestamp 仍能命中
  const normalizedKey = new Request(url.origin + url.pathname);
  const cache = await caches.open(DATA_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) await cache.put(normalizedKey, response.clone()); // CR-09：await
    return response;
  } catch {
    const cached = await cache.match(normalizedKey);
    if (cached) {
      await notifyClients('OFFLINE_MODE'); // CR-09：await，確保警示送達
      return cached;
    }
    // CR-06：無快取且無網路 → 明確 503，前端據此顯示阻斷式錯誤，不可回傳 []
    return new Response(JSON.stringify({ error: 'offline-no-cache' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// ── CDN 資源：cache-first（版本號固定，優先離線可用）──────────────
async function handleCdn(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CDN_CACHE);
      await cache.put(request, response.clone()); // CR-09：await
    }
    return response;
  } catch {
    return new Response('', { status: 503 });
  }
}

// ── 同源靜態資源：network-first + cache fallback ───────────────────
async function handleStatic(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      await cache.put(request, response.clone()); // CR-09：await
    }
    return response;
  } catch {
    return caches.match(request); // 無快取則回 undefined，交由瀏覽器處理
  }
}

// ── Fetch 路由 ─────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  if (url.pathname.endsWith('data/data.json')) {
    event.respondWith(handleData(event.request));
    return;
  }
  if (CDN_HOSTS.some(h => url.hostname === h)) {
    event.respondWith(handleCdn(event.request));
    return;
  }
  if (url.origin === self.location.origin) {
    event.respondWith(handleStatic(event.request));
  }
});
