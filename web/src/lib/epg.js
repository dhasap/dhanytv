// epg.js — antarmuka EPG di main thread: spawn worker, simpan index, hitung now/next.

export class EpgStore {
  constructor() {
    this.index = null;      // channelId -> [{s,e,t}]
    this.ready = false;
    this._listeners = [];
  }

  onReady(fn) { this._listeners.push(fn); if (this.ready) fn(); }

  load(url) {
    try {
      const worker = new Worker(new URL('./epgWorker.js', import.meta.url), { type: 'module' });
      worker.onmessage = (ev) => {
        if (ev.data.ok) {
          this.index = ev.data.index;
          this.ready = true;
          this._listeners.forEach((f) => f());
        } else {
          console.warn('EPG gagal dimuat:', ev.data.error);
        }
        worker.terminate();
      };
      worker.postMessage({ url });
    } catch (e) {
      console.warn('Worker tidak tersedia:', e);
    }
  }

  // Kembalikan {now, next, progress} untuk satu channelId.
  lookup(channelId, at = Date.now()) {
    if (!this.index || !channelId) return null;
    const list = this.index[channelId];
    if (!list || !list.length) return null;
    let now = null, next = null;
    for (let i = 0; i < list.length; i++) {
      const p = list[i];
      if (at >= p.s && at < p.e) {
        now = p;
        next = list[i + 1] || null;
        break;
      }
      if (p.s > at) { next = p; break; }
    }
    let progress = 0;
    if (now && now.e > now.s) progress = Math.min(1, Math.max(0, (at - now.s) / (now.e - now.s)));
    if (!now && !next) return null;
    return { now, next, progress };
  }
}

const jktTime = new Intl.DateTimeFormat('id-ID', {
  hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta',
});

export function fmtTime(ms) {
  if (!ms || isNaN(ms)) return '';
  try { return jktTime.format(new Date(ms)); } catch { return ''; }
}
