'use strict';

const adminLoginForm = document.getElementById('admin-login-form');
const adminLoginId = document.getElementById('admin-id');
const adminLoginPassword = document.getElementById('admin-password');
const adminLoginSubmit = document.getElementById('admin-login-submit');
const adminLoginMessage = document.getElementById('admin-login-message');

async function redirectIfLoggedIn() {
  try {
    const res = await fetch('/api/admin/session');
    if (!res.ok) return;
    const data = await res.json();
    if (data.logged_in) location.replace('/admin');
  } catch (error) {
    // Stay on the login page if the session check is unavailable.
  }
}

adminLoginForm.addEventListener('submit', async event => {
  event.preventDefault();
  adminLoginSubmit.disabled = true;
  adminLoginSubmit.textContent = '확인 중...';
  adminLoginMessage.textContent = '';

  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: adminLoginId.value.trim(),
        password: adminLoginPassword.value,
      }),
    });
    if (!res.ok) throw new Error('아이디 또는 비밀번호가 맞지 않습니다.');
    location.href = '/admin';
  } catch (error) {
    adminLoginMessage.textContent = error.message;
  } finally {
    adminLoginSubmit.disabled = false;
    adminLoginSubmit.textContent = '로그인';
  }
});

redirectIfLoggedIn();
