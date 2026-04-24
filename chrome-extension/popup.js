// PyFlow Popup v3.0 — Universal Video Downloader
// Connects Chrome extension to local yt-dlp Python server
'use strict';

/* ════════════════════════════════════════════════════════════════════
   CONSTANTS
   ════════════════════════════════════════════════════════════════════ */
const SERVER = 'http://localhost:8000';
const HEALTH = `${SERVER}/health`;
const DOWNLOAD = `${SERVER}/add-download`;

// Video quality options  [display label, server value, sub-label]
const VQ = [
  ['Best', 'best', 'Auto'],
  ['4K', '2160p', '2160p'],
  ['2K', '1440p', '1440p'],
  ['1080p', '1080p', 'Full HD'],
  ['720p', '720p', 'HD'],
  ['480p', '480p', 'SD'],
  ['360p', '360p', 'Low'],
  ['240p', '240p', 'Min'],
  ['F-Phone', 'F-video', 'Feature Phone'],
];

// Audio quality options
const AQ = [
  ['Best', 'best', 'Auto'],
  ['320k', '320', 'Lossless'],
  ['256k', '256', 'Hi-Fi'],
  ['192k', '192', 'Standard'],
  ['128k', '128', 'Economy'],
];

// Video format options  [display, server value, sub]
const VF = [
  ['MP4', 'mp4', 'H.264'],
  ['MKV', 'mkv', 'Matroska'],
  ['WebM', 'webm', 'VP9'],
  ['MOV', 'mov', 'QuickTime'],
  ['AVI', 'avi', 'Legacy'],
];

// Audio format options
const AF = [
  ['MP3', 'mp3', 'Universal'],
  ['M4A', 'm4a', 'Apple AAC'],
  ['FLAC', 'flac', 'Lossless'],
  ['OPUS', 'opus', 'Best ratio'],
  ['WAV', 'wav', 'Uncompressed'],
  ['AAC', 'aac', 'AAC raw'],
];

/* ════════════════════════════════════════════════════════════════════
   STATE
   ════════════════════════════════════════════════════════════════════ */
const S = {
  online: false,
  type: 'video', // "video" | "audio"
  qualityIdx: 3, // default 1080p
  formatIdx: 0, // default MP4
  qList: VQ,
  fList: VF,
  playlist: 'single', // "single" | "playlist"
  url: '',
  title: '',
  isYT: false,
  isPlaylist: false,
  busy: false,
  manualInput: false,
};

/* ════════════════════════════════════════════════════════════════════
   DOM HELPERS
   ════════════════════════════════════════════════════════════════════ */
const $ = id => document.getElementById(id);
const el = {
  scDot: () => $('scDot'),
  scTxt: () => $('scTxt'),
  errStrip: () => $('errStrip'),
  errTxt: () => $('errTxt'),
  errX: () => $('errX'),
  mediaCard: () => $('mediaCard'),
  mcThumb: () => $('mcThumb'),
  mcTitle: () => $('mcTitle'),
  mcHost: () => $('mcHost'),
  mcBadge: () => $('mcBadge'),
  urlIn: () => $('urlIn'),
  pasteBtn: () => $('pasteBtn'),
  clearBtn: () => $('clearBtn'),
  plBlock: () => $('plBlock'),
  plSeg: () => $('plSeg'),
  qPrev: () => $('qPrev'),
  qNext: () => $('qNext'),
  qVal: () => $('qVal'),
  qSub: () => $('qSub'),
  fPrev: () => $('fPrev'),
  fNext: () => $('fNext'),
  fVal: () => $('fVal'),
  fSub: () => $('fSub'),
  dlBtn: () => $('dlBtn'),
  dlContent: () => $('dlContent'),
  fsYtdlp: () => $('fsYtdlp'),
  fsQueue: () => $('fsQueue'),
  fsActive: () => $('fsActive'),
  fsDot: () => $('fsDot'),
  toast: () => $('toast'),
  toastIco: () => $('toastIco'),
  toastMsg: () => $('toastMsg'),
  reviewBtn: () => $('reviewBtn'),
};

/* ════════════════════════════════════════════════════════════════════
   BOOT
   ════════════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  initCanvas();
  loadPrefs();
  wireEvents();
  renderDials();

  // Kick off async tasks in parallel
  Promise.all([pingServer(), detectPage()]);

  // Refresh server stats every 8 seconds
  setInterval(pingServer, 8000);
});

/* ════════════════════════════════════════════════════════════════════
   BACKGROUND CANVAS — Neural Network Particles
   ════════════════════════════════════════════════════════════════════ */
function initCanvas() {
  const canvas = $('bgCanvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 370;
  canvas.height = 480;

  // Nodes
  const N = 28;
  const nodes = Array.from({ length: N }, () => ({
    x: Math.random() * canvas.width,
    y: Math.random() * canvas.height,
    vx: (Math.random() - 0.5) * 0.35,
    vy: (Math.random() - 0.5) * 0.35,
    r: Math.random() * 1.8 + 0.6,
    a: Math.random() * Math.PI * 2,
  }));

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Update positions
    for (const n of nodes) {
      n.x += n.vx;
      n.y += n.vy;
      if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
      if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
    }

    // Draw edges
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 90) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(0,255,180,${(1 - d / 90) * 0.18})`;
          ctx.lineWidth = 0.6;
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw nodes
    for (const n of nodes) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,255,180,0.45)';
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  draw();
}

/* ════════════════════════════════════════════════════════════════════
   SERVER HEALTH
   ════════════════════════════════════════════════════════════════════ */
async function pingServer() {
  el.scDot().className = 'sc-dot checking';
  el.scTxt().textContent = 'PINGING';

  try {
    const res = await fetch(HEALTH, { signal: AbortSignal.timeout(3000) });
    const data = await res.json();

    S.online = res.ok;

    if (res.ok) {
      el.scDot().className = 'sc-dot online';
      el.scTxt().textContent = 'ONLINE';
      el.fsYtdlp().textContent = `yt-dlp ${data.ytdlp_version || '?'}`;
      el.fsQueue().textContent = data.queue_size ?? '0';
      el.fsActive().textContent = data.active_downloads ?? '0';
      el.fsDot().style.background = 'var(--bio)';
    } else {
      throw new Error('non-ok');
    }
  } catch {
    S.online = false;
    el.scDot().className = 'sc-dot offline';
    el.scTxt().textContent = 'OFFLINE';
    el.fsDot().style.background = 'var(--danger)';
    showErr('Server offline — run: pyflow');
  }
}

/* ════════════════════════════════════════════════════════════════════
   PAGE DETECTION
   ════════════════════════════════════════════════════════════════════ */
async function detectPage() {
  try {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (!tab?.url) return;

    const url = tab.url;

    // Skip non-web pages
    if (
      url.startsWith('chrome://') ||
      url.startsWith('about:') ||
      url.startsWith('chrome-extension://') ||
      url.startsWith('moz-extension://')
    ) {
      showErr('Navigate to a video page to detect media.');
      return;
    }

    // Try content script first
    let info = null;
    try {
      info = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_INFO' });
    } catch {
      // Content script not injected (e.g. newly opened tab) — derive from tab
      info = fallbackInfo(tab);
    }

    if (!info) info = fallbackInfo(tab);
    applyInfo(info);
  } catch (e) {
    showErr('Could not detect page: ' + e.message);
  }
}

function fallbackInfo(tab) {
  const url = tab.url || '';
  const title = (tab.title || 'Untitled')
    .replace(/ ?[-–|].*YouTube.*$/, '')
    .trim();
  let host = '';
  try {
    host = new URL(url).hostname.replace(/^www\./, '');
  } catch {}
  const isYT = /youtube\.com|youtu\.be/.test(host);
  const params = isYT ? new URL(url).searchParams : new URLSearchParams();
  const videoId = isYT ? params.get('v') : null;
  const thumbnail = videoId
    ? `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`
    : null;
  const isPlaylist = isYT && params.has('list');
  const siteName = guessSiteName(host);
  return {
    url,
    title,
    host,
    isYT,
    isPlaylist,
    videoId,
    thumbnail,
    siteName,
    hasMedia: isYT && !!videoId,
  };
}

function guessSiteName(host) {
  const map = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'vimeo.com': 'Vimeo',
    'twitch.tv': 'Twitch',
    'twitter.com': 'X / Twitter',
    'x.com': 'X / Twitter',
    'tiktok.com': 'TikTok',
    'reddit.com': 'Reddit',
    'instagram.com': 'Instagram',
    'facebook.com': 'Facebook',
    'soundcloud.com': 'SoundCloud',
    'bandcamp.com': 'Bandcamp',
    'dailymotion.com': 'Dailymotion',
    'bilibili.com': 'Bilibili',
    'rumble.com': 'Rumble',
    'odysee.com': 'Odysee',
  };
  for (const [k, v] of Object.entries(map)) {
    if (host.includes(k)) return v;
  }
  // Capitalise first segment
  const seg = host.split('.')[0];
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

function applyInfo(info) {
  if (S.manualInput) return; // 🛑 Stops auto-fill if user typed manually

  S.url = info.url || '';
  S.title = info.title || 'Untitled';
  S.isYT = !!info.isYouTube;
  S.isPlaylist = !!info.isPlaylist;
  el.urlIn().value = S.url;

  if (S.url) {
    el.mediaCard().style.display = 'flex';
    el.mediaCard().classList.add('refreshing');
    setTimeout(() => el.mediaCard().classList.remove('refreshing'), 400);

    el.mcTitle().textContent = S.title.slice(0, 80);
    el.mcHost().textContent = info.host || '';
    el.mcBadge().textContent = (info.siteName || 'WEB')
      .toUpperCase()
      .slice(0, 12);
    if (info.thumbnail) {
      el.mcThumb().src = info.thumbnail;
      el.mcThumb().onerror = () => {
        el.mcThumb().style.display = 'none';
      };
    } else {
      el.mcThumb().style.display = 'none';
    }
  }
  if (S.isPlaylist) {
    el.plBlock().style.display = 'flex';
  }
}

/* ════════════════════════════════════════════════════════════════════
   EVENTS
   ════════════════════════════════════════════════════════════════════ */
function wireEvents() {
  // Error dismiss
  el.errX().addEventListener('click', hideErr);

  // URL input
  el.urlIn().addEventListener('input', () => {
    S.url = el.urlIn().value.trim();
    S.manualInput = true; // 🔒 Locks auto-detection
  });

  el.reviewBtn().addEventListener('click', handleReview);

  // Paste
  el.pasteBtn().addEventListener('click', async () => {
    try {
      const txt = await navigator.clipboard.readText();
      if (txt) {
        el.urlIn().value = txt.trim();
        S.url = txt.trim();
        toast('📋 URL pasted', '📋');
      }
    } catch {
      toast('Clipboard access denied', '⚠️');
    }
  });

  // Clear
  el.clearBtn().addEventListener('click', () => {
    el.urlIn().value = '';
    S.url = '';
  });

  // Playlist seg
  el.plSeg()
    .querySelectorAll('.seg-pill')
    .forEach(btn => {
      btn.addEventListener('click', () => {
        el.plSeg()
          .querySelectorAll('.seg-pill')
          .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        S.playlist = btn.dataset.val;
      });
    });

  // Type pills
  document.querySelectorAll('.type-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document
        .querySelectorAll('.type-pill')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      S.type = btn.dataset.type;

      if (S.type === 'audio') {
        S.qList = AQ;
        S.fList = AF;
        S.qualityIdx = 0;
        S.formatIdx = 0;
      } else {
        S.qList = VQ;
        S.fList = VF;
        S.qualityIdx = 3;
        S.formatIdx = 0;
      }
      renderDials();
      savePrefs();
    });
  });

  // Quality arrows
  el.qPrev().addEventListener('click', () => {
    nudge('q', -1);
  });
  el.qNext().addEventListener('click', () => {
    nudge('q', +1);
  });

  // Format arrows
  el.fPrev().addEventListener('click', () => {
    nudge('f', -1);
  });
  el.fNext().addEventListener('click', () => {
    nudge('f', +1);
  });

  // Download
  el.dlBtn().addEventListener('click', handleDownload);
}

function nudge(axis, dir) {
  if (axis === 'q') {
    S.qualityIdx = (S.qualityIdx + dir + S.qList.length) % S.qList.length;
  } else {
    S.formatIdx = (S.formatIdx + dir + S.fList.length) % S.fList.length;
  }
  renderDials();
  savePrefs();
}

/* ════════════════════════════════════════════════════════════════════
   DIAL RENDERING
   ════════════════════════════════════════════════════════════════════ */
function renderDials() {
  const q = S.qList[S.qualityIdx];
  const f = S.fList[S.formatIdx];
  el.qVal().textContent = q[0];
  el.qSub().textContent = q[2];
  el.fVal().textContent = f[0];
  el.fSub().textContent = f[2];
}

/* ════════════════════════════════════════════════════════════════════
   DOWNLOAD
   ════════════════════════════════════════════════════════════════════ */
async function handleDownload() {
  hideErr();

  const url = el.urlIn().value.trim();
  if (!url) {
    showErr('Enter or auto-detect a video URL first.');
    return;
  }

  if (!S.online) {
    showErr('Server is offline. Run: pyflow');
    toast('Server offline', '🔴');
    return;
  }

  if (S.busy) return;

  // Build payload — 100% compatible with PyFlow server API
  const qEntry = S.qList[S.qualityIdx];
  const fEntry = S.fList[S.formatIdx];
  const isPlaylist = S.isPlaylist && S.playlist === 'playlist';

  const payload = {
    url: url,
    download_type: S.type,
    is_playlist: isPlaylist,
    quality: qEntry[1], // server value e.g. "1080p", "best", "320"
    format: fEntry[1], // server value e.g. "mp4", "mp3"
    title: S.title || 'Untitled',
  };

  setBusy(true);

  try {
    const res = await fetch(DOWNLOAD, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10000),
    });

    if (!res.ok) {
      const err = await res
        .json()
        .catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail || `Server ${res.status}`);
    }

    const result = await res.json();
    setBusy(false);

    // Success state
    el.dlContent().innerHTML = `✅ QUEUED  [${result.task_id}]`;
    toast(`Queued: ${S.title.slice(0, 38)}`, '⬇️');

    // Refresh stats
    setTimeout(pingServer, 800);

    // Reset button after 2.5 s
    setTimeout(() => {
      el.dlContent().innerHTML = `
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
          <path d="M10 2v11M5 9l5 5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M2 15v1a2 2 0 002 2h12a2 2 0 002-2v-1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        SEND TO PYFLOW`;
      el.dlBtn().disabled = false;
      S.busy = false;
    }, 2500);
  } catch (e) {
    setBusy(false);
    const msg =
      e.name === 'TimeoutError'
        ? 'Request timed out — is the server running?'
        : e.message;
    showErr(msg);
    toast(msg, '❌');
  }
}

function setBusy(on) {
  S.busy = on;
  el.dlBtn().disabled = on;
  if (on) {
    el.dlContent().innerHTML = `<span class="spin">↻</span> SENDING…`;
  }
}

/* ════════════════════════════════════════════════════════════════════
   UI HELPERS
   ════════════════════════════════════════════════════════════════════ */
function showErr(msg) {
  el.errTxt().textContent = msg;
  el.errStrip().style.display = 'flex';
}

function hideErr() {
  el.errStrip().style.display = 'none';
}

let _toastTimer;
function toast(msg, ico = '✅') {
  el.toastIco().textContent = ico;
  el.toastMsg().textContent = msg;
  el.toast().classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.toast().classList.remove('show'), 3500);
}

/* ════════════════════════════════════════════════════════════════════
   PREFERENCES
   ════════════════════════════════════════════════════════════════════ */
function savePrefs() {
  chrome.storage.sync
    .set({
      pf_type: S.type,
      pf_qi: S.qualityIdx,
      pf_fi: S.formatIdx,
    })
    .catch(() => {});
}

function loadPrefs() {
  chrome.storage.sync.get(['pf_type', 'pf_qi', 'pf_fi'], r => {
    if (r.pf_type) {
      S.type = r.pf_type;
      if (r.pf_type === 'audio') {
        S.qList = AQ;
        S.fList = AF;
        document.querySelectorAll('.type-pill').forEach(b => {
          b.classList.toggle('active', b.dataset.type === 'audio');
        });
      }
    }
    if (r.pf_qi !== undefined) S.qualityIdx = r.pf_qi;
    if (r.pf_fi !== undefined) S.formatIdx = r.pf_fi;
    renderDials();
  });
}

/* ════════════════════════════════════════════════════════════════════
REVIEW / VALIDATION SYSTEM (Uses existing Media Card above input)
════════════════════════════════════════════════════════════════════ */
async function handleReview() {
  hideErr();
  const raw = el.urlIn().value.trim();
  if (!raw) {
    showErr('Please paste or type a valid URL first.');
    return;
  }

  if (!isValidUrl(raw)) {
    showErr('Invalid URL format. Must start with http:// or https://');
    return;
  }

  S.url = raw;
  S.manualInput = true;

  // Parse domain & generate fallback info
  let host = '',
    siteName = 'Web',
    thumbnail = null;
  try {
    const u = new URL(raw);
    host = u.hostname.replace(/^www\./, '');
    siteName = guessSiteName(host);
    if (/youtube\.com|youtu\.be/.test(host)) {
      const v = u.searchParams.get('v') || u.pathname.slice(1).split('/')[0];
      if (v) thumbnail = `https://i.ytimg.com/vi/${v}/mqdefault.jpg`;
    }
  } catch {
    showErr('Could not parse URL structure.');
    return;
  }

  // Populate the EXISTING media card above the input
  el.mediaCard().style.display = 'flex';
  el.mcTitle().textContent = siteName + ' Video Detected';
  el.mcHost().textContent = host;
  el.mcBadge().textContent = siteName.toUpperCase().slice(0, 12);
  el.mcThumb().src = thumbnail || '';
  el.mcThumb().style.display = thumbnail ? 'block' : 'none';
  if (!thumbnail) el.mcThumb().onerror = () => {};

  toast('🔗 Link verified. Ready to queue.', '✅');
}

function isValidUrl(string) {
  try {
    const u = new URL(string);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}
