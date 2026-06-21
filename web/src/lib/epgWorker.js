// epgWorker.js — parse EPG XMLTV (8 MB) di Web Worker agar UI tidak nge-freeze.
// Output: map channelId -> array program [{s,e,t}] (epoch ms + judul), terurut.
// Parsing pakai regex streaming (bukan DOMParser) supaya hemat memori & cepat.

self.onmessage = async (ev) => {
  const { url } = ev.data;
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const text = await res.text();
    const index = parseXMLTV(text);
    // serialize ringkas
    self.postMessage({ ok: true, index });
  } catch (err) {
    self.postMessage({ ok: false, error: String(err && err.message ? err.message : err) });
  }
};

// "20260620010000 +0700" -> epoch ms
function parseTime(s) {
  // YYYYMMDDHHMMSS +ZZZZ
  const m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\s*([+-]\d{4})?/.exec(s.trim());
  if (!m) return NaN;
  const [, Y, Mo, D, H, Mi, S, tz] = m;
  let iso = `${Y}-${Mo}-${D}T${H}:${Mi}:${S}`;
  if (tz) iso += tz.slice(0, 3) + ':' + tz.slice(3);
  else iso += '+07:00'; // default Asia/Jakarta
  return new Date(iso).getTime();
}

function decodeEntities(s) {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&');
}

const PROG_RE = /<programme\b([^>]*)>([\s\S]*?)<\/programme>/g;
const TITLE_RE = /<title[^>]*>([\s\S]*?)<\/title>/;
const START_RE = /start="([^"]*)"/;
const STOP_RE = /stop="([^"]*)"/;
const CH_RE = /channel="([^"]*)"/;

function parseXMLTV(text) {
  const index = {}; // channelId -> [{s,e,t}]
  let m;
  while ((m = PROG_RE.exec(text)) !== null) {
    const attrs = m[1];
    const body = m[2];
    const chm = CH_RE.exec(attrs);
    if (!chm) continue;
    const ch = chm[1];
    const sm = START_RE.exec(attrs);
    const em = STOP_RE.exec(attrs);
    const tm = TITLE_RE.exec(body);
    const s = sm ? parseTime(sm[1]) : NaN;
    const e = em ? parseTime(em[1]) : NaN;
    const t = tm ? decodeEntities(tm[1]).trim() : '';
    if (!ch || isNaN(s)) continue;
    (index[ch] || (index[ch] = [])).push({ s, e: isNaN(e) ? s : e, t });
  }
  // urutkan tiap channel by start
  for (const k in index) index[k].sort((a, b) => a.s - b.s);
  return index;
}
