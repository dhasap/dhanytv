// m3u.js — parser M3U/M3U8 untuk dhanytv
// Mendukung #EXTINF (tvg-id, tvg-logo, group-title, nama),
// #EXTVLCOPT (http-referrer / http-user-agent / http-origin),
// dan #KODIPROP (inputstream.adaptive.license_type / license_key).

const ATTR_RE = /([a-zA-Z0-9_-]+)="([^"]*)"/g;

function parseAttrs(line) {
  const attrs = {};
  let m;
  while ((m = ATTR_RE.exec(line)) !== null) attrs[m[1]] = m[2];
  return attrs;
}

// Channel name = teks setelah koma terakhir di baris #EXTINF
function parseName(line) {
  const idx = line.indexOf(',');
  return idx === -1 ? '' : line.slice(idx + 1).trim();
}

function streamType(url) {
  const u = url.split('|')[0].split('?')[0].toLowerCase();
  if (u.endsWith('.mpd')) return 'dash';
  if (u.endsWith('.m3u8')) return 'hls';
  if (u.endsWith('.ts')) return 'ts';
  // default ke hls untuk endpoint live tanpa ekstensi
  return 'hls';
}

// Pisahkan sufiks pipe header: url|Referer=...&User-Agent=...
function splitPipeHeaders(rawUrl) {
  const parts = rawUrl.split('|');
  const url = parts[0];
  const headers = {};
  if (parts[1]) {
    parts[1].split('&').forEach((kv) => {
      const eq = kv.indexOf('=');
      if (eq > 0) headers[kv.slice(0, eq).trim()] = decodeURIComponent(kv.slice(eq + 1).trim());
    });
  }
  return { url, headers };
}

/**
 * Parse teks M3U menjadi array channel.
 * @param {string} text
 * @returns {Array<Channel>}
 */
export function parseM3U(text) {
  const lines = text.split(/\r?\n/);
  const channels = [];
  // Directive (#KODIPROP/#EXTVLCOPT) bisa muncul SEBELUM atau SESUDAH #EXTINF,
  // jadi kita akumulasi di `pending` sepanjang blok channel sampai ketemu URL.
  const newChan = () => ({ name: '', tvgId: '', logo: '', group: 'Lainnya', headers: {}, kodiprops: {}, url: '', type: 'hls', drm: null });
  let pending = newChan();

  for (let raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    if (line.startsWith('#EXTINF')) {
      const attrs = parseAttrs(line);
      pending.tvgId = attrs['tvg-id'] || '';
      pending.logo = attrs['tvg-logo'] || '';
      pending.group = attrs['group-title'] || 'Lainnya';
      pending.name = parseName(line) || attrs['tvg-name'] || pending.tvgId || 'Tanpa Nama';
      continue;
    }

    if (line.startsWith('#EXTVLCOPT')) {
      const v = line.slice('#EXTVLCOPT:'.length);
      const eq = v.indexOf('=');
      if (eq > 0) {
        const key = v.slice(0, eq).trim().toLowerCase();
        const val = v.slice(eq + 1).trim();
        if (key === 'http-referrer' || key === 'http-referer') pending.headers['Referer'] = val;
        else if (key === 'http-user-agent') pending.headers['User-Agent'] = val;
        else if (key === 'http-origin') pending.headers['Origin'] = val;
      }
      continue;
    }

    if (line.startsWith('#KODIPROP')) {
      const v = line.slice('#KODIPROP:'.length);
      const eq = v.indexOf('=');
      if (eq > 0) {
        const key = v.slice(0, eq).trim();
        const val = v.slice(eq + 1).trim();
        pending.kodiprops[key] = val;
        if (key === 'inputstream.adaptive.license_type') {
          pending.drm = pending.drm || {};
          // beberapa playlist menaruh semuanya di satu baris:
          // license_type=clearkey&license_key=KID:KEY&User-Agent=referrer=...
          const parts = val.split('&');
          pending.drm.type = parts[0].trim();
          for (let i = 1; i < parts.length; i++) {
            const seg = parts[i];
            const se = seg.indexOf('=');
            if (se < 0) continue;
            const k = seg.slice(0, se).trim().toLowerCase();
            const vv = seg.slice(se + 1).trim();
            if (k === 'license_key') pending.drm.key = vv;
            else if (k === 'user-agent') {
              if (/^referrer=/i.test(vv)) pending.headers['Referer'] = vv.replace(/^referrer=/i, '');
              else pending.headers['User-Agent'] = vv;
            }
          }
        }
        if (key === 'inputstream.adaptive.license_key' && !pending.drm?.key) {
          pending.drm = pending.drm || {};
          pending.drm.key = val; // JSON {"kid":"key"}, "kid:key", atau URL license server
        }
      }
      continue;
    }

    if (line.startsWith('#')) continue; // komentar/separator lain (dibiarkan, pending tetap)

    // baris non-# = URL stream -> tutup channel
    const { url, headers } = splitPipeHeaders(line);
    Object.assign(pending.headers, headers);
    pending.url = url;
    pending.type = streamType(url);
    if (pending.drm) pending.drm = normalizeDrm(pending.drm);
    pending.id = pending.tvgId || slug(pending.name) || `ch-${channels.length}`;
    channels.push(pending);
    pending = newChan();
  }

  return channels;
}

/**
 * Ubah {type, key} mentah menjadi konfigurasi DRM siap-pakai untuk Shaka.
 * @returns {{system:'clearkey'|'widevine', clearKeys?:Object, serverUrl?:string}|null}
 */
function normalizeDrm(drm) {
  const type = (drm.type || '').toLowerCase();
  const key = (drm.key || '').trim();
  // Widevine: license_key berupa URL license server
  if (type.includes('widevine') || /^https?:\/\//i.test(key)) {
    if (/^https?:\/\//i.test(key)) return { system: 'widevine', serverUrl: key };
    return { system: 'widevine', serverUrl: '' }; // butuh server (mungkin di header lain)
  }
  // ClearKey
  if (type.includes('clearkey')) {
    const clearKeys = parseClearKeys(key);
    if (clearKeys) return { system: 'clearkey', clearKeys };
  }
  // tipe lain tak dikenal -> tandai butuh DRM
  return { system: type || 'unknown' };
}

// Terima JSON {"kid":"key"} atau "kid:key" (hex), kembalikan map hex.
function parseClearKeys(raw) {
  if (!raw) return null;
  const s = raw.trim();
  if (s.startsWith('{')) {
    try {
      const obj = JSON.parse(s);
      const out = {};
      for (const k in obj) out[stripHex(k)] = stripHex(obj[k]);
      return Object.keys(out).length ? out : null;
    } catch { return null; }
  }
  if (s.includes(':')) {
    const [kid, key] = s.split(':');
    if (kid && key) return { [stripHex(kid)]: stripHex(key) };
  }
  return null;
}

function stripHex(s) { return String(s).trim().replace(/^0x/i, ''); }

function slug(s) {
  return (s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-');
}

/**
 * Ringkas daftar grup beserta jumlah channel-nya, terurut desc.
 */
export function groupSummary(channels) {
  const map = new Map();
  for (const c of channels) map.set(c.group, (map.get(c.group) || 0) + 1);
  return [...map.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

/**
 * @typedef {Object} Channel
 * @property {string} id
 * @property {string} name
 * @property {string} tvgId
 * @property {string} logo
 * @property {string} group
 * @property {string} url
 * @property {('hls'|'dash'|'ts')} type
 * @property {Object} headers   // Referer/User-Agent/Origin
 * @property {Object} kodiprops
 * @property {?{type:string,key:string}} drm
 */
