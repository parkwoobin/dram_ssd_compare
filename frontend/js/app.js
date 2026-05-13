'use strict';

const state = {
  category: 'memory',
  sort: 'popular',
  loading: false,
};

const el = {
  tabBtns: document.querySelectorAll('.tab-btn'),
  sortBtns: document.querySelectorAll('.sort-btn'),
  lastUpdated: document.getElementById('last-updated'),
  statsBar: document.getElementById('stats-bar'),
  tableWrap: document.getElementById('table-wrap'),
  tableBody: document.querySelector('#compare-table tbody'),
  thead: document.querySelector('#compare-table thead tr'),
};

function fmt(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString('ko-KR') + '원';
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

function renderTable(data) {
  // stats
  const matchRate = data.total > 0
    ? ((data.matched / data.total) * 100).toFixed(1)
    : 0;
  el.statsBar.innerHTML = `
    <span>전체 <strong>${data.total}개</strong></span>
    <span>·</span>
    <span>스마트컴 매칭 <strong>${data.matched}개</strong> (${matchRate}%)</span>
  `;

  // rows
  el.tableBody.innerHTML = data.items.map((item, idx) => {
    const rank = item.danawa_rank ?? (idx + 1);
    const smtName = item.smtcom_name
      ? `<div class="product-name">${item.smtcom_name}</div>`
      : `<span class="no-match">스마트컴 미취급</span>`;
    const smtPrice = item.smtcom_price != null
      ? `<span class="price">${fmt(item.smtcom_price)}</span>`
      : `<span class="price-null">-</span>`;

    return `
      <tr>
        <td class="center">${rankBadge(rank)}</td>
        <td><div class="product-name">${item.danawa_name}</div></td>
        <td class="right"><span class="price">${fmt(item.danawa_price)}</span></td>
        <td>${smtName}</td>
        <td class="right">${smtPrice}</td>
        <td class="center">${diffHtml(item.price_diff)}</td>
      </tr>`;
  }).join('');
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

async function fetchAndRender() {
  if (state.loading) return;
  state.loading = true;
  showLoading();

  const url = `/api/compare/${state.category}?sort=${state.sort}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderTable(data);

    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    el.lastUpdated.textContent = `마지막 업데이트: ${now}`;
  } catch (e) {
    showError(`데이터 로드 실패: ${e.message}`);
  } finally {
    state.loading = false;
  }
}

// Tab 이벤트
el.tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    state.category = btn.dataset.cat;
    el.tabBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

// Sort 이벤트
el.sortBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    state.sort = btn.dataset.sort;
    el.sortBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    fetchAndRender();
  });
});

// 초기 로드
fetchAndRender();
