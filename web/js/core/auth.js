/* 身份状态与登录界面。 */

import { API_BASE, GET, setToken, getToken, setUnauthorizedHandler } from './api.js';
import { state } from './state.js';
import { toast } from './ui.js';
import { explicitView, go } from './router.js';

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
    window.dispatchEvent(new Event('pms:login'));
    await enterDefaultView();
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
  document.getElementById('userRole').classList.add('hide');
  document.getElementById('view').innerHTML = '';
  document.getElementById('mask').classList.remove('show');
  const badge = document.getElementById('notifBadge');
  if (badge) {
    badge.textContent = '0';
    badge.classList.add('hide');
  }
  showLogin('已退出登录');
}

export function renderUserChip() {
  const u = AUTH.user;
  if (!u) return;
  const name = u.display_name || 'U';
  document.getElementById('userAvatar').textContent = name.slice(0, 1);
  document.getElementById('userName').textContent = name;
  const roleLabel = ROLE_LABEL[u.role] || u.role;
  const roleEl = document.getElementById('userRole');
  // 显示名里已经带了角色（如「系统管理员」「流程管理科」）时不再重复显示角色标签
  const duplicate = name.includes(roleLabel);
  roleEl.textContent = duplicate ? '' : roleLabel;
  roleEl.classList.toggle('hide', duplicate);
}

/** 枚举中文标签由后端下发，前端不维护映射表 */
export async function loadMeta() {
  try {
    const meta = await GET('/projects/meta/summary');
    state.meta.methodology = meta.methodology_labels || {};
    state.meta.status = meta.status_labels || {};
    state.meta.stage = meta.stage_names || {};
    state.meta.setupStage = meta.setup_stage_names || {};
    document.getElementById('backendState').textContent = '后端已连接';
  } catch (e) {
    document.getElementById('backendState').innerHTML =
      '<span style="color:var(--bad)">后端未连接</span>';
    throw e;
  }
}

/**
 * 登录/启动后的落地页：显式 hash/路径优先；
 * 否则只有“已确认首次上线且 8 个阶段仍就绪”才进驾驶舱，其余进「开始使用」。
 */
export async function enterDefaultView() {
  const explicit = explicitView();
  if (explicit) {
    go(explicit);
    return;
  }
  let view = 'start';
  try {
    const startup = await GET('/start/status');
    if (startup.pilot_confirmed && startup.pilot_ready_count >= startup.pilot_total) {
      view = 'dashboard';
    }
  } catch (e) {
    // 启动页会自己展示错误与重试，不要把用户挡在空白页
  }
  go(view);
}

// 令牌失效由 api 层回调到这里：清身份 + 弹登录页
setUnauthorizedHandler(() => {
  setAuth('', null);
  showLogin('登录已过期，请重新登录');
});

// 恢复上次登录的令牌（localStorage），user 信息等 /auth/me 回来再填
const savedToken = localStorage.getItem('psm_token');
if (savedToken) setToken(savedToken);
