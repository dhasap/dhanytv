/* sw.js — service worker dhanytv Web (PWA: offline shell + cache).
   Strategi:
   - App shell (HTML/CSS/JS/ikon) → cache-first, di-precache saat install.
   - Library CDN (hls.js/Shaka) → stale-while-revalidate.
   - Playlist/EPG (raw.githubusercontent) → network-first (data harus fresh), fallback cache.
   - Stream (.ts/.m4s/.m3u8/.mpd) & proxy → JANGAN di-cache (live, besar).
*/
const VERSION = 'dhany-v1';
const SHELL = `${VERSION}-shell`;
const RUNTIME = `${VERSION}-rt`;

const SHELL_ASSETS = [
  './',
  './index.html',
  './src/styles.css',
  './src/main.js',
  './src/lib/m3u.js',
  './src/lib/epg.js',
  './src/lib/epgWorker.js',
  './src/lib/player.js',
  './src/lib/proxy.js',
  './manifest.webmanifest',
  './public/icon-192.png',
  './public/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    await c.addAll(SHELL_ASSETS.map((u) => new Request(u, { cache: 'reload' }))).catch(() => {});
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)));
    self.clients.claim();
  })());
});

function isStream(url) {
  return /\.(ts|m4s|mp4|aac|m3u8|mpd|key)(\?|$)/i.test(url) ||
    /workers\.dev|\/\?url=/.test(url); // proxy
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Jangan ganggu stream/proxy/license — biarkan langsung ke network.
  if (isStream(req.url)) return;

  // Data playlist/EPG → network-first.
  if (/raw\.githubusercontent\.com/.test(url.hostname)) {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const c = await caches.open(RUNTIME); c.put(req, fresh.clone()); return fresh;
      } catch { return (await caches.match(req)) || Response.error(); }
    })());
    return;
  }

  // CDN library → stale-while-revalidate.
  if (/cdn\.jsdelivr\.net/.test(url.hostname)) {
    e.respondWith((async () => {
      const cached = await caches.match(req);
      const net = fetch(req).then((r) => { caches.open(RUNTIME).then((c) => c.put(req, r.clone())); return r; }).catch(() => cached);
      return cached || net;
    })());
    return;
  }

  // Same-origin app shell → cache-first, fallback network, lalu index.html (SPA).
  if (url.origin === location.origin) {
    e.respondWith((async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        const fresh = await fetch(req);
        const c = await caches.open(SHELL); c.put(req, fresh.clone()); return fresh;
      } catch {
        return (await caches.match('./index.html')) || Response.error();
      }
    })());
  }
});
