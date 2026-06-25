# 3DMark HTML 임베드 패치 가이드

원본 파일(`3DMark_260608_share.html`)을 업데이트할 때 반드시 아래 변경사항을 다시 적용해야 한다.

---

## 1. CSS 범위 한정 (`:root` / `body` → `.mark-root`)

원본은 `body`, `:root` 기준으로 스타일을 선언하지만, 이 프로젝트에서는 해당 HTML을 메인 앱에 **div로 삽입**하기 때문에 전역 스타일 충돌을 막기 위해 모든 셀렉터 앞에 `.mark-root`를 붙인다.

| 원본 | 변경 후 |
|------|---------|
| `:root { ... }` | `.mark-root { ... }` |
| `body.light { ... }` | `.mark-root.light { ... }` |
| `header { ... }` | `.mark-root header { ... }` |
| `button { ... }` | `.mark-root button { ... }` |
| `#distTune { position:fixed; ... }` | `.mark-root #distTune { position:absolute; ... }` |

`position:fixed` → `position:absolute` 변경에 주의. fixed는 메인 앱 레이아웃을 벗어나 띄워지므로 absolute로 교체한다.

---

## 2. 컨테이너 크기 고정

`.mark-root`에 아래 속성을 추가한다. 메인 앱 내에 카드 형태로 삽입되기 때문에 전체화면 대신 고정 높이를 사용한다.

```css
.mark-root {
  height: 82vh;
  min-height: 500px;
  overflow: hidden;
  border-radius: 8px;
}
```

---

## 3. 테마 버튼 제거

원본의 헤더 내 테마 토글 버튼(`#themeBtn`)과 관련 이벤트 리스너를 **제거**한다. 테마는 메인 앱의 버튼으로 통합 제어한다.

제거 대상:
```html
<!-- 제거 -->
<button class="icon" id="themeBtn" title="다크/라이트 전환">🌙</button>
```
```js
// 제거
document.getElementById('themeBtn').addEventListener('click', () => { ... });
```

`applyTheme()` 함수 내에서도 `themeBtn` 텍스트를 바꾸는 코드를 제거한다:
```js
// 제거
document.getElementById('themeBtn').textContent = theme === 'light' ? '☀️' : '🌙';
```

---

## 4. 테마 초기값 변경

```js
// 원본
let theme = (localStorage.getItem('3dmark_theme') || 'dark');

// 변경 후 — site_theme(메인 앱 테마)를 fallback으로 사용
let theme = (localStorage.getItem('3dmark_theme') || localStorage.getItem('site_theme') || 'light');
```

---

## 5. `applyTheme()` 대상 변경

```js
// 원본
document.body.classList.toggle('light', theme === 'light');

// 변경 후
(document.querySelector('.mark-root') || document.body).classList.toggle('light', theme === 'light');
```

---

## 6. `fmt` 함수명 변경

메인 앱의 전역 `fmt` 함수와 충돌하므로 `markFmt`로 rename한다.

```js
// 원본
const fmt = n => ...
// 사용: fmt(p.value)

// 변경 후
const markFmt = n => ...
// 사용: markFmt(p.value)
```

---

## 7. DOM 참조 변경 (`document.body` → `.mark-root`)

메인 앱 body에 영향을 주지 않도록 아래 참조를 변경한다.

```js
// accent 색상 읽기
// 원본
getComputedStyle(document.body).getPropertyValue('--accent')
// 변경 후
getComputedStyle(document.querySelector('.mark-root') || document.body).getPropertyValue('--accent')

// 팝업 box 삽입
// 원본
document.body.appendChild(box)
// 변경 후
(document.querySelector('.mark-root') || document.body).appendChild(box)
```

---

## 8. `openPanel()` 위치 계산 수정

원본은 모바일에서 바텀시트로 동작하지만, 임베드 환경에서는 기어 버튼 기준 드롭다운으로 변경한다.

```js
function openPanel(o) {
  const panel = document.getElementById('panel');
  if (o) {
    const gear = document.getElementById('gearBtn');
    const r = gear.getBoundingClientRect();
    const gap = 6, margin = 12;
    const panelWidth = Math.min(window.innerWidth - margin * 2, window.innerWidth <= 560 ? 360 : 380);
    const right = Math.max(margin, Math.min(window.innerWidth - r.right, window.innerWidth - panelWidth - margin));
    panel.style.top = (r.bottom + 4) + 'px';
    panel.style.right = right + 'px';
    panel.style.left = 'auto';
    panel.style.bottom = 'auto';
    panel.style.width = window.innerWidth <= 560 ? `calc(100vw - ${margin * 2}px)` : '';
    panel.style.maxHeight = `calc(100vh - ${r.bottom + gap + margin}px)`;
  }
  panel.classList.toggle('open', o);
  document.getElementById('backdrop').classList.toggle('open', o);
}
```

---

## 9. 앱 테마 변경 감지 (MutationObserver) 추가

스크립트 맨 끝, `applyTheme()` 호출 이후에 아래 코드를 추가한다. 메인 앱에서 테마를 바꿀 때 차트 색상도 함께 업데이트된다.

```js
/* 앱 테마 변경 감지 */
(function() {
  const root = document.querySelector('.mark-root');
  if (!root) return;
  let _pendingRender = false;
  new MutationObserver(() => {
    const next = root.classList.contains('light') ? 'light' : 'dark';
    if (next === theme) return;
    theme = next;
    COL = { ...THEME_COLORS[theme] };
    syncPickers(); refreshChips();
    // 섹션이 숨겨져 있으면 렌더 보류
    if (root.offsetParent === null) { _pendingRender = true; return; }
    render();
  }).observe(root, { attributes: true, attributeFilter: ['class'] });
  // 섹션이 다시 보일 때 pending render 실행
  new MutationObserver(() => {
    if (_pendingRender && root.offsetParent !== null) {
      _pendingRender = false;
      requestAnimationFrame(() => { render(); fit(); });
    }
  }).observe(root.closest('[style]') || root.parentElement, { attributes: true, attributeFilter: ['style'] });
})();
requestAnimationFrame(fit);
```

---

## 10. z-index 보정

기어 버튼과 패널이 메인 앱 요소에 가려지지 않도록 추가한다.

```css
.mark-root #gearBtn { position: absolute !important; top: 10px; right: 18px; }
.mark-root #panel   { z-index: 9999 !important; }
.mark-root #backdrop { z-index: 9998 !important; }
.mark-root #stage   { will-change: auto !important; }
```

---

## 체크리스트

파일 교체 후 확인 사항:

- [ ] CSS 셀렉터 전체 `.mark-root` 접두사 적용
- [ ] `#themeBtn` 버튼 및 이벤트 리스너 제거
- [ ] `theme` 초기값 fallback 수정
- [ ] `fmt` → `markFmt` rename
- [ ] `document.body` 참조 → `.mark-root` 참조로 교체
- [ ] MutationObserver 블록 추가
- [ ] `openPanel()` 드롭다운 위치 계산 코드 교체
- [ ] `#distTune` position `fixed` → `absolute` 확인
