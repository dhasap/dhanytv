/**
 * dhanytv stream-proxy — Cloudflare Worker (Fase 2, hardened)
 * ----------------------------------------------------------
 * Fungsi: inject header Referer/User-Agent/Origin (#EXTVLCOPT), tambah CORS,
 * proxy manifest (HLS .m3u8 / DASH .mpd) + segmen + lisensi DRM, dan rewrite
 * URL di dalam manifest agar ikut lewat proxy.
 *
 * 🔒 Keamanan (anti-abuse / anti-SSRF):
 *   1. CORS dibatasi ke ALLOWED_ORIGINS (var). Origin/Referer browser yang tidak
 *      cocok ditolak (mencegah situs lain "nebeng" proxy kamu).
 *   2. Proteksi SSRF: target wajib http(s) publik; localhost / IP privat /
 *      link-local / metadata endpoint (169.254.169.254, dll) diblokir.
 *   3. Rate limit per-IP (binding RL, opsional) → balas 429 bila kebanyakan.
 *   4. Hanya method GET/HEAD/OPTIONS. Batasi panjang URL & port aneh.
 *   5. Tidak meneruskan cookie / header sensitif; respons diberi header anti-sniff.
 *
 * Konfigurasi (wrangler.toml [vars]):
 *   ALLOWED_ORIGINS = "https://dhasap.github.io,https://dhanytv.pages.dev"
 *   (kosongkan untuk izinkan semua — TIDAK disarankan di produksi)
 *
 * Deploy:  cd web/proxy && npm i -g wrangler && wrangler deploy
 */

const MAX_URL = 2048;

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allow = parseAllowed(env && env.ALLOWED_ORIGINS);
    const cors = corsHeaders(origin, allow);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET' && request.method !== 'HEAD')
      return deny(405, 'method not allowed', cors);

    // 1) Batasi pemakaian ke origin yang diizinkan (anti nebeng dari situs lain).
    if (allow.length) {
      const ref = request.headers.get('Referer') || '';
      const okOrigin = origin && allow.includes(origin);
      const okRef = ref && allow.some((a) => ref.startsWith(a));
      // izinkan request tanpa Origin/Referer (mis. <video> langsung) hanya jika
      // bukan dari browser cross-site; tapi tolak Origin/Referer yang TIDAK cocok.
      if ((origin && !okOrigin) || (!origin && ref && !okRef)) return deny(403, 'origin not allowed', cors);
    }

    // 2) Rate limit per-IP (opsional, butuh binding RL di wrangler.toml).
    if (env && env.RL && typeof env.RL.limit === 'function') {
      const ip = request.headers.get('CF-Connecting-IP') || 'anon';
      try {
        const { success } = await env.RL.limit({ key: ip });
        if (!success) return deny(429, 'rate limit exceeded — coba lagi sebentar', cors);
      } catch { /* jika binding error, jangan blokir total */ }
    }

    const reqUrl = new URL(request.url);
    const target = reqUrl.searchParams.get('url');
    if (!target) return deny(400, 'missing ?url', cors);
    if (target.length > MAX_URL) return deny(414, 'url too long', cors);

    // 3) Proteksi SSRF.
    let tUrl;
    try { tUrl = new URL(target); } catch { return deny(400, 'invalid url', cors); }
    if (tUrl.protocol !== 'http:' && tUrl.protocol !== 'https:') return deny(400, 'scheme not allowed', cors);
    if (isBlockedHost(tUrl.hostname)) return deny(403, 'target host blocked', cors);
    if (tUrl.hostname === reqUrl.hostname) return deny(400, 'refusing to proxy self', cors);
    if (tUrl.port && !['', '80', '443', '8080', '8443'].includes(tUrl.port)) return deny(400, 'port not allowed', cors);

    // header kustom dari query (base64 JSON) — hanya header stream yang relevan.
    let extra = {};
    const h = reqUrl.searchParams.get('h');
    if (h) { try { extra = JSON.parse(atob(decodeURIComponent(h))); } catch {} }

    const fwd = new Headers();
    const ALLOWED_FWD = ['referer', 'user-agent', 'origin'];
    for (const [k, v] of Object.entries(extra)) {
      if (ALLOWED_FWD.includes(String(k).toLowerCase())) fwd.set(k, String(v).slice(0, 512));
    }
    const range = request.headers.get('Range');
    if (range) fwd.set('Range', range);
    if (!fwd.has('User-Agent')) fwd.set('User-Agent', 'Mozilla/5.0 (SmartTV) dhanytv-proxy');

    let upstream;
    try {
      upstream = await fetch(tUrl.toString(), { method: 'GET', headers: fwd, redirect: 'follow' });
    } catch (e) {
      return deny(502, 'upstream fetch failed', cors);
    }

    const ct = (upstream.headers.get('Content-Type') || '').toLowerCase();
    const isHls = /mpegurl|m3u8/.test(ct) || /\.m3u8(\?|$)/i.test(target);
    const isDash = /dash\+xml|\.mpd/.test(ct) || /\.mpd(\?|$)/i.test(target);

    const out = new Headers(cors);
    out.set('X-Content-Type-Options', 'nosniff');
    for (const k of ['Content-Type', 'Content-Length', 'Accept-Ranges', 'Content-Range', 'Cache-Control']) {
      const val = upstream.headers.get(k);
      if (val) out.set(k, val);
    }

    if (isHls || isDash) {
      const text = await upstream.text();
      const selfBase = `${reqUrl.origin}${reqUrl.pathname}`;
      const body = isHls ? rewriteHls(text, target, selfBase, h) : rewriteDash(text, target, selfBase, h);
      out.set('Content-Type', isHls ? 'application/vnd.apple.mpegurl' : 'application/dash+xml');
      out.delete('Content-Length');
      return new Response(body, { status: upstream.status, headers: out });
    }
    return new Response(upstream.body, { status: upstream.status, headers: out });
  },
};

/* ---------- keamanan ---------- */
function parseAllowed(v) {
  return (v || '').split(',').map((s) => s.trim().replace(/\/+$/, '')).filter(Boolean);
}
function corsHeaders(origin, allow) {
  const allowOrigin = !allow.length ? '*' : (allow.includes(origin) ? origin : allow[0]);
  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'GET,HEAD,OPTIONS',
    'Access-Control-Allow-Headers': 'Range,Content-Type',
    'Access-Control-Expose-Headers': 'Content-Length,Content-Range,Accept-Ranges',
    'Vary': 'Origin',
  };
}
function deny(status, msg, cors) {
  return new Response(msg, { status, headers: { ...cors, 'Content-Type': 'text/plain' } });
}
function isBlockedHost(hostname) {
  const h = (hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
  if (!h) return true;
  if (h === 'localhost' || h.endsWith('.local') || h.endsWith('.internal') || h.endsWith('.localhost')) return true;
  if (h === 'metadata.google.internal') return true;
  // IPv6 loopback / link-local / unique-local
  if (h === '::1' || h.startsWith('fe80:') || h.startsWith('fc') || h.startsWith('fd')) return true;
  // IPv4 literal?
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (m) {
    const a = +m[1], b = +m[2];
    if (a === 10 || a === 127 || a === 0) return true;                 // private / loopback / this
    if (a === 169 && b === 254) return true;                            // link-local + metadata
    if (a === 192 && b === 168) return true;                            // private
    if (a === 172 && b >= 16 && b <= 31) return true;                   // private
    if (a === 100 && b >= 64 && b <= 127) return true;                  // CGNAT
    if (a >= 224) return true;                                          // multicast / reserved
  }
  return false;
}

/* ---------- rewrite manifest ---------- */
function absolutize(ref, baseUrl) { try { return new URL(ref, baseUrl).toString(); } catch { return ref; } }
function wrap(absUrl, selfBase, h) { let u = `${selfBase}?url=${encodeURIComponent(absUrl)}`; if (h) u += `&h=${h}`; return u; }

function rewriteHls(text, manifestUrl, selfBase, h) {
  return text.split(/\r?\n/).map((line) => {
    const t = line.trim();
    if (!t) return line;
    if (t.startsWith('#')) return line.replace(/URI="([^"]+)"/g, (_m, uri) => `URI="${wrap(absolutize(uri, manifestUrl), selfBase, h)}"`);
    return wrap(absolutize(t, manifestUrl), selfBase, h);
  }).join('\n');
}
function rewriteDash(text, manifestUrl, selfBase, h) {
  text = text.replace(/<BaseURL>([^<]+)<\/BaseURL>/g, (_m, u) => `<BaseURL>${wrap(absolutize(u.trim(), manifestUrl), selfBase, h)}</BaseURL>`);
  text = text.replace(/(media|initialization|sourceURL)="((?:https?:)?\/\/[^"]+)"/g, (_m, attr, u) => `${attr}="${wrap(absolutize(u, manifestUrl), selfBase, h)}"`);
  return text;
}
