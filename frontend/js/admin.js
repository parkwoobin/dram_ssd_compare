'use strict';

const adminState = {
  tab: 'memory',
  products: [],
  trendDefaults: { memory: '', ssd: '' },
  estimatePostGroups: [],
};

const adminEl = {
  tabs: document.querySelectorAll('[data-admin-tab]'),
  desktopTabs: document.querySelectorAll('.admin-tabs [data-admin-tab]'),
  sidebarTabs: document.querySelectorAll('#admin-sidebar [data-admin-tab]'),
  sidebarOverlay: document.getElementById('admin-sidebar-overlay'),
  sidebar: document.getElementById('admin-sidebar'),
  hamburger: document.getElementById('admin-hamburger-btn'),
  sidebarClose: document.getElementById('admin-sidebar-close'),
  productsSection: document.getElementById('admin-products-section'),
  trendSection: document.getElementById('admin-trend-section'),
  markSection: document.getElementById('admin-3dmark-section'),
  dduSection: document.getElementById('admin-ddu-section'),
  estimatesSection: document.getElementById('admin-estimates-section'),
  productSource: document.getElementById('admin-product-source'),
  productSearch: document.getElementById('admin-product-search'),
  productRefresh: document.getElementById('admin-product-refresh'),
  productsBody: document.getElementById('admin-products-body'),
  trendMemory: document.getElementById('admin-trend-memory'),
  trendSsd: document.getElementById('admin-trend-ssd'),
  trendSave: document.getElementById('admin-trend-save'),
  markFile: document.getElementById('admin-3dmark-file'),
  markImport: document.getElementById('admin-3dmark-import'),
  markHtml: document.getElementById('admin-3dmark-html'),
  markSave: document.getElementById('admin-3dmark-save'),
  markStatus: document.getElementById('admin-3dmark-status'),
  estimateAuthorKeywords: document.getElementById('admin-estimate-author-keywords'),
  estimateSettingsSave: document.getElementById('admin-estimate-settings-save'),
  estimateSettingsSummary: document.getElementById('admin-estimate-settings-summary'),
  estimateCrawl: document.getElementById('admin-estimate-crawl'),
  estimateStatus: document.getElementById('admin-estimate-status'),
  estimatePosts: document.getElementById('admin-estimate-posts'),
  logout: document.getElementById('admin-logout'),
};

function adminFmt(n) {
  if (n == null || n === '') return '';
  return Number(n).toLocaleString('ko-KR');
}

function adminEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function adminFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    location.href = '/admin/login';
    throw new Error('로그인이 필요합니다.');
  }
  return res;
}

function openAdminSidebar() {
  adminEl.sidebar.classList.add('open');
  adminEl.sidebarOverlay.classList.add('open');
}

function closeAdminSidebar() {
  adminEl.sidebar.classList.remove('open');
  adminEl.sidebarOverlay.classList.remove('open');
}

function showAdminSection(tab) {
  adminState.tab = tab;
  adminEl.tabs.forEach(btn => btn.classList.toggle('active', btn.dataset.adminTab === tab));
  adminEl.productsSection.style.display = ['memory', 'ssd'].includes(tab) ? '' : 'none';
  adminEl.trendSection.style.display = tab === 'trend' ? '' : 'none';
  adminEl.markSection.style.display = tab === '3dmark' ? '' : 'none';
  adminEl.dduSection.style.display = tab === 'ddu' ? '' : 'none';
  adminEl.estimatesSection.style.display = tab === 'estimates' ? '' : 'none';

  if (tab === 'memory' || tab === 'ssd') loadAdminProducts();
  if (tab === 'trend') loadAdminTrend();
  if (tab === '3dmark') load3dmarkHtml();
  if (tab === 'estimates') loadAdminEstimateSettings();
}

async function loadAdminProducts() {
  const category = adminState.tab;
  const source = adminEl.productSource.value;
  adminEl.productsBody.innerHTML = '<tr><td colspan="6"><div class="loading">DB 로딩 중...</div></td></tr>';
  try {
    const res = await adminFetch(`/api/admin/products?category=${category}&source=${source}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    adminState.products = await res.json();
    renderAdminProducts();
  } catch (e) {
    adminEl.productsBody.innerHTML = `<tr><td colspan="6"><div class="error-msg">로드 실패: ${adminEscape(e.message)}</div></td></tr>`;
  }
}

function renderAdminProducts() {
  const query = adminEl.productSearch.value.trim().toLowerCase();
  const rows = query
    ? adminState.products.filter(item => item.name.toLowerCase().includes(query))
    : adminState.products;

  adminEl.productsBody.innerHTML = rows.map(item => `
    <tr data-product-id="${item.id}">
      <td>${item.id}</td>
      <td><input class="admin-cell-input admin-product-name" value="${adminEscape(item.name)}" /></td>
      <td class="right"><input class="admin-cell-input admin-product-price" type="number" value="${item.price ?? ''}" /></td>
      <td class="right"><input class="admin-cell-input admin-product-rank" type="number" value="${item.rank ?? ''}" /></td>
      <td>${new Date(item.crawled_at).toLocaleString('ko-KR')}</td>
      <td class="center"><button class="filter-btn admin-product-save">저장</button></td>
    </tr>
  `).join('') || '<tr><td colspan="6"><div class="loading">데이터 없음</div></td></tr>';

  document.querySelectorAll('.admin-product-save').forEach(btn => {
    btn.addEventListener('click', () => saveAdminProduct(btn.closest('tr')));
  });
}

async function saveAdminProduct(row) {
  const id = row.dataset.productId;
  const payload = {
    name: row.querySelector('.admin-product-name').value,
    price: row.querySelector('.admin-product-price').value === '' ? null : Number(row.querySelector('.admin-product-price').value),
    rank: row.querySelector('.admin-product-rank').value === '' ? null : Number(row.querySelector('.admin-product-rank').value),
  };
  const res = await adminFetch(`/api/admin/products/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    alert('저장 실패');
    return;
  }
  await loadAdminProducts();
}

async function loadProductOptions(category, selectEl, selectedName) {
  const res = await fetch(`/api/trend/products?category=${category}`);
  const data = await res.json();
  const products = data.products || [];
  selectEl.innerHTML = '<option value="">자동 선택</option>' + products
    .map(name => `<option value="${adminEscape(name)}">${adminEscape(name)}</option>`)
    .join('');
  selectEl.value = selectedName || '';
}

async function loadAdminTrend() {
  const res = await adminFetch('/api/admin/trend-defaults');
  adminState.trendDefaults = await res.json();
  await Promise.all([
    loadProductOptions('memory', adminEl.trendMemory, adminState.trendDefaults.memory),
    loadProductOptions('ssd', adminEl.trendSsd, adminState.trendDefaults.ssd),
  ]);
}

async function saveAdminTrend() {
  const payload = {
    memory: adminEl.trendMemory.value,
    ssd: adminEl.trendSsd.value,
  };
  const res = await adminFetch('/api/admin/trend-defaults', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  alert(res.ok ? '저장했습니다.' : '저장 실패');
}

async function load3dmarkHtml() {
  adminEl.markHtml.value = '불러오는 중...';
  const res = await adminFetch('/api/admin/3dmark-html');
  const data = await res.json();
  adminEl.markHtml.value = data.html || '';
  adminEl.markStatus.textContent = '현재 적용된 HTML을 불러왔습니다';
}

async function save3dmarkHtml() {
  adminEl.markSave.disabled = true;
  adminEl.markStatus.textContent = '적용 중...';
  const res = await adminFetch('/api/admin/3dmark-html', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ html: adminEl.markHtml.value }),
  });
  adminEl.markSave.disabled = false;
  adminEl.markStatus.textContent = res.ok
    ? '공개 3DMark 탭에 적용했습니다'
    : '적용 실패';
}

async function import3dmarkHtml() {
  adminEl.markFile.click();
}

async function handle3dmarkFileChange() {
  const file = adminEl.markFile.files && adminEl.markFile.files[0];
  if (!file) return;
  adminEl.markImport.disabled = true;
  adminEl.markStatus.textContent = `${file.name} 불러오는 중...`;
  try {
    const html = await file.text();
    adminEl.markHtml.value = html;
    await save3dmarkHtml();
    adminEl.markStatus.textContent = `${file.name} 적용 완료`;
  } catch (e) {
    adminEl.markStatus.textContent = `불러오기 실패: ${e.message}`;
  } finally {
    adminEl.markImport.disabled = false;
    adminEl.markFile.value = '';
  }
}

function parseAdminEstimateKeywords(value) {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

function updateAdminEstimateSummary(names) {
  const authorText = names.length ? `글쓴이 포함: ${names.join(', ')}` : '기본 글쓴이 키워드 사용';
  adminEl.estimateSettingsSummary.textContent = `${authorText} · 스마트 조립비 포함만`;
}

function adminFormatDate(value) {
  return value ? new Date(value).toLocaleString('ko-KR') : '';
}

function adminFormatPostDate(value) {
  if (!value) return '';
  const date = new Date(value);
  const yy = String(date.getFullYear()).slice(-2);
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `작성일 : ${yy}-${mm}-${dd} ${hh}:${min}`;
}

async function loadAdminEstimateSettings() {
  try {
    const res = await adminFetch('/api/estimates/settings');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const settings = await res.json();
    const names = Array.isArray(settings.names) ? settings.names : [];
    adminEl.estimateAuthorKeywords.value = names.join(', ');
    updateAdminEstimateSummary(names);
  } catch (e) {
    adminEl.estimateSettingsSummary.textContent = `설정 로드 실패: ${e.message}`;
  }
  await loadAdminEstimatePosts();
}

async function saveAdminEstimateSettings() {
  const names = parseAdminEstimateKeywords(adminEl.estimateAuthorKeywords.value);
  adminEl.estimateSettingsSave.disabled = true;
  adminEl.estimateSettingsSave.textContent = '저장 중...';
  try {
    const res = await adminFetch('/api/estimates/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const savedNames = Array.isArray(data.names) ? data.names : names;
    adminEl.estimateAuthorKeywords.value = savedNames.join(', ');
    updateAdminEstimateSummary(savedNames);
  } catch (e) {
    adminEl.estimateSettingsSummary.textContent = `설정 저장 실패: ${e.message}`;
  } finally {
    adminEl.estimateSettingsSave.disabled = false;
    adminEl.estimateSettingsSave.textContent = '설정 저장';
  }
}

async function loadAdminEstimatePosts() {
  adminEl.estimatePosts.innerHTML = '<div class="loading">수집된 견적 목록 불러오는 중...</div>';
  try {
    const res = await adminFetch('/api/estimates/posts?limit=1000');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    adminState.estimatePostGroups = await res.json();
    renderAdminEstimatePosts();
  } catch (e) {
    adminEl.estimatePosts.innerHTML = `<div class="error-msg">견적 목록 로드 실패: ${adminEscape(e.message)}</div>`;
  }
}

function renderAdminEstimatePosts() {
  const groups = Array.isArray(adminState.estimatePostGroups) ? adminState.estimatePostGroups : [];
  if (!groups.length) {
    adminEl.estimatePosts.innerHTML = '<div class="trend-empty">아직 수집된 견적 링크가 없습니다.</div>';
    return;
  }

  adminEl.estimatePosts.innerHTML = groups.map((group, index) => {
    const posts = Array.isArray(group.posts) ? group.posts : [];
    const postRows = posts.map(post => `
      <li class="admin-estimate-post-link">
        <a href="${adminEscape(post.url)}" target="_blank" rel="noopener noreferrer">
          ${adminEscape(post.title || `견적 #${post.wr_id}`)}
        </a>
        <a class="admin-estimate-post-url" href="${adminEscape(post.url)}" target="_blank" rel="noopener noreferrer">
          ${adminEscape(post.url)}
        </a>
        ${post.posted_at ? `
          <div class="admin-estimate-post-meta">
            ${adminEscape(adminFormatPostDate(post.posted_at))}
          </div>
        ` : ''}
      </li>
    `).join('');

    return `
      <details class="admin-estimate-author" ${index === 0 ? 'open' : ''}>
        <summary>
          <span>${adminEscape(group.author)}</span>
          <strong>${adminFmt(group.post_count)}개 견적</strong>
        </summary>
        <ul class="admin-estimate-post-list">${postRows}</ul>
      </details>
    `;
  }).join('');
}

async function crawlAdminEstimates() {
  adminEl.estimateCrawl.disabled = true;
  adminEl.estimateCrawl.textContent = '수집 중...';
  try {
    const settingsRes = await adminFetch('/api/estimates/settings');
    const settings = await settingsRes.json();
    const res = await adminFetch('/api/estimates/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names: settings.names || [], max_pages: 3 }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    adminEl.estimateStatus.textContent = `신규 ${data.saved_posts || 0}건 저장`;
    await loadAdminEstimatePosts();
  } catch (e) {
    adminEl.estimateStatus.textContent = `수집 실패: ${e.message}`;
  } finally {
    adminEl.estimateCrawl.disabled = false;
    adminEl.estimateCrawl.textContent = '최근 3페이지 수동 수집';
  }
}

async function logoutAdmin() {
  await fetch('/api/admin/logout', { method: 'POST' });
  location.href = '/admin/login';
}

adminEl.desktopTabs.forEach(btn => btn.addEventListener('click', () => showAdminSection(btn.dataset.adminTab)));
adminEl.sidebarTabs.forEach(btn => {
  btn.addEventListener('click', () => {
    closeAdminSidebar();
    showAdminSection(btn.dataset.adminTab);
  });
});
adminEl.hamburger.addEventListener('click', openAdminSidebar);
adminEl.sidebarClose.addEventListener('click', closeAdminSidebar);
adminEl.sidebarOverlay.addEventListener('click', closeAdminSidebar);
adminEl.productSource.addEventListener('change', loadAdminProducts);
adminEl.productRefresh.addEventListener('click', loadAdminProducts);
adminEl.productSearch.addEventListener('input', renderAdminProducts);
adminEl.trendSave.addEventListener('click', saveAdminTrend);
adminEl.markImport.addEventListener('click', import3dmarkHtml);
adminEl.markFile.addEventListener('change', handle3dmarkFileChange);
adminEl.markSave.addEventListener('click', save3dmarkHtml);
adminEl.estimateSettingsSave.addEventListener('click', saveAdminEstimateSettings);
adminEl.estimateAuthorKeywords.addEventListener('keydown', e => {
  if (e.key === 'Enter') saveAdminEstimateSettings();
});
adminEl.estimateCrawl.addEventListener('click', crawlAdminEstimates);
adminEl.logout.addEventListener('click', logoutAdmin);

showAdminSection('memory');
