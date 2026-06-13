/**
 * Edifico Service Worker
 *
 * Strategii cache:
 * - Static assets (CSS, JS, fonts, icons): stale-while-revalidate
 *   (servesc rapid din cache, dar reactualizez in background)
 * - HTML pagini: network-first (incerc reteaua intai, fallback la cache)
 * - Fallback offline: pagina /offline cand reteaua si cache-ul nu raspund
 *
 * Versiune: bump cand schimbi assets statice ca clienti sa updateze cache-ul.
 */

const CACHE_VERSION = 'edifico-v3'; /* bump: tokens.css (DS faza 1) + librarii viewer self-host (BIM faza 1) */
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const OFFLINE_URL = '/offline';

// Assets esentiale pre-cache la install (pentru offline-first)
const PRECACHE_URLS = [
  '/offline',
  '/static/css/tokens.css',
  '/static/css/style.css',
  '/static/favicon.svg',
  '/static/img/edifico-logo-stacked.svg',
  '/static/img/edifico-logo.svg',
  '/static/img/edifico-mark.svg',
  '/static/img/pwa/icon-192.png',
  '/static/img/pwa/icon-512.png',
  '/static/img/pwa/apple-touch-icon.png',
];

// Librarii viewer 3D vendorizate (self-host) - precache best-effort.
// Sunt mari (~10MB) si optionale: le incarcam separat ca un esec sa NU
// rupa instalarea service worker-ului (PRECACHE_URLS esential ramane garantat).
const VIEWER_LIB_URLS = [
  '/static/lib/xeokit-sdk@2.6.78/xeokit-sdk.es.min.js',
  '/static/lib/web-ifc@0.0.50/web-ifc-api.js',
  '/static/lib/web-ifc@0.0.50/web-ifc.wasm',
  '/static/lib/web-ifc@0.0.50/web-ifc-mt.wasm',
];

// ============================================================
// INSTALL: pre-cache asset-uri esentiale + skip waiting
// ============================================================
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS)
        // Librariile viewer (mari, optionale): best-effort, fiecare individual,
        // ca un 404/timeout sa NU rupa instalarea SW-ului.
        .then(() => Promise.allSettled(
          VIEWER_LIB_URLS.map((u) =>
            cache.add(u).catch((e) => console.warn('[SW] Lib viewer ne-cache-uita:', u, e))
          )
        ))
      )
      .then(() => self.skipWaiting())
      .catch((err) => console.warn('[SW] Precache esuat partial:', err))
  );
});

// ============================================================
// ACTIVATE: stergere cache-uri vechi + claim clients
// ============================================================
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((k) => !k.startsWith(CACHE_VERSION))
        .map((k) => {
          console.log('[SW] Sterg cache vechi:', k);
          return caches.delete(k);
        })
    )).then(() => self.clients.claim())
  );
});

// ============================================================
// FETCH: strategie diferita per tip de request
// ============================================================
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Doar GET-uri pe origin-ul nostru (nu cache POST, nu cache cross-origin)
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;

  // SSE stream (Faza 7): NU cache, mereu live
  if (url.pathname.startsWith('/bim/api/events/stream')) {
    return;  // browser foloseste reteaua direct
  }

  // API JSON: network-only (datele trebuie sa fie fresh)
  if (url.pathname.startsWith('/bim/api/') || url.pathname.includes('/api/')) {
    event.respondWith(fetch(request).catch(() => new Response(
      JSON.stringify({error: 'offline'}), {
        status: 503, headers: {'Content-Type': 'application/json'}
      }
    )));
    return;
  }

  // Static assets (CSS, JS, img, fonts): stale-while-revalidate
  const isStatic = url.pathname.startsWith('/static/') ||
                   url.pathname === '/favicon.ico' ||
                   url.pathname === '/static/favicon.svg';
  if (isStatic) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Pagini HTML: network-first cu fallback la cache + offline page
  event.respondWith(networkFirstWithOfflineFallback(request));
});


// ============================================================
// STRATEGII
// ============================================================

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);

  const networkFetch = fetch(request).then((response) => {
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  }).catch(() => null);

  return cached || networkFetch || new Response('', { status: 503 });
}

async function networkFirstWithOfflineFallback(request) {
  try {
    const response = await fetch(request);
    // Cache successful navigation responses pentru reuse offline
    if (response && response.ok && request.mode === 'navigate') {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // Network failed - try cache
    const cache = await caches.open(RUNTIME_CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;

    // Pentru navigation requests, fallback la pagina offline
    if (request.mode === 'navigate') {
      const offlineCache = await caches.open(STATIC_CACHE);
      const offlinePage = await offlineCache.match(OFFLINE_URL);
      if (offlinePage) return offlinePage;
    }

    return new Response('Offline', { status: 503, statusText: 'Offline' });
  }
}


// ============================================================
// MESSAGE: receive messages from clients (ex: SKIP_WAITING)
// ============================================================
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
