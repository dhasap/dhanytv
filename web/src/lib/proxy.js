// proxy.js — helper untuk merutekan stream lewat stream-proxy (Fase 2).
// Proxy dibutuhkan saat channel butuh header Referer/User-Agent/Origin (forbidden
// headers di browser) atau saat origin CDN tidak mengizinkan CORS.
//
// Konfigurasi proxy disimpan di localStorage ('dhany_proxy'). Worker contoh ada di
// web/proxy/worker.js (Cloudflare Worker).

const LS_KEY = 'dhany_proxy';

export function getProxyBase() {
  try { return (localStorage.getItem(LS_KEY) || '').trim().replace(/\/+$/, ''); } catch { return ''; }
}
export function setProxyBase(url) {
  try { localStorage.setItem(LS_KEY, (url || '').trim()); } catch {}
}
export function hasProxy() { return !!getProxyBase(); }

// Channel butuh proxy bila punya header khusus.
export function needsProxy(channel) {
  return channel && channel.headers && Object.keys(channel.headers).length > 0;
}

/**
 * Bungkus URL stream agar lewat proxy, menyertakan header sebagai query.
 * Bentuk: <PROXY>/?url=<enc>&h=<base64(JSON headers)>
 */
export function proxify(url, headers) {
  const base = getProxyBase();
  if (!base) return url;
  let q = `${base}/?url=${encodeURIComponent(url)}`;
  if (headers && Object.keys(headers).length) {
    const enc = b64(JSON.stringify(headers));
    q += `&h=${encodeURIComponent(enc)}`;
  }
  return q;
}

function b64(s) {
  try { return btoa(unescape(encodeURIComponent(s))); } catch { return btoa(s); }
}
