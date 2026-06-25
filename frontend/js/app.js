'use strict';

const state = {
  category: 'memory',
  sort: 'popular',
  ddr: '',
  eccExclude: false,
  capacityGb: '',
  memCapGb: '',
  trendCategory: 'memory',
  trendDays: 7,
  loading: false,
  allItems: [],
};

const el = {
  tabBtns: document.querySelectorAll('.tab-btn'),
  sortBtns: document.querySelectorAll('.sort-btn'),
  lastUpdated: document.getElementById('last-updated'),
  statsBar: document.getElementById('stats-bar'),
  tableBody: document.querySelector('#compare-table tbody'),
  compareSection: document.getElementById('compare-section'),
  trendSection: document.getElementById('trend-section'),
  dduSection: document.getElementById('ddu-section'),
  markSection: document.getElementById('3dmark-section'),
  memoryFilters: document.getElementById('memory-filters'),
  ssdFilters: document.getElementById('ssd-filters'),
  searchInput: document.getElementById('search-input'),
  eccExclude: document.getElementById('ecc-exclude'),
  trendCatBtns: document.querySelectorAll('.trend-cat-btn'),
  trendSelect: document.getElementById('trend-product-select'),
  trendChartWrap: document.getElementById('trend-chart-wrap'),
  trendCanvas: document.getElementById('trend-chart'),
  trendEmpty: document.getElementById('trend-empty'),
  hoverPopup: document.getElementById('hover-popup'),
  hoverTitle: document.getElementById('hover-popup-title'),
  hoverCanvas: document.getElementById('hover-chart'),
  hoverNoData: document.getElementById('hover-no-data'),
};

// ── Theme ─────────────────────────────────────────────────────
(function initTheme() {
  const saved = localStorage.getItem('site_theme');
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved ?? (systemDark ? 'dark' : 'light');
  document.body.dataset.theme = theme;
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '🌙' : '☀️';
})();

function broadcastTheme(theme) {
  const markRoot = document.querySelector('.mark-root');
  if (markRoot) markRoot.classList.toggle('light', theme === 'light');
  const dduRoot = document.querySelector('.ddu-root');
  if (dduRoot) dduRoot.classList.toggle('dark', theme === 'dark');
  if (trendChartInstance) loadTrendHistory();
}

const _themeToggleBtn = document.getElementById('theme-toggle');
if (_themeToggleBtn) {
  _themeToggleBtn.addEventListener('click', () => {
    const next = document.body.dataset.theme === 'dark' ? 'light' : 'dark';
    document.body.dataset.theme = next;
    localStorage.setItem('site_theme', next);
    _themeToggleBtn.textContent = next === 'dark' ? '🌙' : '☀️';
    broadcastTheme(next);
  });
}

let trendChartInstance = null;
let hoverChartInstance = null;
let hoverFetchController = null;
let hoverHideTimer = null;
const productNameCollator = new Intl.Collator(['ko-KR', 'en-US'], {
  numeric: true,
  sensitivity: 'base',
});

// ── Formatters ────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString('ko-KR') + '원';
}

function fmtTooltipWon(value) {
  if (value == null) return '데이터 없음';
  return `${Math.round(Number(value)).toLocaleString('ko-KR')}원`;
}

function rankBadge(rank) {
  const cls = rank === 1 ? 'top1' : rank === 2 ? 'top2' : rank === 3 ? 'top3' : '';
  return `<span class="rank-badge ${cls}">${rank}</span>`;
}

function diffHtml(diff) {
  if (diff == null) return '<span class="no-match">-</span>';
  if (diff === 0) return '<span class="diff same">±0원</span>';
  const sign = diff > 0 ? '+' : '';
  const cls = diff < 0 ? 'cheaper' : 'expensive';
  const label = diff < 0 ? '스마트컴 ↓' : '스마트컴 ↑';
  return `<span class="diff ${cls}">${sign}${Math.abs(diff).toLocaleString('ko-KR')}원<br><small>${label}</small></span>`;
}

// ── Compare table ─────────────────────────────────────────────

function renderTable(items) {
  const query = el.searchInput.value.trim().toLowerCase();
  const filtered = query
    ? items.filter(it =>
        it.danawa_name.toLowerCase().includes(query) ||
        (it.smtcom_name && it.smtcom_name.toLowerCase().includes(query))
      )
    : items;

  const matched = filtered.filter(it => it.smtcom_name).length;
  const matchRate = filtered.length > 0
    ? ((matched / filtered.length) * 100).toFixed(1)
    : 0;
  el.statsBar.innerHTML = `
    <span>전체 <strong>${filtered.length}개</strong></span>
    <span>·</span>
    <span>스마트컴 매칭 <strong>${matched}개</strong> (${matchRate}%)</span>
    ${query ? `<span>· 검색: "<strong>${query}</strong>"</span>` : ''}
  `;

  el.tableBody.innerHTML = filtered.map((item, idx) => {
    const rank = idx + 1;
    const smtName = item.smtcom_name
      ? `<div class="product-name">${item.smtcom_name}</div>`
      : `<span class="no-match">스마트컴 미취급</span>`;
    const smtPrice = item.smtcom_price != null
      ? `<span class="price">${fmt(item.smtcom_price)}</span>`
      : `<span class="price-null">-</span>`;

    const dname = encodeURIComponent(item.danawa_name);
    const sname = item.smtcom_name ? encodeURIComponent(item.smtcom_name) : '';

    return `
      <tr class="data-row"
          data-dname="${dname}"
          data-sname="${sname}">
        <td class="center">${rankBadge(rank)}</td>
        <td><div class="product-name">${item.danawa_name}</div></td>
        <td class="right"><span class="price">${fmt(item.danawa_price)}</span></td>
        <td>${smtName}</td>
        <td class="right">${smtPrice}</td>
        <td class="center">${diffHtml(item.price_diff)}</td>
      </tr>`;
  }).join('') || `<tr><td colspan="6"><div class="loading" style="padding:30px">검색 결과 없음</div></td></tr>`;

  attachRowHover();
}

function showLoading() {
  el.tableBody.innerHTML = `
    <tr><td colspan="6">
      <div class="loading"><div class="spinner"></div> 가격 수집 중...</div>
    </td></tr>`;
}

function showError(msg) {
  el.tableBody.innerHTML = `
    <tr><td colspan="6">
      <div class="error-msg">⚠️ ${msg}</div>
    </td></tr>`;
}

function buildCompareUrl() {
  const params = new URLSearchParams({ sort: state.sort });
  if (state.category === 'memory') {
    if (state.ddr) params.set('ddr', state.ddr);
    if (state.eccExclude) params.set('ecc_exclude', 'true');
    if (state.memCapGb) params.set('capacity_gb', state.memCapGb);
  } else if (state.category === 'ssd') {
    if (state.capacityGb) params.set('capacity_gb', state.capacityGb);
  }
  return `/api/compare/${state.category}?${params}`;
}

async function fetchAndRender() {
  if (state.loading) return;
  state.loading = true;
  showLoading();

  try {
    const res = await fetch(buildCompareUrl());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.allItems = data.items;
    renderTable(state.allItems);

    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    el.lastUpdated.textContent = `마지막 업데이트: ${now}`;
  } catch (e) {
    showError(`데이터 로드 실패: ${e.message}`);
  } finally {
    state.loading = false;
  }
}

// ── Hover chart ───────────────────────────────────────────────

function attachRowHover() {
  document.querySelectorAll('.data-row').forEach(row => {
    row.addEventListener('mouseenter', onRowEnter);
    row.addEventListener('mouseleave', onRowLeave);
  });
}

function onRowEnter(e) {
  clearTimeout(hoverHideTimer);
  const row = e.currentTarget;
  const dname = decodeURIComponent(row.dataset.dname || '');
  const sname = decodeURIComponent(row.dataset.sname || '') || null;
  if (!dname) return;
  showHoverPopup(e, dname, sname);
}

function onRowLeave() {
  hoverHideTimer = setTimeout(() => {
    el.hoverPopup.style.display = 'none';
    if (hoverFetchController) hoverFetchController.abort();
  }, 200);
}

el.hoverPopup.addEventListener('mouseenter', () => clearTimeout(hoverHideTimer));
el.hoverPopup.addEventListener('mouseleave', () => {
  hoverHideTimer = setTimeout(() => {
    el.hoverPopup.style.display = 'none';
  }, 200);
});

function positionPopup(mouseEvent) {
  const pad = 16;
  const pw = 320, ph = 220;
  let x = mouseEvent.clientX + pad;
  let y = mouseEvent.clientY + pad;
  if (x + pw > window.innerWidth) x = mouseEvent.clientX - pw - pad;
  if (y + ph > window.innerHeight) y = mouseEvent.clientY - ph - pad;
  el.hoverPopup.style.left = `${x + window.scrollX}px`;
  el.hoverPopup.style.top = `${y + window.scrollY}px`;
}

async function showHoverPopup(mouseEvent, dname, sname) {
  positionPopup(mouseEvent);
  el.hoverPopup.style.display = 'block';
  el.hoverTitle.textContent = dname.length > 40 ? dname.slice(0, 38) + '…' : dname;
  el.hoverCanvas.style.display = 'none';
  el.hoverNoData.style.display = 'none';

  if (hoverFetchController) hoverFetchController.abort();
  hoverFetchController = new AbortController();

  try {
    const params = new URLSearchParams({ category: state.category, danawa_name: dname, days: 30 });
    if (sname) params.set('smtcom_name', sname);
    const res = await fetch(`/api/trend/daily-history?${params}`, { signal: hoverFetchController.signal });
    if (!res.ok) throw new Error('fetch error');
    const data = await res.json();

    if (!data.history || data.history.length === 0) {
      el.hoverNoData.style.display = 'block';
      return;
    }

    el.hoverCanvas.style.display = 'block';
    renderHoverChart(data.history);
  } catch (e) {
    if (e.name !== 'AbortError') {
      el.hoverNoData.style.display = 'block';
    }
  }
}

function renderHoverChart(history) {
  if (hoverChartInstance) hoverChartInstance.destroy();
  const labels = history.map(h => h.date.slice(5)); // MM-DD
  const dw = history.map(h => h.danawa_price);
  const smt = history.map(h => h.smtcom_price);

  hoverChartInstance = new Chart(el.hoverCanvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '다나와',
          data: dw,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.08)',
          tension: 0.3,
          pointRadius: 2,
          pointStyle: 'square',
          spanGaps: true,
        },
        {
          label: '스마트컴',
          data: smt,
          borderColor: '#dc2626',
          backgroundColor: 'rgba(220,38,38,0.08)',
          tension: 0.3,
          pointRadius: 2,
          pointStyle: 'square',
          spanGaps: true,
        },
      ],
    },
    options: {
      animation: false,
      responsive: false,
      plugins: {
        legend: { position: 'top', labels: { font: { size: 12 }, boxWidth: 12 } },
        tooltip: {
          titleFont: { size: 12 },
          bodyFont: { size: 12 },
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmtTooltipWon(ctx.raw)}`,
          },
        },
      },
      scales: {
        y: {
          ticks: {
            font: { size: 11 },
            callback: v => (v / 10000).toFixed(0) + '만',
          },
        },
        x: { ticks: { font: { size: 11 }, maxTicksLimit: 8 } },
      },
    },
  });
}

// ── Trend tab ─────────────────────────────────────────────────

async function loadTrendProducts() {
  el.trendSelect.innerHTML = '<option value="">불러오는 중...</option>';
  try {
    const res = await fetch(`/api/trend/products?category=${state.trendCategory}`);
    const data = await res.json();
    const products = [...(data.products || [])].sort((a, b) => productNameCollator.compare(a, b));
    if (products.length === 0) {
      el.trendSelect.innerHTML = '<option value="">제품 없음</option>';
      return;
    }
    el.trendSelect.innerHTML = products
      .map(p => `<option value="${encodeURIComponent(p)}">${p}</option>`)
      .join('');

    // Default selection (중고 제외 우선)
    const defaultName = state.trendCategory === 'memory'
      ? products.find(p => /삼성/.test(p) && /16GB/i.test(p) && !/중고/.test(p))
        || products.find(p => /삼성/.test(p) && /16GB/i.test(p))
        || products[0]
      : products.find(p => /삼성/.test(p) && /990 PRO/i.test(p) && /1TB/i.test(p))
        || products.find(p => /삼성/.test(p) && /980 PRO/i.test(p) && /1TB/i.test(p))
        || products.find(p => /삼성/.test(p) && /990|980/.test(p))
        || products[0];

    if (defaultName) {
      el.trendSelect.value = encodeURIComponent(defaultName);
    }
    
    await loadTrendHistory();
  } catch (e) {
    el.trendSelect.innerHTML = '<option value="">불러오기 실패</option>';
  }
}

async function loadTrendHistory() {
  const encodedName = el.trendSelect.value;
  if (!encodedName) return;
  const dname = decodeURIComponent(encodedName);

  el.trendChartWrap.style.display = 'flex';
  el.trendChartWrap.innerHTML = '<div class="loading"><div class="spinner"></div> 데이터 로딩 중...</div>';
  el.trendCanvas.style.display = 'none';
  el.trendEmpty.style.display = 'none';

  try {
    const params = new URLSearchParams({
      category: state.trendCategory,
      danawa_name: dname,
      days: state.trendDays,
    });
    const res = await fetch(`/api/trend/daily-history?${params}`);
    const data = await res.json();

    el.trendChartWrap.style.display = 'none';

    if (!data.history || data.history.length === 0) {
      el.trendEmpty.style.display = 'block';
      return;
    }

    el.trendCanvas.style.display = 'block';
    renderTrendChart(data);
  } catch (e) {
    el.trendChartWrap.innerHTML = `<div class="error-msg">⚠️ 로드 실패: ${e.message}</div>`;
  }
}

function renderTrendChart(data) {
  if (trendChartInstance) trendChartInstance.destroy();

  const labels = data.history.map(h => h.date);
  const dw = data.history.map(h => h.danawa_price);
  const smt = data.history.map(h => h.smtcom_price);

  const isDark = document.body.dataset.theme === 'dark';
  const chartBg    = isDark ? '#1e2530' : '#ffffff';
  const gridColor  = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)';
  const tickColor  = isDark ? '#9ca3af' : '#555555';
  const legendColor = isDark ? '#e5e7eb' : '#111111';

  trendChartInstance = new Chart(el.trendCanvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '다나와',
          data: dw,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.1)',
          tension: 0.3,
          pointRadius: 4,
          pointHitRadius: 12,
          pointHoverRadius: 6,
          pointStyle: 'square',
          fill: false,
          spanGaps: true,
        },
        {
          label: '스마트컴',
          data: smt,
          borderColor: '#dc2626',
          backgroundColor: 'rgba(220,38,38,0.1)',
          tension: 0.3,
          pointRadius: 4,
          pointHitRadius: 12,
          pointHoverRadius: 6,
          pointStyle: 'square',
          fill: false,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            usePointStyle: true,
            pointStyle: 'rect',
            pointStyleWidth: 12,
            boxWidth: 12,
            boxHeight: 12,
            font: { size: 13 },
            color: legendColor,
          },
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          titleFont: { size: 13 },
          bodyFont: { size: 13 },
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${fmtTooltipWon(ctx.raw)}`,
          },
        },
        chartAreaBackground: { color: chartBg },
      },
      scales: {
        y: {
          ticks: {
            font: { size: 12 },
            color: tickColor,
            callback: v => Number(v).toLocaleString('ko-KR') + '원',
          },
          grid: { color: gridColor },
          border: { color: gridColor },
        },
        x: {
          ticks: { font: { size: 12 }, maxTicksLimit: 12, color: tickColor },
          grid: { color: gridColor },
          border: { color: gridColor },
        },
      },
    },
    plugins: [{
      id: 'chartAreaBackground',
      beforeDraw(chart) {
        const { ctx, chartArea } = chart;
        if (!chartArea) return;
        ctx.save();
        ctx.fillStyle = chart.options.plugins.chartAreaBackground.color;
        ctx.fillRect(chartArea.left, chartArea.top, chartArea.width, chartArea.height);
        ctx.restore();
      },
    }],
  });
}

// ── Section switching ─────────────────────────────────────────

function hideAll() {
  el.compareSection.style.display = 'none';
  el.trendSection.style.display = 'none';
  el.dduSection.style.display = 'none';
  el.markSection.style.display = 'none';
}

function showCompare(cat) {
  hideAll();
  el.compareSection.style.display = '';
  el.memoryFilters.style.display = cat === 'memory' ? '' : 'none';
  el.ssdFilters.style.display = cat === 'ssd' ? '' : 'none';
}

function showTrend() {
  hideAll();
  el.trendSection.style.display = '';
  loadTrendProducts();
}

const _loadedSections = {};

async function loadHtmlSection(sectionEl, url, wrapClass) {
  if (_loadedSections[wrapClass]) return;
  _loadedSections[wrapClass] = true;

  try {
    const resp = await fetch(url);
    const html = await resp.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // 외부 스타일시트
    for (const link of doc.querySelectorAll('link[rel="stylesheet"]')) {
      if (!document.querySelector(`link[href="${link.href}"]`)) {
        const el = document.createElement('link');
        el.rel = 'stylesheet'; el.href = link.href;
        document.head.appendChild(el);
      }
    }

    // 외부 스크립트 (순서대로 로드)
    for (const s of doc.querySelectorAll('script[src]')) {
      if (!document.querySelector(`script[src="${s.src}"]`)) {
        await new Promise(res => {
          const script = document.createElement('script');
          script.src = s.src; script.onload = res; script.onerror = res;
          document.head.appendChild(script);
        });
      }
    }

    // 인라인 스타일
    for (const styleEl of doc.querySelectorAll('style')) {
      const style = document.createElement('style');
      style.textContent = styleEl.textContent;
      document.head.appendChild(style);
    }

    // 콘텐츠 래퍼
    const wrapper = document.createElement('div');
    wrapper.className = wrapClass;
    const currentTheme = document.body.dataset.theme || 'light';
    if (wrapClass === 'mark-root') wrapper.classList.toggle('light', currentTheme === 'light');
    if (wrapClass === 'ddu-root') wrapper.classList.toggle('dark', currentTheme === 'dark');
    wrapper.innerHTML = doc.body.innerHTML;
    sectionEl.appendChild(wrapper);

    // 인라인 스크립트 실행
    for (const oldScript of [...wrapper.querySelectorAll('script')]) {
      const newScript = document.createElement('script');
      newScript.textContent = oldScript.textContent;
      oldScript.parentNode.replaceChild(newScript, oldScript);
    }
  } catch (e) {
    sectionEl.innerHTML = `<p style="color:red;padding:20px">로드 실패: ${e.message}</p>`;
    delete _loadedSections[wrapClass];
  }
}

function showDdu() {
  hideAll();
  el.dduSection.style.display = '';
  loadHtmlSection(el.dduSection, '/html/DDU%20%EB%93%9C%EB%9D%BC%EC%9D%B4%EB%B2%84%20%ED%81%B4%EB%A6%B0%EC%84%A4%EC%B9%98%20%EA%B0%80%EC%9D%B4%EB%93%9C.html', 'ddu-root');
}

function show3dmark() {
  hideAll();
  el.markSection.style.display = '';
  loadHtmlSection(el.markSection, '/html/3DMark_260608_share.html?v=19', 'mark-root');
}

// ── Sidebar ───────────────────────────────────────────────────
const _sidebarOverlay = document.getElementById('sidebar-overlay');
const _sidebar = document.getElementById('sidebar');
const _hamburgerBtn = document.getElementById('hamburger-btn');
const _sidebarClose = document.getElementById('sidebar-close');

function openSidebar() {
  _sidebar.classList.add('open');
  _sidebarOverlay.classList.add('open');
}
function closeSidebar() {
  _sidebar.classList.remove('open');
  _sidebarOverlay.classList.remove('open');
}

if (_hamburgerBtn) _hamburgerBtn.addEventListener('click', openSidebar);
if (_sidebarClose) _sidebarClose.addEventListener('click', closeSidebar);
if (_sidebarOverlay) _sidebarOverlay.addEventListener('click', closeSidebar);

// ── Tab switch helper ─────────────────────────────────────────
function switchTab(cat) {
  el.tabBtns.forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
  document.querySelectorAll('.sidebar-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));

  if (cat === 'trend') {
    state.category = 'memory';
    showTrend();
  } else if (cat === 'ddu') {
    showDdu();
  } else if (cat === '3dmark') {
    show3dmark();
  } else {
    state.category = cat;
    state.memCapGb = '';
    state.capacityGb = '';
    document.querySelectorAll('[data-mem-cap]').forEach(b => b.classList.toggle('active', b.dataset.memCap === ''));
    document.querySelectorAll('[data-cap]').forEach(b => b.classList.toggle('active', b.dataset.cap === ''));
    showCompare(cat);
    fetchAndRender();
  }
}

// ── Event bindings ────────────────────────────────────────────

el.tabBtns.forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.cat));
});

document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    closeSidebar();
    switchTab(btn.dataset.cat);
  });
});

el.sortBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    state.sort = btn.dataset.sort;
    el.sortBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

el.searchInput.addEventListener('input', () => {
  if (state.allItems.length > 0) renderTable(state.allItems);
});

el.eccExclude.addEventListener('change', () => {
  state.eccExclude = el.eccExclude.checked;
  fetchAndRender();
});

// DDR filter buttons
document.querySelectorAll('[data-ddr]').forEach(btn => {
  btn.addEventListener('click', () => {
    state.ddr = btn.dataset.ddr;
    document.querySelectorAll('[data-ddr]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

// SSD capacity filter buttons
document.querySelectorAll('[data-cap]').forEach(btn => {
  btn.addEventListener('click', () => {
    state.capacityGb = btn.dataset.cap;
    document.querySelectorAll('[data-cap]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

// RAM capacity filter buttons
document.querySelectorAll('[data-mem-cap]').forEach(btn => {
  btn.addEventListener('click', () => {
    state.memCapGb = btn.dataset.memCap;
    document.querySelectorAll('[data-mem-cap]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

// Trend category sub-tabs
el.trendCatBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    state.trendCategory = btn.dataset.tcat;
    el.trendCatBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadTrendProducts();
  });
});

el.trendSelect.addEventListener('change', loadTrendHistory);

// Days buttons
document.querySelectorAll('.days-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    state.trendDays = parseInt(btn.dataset.days, 10);
    document.querySelectorAll('.days-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadTrendHistory();
  });
});

// ── Init ──────────────────────────────────────────────────────
// Prevent Enter key from accidentally activating first button: ensure buttons are non-submit
document.querySelectorAll('button').forEach(b => b.setAttribute('type', 'button'));

fetchAndRender();
