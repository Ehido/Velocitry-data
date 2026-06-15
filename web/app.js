/* ============================================================
   Velocitry front-end — reads benchmarks.json and renders a
   ranked, searchable, comparable hardware leaderboard.
   ============================================================ */

const state = {
  data: null,
  category: 'gpus',
  search: '',
  sort: 'performance_score',
  compare: new Map(), // key -> item
};

const MAX_COMPARE = 4;

// Per-category config: which fields to show as spec chips, perf bar source, etc.
const CONFIG = {
  gpus: {
    label: 'Graphics Cards',
    brandOf: (n) => n.split(' ')[0],
    perfMax: 100,
    perfField: 'performance_score',
    perfHint: (it) => `${it.avg_fps_1080p} fps · 1080p`,
    chips: (it) => [
      ['VRAM', it.vram],
      ['Arch', it.arch],
      ['TDP', `${it.tdp}W`],
      ['Upscaling', it.dlss],
      ['Year', it.year],
    ],
    cmpRows: [
      ['Performance', (i) => i.performance_score, 'max'],
      ['Avg FPS (1080p)', (i) => i.avg_fps_1080p, 'max'],
      ['VRAM', (i) => i.vram, null],
      ['CUDA / Cores', (i) => i.cuda, 'max'],
      ['Boost clock', (i) => `${i.boost_mhz} MHz`, null],
      ['Bandwidth', (i) => `${i.bandwidth_gbs} GB/s`, null],
      ['TDP', (i) => `${i.tdp} W`, 'min'],
      ['Price', (i) => `£${i.price_gbp}`, null],
      ['Value score', (i) => i.price_perf_ratio, 'max'],
    ],
  },
  cpus: {
    label: 'Processors',
    brandOf: (n) => n.split(' ')[0],
    perfMax: 100,
    perfField: 'performance_score',
    perfHint: (it) => `${it.avg_fps} fps · gaming avg`,
    chips: (it) => [
      ['Cores', it.cores_threads],
      ['Boost', `${it.boost_ghz} GHz`],
      ['TDP', `${it.tdp}W`],
      ['L3', `${it.l3_mb}MB`],
      ['Year', it.year],
    ],
    cmpRows: [
      ['Performance', (i) => i.performance_score, 'max'],
      ['Avg FPS (gaming)', (i) => i.avg_fps, 'max'],
      ['Cores / Threads', (i) => i.cores_threads, null],
      ['Base clock', (i) => `${i.base_ghz} GHz`, null],
      ['Boost clock', (i) => `${i.boost_ghz} GHz`, 'max'],
      ['Multi-core', (i) => i.multi_score, 'max'],
      ['Single-core', (i) => i.single_score, 'max'],
      ['TDP', (i) => `${i.tdp} W`, 'min'],
      ['Price', (i) => `£${i.price_gbp}`, null],
      ['Value score', (i) => i.price_perf_ratio, 'max'],
    ],
  },
  rams: {
    label: 'Memory',
    brandOf: (n) => n.split(' ')[0],
    perfMax: 100,
    perfField: 'performance_score',
    perfHint: (it) => `${it.bandwidth_gbs} GB/s`,
    chips: (it) => [
      ['Capacity', it.capacity],
      ['Speed', it.speed],
      ['Latency', it.latency],
      ['Type', it.gen],
    ],
    cmpRows: [
      ['Performance', (i) => i.performance_score, 'max'],
      ['Capacity', (i) => i.capacity, null],
      ['Speed', (i) => i.speed, null],
      ['Latency', (i) => i.latency, null],
      ['Bandwidth', (i) => `${i.bandwidth_gbs} GB/s`, 'max'],
      ['Type', (i) => i.gen, null],
      ['Price', (i) => `£${i.price_gbp}`, 'min'],
    ],
  },
};

const $ = (sel) => document.querySelector(sel);
const keyOf = (it) => `${state.category}:${it.name}`;

/* ───────────── Boot ───────────── */
async function boot() {
  try {
    state.data = await loadData();
  } catch (err) {
    $('#board').innerHTML =
      `<p class="empty">Couldn't load <code>benchmarks.json</code>.<br>
       Serve this folder over HTTP (e.g. <code>python -m http.server</code>) so the data can be fetched.</p>`;
    console.error(err);
    return;
  }
  renderMeta();
  renderHeroStats();
  wireControls();
  render();
}

// Try a couple of likely locations for the data file.
async function loadData() {
  const candidates = ['../benchmarks.json', '/benchmarks.json', 'benchmarks.json', './benchmarks.json'];
  for (const url of candidates) {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (_) { /* try next */ }
  }
  throw new Error('benchmarks.json not found');
}

/* ───────────── Meta / footer ───────────── */
function renderMeta() {
  const meta = state.data._meta || {};
  if (meta.last_updated) {
    $('#updatedPill').innerHTML =
      `<span class="dot"></span> updated ${formatDate(meta.last_updated)}`;
  }
  $('#footerNote').textContent = meta.note || '';
  $('#sourceCredits').innerHTML = (meta.source_credits || [])
    .map((s) => `<span class="source-tag">${s}</span>`)
    .join('');
}

function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/* ───────────── Hero stats ───────────── */
function renderHeroStats() {
  const all = ['gpus', 'cpus', 'rams'].flatMap((c) => state.data[c] || []);
  const totalParts = all.length;
  const cheapest = all.reduce((a, b) => (b.price_gbp < a.price_gbp ? b : a));
  const bestValue = all.reduce((a, b) =>
    ((b.price_perf_ratio || 0) > (a.price_perf_ratio || 0) ? b : a));

  const stats = [
    { value: totalParts, label: 'Parts tracked' },
    { value: '3', label: 'Categories' },
    { value: `£${cheapest.price_gbp}`, label: 'Lowest price' },
    { value: bestValue.name.split(' ').slice(-2).join(' '), label: 'Top value pick', small: true },
  ];

  $('#heroStats').innerHTML = stats.map((s) => `
    <div class="stat">
      <div class="stat-value">${s.small ? `<small>${s.value}</small>` : s.value}</div>
      <div class="stat-label">${s.label}</div>
    </div>`).join('');
}

/* ───────────── Controls ───────────── */
function wireControls() {
  $('#tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('.tab');
    if (!btn) return;
    $('#tabs').querySelectorAll('.tab').forEach((t) => t.classList.remove('is-active'));
    btn.classList.add('is-active');
    state.category = btn.dataset.cat;
    state.search = '';
    $('#searchInput').value = '';
    render();
  });

  $('#searchInput').addEventListener('input', (e) => {
    state.search = e.target.value.trim().toLowerCase();
    render();
  });

  $('#sortSelect').addEventListener('change', (e) => {
    state.sort = e.target.value;
    render();
  });

  // Compare tray
  $('#clearCompare').addEventListener('click', () => {
    state.compare.clear();
    renderTray();
    render();
  });
  $('#openCompare').addEventListener('click', openCompareModal);

  // Modal close
  $('#compareModal').addEventListener('click', (e) => {
    if (e.target.hasAttribute('data-close')) closeCompareModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeCompareModal();
  });
}

/* ───────────── Sorting + filtering ───────────── */
function currentList() {
  const cfg = CONFIG[state.category];
  let list = [...(state.data[state.category] || [])];

  if (state.search) {
    list = list.filter((it) => it.name.toLowerCase().includes(state.search));
  }

  const s = state.sort;
  list.sort((a, b) => {
    if (s === 'price_gbp') return a.price_gbp - b.price_gbp;
    if (s === 'price_gbp_desc') return b.price_gbp - a.price_gbp;
    return (b[s] || 0) - (a[s] || 0); // performance, value, tier → descending
  });
  return { list, cfg };
}

/* ───────────── Render board ───────────── */
function render() {
  const { list, cfg } = currentList();
  const board = $('#board');
  const empty = $('#emptyState');

  if (!list.length) {
    board.innerHTML = '';
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  // Rank by raw performance regardless of current sort, for the # medal.
  const perfRank = [...list].sort((a, b) => b[cfg.perfField] - a[cfg.perfField]);
  const rankOf = (it) => perfRank.indexOf(it) + 1;

  board.innerHTML = list.map((it, i) => {
    const rank = rankOf(it);
    const topClass = rank <= 3 ? ` top${rank}` : '';
    const pct = Math.round((it[cfg.perfField] / cfg.perfMax) * 100);
    const inCompare = state.compare.has(keyOf(it));
    const chips = cfg.chips(it)
      .filter(([, v]) => v != null)
      .map(([k, v]) => `<span class="chip">${k} <b>${v}</b></span>`)
      .join('');

    return `
    <article class="card${topClass}" style="animation-delay:${i * 35}ms">
      <div class="rank"><small>RANK</small>${rank}</div>
      <div class="card-main">
        <div class="card-brand">${cfg.brandOf(it.name)}</div>
        <div class="card-name" title="${it.name}">${it.name}</div>
        <div class="specs">${chips}</div>
        <div class="perf">
          <div class="perf-track"><div class="perf-fill" data-pct="${pct}"></div></div>
          <div class="perf-meta">
            <span><b>${it[cfg.perfField]}</b> / ${cfg.perfMax} performance</span>
            <span>${cfg.perfHint(it)}</span>
          </div>
        </div>
      </div>
      <div class="card-side">
        <div class="price"><span>£</span>${formatPrice(it.price_gbp)}</div>
        ${it.pp_label ? `<span class="value-badge ${it.pp_label}">${it.pp_label} value</span>` : ''}
        <div class="card-actions">
          ${it.tier != null ? `<span class="tier-pill">Tier ${it.tier}</span>` : ''}
          <button class="compare-toggle${inCompare ? ' active' : ''}" data-key="${keyOf(it)}">
            ${inCompare ? '✓ Added' : '+ Compare'}
          </button>
        </div>
      </div>
    </article>`;
  }).join('');

  // Animate perf bars after paint.
  requestAnimationFrame(() => {
    board.querySelectorAll('.perf-fill').forEach((el) => {
      el.style.width = el.dataset.pct + '%';
    });
  });

  // Wire compare toggles.
  board.querySelectorAll('.compare-toggle').forEach((btn) => {
    btn.addEventListener('click', () => toggleCompare(btn.dataset.key));
  });
}

function formatPrice(n) {
  return n.toLocaleString('en-GB');
}

/* ───────────── Compare ───────────── */
function toggleCompare(key) {
  if (state.compare.has(key)) {
    state.compare.delete(key);
  } else {
    if (state.compare.size >= MAX_COMPARE) {
      flashTray(`Compare up to ${MAX_COMPARE} at a time`);
      return;
    }
    const it = (state.data[state.category] || []).find((x) => keyOf(x) === key);
    if (it) state.compare.set(key, { item: it, category: state.category });
  }
  renderTray();
  render();
}

function renderTray() {
  const tray = $('#compareTray');
  const n = state.compare.size;
  tray.hidden = n === 0;
  $('#compareCount').textContent = n;
  $('#openCompare').disabled = n < 2;

  $('#compareChips').innerHTML = [...state.compare.entries()].map(([key, { item }]) => `
    <span class="compare-chip">${item.name}
      <button data-key="${key}" aria-label="Remove">✕</button>
    </span>`).join('');

  $('#compareChips').querySelectorAll('button').forEach((b) => {
    b.addEventListener('click', () => {
      state.compare.delete(b.dataset.key);
      renderTray();
      render();
    });
  });
}

let flashTimer;
function flashTray(msg) {
  const btn = $('#openCompare');
  const prev = btn.textContent;
  btn.textContent = msg;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => renderTray(), 1400);
}

function openCompareModal() {
  const entries = [...state.compare.values()];
  if (entries.length < 2) return;

  // All compared items share a category in this simple version.
  const cfg = CONFIG[entries[0].category];
  const items = entries.map((e) => e.item);

  // Pre-compute the "best" value per row for highlighting.
  const bestIndex = cfg.cmpRows.map(([, getter, dir]) => {
    if (!dir) return -1;
    const nums = items.map((it) => parseFloat(String(getter(it)).replace(/[^\d.]/g, '')));
    if (nums.some(isNaN)) return -1;
    const target = dir === 'max' ? Math.max(...nums) : Math.min(...nums);
    return nums.indexOf(target);
  });

  $('#compareGrid').innerHTML = items.map((it, col) => `
    <div class="cmp-col">
      <div class="cmp-head">
        <div class="card-brand">${cfg.brandOf(it.name)}</div>
        <div class="card-name">${it.name}</div>
        <div class="price"><span>£</span>${formatPrice(it.price_gbp)}</div>
      </div>
      ${cfg.cmpRows.map(([label, getter], r) => `
        <div class="cmp-row${bestIndex[r] === col ? ' best' : ''}">
          <span class="k">${label}</span>
          <span class="v">${getter(it) ?? '—'}</span>
        </div>`).join('')}
    </div>`).join('');

  const modal = $('#compareModal');
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
}

function closeCompareModal() {
  $('#compareModal').hidden = true;
  document.body.style.overflow = '';
}

boot();
