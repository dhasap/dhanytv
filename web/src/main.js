// main.js — bootstrap aplikasi dhanytv Web (MVP / Fase 1).
import { parseM3U, groupSummary } from './lib/m3u.js';
import { EpgStore, fmtTime } from './lib/epg.js';
import { Player } from './lib/player.js';

const REPO = 'https://raw.githubusercontent.com/dhasap/dhanytv/main';
const SOURCES = {
  ott:  { url: `${REPO}/dhanytv-ott.m3u`, label: 'OTT (kompatibel)' },
  full: { url: `${REPO}/dhanytv.m3u`,     label: 'Lengkap (butuh DRM)' },
};
const EPG_URL = `${REPO}/epg.xml`;
const CACHE_TTL = 60 * 60 * 1000; // 1 jam

const state = {
  mode: 'ott',
  channels: [],
  groups: [],
  filterGroup: 'all',
  query: '',
  favorites: loadFavs(),
};
const epg = new EpgStore();
let player = null;
let searchTimer = null;

/* ---------- util ---------- */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function loadFavs() { try { return JSON.parse(localStorage.getItem('dhany_favs') || '[]'); } catch { return []; } }
function saveFavs() { localStorage.setItem('dhany_favs', JSON.stringify(state.favorites)); }
function isFav(id) { return state.favorites.includes(id); }
function toggleFav(id) {
  const i = state.favorites.indexOf(id);
  if (i === -1) state.favorites.push(id); else state.favorites.splice(i, 1);
  saveFavs();
}

/* ---------- caching playlist ---------- */
async function fetchPlaylist(mode) {
  const key = `dhany_pl_${mode}`;
  try {
    const c = JSON.parse(localStorage.getItem(key) || 'null');
    if (c && Date.now() - c.t < CACHE_TTL && c.text) return c.text;
  } catch {}
  const res = await fetch(SOURCES[mode].url, { cache: 'no-store' });
  if (!res.ok) throw new Error('Gagal memuat playlist (HTTP ' + res.status + ')');
  const text = await res.text();
  try { localStorage.setItem(key, JSON.stringify({ t: Date.now(), text })); } catch {}
  return text;
}

/* ---------- boot ---------- */
async function boot() {
  initTheme();
  bindHeader();
  $('#app').innerHTML = `<div class="loading-screen"><div class="spinner"></div><p>Memuat daftar channel…</p></div>`;
  try {
    const text = await fetchPlaylist(state.mode);
    state.channels = parseM3U(text);
    state.groups = groupSummary(state.channels);
  } catch (e) {
    $('#app').innerHTML = `<div class="empty"><h2>Gagal memuat</h2><p>${esc(e.message)}</p><p>Coba muat ulang halaman.</p></div>`;
    return;
  }
  epg.onReady(() => { refreshEpgOnScreen(); });
  epg.load(EPG_URL);
  setInterval(refreshEpgOnScreen, 60 * 1000); // update now/next tiap menit
  window.addEventListener('hashchange', route);
  route();
}

/* ---------- routing (hash) ---------- */
function route() {
  const h = location.hash.replace(/^#\/?/, '');
  if (h.startsWith('channel/')) {
    const id = decodeURIComponent(h.slice('channel/'.length));
    renderPlayer(id);
  } else {
    renderHome();
  }
  window.scrollTo(0, 0);
}

/* ---------- filtering ---------- */
function visibleChannels() {
  const q = state.query.trim().toLowerCase();
  return state.channels.filter((c) => {
    if (state.filterGroup === '__fav') { if (!isFav(c.id)) return false; }
    else if (state.filterGroup !== 'all' && c.group !== state.filterGroup) return false;
    if (q && !(`${c.name} ${c.group}`.toLowerCase().includes(q))) return false;
    return true;
  });
}

/* ---------- home view ---------- */
function renderHome() {
  const favCount = state.favorites.length;
  const sidebar = `
    <aside class="sidebar">
      <h3>Kategori</h3>
      <button class="cat-btn ${state.filterGroup === 'all' ? 'active' : ''}" data-group="all">
        <span>Semua channel</span><span class="count">${state.channels.length}</span></button>
      ${favCount ? `<button class="cat-btn ${state.filterGroup === '__fav' ? 'active' : ''}" data-group="__fav"><span>★ Favorit</span><span class="count">${favCount}</span></button>` : ''}
      ${state.groups.map((g) => `
        <button class="cat-btn ${state.filterGroup === g.name ? 'active' : ''}" data-group="${esc(g.name)}">
          <span>${esc(g.name)}</span><span class="count">${g.count}</span></button>`).join('')}
    </aside>`;

  const chips = `
    <div class="chips mobile-only">
      <button class="chip ${state.filterGroup === 'all' ? 'active' : ''}" data-group="all">Semua</button>
      ${favCount ? `<button class="chip ${state.filterGroup === '__fav' ? 'active' : ''}" data-group="__fav">★ Favorit</button>` : ''}
      ${state.groups.slice(0, 24).map((g) => `<button class="chip ${state.filterGroup === g.name ? 'active' : ''}" data-group="${esc(g.name)}">${esc(g.name)}</button>`).join('')}
    </div>`;

  $('#app').innerHTML = `
    <div class="layout">
      ${sidebar}
      <main class="main">
        ${chips}
        <h1 class="page-title" id="ph-title"></h1>
        <p class="page-sub" id="ph-sub"></p>
        <div class="grid" id="grid"></div>
        <div id="empty-slot"></div>
      </main>
    </div>`;

  document.querySelectorAll('[data-group]').forEach((b) => b.addEventListener('click', () => {
    state.filterGroup = b.dataset.group; renderHome();
  }));

  paintGrid();
}

function paintGrid() {
  const list = visibleChannels();
  const title = state.filterGroup === 'all' ? 'Semua Channel'
    : state.filterGroup === '__fav' ? 'Favorit' : state.filterGroup;
  $('#ph-title').textContent = state.query ? `Hasil pencarian "${state.query}"` : title;
  $('#ph-sub').textContent = `${list.length} channel · mode ${SOURCES[state.mode].label}`;
  const grid = $('#grid');
  const slot = $('#empty-slot');
  if (!list.length) {
    grid.innerHTML = '';
    slot.innerHTML = `<div class="empty"><h2>Tidak ada channel</h2><p>Coba kata kunci atau kategori lain.</p></div>`;
    return;
  }
  slot.innerHTML = '';
  grid.innerHTML = list.map(cardHTML).join('');
  grid.querySelectorAll('.card').forEach((el) => {
    el.addEventListener('click', () => { location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`; });
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); el.click(); } });
  });
  refreshEpgOnScreen();
}

function cardHTML(c) {
  const initials = esc((c.name || '?').slice(0, 2).toUpperCase());
  const logo = c.logo ? `<img loading="lazy" src="${esc(c.logo)}" alt="${esc(c.name)}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'${initials}'}))">` : `<span class="ph">${initials}</span>`;
  const drm = c.drm || c.type === 'dash';
  return `
    <div class="card" data-id="${esc(c.id)}" tabindex="0" role="button" aria-label="Tonton ${esc(c.name)}">
      <div class="badges">
        <span class="badge ${drm ? 'drm' : 'hls'}">${drm ? 'DRM' : 'HLS'}</span>
      </div>
      <span class="badge live"><i></i>LIVE</span>
      <div class="thumb">${logo}</div>
      <div class="meta">
        <div class="name">${esc(c.name)}</div>
        <div class="group">${esc(c.group)}</div>
        <div class="now" data-epg="${esc(c.tvgId)}"></div>
        <div class="progress" data-prog="${esc(c.tvgId)}" style="display:none"><i style="width:0"></i></div>
      </div>
    </div>`;
}

/* ---------- EPG painting ---------- */
function refreshEpgOnScreen() {
  if (!epg.ready) return;
  document.querySelectorAll('.now[data-epg]').forEach((el) => {
    const id = el.dataset.epg;
    const info = id ? epg.lookup(id) : null;
    const prog = el.parentElement.querySelector('.progress');
    if (info && info.now) {
      el.innerHTML = `<b>${esc(info.now.t || 'Acara')}</b>`;
      if (prog) { prog.style.display = 'block'; prog.querySelector('i').style.width = (info.progress * 100).toFixed(1) + '%'; }
    } else if (info && info.next) {
      el.innerHTML = `Berikutnya: ${esc(info.next.t)} · ${fmtTime(info.next.s)}`;
      if (prog) prog.style.display = 'none';
    } else {
      el.textContent = 'Jadwal belum tersedia';
      if (prog) prog.style.display = 'none';
    }
  });
  // overlay player
  const pi = $('#player-epg');
  if (pi && pi.dataset.epg) {
    const info = epg.lookup(pi.dataset.epg);
    if (info && info.now) pi.innerHTML = `<span>Sekarang:</span> <b>${esc(info.now.t)}</b> · ${fmtTime(info.now.s)}–${fmtTime(info.now.e)}${info.next ? ` &nbsp;•&nbsp; Berikutnya: ${esc(info.next.t)}` : ''}`;
    else if (info && info.next) pi.innerHTML = `Berikutnya: <b>${esc(info.next.t)}</b> · ${fmtTime(info.next.s)}`;
    else pi.textContent = 'Jadwal acara belum tersedia.';
  }
}

/* ---------- player view ---------- */
function renderPlayer(id) {
  const c = state.channels.find((x) => x.id === id);
  if (!c) { location.hash = ''; return; }
  const related = state.channels.filter((x) => x.group === c.group && x.id !== c.id).slice(0, 16);

  $('#app').innerHTML = `
    <div class="main player-view">
      <button class="back-btn" id="back">← Kembali</button>
      <div class="player-grid">
        <div>
          <div class="video-shell">
            <video id="video" playsinline controls></video>
            <div class="video-overlay" id="overlay"><div><div class="spinner"></div><p id="ov-msg" style="margin-top:14px">Memuat stream…</p></div></div>
          </div>
          <div class="player-info">
            <h1>${esc(c.name)}</h1>
            <div class="epg-now" id="player-epg" data-epg="${esc(c.tvgId)}">…</div>
            <button class="fav-btn ${isFav(c.id) ? 'on' : ''}" id="fav">${isFav(c.id) ? '★ Tersimpan' : '☆ Favoritkan'}</button>
          </div>
        </div>
        <aside class="related">
          <h3>Channel terkait · ${esc(c.group)}</h3>
          ${related.length ? related.map((r) => relItemHTML(r)).join('') : '<p style="color:var(--text-muted);font-size:.85rem">Tidak ada channel lain di grup ini.</p>'}
        </aside>
      </div>
    </div>`;

  $('#back').addEventListener('click', () => { location.hash = ''; });
  $('#fav').addEventListener('click', (e) => {
    toggleFav(c.id);
    e.target.classList.toggle('on', isFav(c.id));
    e.target.textContent = isFav(c.id) ? '★ Tersimpan' : '☆ Favoritkan';
  });
  document.querySelectorAll('.rel-item').forEach((el) => el.addEventListener('click', () => {
    location.hash = `#/channel/${encodeURIComponent(el.dataset.id)}`;
  }));

  const overlay = $('#overlay'); const ovMsg = $('#ov-msg');
  player = new Player($('#video'), {
    onState(stateName, msg) {
      if (stateName === 'playing') { overlay.classList.add('hidden'); }
      else { overlay.classList.remove('hidden'); ovMsg.textContent = msg || (stateName === 'loading' ? 'Memuat stream…' : ''); }
      if (stateName === 'error') { overlay.querySelector('.spinner').style.display = 'none'; }
      else { overlay.querySelector('.spinner').style.display = ''; }
    },
  });
  player.play(c);
  refreshEpgOnScreen();
}

function relItemHTML(r) {
  const ini = esc((r.name || '?').slice(0, 2).toUpperCase());
  const img = r.logo ? `<img loading="lazy" src="${esc(r.logo)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'${ini}'}))">` : `<span class="ph">${ini}</span>`;
  return `<div class="rel-item" data-id="${esc(r.id)}">${img}<span class="rn">${esc(r.name)}</span></div>`;
}

/* ---------- header & theme ---------- */
function bindHeader() {
  const input = $('#search');
  input.addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => {
      state.query = v;
      if (!location.hash || location.hash === '#/' || location.hash === '#') paintGrid();
      else { location.hash = ''; }
    }, 220);
  });
  $('#theme').addEventListener('click', toggleTheme);
  $('#mode').addEventListener('change', async (e) => {
    state.mode = e.target.value;
    $('#app').innerHTML = `<div class="loading-screen"><div class="spinner"></div><p>Mengganti mode…</p></div>`;
    try {
      const text = await fetchPlaylist(state.mode);
      state.channels = parseM3U(text);
      state.groups = groupSummary(state.channels);
      state.filterGroup = 'all';
      location.hash = '';
      renderHome();
    } catch (err) { $('#app').innerHTML = `<div class="empty"><p>${esc(err.message)}</p></div>`; }
  });
  $('.brand').addEventListener('click', () => { location.hash = ''; });
}

function initTheme() {
  const saved = localStorage.getItem('dhany_theme');
  const dark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', dark);
}
function toggleTheme() {
  const dark = !document.documentElement.classList.contains('dark');
  document.documentElement.classList.toggle('dark', dark);
  localStorage.setItem('dhany_theme', dark ? 'dark' : 'light');
}

boot();
