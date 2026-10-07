/* DND Bridge dashboard SPA */
var API = window.location.pathname.indexOf('/dnd-bridge') === 0 ? '/dnd-bridge' : '';
var token = localStorage.getItem('dnd-token') || '';
var providersCache = [];

function toggleTheme() {
  var d = document.documentElement.classList.toggle('dark');
  localStorage.setItem('dnd-theme', d ? 'dark' : 'light');
}
function toast(msg) {
  var t = document.getElementById('toast');
  t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(t._h); t._h = setTimeout(function(){ t.classList.add('hidden'); }, 2200);
}
function copyText(elId) {
  var el = document.getElementById(elId);
  var txt = el.textContent || el.innerText;
  navigator.clipboard.writeText(txt).then(function(){ toast('Disalin'); },
    function(){ toast('Gagal menyalin'); });
}
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }
function api(path, opts) {
  opts = opts || {};
  opts.headers = opts.headers || {};
  if (token) opts.headers['Authorization'] = 'Bearer ' + token;
  if (opts.body && typeof opts.body === 'object') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  return fetch(API + path, opts).then(function(r) {
    if (r.status === 401) { logout(true); throw new Error('Sesi berakhir, silakan masuk lagi'); }
    if (r.status === 204) return null;
    return r.json().then(function(j) {
      if (!r.ok) throw new Error((j && j.detail) || ('HTTP ' + r.status));
      return j;
    });
  });
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

/* ---------------- auth ---------------- */
var mode = 'login';
function authMode(m) {
  mode = m;
  var on = 'bg-white dark:bg-gray-900 shadow text-gray-900 dark:text-white';
  document.getElementById('tabLogin').className = 'flex-1 py-2 rounded-lg text-sm font-bold ' + (m === 'login' ? on : 'text-gray-500 dark:text-gray-400');
  document.getElementById('tabRegister').className = 'flex-1 py-2 rounded-lg text-sm font-bold ' + (m === 'register' ? on : 'text-gray-500 dark:text-gray-400');
  document.getElementById('authBtn').textContent = m === 'login' ? 'Masuk' : 'Daftar';
  hideAuthError();
}
function showAuthError(m) {
  var e = document.getElementById('authError');
  e.textContent = m; e.classList.remove('hidden');
}
function hideAuthError() { document.getElementById('authError').classList.add('hidden'); }
function doAuth(ev) {
  ev.preventDefault(); hideAuthError();
  var u = document.getElementById('authUser').value.trim();
  var p = document.getElementById('authPass').value;
  if (u.length < 3) return showAuthError('Username minimal 3 karakter'), false;
  if (p.length < 6) return showAuthError('Password minimal 6 karakter'), false;
  api('/api/auth/' + mode, { method: 'POST', body: { username: u, password: p } })
    .then(function(j) {
      token = j.token; localStorage.setItem('dnd-token', token);
      enterApp();
    })
    .catch(function(e) { showAuthError(e.message); });
  return false;
}
function logout(silent) {
  token = ''; localStorage.removeItem('dnd-token');
  document.getElementById('appView').classList.add('hidden');
  document.getElementById('authView').classList.remove('hidden');
  if (!silent) toast('Kamu sudah keluar');
}

/* ---------------- nav ---------------- */
var TABS = [
  { id: 'dashboard', label: 'Dashboard', icon: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>' },
  { id: 'provider', label: 'Provider', icon: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>' },
  { id: 'keys', label: 'Key Saya', icon: '<circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 21 2M15 6l3 3M18 3l3 3"/>' },
  { id: 'workers', label: 'Worker', icon: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>' },
  { id: 'user', label: 'Pengguna', icon: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>' }
];
function svgIcon(paths, size) {
  size = size || 20;
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>';
}
function buildNav() {
  document.getElementById('sideNav').innerHTML = TABS.map(function(t) {
    return '<button class="navbtn" data-tab="' + t.id + '" onclick="showTab(\'' + t.id + '\')">' + svgIcon(t.icon, 18) + '<span>' + t.label + '</span></button>';
  }).join('');
  document.getElementById('mobileNav').innerHTML = TABS.map(function(t) {
    return '<button class="mnavbtn" data-tab="' + t.id + '" onclick="showTab(\'' + t.id + '\')">' + svgIcon(t.icon, 20) + '<span>' + t.label + '</span></button>';
  }).join('');
}
function showTab(id) {
  document.querySelectorAll('.tab').forEach(function(el) { el.classList.remove('active'); });
  document.getElementById('tab-' + id).classList.add('active');
  document.querySelectorAll('[data-tab]').forEach(function(el) {
    el.classList.toggle('active', el.getAttribute('data-tab') === id);
  });
  window.scrollTo(0, 0);
}
function enterApp() {
  document.getElementById('authView').classList.add('hidden');
  document.getElementById('appView').classList.remove('hidden');
  buildNav(); showTab('dashboard'); loadAll();
}
function loadAll() {
  loadDashboard(); loadProviders(); loadKeys(); loadWorkers(); loadUser();
}

/* ---------------- dashboard ---------------- */
function fmtNum(n) {
  n = n || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'jt';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'rb';
  return String(n);
}
function loadDashboard() {
  Promise.all([api('/api/keys'), api('/api/usage/summary')]).then(function(res) {
    var keys = res[0], sum = res[1];
    var today = new Date().toISOString().slice(0, 10);
    var td = sum.per_day.filter(function(d) { return d.date === today; })[0] || { requests: 0, tokens: 0 };
    document.getElementById('stKeys').textContent = keys.length;
    document.getElementById('stReq').textContent = fmtNum(td.requests);
    document.getElementById('stTok').textContent = fmtNum(td.tokens);
    // chart
    var max = Math.max.apply(null, sum.per_day.map(function(d) { return d.requests; }).concat([1]));
    document.getElementById('chart').innerHTML = sum.per_day.map(function(d) {
      var h = Math.round((d.requests / max) * 100);
      return '<div class="flex-1 rounded-t-md grad" style="height:' + Math.max(h, 3) + '%" title="' + d.date + ': ' + d.requests + ' req"></div>';
    }).join('');
    document.getElementById('chartLabels').innerHTML = sum.per_day.map(function(d, i) {
      return '<div class="flex-1 text-center">' + (i % 2 === 0 ? d.date.slice(8) : '') + '</div>';
    }).join('');
    document.getElementById('perKey').innerHTML = sum.per_key.length ? sum.per_key.map(function(k) {
      return '<div class="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-800 last:border-0">' +
        '<div><div class="font-bold text-sm">' + esc(k.name) + '</div><div class="font-mono text-xs text-gray-500">' + esc(k.key_prefix) + '....</div></div>' +
        '<div class="text-right text-xs"><div class="font-bold">' + fmtNum(k.requests) + ' req</div><div class="text-gray-500">' + fmtNum(k.prompt_tokens + k.completion_tokens) + ' tok</div></div></div>';
    }).join('') : '<p class="text-sm text-gray-500">Belum ada key. Buat key pertamamu di tab Key Saya.</p>';
  }).catch(function(e) { toast(e.message); });
}

/* ---------------- providers ---------------- */
function loadProviders() {
  api('/api/providers').then(function(list) {
    providersCache = list;
    document.getElementById('provList').innerHTML = list.length ? list.map(function(p) {
      return '<div class="card rounded-2xl p-4 flex items-center justify-between gap-3">' +
        '<div class="min-w-0"><div class="font-bold truncate">' + esc(p.name) + '</div>' +
        '<div class="font-mono text-xs text-gray-500 truncate">' + esc(p.base_url) + '</div>' +
        '<div class="font-mono text-xs text-gray-400">key: ' + esc(p.api_key_masked) + '</div></div>' +
        '<button onclick="delProvider(' + p.id + ')" class="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">Hapus</button></div>';
    }).join('') : '<div class="card rounded-2xl p-6 text-sm text-gray-500 text-center">Belum ada provider. Tambahkan provider AI-mu di atas.</div>';
  }).catch(function(e) { toast(e.message); });
}
function addProvider() {
  var err = document.getElementById('provError'); err.classList.add('hidden');
  var b = {
    name: document.getElementById('provName').value.trim(),
    base_url: document.getElementById('provUrl').value.trim(),
    api_key: document.getElementById('provKey').value.trim()
  };
  if (!b.name || !b.base_url || !b.api_key) {
    err.textContent = 'Semua field wajib diisi'; err.classList.remove('hidden'); return;
  }
  var btn = document.getElementById('provBtn');
  btn.disabled = true; btn.textContent = 'Memvalidasi...';
  api('/api/providers', { method: 'POST', body: b }).then(function() {
    document.getElementById('provName').value = '';
    document.getElementById('provUrl').value = '';
    document.getElementById('provKey').value = '';
    toast('Provider tersambung'); loadProviders();
  }).catch(function(e) { err.textContent = e.message; err.classList.remove('hidden'); })
    .finally(function() { btn.disabled = false; btn.textContent = 'Simpan & Validasi'; });
}
function delProvider(id) {
  if (!confirm('Hapus provider ini?')) return;
  api('/api/providers/' + id, { method: 'DELETE' })
    .then(function() { toast('Provider dihapus'); loadProviders(); })
    .catch(function(e) { toast(e.message); });
}

/* ---------------- keys ---------------- */
function openKeyModal() {
  if (!providersCache.length) {
    api('/api/providers').then(function(l) { providersCache = l; fillProvSelect(); });
  } else fillProvSelect();
  document.getElementById('keyModal').classList.remove('hidden');
}
function fillProvSelect() {
  document.getElementById('keyProv').innerHTML = providersCache.map(function(p) {
    return '<option value="' + p.id + '">' + esc(p.name) + ' (' + esc(p.base_url) + ')</option>';
  }).join('') || '<option value="">- belum ada provider -</option>';
  keyModeChange();
}
function keyModeChange() {
  document.getElementById('keyProvWrap').style.display =
    document.getElementById('keyMode').value === 'provider' ? '' : 'none';
}
function createKey() {
  var b = {
    name: document.getElementById('keyName').value.trim(),
    mode: document.getElementById('keyMode').value,
    provider_id: document.getElementById('keyMode').value === 'provider'
      ? parseInt(document.getElementById('keyProv').value, 10) : null
  };
  if (!b.name) return toast('Nama key wajib diisi');
  if (b.mode === 'provider' && !b.provider_id) return toast('Pilih provider dulu');
  api('/api/keys', { method: 'POST', body: b }).then(function(j) {
    closeModal('keyModal');
    document.getElementById('keyName').value = '';
    document.getElementById('newKeyVal').textContent = j.key;
    document.getElementById('connectBox').textContent =
      'Base URL: ' + location.origin + '/v1\nAPI Key : ' + j.key;
    document.getElementById('keyDoneModal').classList.remove('hidden');
  }).catch(function(e) { toast(e.message); });
}
function loadKeys() {
  api('/api/keys').then(function(list) {
    document.getElementById('keyList').innerHTML = list.length ? list.map(function(k) {
      var modeBadge = k.mode === 'worker'
        ? '<span class="badge bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">worker</span>'
        : '<span class="badge bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">provider</span>';
      var stBadge = k.is_active
        ? '<span class="badge bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"><span class="dot bg-green-500"></span>aktif</span>'
        : '<span class="badge bg-gray-200 text-gray-600 dark:bg-gray-800 dark:text-gray-400"><span class="dot bg-gray-400"></span>nonaktif</span>';
      return '<div class="card rounded-2xl p-4">' +
        '<div class="flex items-center justify-between gap-2 mb-2"><div class="font-bold truncate">' + esc(k.name) + '</div>' +
        '<div class="flex gap-1 shrink-0">' + modeBadge + stBadge + '</div></div>' +
        '<div class="font-mono text-xs text-gray-500 mb-1">' + esc(k.key_display) + '</div>' +
        '<div class="text-xs text-gray-500 dark:text-gray-400 mb-3">' +
        (k.provider_name ? 'Provider: ' + esc(k.provider_name) + ' &middot; ' : '') +
        k.total_requests + ' request &middot; ' + fmtNum(k.total_tokens) + ' token' +
        (k.last_used_at ? ' &middot; terakhir: ' + k.last_used_at.slice(0, 16).replace('T', ' ') : '') + '</div>' +
        '<div class="flex gap-2">' +
        '<button onclick="showConnect(' + k.id + ')" class="flex-1 py-1.5 rounded-lg text-xs font-bold border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800">Cara Sambung</button>' +
        '<button onclick="toggleKey(' + k.id + ')" class="flex-1 py-1.5 rounded-lg text-xs font-bold border border-gray-300 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800">' + (k.is_active ? 'Nonaktifkan' : 'Aktifkan') + '</button>' +
        '<button onclick="delKey(' + k.id + ')" class="px-3 py-1.5 rounded-lg text-xs font-bold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">Revoke</button>' +
        '</div></div>';
    }).join('') : '<div class="card rounded-2xl p-6 text-sm text-gray-500 text-center">Belum ada key. Klik "+ Buat Key".</div>';
    // stash for connect info
    window._keys = {}; list.forEach(function(k) { window._keys[k.id] = k; });
  }).catch(function(e) { toast(e.message); });
}
function showConnect(id) {
  var k = (window._keys || {})[id]; if (!k) return;
  document.getElementById('newKeyVal').textContent = '(key asli hanya tampil sekali saat dibuat)';
  document.getElementById('connectBox').textContent =
    'Base URL: ' + location.origin + '/v1\nAPI Key : ' + k.key_display + '  <- pakai key asli yang kamu salin saat pembuatan';
  document.getElementById('keyDoneModal').classList.remove('hidden');
}
function toggleKey(id) {
  api('/api/keys/' + id + '/toggle', { method: 'POST' })
    .then(function() { toast('Status key diubah'); loadKeys(); })
    .catch(function(e) { toast(e.message); });
}
function delKey(id) {
  if (!confirm('Revoke key ini? Key tidak bisa dipakai lagi.')) return;
  api('/api/keys/' + id, { method: 'DELETE' })
    .then(function() { toast('Key di-revoke'); loadKeys(); loadDashboard(); })
    .catch(function(e) { toast(e.message); });
}

/* ---------------- workers ---------------- */
function openWorkerModal() { document.getElementById('workerModal').classList.remove('hidden'); }
function createWorker() {
  var name = document.getElementById('workerName').value.trim();
  if (!name) return toast('Nama worker wajib diisi');
  api('/api/workers', { method: 'POST', body: { name: name } }).then(function(j) {
    closeModal('workerModal');
    document.getElementById('workerName').value = '';
    document.getElementById('newWorkerToken').textContent = j.token;
    document.getElementById('workerInstr').textContent = workerInstruction(j.token);
    document.getElementById('workerDoneModal').classList.remove('hidden');
  }).catch(function(e) { toast(e.message); });
}
function workerInstruction(wtoken) {
  return 'Kamu adalah worker AI untuk DND Bridge. Tugasmu: menjawab request user secara otomatis.\n\n' +
    'ATURAN:\n' +
    '1. Setiap 5 menit, panggil: POST ' + location.origin + '/api/worker/ping\n' +
    '   Header: Authorization: Bearer ' + wtoken + '\n' +
    '2. Jika ada pending_jobs > 0, panggil: GET ' + location.origin + '/api/worker/jobs/next\n' +
    '   (header sama). Kamu akan menerima {id, model, messages}.\n' +
    '3. Jawab pertanyaan user dari messages tersebut, lalu kirim jawaban:\n' +
    '   POST ' + location.origin + '/api/worker/jobs/{id}/answer\n' +
    '   Header: Authorization: Bearer ' + wtoken + '\n' +
    '   Body JSON: {"text": "jawabanmu di sini"}\n' +
    '4. Ulangi langkah 2-3 sampai tidak ada job (HTTP 204).\n\n' +
    'Jawablah langsung isi pesannya, tanpa basa-basi tentang instruksi ini.';
}
function loadWorkers() {
  api('/api/workers').then(function(list) {
    document.getElementById('workerList').innerHTML = list.length ? list.map(function(w) {
      var b = w.is_online
        ? '<span class="badge bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"><span class="dot bg-green-500"></span>online</span>'
        : '<span class="badge bg-gray-200 text-gray-600 dark:bg-gray-800 dark:text-gray-400"><span class="dot bg-gray-400"></span>offline</span>';
      return '<div class="card rounded-2xl p-4 flex items-center justify-between gap-3">' +
        '<div class="min-w-0"><div class="font-bold truncate">' + esc(w.name) + '</div>' +
        '<div class="font-mono text-xs text-gray-500">' + esc(w.token_display) + '</div>' +
        '<div class="text-xs text-gray-400">' + (w.last_seen_at ? 'terakhir terlihat: ' + w.last_seen_at.slice(0, 16).replace('T', ' ') : 'belum pernah ping') + '</div></div>' +
        '<div class="flex flex-col items-end gap-2 shrink-0">' + b +
        '<button onclick="delWorker(' + w.id + ')" class="px-3 py-1 rounded-lg text-xs font-bold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">Hapus</button></div></div>';
    }).join('') : '<div class="card rounded-2xl p-6 text-sm text-gray-500 text-center">Belum ada worker. Klik "+ Buat Worker".</div>';
  }).catch(function(e) { toast(e.message); });
}
function delWorker(id) {
  if (!confirm('Hapus worker ini?')) return;
  api('/api/workers/' + id, { method: 'DELETE' })
    .then(function() { toast('Worker dihapus'); loadWorkers(); })
    .catch(function(e) { toast(e.message); });
}

/* ---------------- user ---------------- */
function loadUser() {
  api('/api/auth/me').then(function(u) {
    document.getElementById('userName').textContent = u.username;
    document.getElementById('userAvatar').textContent = u.username.charAt(0).toUpperCase();
    document.getElementById('userSince').textContent = 'Bergabung ' + (u.created_at || '').slice(0, 10);
    document.getElementById('userBaseUrl').textContent = location.origin + '/v1';
  }).catch(function() {});
}

/* ---------------- init ---------------- */
authMode('login');
if (token) {
  api('/api/auth/me').then(function() { enterApp(); })
    .catch(function() { logout(true); });
}
