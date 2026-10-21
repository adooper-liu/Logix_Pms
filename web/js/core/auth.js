/* 身份状态与登录界面。 */

import { API_BASE, GET, setToken, getToken, setUnauthorizedHandler } from './api.js';
import { state } from './state.js';
import { toast } from './ui.js';
import { go } from './router.js';

export const AUTH = { user: null };

export const ROLE_LABEL = {
  ADMIN: '管理员', MANAGER: '流程管理科', OWNER: '流程 Owner', VIEWER: '只读',
};

export function setAuth(token, user) {
  setToken(token);
  AUTH.user = user || null;
  if (token) localStorage.setItem('psm_token', token);
  else localStorage.removeItem('psm_token');
}

export function isLoggedIn() {
  return !!getToken();
}

export const role = () => (AUTH.user ? AUTH.user.role : 'VIEWER');
/** 能写业务数据（项目、异常、流程模型） */
export const canWrite = () => ['ADMIN', 'MANAGER', 'OWNER'].includes(role());
/** 能改结构性数据（流程架构、KPI 定义、知识库、用户） */
export const canManage = () => ['ADMIN', 'MANAGER'].includes(role());

/* -------------------------------------------------- 登录界面 */

export function showLogin(message) {
  const mask = document.getElementById('loginMask');
  if (!mask) return;
  mask.classList.remove('hide');
  const err = document.getElementById('loginErr');
  if (message) {
    err.textContent = message;
    err.classList.remove('hide');
  } else {
    err.classList.add('hide');
  }
  setTimeout(() => {
    const input = document.getElementById('loginUser');
    if (input) input.focus();
  }, 60);
}

export function hideLogin() {
  document.getElementById('loginMask').classList.add('hide');
  document.getElementById('loginUser').value = '';
  document.getElementById('loginPass').value = '';
  document.getElementById('loginErr').classList.add('hide');
}

export async function doLogin() {
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  const err = document.getElementById('loginErr');
  const btn = document.getElementById('loginBtn');

  if (!username || !password) {
    err.textContent = '请输入用户名和口令';
    err.classList.remove('hide');
    return;
  }

  btn.disabled = true;
  btn.textContent = '登录中…';
  try {
    // 登录不能用 api()：它的 401 处理会再次弹登录框，形成递归
    const res = await fetch(API_BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.detail || ('登录失败（' + res.status + '）'));
    }
    setAuth(body.token, body.user);
    hideLogin();
    renderUserChip();
    await loadMeta();
    go('dashboard');
    toast('欢迎回来，' + body.user.display_name);
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove('hide');
  } finally {
    btn.disabled = false;
    btn.textContent = '登录';
  }
}

export function logout() {
  setAuth('', null);
  AUTH.user = null;
  state.view = 'dashboard';
  document.getElementById('userName').textContent = '未登录';
  document.getElementById('userAvatar').textContent = '--';
  document.getElementById('userRole').textContent = '';
  document.getElementById('view').innerHTML = '';
  document.getElementById('mask').classList.remove('show');
  showLogin('已退出登录');
}

export function renderUserChip() {
  const u = AUTH.user;
  if (!u) return;
  document.getElementById('userAvatar').textContent = (u.display_name || 'U').slice(-2);
  document.getElementById('userName').textContent = u.display_name;
  document.getElementById('userRole').textContent = ROLE_LABEL[u.role] || u.role;
}

/** 枚举中文标签由后端下发，前端不维护映射表 */
export async function loadMeta() {
  try {
    const meta = await GET('/projects/meta/summary');
    state.meta.methodology = meta.methodology_labels || {};
    state.meta.status = meta.status_labels || {};
    state.meta.stage = meta.stage_names || {};
    document.getElementById('backendState').textContent = '后端已连接';
  } catch (e) {
    document.getElementById('backendState').innerHTML =
      '<span style="color:#ef4444">后端未连接</span>';
    throw e;
  }
}

// 令牌失效由 api 层回调到这里：清身份 + 弹登录页
setUnauthorizedHandler(() => {
  setAuth('', null);
  showLogin('登录已过期，请重新登录');
});

// 恢复上次登录的令牌（localStorage），user 信息等 /auth/me 回来再填
const savedToken = localStorage.getItem('psm_token');
if (savedToken) setToken(savedToken);
