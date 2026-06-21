// player.js — pemutar multi-format:
//   HLS (.m3u8) -> hls.js (fallback native Safari)
//   DASH (.mpd) + DRM (ClearKey / Widevine) -> Shaka Player (EME)
// Integrasi stream-proxy (Fase 2) untuk inject header + atasi CORS.

import { needsProxy, hasProxy, proxify, getProxyBase } from './proxy.js';

export class Player {
  constructor(videoEl, { onState } = {}) {
    this.video = videoEl;
    this.hls = null;
    this.shaka = null;
    this.onState = onState || (() => {});
    this.current = null;
    this.levels = [];
  }

  _set(state, msg) { this.onState(state, msg); }

  destroy() {
    if (this.hls) { try { this.hls.destroy(); } catch {} this.hls = null; }
    if (this.shaka) { try { this.shaka.destroy(); } catch {} this.shaka = null; }
    try { this.video.removeAttribute('src'); this.video.load(); } catch {}
  }

  async play(channel) {
    this.destroy();
    this.current = channel;
    this.levels = [];
    this._set('loading');

    const proxyReady = hasProxy();
    const useProxy = needsProxy(channel) && proxyReady;

    // Channel butuh header tapi belum ada proxy -> beri tahu jelas.
    if (needsProxy(channel) && !proxyReady) {
      this._set('error', 'Channel ini butuh header khusus (Referer/User-Agent) → aktifkan Stream Proxy di Pengaturan (⚙) untuk memutarnya. Bisa juga geo-locked di luar Indonesia.');
      return;
    }

    try {
      if (channel.type === 'dash' || channel.drm) {
        await this._playShaka(channel, useProxy);
      } else {
        await this._playHls(channel, useProxy);
      }
    } catch (e) {
      this._set('error', friendlyError(channel, 'fatal'));
    }
  }

  /* ---------------- HLS (hls.js) ---------------- */
  async _playHls(channel, useProxy) {
    const url = useProxy ? proxify(channel.url, channel.headers) : channel.url;
    const canNative = this.video.canPlayType('application/vnd.apple.mpegurl');

    if (canNative && !window.Hls) { this._attachNative(url); return; }

    if (window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        maxBufferLength: 30,
        manifestLoadingTimeOut: 14000,
        fragLoadingTimeOut: 22000,
        enableWorker: true,
      });
      this.hls = hls;
      hls.attachMedia(this.video);
      hls.on(window.Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(url));
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        this._set('playing');
        this.levels = (hls.levels || []).map((l, i) => ({ i, name: l.height ? l.height + 'p' : 'Auto' }));
        this.video.play().catch(() => {});
      });
      hls.on(window.Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        if (data.type === window.Hls.ErrorTypes.NETWORK_ERROR) { this._set('error', friendlyError(channel, 'jaringan')); try { hls.startLoad(); } catch {} }
        else if (data.type === window.Hls.ErrorTypes.MEDIA_ERROR) { try { hls.recoverMediaError(); } catch { this._set('error', 'Gagal memuat media.'); } }
        else this._set('error', friendlyError(channel, 'fatal'));
      });
      return;
    }
    if (canNative) { this._attachNative(url); return; }
    this._set('error', 'Format HLS tidak didukung browser ini.');
  }

  _attachNative(url) {
    this.video.src = url;
    this.video.addEventListener('loadedmetadata', () => { this._set('playing'); this.video.play().catch(() => {}); }, { once: true });
    this.video.addEventListener('error', () => this._set('error', friendlyError(this.current, 'native')), { once: true });
  }

  /* ---------------- DASH + DRM (Shaka) ---------------- */
  async _playShaka(channel, useProxy) {
    if (!window.shaka) { this._set('error', 'Pemutar DASH (Shaka) belum termuat. Muat ulang halaman.'); return; }
    if (!window.shaka.Player.isBrowserSupported()) { this._set('error', 'Browser ini tidak mendukung pemutaran DASH/DRM (EME). Coba Chrome/Edge di Android atau desktop.'); return; }

    window.shaka.polyfill.installAll();
    const player = new window.shaka.Player();
    this.shaka = player;
    await player.attach(this.video);

    // Konfigurasi DRM
    const drm = channel.drm;
    if (drm) {
      if (drm.system === 'clearkey' && drm.clearKeys) {
        player.configure({ drm: { clearKeys: drm.clearKeys } });
      } else if (drm.system === 'widevine' && drm.serverUrl) {
        player.configure({ drm: { servers: { 'com.widevine.alpha': useProxy ? proxify(drm.serverUrl, channel.headers) : drm.serverUrl } } });
      } else if (drm.system === 'unknown') {
        this._set('error', 'Channel ini memakai DRM yang belum didukung di browser.');
        return;
      }
    }

    // Rute semua request (manifest + segmen + lisensi) lewat proxy bila perlu header.
    if (useProxy) {
      const base = getProxyBase();
      const headers = channel.headers;
      player.getNetworkingEngine().registerRequestFilter((_type, request) => {
        request.uris = request.uris.map((u) => (u.startsWith(base) ? u : proxify(u, headers)));
      });
    }

    player.addEventListener('error', (ev) => {
      const code = ev && ev.detail ? ev.detail.code : '';
      this._set('error', friendlyError(channel, 'shaka') + (code ? ` (kode ${code})` : ''));
    });

    try {
      await player.load(channel.url);
      this._set('playing');
      this.video.play().catch(() => {});
    } catch (err) {
      const code = err && err.code ? ` (kode ${err.code})` : '';
      this._set('error', friendlyError(channel, 'shaka') + code);
    }
  }

  setLevel(i) { if (this.hls) this.hls.currentLevel = i; }
}

function friendlyError(channel, kind) {
  const hasHeaders = channel && channel.headers && Object.keys(channel.headers).length > 0;
  if (kind === 'shaka') {
    if (channel.drm && channel.drm.system === 'widevine') return 'Gagal memutar stream Widevine. Tidak didukung di iOS/Safari; di desktop/Android perlu CDM aktif & proxy header.';
    return 'Gagal memutar stream DASH/DRM. Mungkin lisensi/CORS/geo. Coba aktifkan proxy atau channel lain.';
  }
  if (hasHeaders) return 'Stream butuh header khusus — aktifkan Stream Proxy (⚙). Mungkin juga geo-locked di luar Indonesia.';
  if (kind === 'jaringan') return 'Gagal terhubung ke stream. Mungkin offline, CORS, atau geo-locked. Coba lagi / channel lain.';
  return 'Stream sedang tidak bisa diputar. Coba channel lain atau muat ulang.';
}
