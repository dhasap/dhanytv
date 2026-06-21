// player.js — pembungkus pemutar HLS (hls.js) dengan fallback native (Safari).
// Fase 2: DASH + DRM (Shaka) & proxy header akan ditambahkan di sini.

export class Player {
  constructor(videoEl, { onState } = {}) {
    this.video = videoEl;
    this.hls = null;
    this.onState = onState || (() => {});
    this.current = null;
  }

  _set(state, msg) { this.onState(state, msg); }

  destroy() {
    if (this.hls) { try { this.hls.destroy(); } catch {} this.hls = null; }
    try { this.video.removeAttribute('src'); this.video.load(); } catch {}
  }

  async play(channel) {
    this.destroy();
    this.current = channel;
    this._set('loading');

    if (channel.type === 'dash' || channel.drm) {
      // OTT MVP belum dukung DASH/DRM (lihat Fase 2)
      this._set('error', 'Channel ini butuh player DRM/DASH (mode Lengkap belum aktif). Coba channel HLS.');
      return;
    }

    const url = channel.url;
    const isHls = channel.type === 'hls';
    const canNative = this.video.canPlayType('application/vnd.apple.mpegurl');

    // Safari/iOS: HLS native
    if (isHls && canNative && !window.Hls) {
      this._attachNative(url);
      return;
    }

    if (isHls && window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        maxBufferLength: 30,
        manifestLoadingTimeOut: 12000,
        fragLoadingTimeOut: 20000,
        enableWorker: true,
      });
      this.hls = hls;
      hls.attachMedia(this.video);
      hls.on(window.Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(url));
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        this._set('playing');
        this._exposeLevels(hls.levels);
        this.video.play().catch(() => {});
      });
      hls.on(window.Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) {
          this._set('error', friendlyError(channel, 'jaringan'));
          // coba recover sekali
          try { hls.startLoad(); } catch {}
        } else if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) {
          try { hls.recoverMediaError(); } catch { this._set('error', 'Gagal memuat media.'); }
        } else {
          this._set('error', friendlyError(channel, 'fatal'));
        }
      });
      return;
    }

    if (isHls && canNative) { this._attachNative(url); return; }

    this._set('error', 'Format stream tidak didukung browser ini.');
  }

  _attachNative(url) {
    this.video.src = url;
    this.video.addEventListener('loadedmetadata', () => {
      this._set('playing');
      this.video.play().catch(() => {});
    }, { once: true });
    this.video.addEventListener('error', () => {
      this._set('error', friendlyError(this.current, 'native'));
    }, { once: true });
  }

  _exposeLevels(levels) {
    this.levels = (levels || []).map((l, i) => ({ i, height: l.height, name: l.height ? l.height + 'p' : 'Auto' }));
  }

  setLevel(i) { if (this.hls) this.hls.currentLevel = i; }
}

function friendlyError(channel, kind) {
  const hasHeaders = channel && channel.headers && Object.keys(channel.headers).length > 0;
  if (hasHeaders) return 'Stream ini butuh header khusus (Referer/User-Agent) — perlu proxy (Fase 2). Mungkin juga geo-locked di luar Indonesia.';
  if (kind === 'jaringan') return 'Gagal terhubung ke stream. Mungkin offline, CORS, atau geo-locked. Coba lagi atau pilih channel lain.';
  return 'Stream sedang tidak bisa diputar. Coba channel lain atau muat ulang.';
}
