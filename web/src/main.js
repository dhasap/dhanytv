// main.js — dhanytv Web (aplikasi nonton TV profesional).
import { parseM3U, groupSummary } from './lib/m3u.js';
import { EpgStore, fmtTime } from './lib/epg.js';
import { Player } from './lib/player.js';
import { getProxyBase, setProxyBase } from './lib/proxy.js';

const REPO = 'https://raw.githubusercontent.com/dhasap/dhanytv/main';
const SOURCES = {
  ott:  { url: `${REPO}/dhanytv-ott.m3u`, label: 'OTT (kompatibel)' },
  full: { url: `${REPO}/dhanytv.m3u`,     label: 'Lengkap (DRM)' },
};
const EPG_URL = `${REPO}/epg.xml`;
const CACHE_TTL = 60 * 60 * 1000;
const PAGE = 120; // render bertahap

const state = {
  mode: 'ott',
  channels: [],
  byId: new Map(),
  groups: [],
  filterGroup: 'all',
  query: '',
  favorites: ls('dhany_favs', []),
  history: ls('dhany_history', []),
};
const epg = new EpgStore();
let player = null;
let searchTimer = null;
let deferredInstall = null;

/* ---------- util ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function ls(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
const isFav = (id) => state.favorites.includes(id);
function toggleFav(id) {
  const i = state.favorites.indexOf(id);
  if (i === -1) state.favorites.unshift(id); else state.favorites.splice(i, 1);
  save('dhany_favs', state.favorites);
}
function recordHistory(id) {
  state.history = [id, ...state.history.filter((x) => x !== id)].slice(0, 24);
  save('dhany_history', state.history);
}
function wireImgFallback(root) {
  $$('img[data-ini]', root || document).forEach((img) => {
    if (img._w) return; img._w = true;
    img.addEventListener('error', () => {
      const s = document.createElement('span'); s.className = 'ph'; s.textContent = img.dataset.ini || '?';
      img.replaceWith(s);
    }, { once: true });
  });
}

/* ---------- playlist ---------- */
async function fetchPlaylist(mode) {
  const key = `dhany_pl_${mode}`;
  try { const c = JSON.parse(localStorage.getItem(key) || 'null'); if (c && Date.now() - c.t < CACHE_TTL && c.text) return c.text; } catch {}
  const res = await fetch(SOURCES[mode].url, { cache: 'no-store' });
  if (!res.ok) throw new Error('Gagal memuat playlist (HTTP ' + res.status + ')');
  const text = await res.text();
  try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), text })); } catch {}
  return text;
}
function indexChannels() {
  state.byId = new Map(state.channels.map((c) => [c.id, c]));
  state.groups = groupSummary(state.channels);
}

/* ---------- boot ---------- */
async function boot() {
  initTheme(); bindHeader(); bindSettings(); registerSW(); bindInstall();
  $('#app').innerHTML = loader('Memuat daftar channel…');
  try {
    state.channels = parseM3U(await fetchPlaylist(state.mode));
    indexChannels();
  } catch (e) {
    $('#app').innerHTML = stateMsg('Gagal memuat', esc(e.message) + '. Coba muat ulang halaman.');
    return;
  }
  epg.onReady(refreshEpgOnScreen);
  epg.load(EPG_URL);
  setInterval(refreshEpgOnScreen, 60 * 1000);
  window.addEventListener('hashchange', route);
  route();
}

const loader = (t) => `<div class="loading-screen"><div class="spinner"></div><p>${esc(t)}</p></div>`;
const stateMsg = (h, p) => `<div class="empty"><h2>${esc(h)}</h2><p>${esc(p)}</p></div>`;

/* ---------- routing ---------- */
function route() {
  const h = location.hash.replace(/^#\/?/, '');
  if (h.startsWith('channel/')) renderPlayer(decodeURIComponent(h.slice(8)));
  else if (h === 'guide') renderGuide();
  else if (h === 'favorit') { state.filterGroup = '__fav'; renderHome(); }
  else renderHome();
  setActiveNav(h);
  window.scrollTo(0, 0);
}
function setActiveNav(h) {
  const tab = h.startsWith('channel/') ? '' : (h === 'guide' ? 'guide' : h === 'favorit' ? 'favorit' : '');
  $$('.nav-link').forEach((a) => a.classList.toggle('active', (a.dataset.nav || '') === tab));
}

/* ---------- filtering ---------- */
function visibleChannels() {
  const q = state.query.trim().toLowerCase();
  return state.channels.filter((c) => {
    if (state.filterGroup === '__fav') { if (!isFav(c.id)) return false; }
    else if (state.filterGroup !== 'all' && c.group !== state.filterGroup) return false;
    if (q && !`${c.name} ${c.group}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

/* ---------- home ---------- */
function renderHome() {
  const favCount = state.favorites.length;
  const showRows = state.filterGroup === 'all' && !state.query;
  const histChannels = state.history.map((id) => state.byId.get(id)).filter(Boolean).slice(0, 12);

  $('#app').innerHTML = `
    <div class="layout">
      <aside class="sidebar">
        <h3>Kategori</h3>
        <button class="cat-btn ${state.filterGroup === 'all' ? 'active' : ''}" data-group="all"><span>Semua channel</span><span class="count">${state.channels.length}</span></button>
        ${favCount ? `<button class="cat-btn ${state.filterGroup === '__fav' ? 'active' : ''}" data-group="__fav"><span>★ Favorit</span><span class="count">${favCount}</span></button>` : ''}
        ${state.groups.map((g) => `<button class="cat-btn ${state.filterGroup === g.name ? 'active' : ''}" data-group="${esc(g.name)}"><span>${esc(g.name)}</span><span class="count">${g.count}</span></button>`).join('')}
      </aside>
      <main class="main">
        <div class="chips mobile-only">
          <button class="chip ${state.filterGroup === 'all' ? 'active' : ''}" data-group="all">Semua</button>
          ${favCount ? `<button class="chip ${state.filterGroup === '__fav' ? 'active' : ''}" data-group="__fav">★ Favorit</button>` : ''}
          ${state.groups.slice(0, 24).map((g) => `<button class="chip ${state.filterGroup === g.name ? 'active' : ''}" data-group="${esc(g.name)}">${esc(g.name)}</button>`).join('')}
        </div>
        ${showRows && histChannels.length ? rowHTML('Lanjut nonton', histChannels) : ''}
        ${showRows ? `<div id="live-row-slot"></div>` : ''}
        <h2 class="page-title" id="ph-title"></h2>
        <p class="page-sub" id="ph-sub"></p>
        <div class="grid" id="grid"></div>
        <div id="grid-sentinel"></div>
        <div id="empty-slot"></div>
      </main>
    </div>`;

  $$('[data-group]').forEach((b) => b.addEventListener('click', () => { state.filterGroup = b.dataset.group; location.hash = ''; renderHome(); }));
  if (showRows) renderLiveRow();
  bindRowClicks();
  paintGrid();
}

function rowHTML(title, list) {
  return `<section class="hrow"><h2 class="row-title">${esc(title)}</h2>
    <div class="row-scroll">${list.map((c) => miniCard(c)).join('')}</div></section>`;
}
function miniCard(c) {
  const ini = esc((c.name || '?').slice(0, 2).toUpperCase());
  const logo = c.logo ? `<img loading="lazy" src="${esc(c.logo)}" alt="" data-ini="${ini}">` : `<span class="ph">${ini}</span>`;
  return `<button class="mini" data-id="${esc(c.id)}" title="${esc(c.name)}"><div class="mini-thumb">${logo}<span class="live-dot"></span></div><span class="mini-name">${esc(c.name)}</span></button>`;
}
function renderLiveRow() {
  const slot = $('#live-row-slot'); if (!slot) return;
  const paint = () => {
    if (!epg.ready) return;
    const live = [];
    for (const c of state.channels) {
      if (!c.tvgId) continue;
      const info = epg.lookup(c.tvgId);
      if (info && info.now && info.now.t) { live.push([c, info.now.t]); if (live.length >= 16) break; }
    }
    if (!live.length) return;
    slot.innerHTML = `<section class="hrow"><h2 class="row-title">Sedang tayang sekarang</h2>
      <div class="row-scroll">${live.map(([c, t]) => `<button class="mini" data-id="${esc(c.id)}" title="${esc(c.name)} — ${esc(t)}">
        <div class="mini-thumb">${c.logo ? `<img loading="lazy" src="${esc(c.logo)}" alt="" data-ini="${esc(c.name.slice(0,2).toUpperCase())}">` : `<span class="ph">${esc(c.name.slice(0,2).toUpperCase())}</span>`}<span class="live-dot"></span></div>
        <span class="mini-name">${esc(c.name)}</span><span class="mini-now">${esc(t)}</span></button>`).join('')}</div></section>`;
    bindRowClicks(); wireImgFallback(slot);
  };
  epg.onReady(paint); paint();
}
function bindRowClicks() {
  $$('.mini[data-id]').forEach((el) => el.addEventListener('click', () => { location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`; }));
  wireImgFallback(document);
}

/* ---------- grid (render bertahap + remote nav) ---------- */
let gridState = null;
function paintGrid() {
  const list = visibleChannels();
  const title = state.filterGroup === 'all' ? 'Semua Channel' : state.filterGroup === '__fav' ? 'Favorit' : state.filterGroup;
  $('#ph-title').textContent = state.query ? `Hasil "${state.query}"` : title;
  $('#ph-sub').textContent = `${list.length} channel · mode ${SOURCES[state.mode].label}`;
  const grid = $('#grid'), slot = $('#empty-slot');
  if (!list.length) { grid.innerHTML = ''; slot.innerHTML = stateMsg('Tidak ada channel', 'Coba kata kunci atau kategori lain.'); return; }
  slot.innerHTML = ''; grid.innerHTML = '';
  gridState = { list, n: 0 };
  appendChunk();
  setupGridObserver();
  setupRemoteNav(grid);
}
function appendChunk() {
  if (!gridState) return;
  const { list } = gridState;
  const next = list.slice(gridState.n, gridState.n + PAGE);
  if (!next.length) return;
  const html = next.map(cardHTML).join('');
  $('#grid').insertAdjacentHTML('beforeend', html);
  gridState.n += next.length;
  const grid = $('#grid');
  grid.querySelectorAll('.card:not([data-wired])').forEach((el) => {
    el.dataset.wired = '1';
    el.addEventListener('click', () => { location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`; });
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); } });
  });
  wireImgFallback(grid);
  refreshEpgOnScreen();
}
function setupGridObserver() {
  const sentinel = $('#grid-sentinel'); if (!sentinel) return;
  if (window._gridObs) window._gridObs.disconnect();
  window._gridObs = new IntersectionObserver((ents) => { if (ents.some((e) => e.isIntersecting)) appendChunk(); }, { rootMargin: '600px' });
  window._gridObs.observe(sentinel);
}
function cardHTML(c) {
  const ini = esc((c.name || '?').slice(0, 2).toUpperCase());
  const logo = c.logo ? `<img loading="lazy" src="${esc(c.logo)}" alt="${esc(c.name)}" data-ini="${ini}">` : `<span class="ph">${ini}</span>`;
  const drm = c.drm || c.type === 'dash';
  return `<div class="card" data-id="${esc(c.id)}" tabindex="0" role="button" aria-label="Tonton ${esc(c.name)}">
    <div class="badges"><span class="badge ${drm ? 'drm' : 'hls'}">${drm ? 'DRM' : 'HLS'}</span></div>
    <span class="badge live"><i></i>LIVE</span>
    <div class="thumb">${logo}</div>
    <div class="meta"><div class="name">${esc(c.name)}</div><div class="group">${esc(c.group)}</div>
      <div class="now" data-epg="${esc(c.tvgId)}"></div>
      <div class="progress" data-prog="${esc(c.tvgId)}" style="display:none"><i style="width:0"></i></div></div>
  </div>`;
}
// navigasi panah untuk remote/Smart TV
function setupRemoteNav(grid) {
  if (grid._nav) return; grid._nav = true;
  grid.addEventListener('keydown', (e) => {
    if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    const cards = $$('.card', grid); const cur = document.activeElement;
    const i = cards.indexOf(cur); if (i < 0) return;
    e.preventDefault();
    const cols = colsCount(cards);
    let t = i;
    if (e.key === 'ArrowRight') t = i + 1;
    else if (e.key === 'ArrowLeft') t = i - 1;
    else if (e.key === 'ArrowDown') t = i + cols;
    else if (e.key === 'ArrowUp') t = i - cols;
    if (cards[t]) { cards[t].focus(); cards[t].scrollIntoView({ block: 'nearest' }); if (t > gridState.n - 24) appendChunk(); }
  });
}
function colsCount(cards) {
  if (cards.length < 2) return 1;
  const top = cards[0].offsetTop; let n = 0;
  for (const c of cards) { if (c.offsetTop !== top) break; n++; }
  return Math.max(1, n);
}

/* ---------- guide / EPG ---------- */
function renderGuide() {
  $('#app').innerHTML = `<div class="main guide-view">
    <h1 class="page-title">Panduan Acara (EPG)</h1>
    <p class="page-sub" id="guide-sub">Memuat jadwal…</p>
    <div id="guide-list" class="guide-list"></div></div>`;
  const paint = () => {
    if (!epg.ready) { $('#guide-sub').textContent = 'EPG belum termuat — tunggu sebentar / muat ulang.'; return; }
    const q = state.query.trim().toLowerCase();
    const rows = state.channels.filter((c) => c.tvgId && epg.lookup(c.tvgId))
      .filter((c) => !q || `${c.name} ${c.group}`.toLowerCase().includes(q));
    $('#guide-sub').textContent = `${rows.length} channel dengan jadwal · zona Asia/Jakarta`;
    $('#guide-list').innerHTML = rows.slice(0, 400).map((c) => {
      const info = epg.lookup(c.tvgId); const ini = esc(c.name.slice(0, 2).toUpperCase());
      const logo = c.logo ? `<img loading="lazy" src="${esc(c.logo)}" data-ini="${ini}" alt="">` : `<span class="ph">${ini}</span>`;
      const now = info.now ? `<b>${esc(info.now.t)}</b> <span class="gt">${fmtTime(info.now.s)}–${fmtTime(info.now.e)}</span>` : '<span class="gt">Jadwal belum tersedia</span>';
      const nxt = info.next ? `<span class="gnext">Berikutnya: ${esc(info.next.t)} · ${fmtTime(info.next.s)}</span>` : '';
      const prog = info.now ? `<div class="progress" style="margin-top:8px"><i style="width:${(info.progress * 100).toFixed(1)}%"></i></div>` : '';
      return `<button class="guide-row" data-id="${esc(c.id)}">
        <span class="guide-logo">${logo}</span>
        <span class="guide-info"><span class="guide-name">${esc(c.name)}</span><span class="guide-prog">${now} ${nxt}</span>${prog}</span>
        <span class="guide-play">▶</span></button>`;
    }).join('') || stateMsg('Belum ada jadwal', 'EPG tidak menemukan acara untuk channel saat ini.');
    $$('.guide-row[data-id]').forEach((el) => el.addEventListener('click', () => { location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`; }));
    wireImgFallback($('#guide-list'));
  };
  epg.onReady(paint); paint();
}

/* ---------- EPG painting (kartu & player) ---------- */
function refreshEpgOnScreen() {
  if (!epg.ready) return;
  $$('.now[data-epg]').forEach((el) => {
    const id = el.dataset.epg; const info = id ? epg.lookup(id) : null;
    const prog = el.parentElement.querySelector('.progress');
    if (info && info.now) { el.innerHTML = `<b>${esc(info.now.t || 'Acara')}</b>`; if (prog) { prog.style.display = 'block'; prog.querySelector('i').style.width = (info.progress * 100).toFixed(1) + '%'; } }
    else if (info && info.next) { el.innerHTML = `Berikutnya: ${esc(info.next.t)} · ${fmtTime(info.next.s)}`; if (prog) prog.style.display = 'none'; }
    else { el.textContent = 'Jadwal belum tersedia'; if (prog) prog.style.display = 'none'; }
  });
  const pi = $('#player-epg');
  if (pi && pi.dataset.epg) {
    const info = epg.lookup(pi.dataset.epg);
    if (info && info.now) pi.innerHTML = `<span>Sekarang:</span> <b>${esc(info.now.t)}</b> · ${fmtTime(info.now.s)}–${fmtTime(info.now.e)}${info.next ? ` &nbsp;•&nbsp; Berikutnya: ${esc(info.next.t)}` : ''}`;
    else if (info && info.next) pi.innerHTML = `Berikutnya: <b>${esc(info.next.t)}</b> · ${fmtTime(info.next.s)}`;
    else pi.textContent = 'Jadwal acara belum tersedia.';
  }
}

/* ---------- player ---------- */
function renderPlayer(id) {
  const c = state.byId.get(id);
  if (!c) { location.hash = ''; return; }
  recordHistory(c.id);
  const related = state.channels.filter((x) => x.group === c.group && x.id !== c.id).slice(0, 18);

  $('#app').innerHTML = `<div class="main player-view">
    <button class="back-btn" id="back">← Kembali</button>
    <div class="player-grid">
      <div>
        <div class="video-shell" id="vshell">
          <video id="video" playsinline></video>
          <div class="video-overlay" id="overlay"><div><div class="spinner"></div><p id="ov-msg">Memuat stream…</p></div></div>
          <div class="player-bar" id="pbar">
            <button class="pb-btn" id="pb-play" title="Play/Pause (Space)">⏸</button>
            <button class="pb-btn" id="pb-mute" title="Mute (M)">🔊</button>
            <input type="range" id="pb-vol" min="0" max="1" step="0.05" value="1" class="pb-vol" title="Volume">
            <div class="pb-spacer"></div>
            <div class="pb-quality" id="pb-quality"></div>
            <button class="pb-btn" id="pb-full" title="Fullscreen (F)">⛶</button>
          </div>
        </div>
        <div class="player-info">
          <div class="pi-head"><h1>${esc(c.name)}</h1><span class="badge ${c.drm || c.type === 'dash' ? 'drm' : 'hls'}" style="position:static">${c.drm || c.type === 'dash' ? 'DRM' : 'HLS'}</span></div>
          <div class="epg-now" id="player-epg" data-epg="${esc(c.tvgId)}">…</div>
          <button class="fav-btn ${isFav(c.id) ? 'on' : ''}" id="fav">${isFav(c.id) ? '★ Tersimpan' : '☆ Favoritkan'}</button>
        </div>
      </div>
      <aside class="related">
        <h3>Channel terkait · ${esc(c.group)}</h3>
        ${related.length ? related.map(relItemHTML).join('') : '<p style="color:var(--text-muted);font-size:.85rem">Tidak ada channel lain di grup ini.</p>'}
      </aside>
    </div></div>`;

  $('#back').addEventListener('click', () => history.length > 1 ? history.back() : (location.hash = ''));
  $('#fav').addEventListener('click', (e) => { toggleFav(c.id); e.target.classList.toggle('on', isFav(c.id)); e.target.textContent = isFav(c.id) ? '★ Tersimpan' : '☆ Favoritkan'; });
  $$('.rel-item').forEach((el) => el.addEventListener('click', () => { location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`; }));
  wireImgFallback(document);

  const video = $('#video'), overlay = $('#overlay'), ovMsg = $('#ov-msg');
  player = new Player(video, {
    onState(st, msg) {
      const sp = overlay.querySelector('.spinner');
      if (st === 'playing') { overlay.classList.add('hidden'); buildQuality(); }
      else { overlay.classList.remove('hidden'); ovMsg.textContent = msg || (st === 'loading' ? 'Memuat stream…' : ''); }
      sp.style.display = st === 'error' ? 'none' : '';
    },
  });
  player.play(c);
  bindPlayerControls(video);
  refreshEpgOnScreen();
}
function relItemHTML(r) {
  const ini = esc((r.name || '?').slice(0, 2).toUpperCase());
  const img = r.logo ? `<img loading="lazy" src="${esc(r.logo)}" alt="" data-ini="${ini}">` : `<span class="ph">${ini}</span>`;
  return `<div class="rel-item" data-id="${esc(r.id)}">${img}<span class="rn">${esc(r.name)}</span></div>`;
}
function bindPlayerControls(video) {
  const play = $('#pb-play'), mute = $('#pb-mute'), vol = $('#pb-vol'), full = $('#pb-full'), shell = $('#vshell');
  const syncPlay = () => play.textContent = video.paused ? '▶' : '⏸';
  play.addEventListener('click', () => video.paused ? video.play() : video.pause());
  video.addEventListener('play', syncPlay); video.addEventListener('pause', syncPlay);
  mute.addEventListener('click', () => { video.muted = !video.muted; mute.textContent = video.muted ? '🔇' : '🔊'; });
  vol.addEventListener('input', () => { video.volume = +vol.value; video.muted = +vol.value === 0; mute.textContent = video.muted ? '🔇' : '🔊'; });
  full.addEventListener('click', () => { if (!document.fullscreenElement) shell.requestFullscreen?.(); else document.exitFullscreen?.(); });
  // tap video → toggle play + tampilkan bar (penting untuk layar sentuh)
  let hideT = null;
  const showBar = () => { shell.classList.add('show'); clearTimeout(hideT); hideT = setTimeout(() => shell.classList.remove('show'), 3000); };
  video.addEventListener('click', () => { video.paused ? video.play() : video.pause(); showBar(); });
  shell.addEventListener('pointermove', showBar);
  document.addEventListener('keydown', playerKeys);
}
function playerKeys(e) {
  const v = $('#video'); if (!v) { document.removeEventListener('keydown', playerKeys); return; }
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  if (e.key === ' ') { e.preventDefault(); v.paused ? v.play() : v.pause(); }
  else if (e.key.toLowerCase() === 'f') $('#pb-full')?.click();
  else if (e.key.toLowerCase() === 'm') $('#pb-mute')?.click();
  else if (e.key === 'ArrowUp') { e.preventDefault(); v.volume = Math.min(1, v.volume + 0.1); $('#pb-vol').value = v.volume; }
  else if (e.key === 'ArrowDown') { e.preventDefault(); v.volume = Math.max(0, v.volume - 0.1); $('#pb-vol').value = v.volume; }
}
function buildQuality() {
  const box = $('#pb-quality'); if (!box || !player || !player.levels || player.levels.length < 2) { if (box) box.innerHTML = ''; return; }
  const opts = [`<option value="-1">Auto</option>`].concat(player.levels.map((l) => `<option value="${l.i}">${esc(l.name)}</option>`));
  box.innerHTML = `<select id="q-sel" title="Kualitas">${opts.join('')}</select>`;
  $('#q-sel').addEventListener('change', (e) => player.setLevel(+e.target.value));
}

/* ---------- header / nav / theme / settings / PWA ---------- */
function bindHeader() {
  $('#search').addEventListener('input', (e) => {
    clearTimeout(searchTimer); const v = e.target.value;
    searchTimer = setTimeout(() => {
      state.query = v;
      const h = location.hash.replace(/^#\/?/, '');
      if (h === 'guide') renderGuide();
      else if (h.startsWith('channel/')) location.hash = '';
      else paintGrid();
    }, 220);
  });
  $('#theme').addEventListener('click', toggleTheme);
  $('#mode').addEventListener('change', async (e) => {
    state.mode = e.target.value;
    $('#app').innerHTML = loader('Mengganti mode…');
    try { state.channels = parseM3U(await fetchPlaylist(state.mode)); indexChannels(); state.filterGroup = 'all'; location.hash = ''; renderHome(); }
    catch (err) { $('#app').innerHTML = stateMsg('Gagal', esc(err.message)); }
  });
}
function bindSettings() {
  const bd = $('#modal-backdrop');
  const open = () => { $('#proxy-url').value = getProxyBase(); bd.hidden = false; };
  const close = () => { bd.hidden = true; };
  $('#settings').addEventListener('click', open);
  $('#modal-cancel').addEventListener('click', close);
  bd.addEventListener('click', (e) => { if (e.target === bd) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !bd.hidden) close(); });
  $('#proxy-save').addEventListener('click', () => { setProxyBase($('#proxy-url').value); close(); if (location.hash.startsWith('#/channel/')) route(); });
  $('#proxy-clear').addEventListener('click', () => { $('#proxy-url').value = ''; setProxyBase(''); });
}
function initTheme() {
  const saved = localStorage.getItem('dhany_theme');
  const dark = saved ? saved === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', dark);
}
function toggleTheme() {
  const dark = !document.documentElement.classList.contains('dark');
  document.documentElement.classList.toggle('dark', dark);
  localStorage.setItem('dhany_theme', dark ? 'dark' : 'light');
}
function registerSW() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
  }
}
function bindInstall() {
  const btn = $('#install');
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredInstall = e; if (btn) btn.hidden = false; });
  btn?.addEventListener('click', async () => { if (!deferredInstall) return; deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; btn.hidden = true; });
  window.addEventListener('appinstalled', () => { if (btn) btn.hidden = true; });
}

boot();
