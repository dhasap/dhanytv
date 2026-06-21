/**
 * dhanytv stream-proxy — Cloudflare Worker (Fase 2)
 * ---------------------------------------------------
 * Tujuan:
 *  1. Inject header Referer / User-Agent / Origin yang tidak bisa di-set browser
 *     (forbidden headers) sesuai #EXTVLCOPT.
 *  2. Menambahkan header CORS supaya browser bisa fetch manifest + segmen.
 *  3. Mem-proxy manifest (HLS .m3u8 / DASH .mpd) + segmen (.ts/.m4s) + lisensi DRM.
 *  4. Menulis ulang URL di dalam manifest agar ikut lewat proxy (header tetap terbawa).
 *
 * Pemakaian dari front-end (lihat web/src/lib/proxy.js):
 *   <WORKER_URL>/?url=<encodeURIComponent(streamUrl)>&h=<base64(JSON headers)>
 *
 * Deploy:
 *   npm i -g wrangler
 *   wrangler deploy   (file ini sebagai entry; set route/worker.dev)
 * Lalu tempel URL worker di Pengaturan (⚙) situs.
 *
 * ⚠️ Catatan: aktifkan rate-limit/cache & batasi origin bila dipublikasikan,
 *   karena proxy terbuka rawan disalahgunakan (lihat PRD §14).
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,HEAD,POST,OPTIONS',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Expose-Headers': '*',
};

export default {
  async fetch(request) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

    const reqUrl = new URL(request.url);
    const target = reqUrl.searchParams.get('url');
    if (!target) return new Response('missing ?url', { status: 400, headers: CORS });

    // header kustom dari query (base64 JSON)
    let extra = {};
    const h = reqUrl.searchParams.get('h');
    if (h) { try { extra = JSON.parse(atob(decodeURIComponent(h))); } catch {} }

    const fwd = new Headers();
    for (const [k, v] of Object.entries(extra)) fwd.set(k, v);
    // teruskan Range untuk seeking segmen
    const range = request.headers.get('Range');
    if (range) fwd.set('Range', range);
    if (!fwd.has('User-Agent')) fwd.set('User-Agent', 'Mozilla/5.0 (SmartTV) dhanytv-proxy');

    let upstream;
    try {
      upstream = await fetch(target, { method: 'GET', headers: fwd, redirect: 'follow' });
    } catch (e) {
      return new Response('upstream fetch failed: ' + e, { status: 502, headers: CORS });
    }

    const ct = (upstream.headers.get('Content-Type') || '').toLowerCase();
    const isHls = /mpegurl|m3u8/.test(ct) || /\.m3u8(\?|$)/i.test(target);
    const isDash = /dash\+xml|\.mpd/.test(ct) || /\.mpd(\?|$)/i.test(target);

    const outHeaders = new Headers(CORS);
    for (const k of ['Content-Type', 'Content-Length', 'Accept-Ranges', 'Content-Range', 'Cache-Control']) {
      const val = upstream.headers.get(k);
      if (val) outHeaders.set(k, val);
    }

    // Manifest -> rewrite URL bagian dalam agar ikut lewat proxy.
    if (isHls || isDash) {
      const text = await upstream.text();
      const selfBase = `${reqUrl.origin}${reqUrl.pathname}`;
      const rewritten = isHls
        ? rewriteHls(text, target, selfBase, h)
        : rewriteDash(text, target, selfBase, h);
      outHeaders.set('Content-Type', isHls ? 'application/vnd.apple.mpegurl' : 'application/dash+xml');
      outHeaders.delete('Content-Length');
      return new Response(rewritten, { status: upstream.status, headers: outHeaders });
    }

    // Segmen / lisensi / lainnya -> stream langsung.
    return new Response(upstream.body, { status: upstream.status, headers: outHeaders });
  },
};

function absolutize(ref, baseUrl) {
  try { return new URL(ref, baseUrl).toString(); } catch { return ref; }
}
function wrap(absUrl, selfBase, h) {
  let u = `${selfBase}?url=${encodeURIComponent(absUrl)}`;
  if (h) u += `&h=${h}`;
  return u;
}

// HLS: baris non-komentar = URI; juga atribut URI="..." (KEY, MAP, MEDIA).
function rewriteHls(text, manifestUrl, selfBase, h) {
  return text.split(/\r?\n/).map((line) => {
    const t = line.trim();
    if (!t) return line;
    if (t.startsWith('#')) {
      return line.replace(/URI="([^"]+)"/g, (_m, uri) => `URI="${wrap(absolutize(uri, manifestUrl), selfBase, h)}"`);
    }
    return wrap(absolutize(t, manifestUrl), selfBase, h);
  }).join('\n');
}

// DASH: rewrite atribut yang berisi URL (BaseURL, media, initialization, sourceURL).
function rewriteDash(text, manifestUrl, selfBase, h) {
  // BaseURL element
  text = text.replace(/<BaseURL>([^<]+)<\/BaseURL>/g, (_m, u) =>
    `<BaseURL>${wrap(absolutize(u.trim(), manifestUrl), selfBase, h)}</BaseURL>`);
  // atribut media/initialization/sourceURL yang absolut (http...)
  text = text.replace(/(media|initialization|sourceURL)="((?:https?:)?\/\/[^"]+)"/g,
    (_m, attr, u) => `${attr}="${wrap(absolutize(u, manifestUrl), selfBase, h)}"`);
  return text;
}
