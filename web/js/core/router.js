/* 渲染调度：视图注册表 + 页面切换。
 *
 * 这里刻意**不 import 任何视图模块**——视图注册由 main.js 完成，
 * 这样 router 不会和 auth/views 形成循环依赖。
 */

import { state, TITLES } from './state.js';
import { viewEl } from './ui.js';
import { esc, skeleton } from './format.js';

/** 视图名 → 渲染函数，由 main.js 在启动时填充 */
export const RENDERERS = {};

export function register(view, render) {
  RENDERERS[view] = render;
}

/** 带骨架屏的渲染：先显示 loading，再填充内容 */
export async function renderAsync(view, loader, painter) {
  const el = viewEl();
  el.innerHTML = '<div class="card">' + skeleton(5) + '</div>';
  let data;
  try {
    data = await loader();
  } catch (e) {
    el.innerHTML = '<div class="errbar"><div><b>加载失败</b> · ' + esc(e.message) +
      '</div><button class="btn btn-g" data-act="shell.retry" data-view="' + view +
      '">重试</button></div>';
    return;
  }
  if (state.view !== view) return;   // 用户在加载期间切换了页面
  painter(data);
}

export function go(view, skipHash) {
  if (!RENDERERS[view]) view = 'dashboard';
  ensureExpertVisible(view);
  state.view = view;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.view === view);
  });
  document.getElementById('pageTitle').textContent = TITLES[view] || view;
  const render = RENDERERS[view];
  if (render) render();
  // 视图名同步到 hash，方便刷新/分享；用 replaceState 避免触发额外的 hashchange 渲染
  if (!skipHash && typeof history !== 'undefined') {
    const target = '#' + view;
    if (location.hash !== target) history.replaceState(null, '', target);
  }
}

/** URL 明确指定的视图；没有则为 null（用于区分“用户点名”与“默认落地”） */
export function explicitView() {
  const hash = (location.hash || '').replace(/^#/, '');
  const path = (location.pathname || '').replace(/^\/+|\/+$/g, '');
  if (RENDERERS[hash]) return hash;
  if (RENDERERS[path]) return path;
  return null;
}

/* -------------------------------------------------- 专家模式
 *
 * 默认露出主线 / 看板 / 工具，其余收进“专家模式”。
 * 状态存 localStorage，刷新/深链保持一致；跳到被收起的视图时自动展开。
 */
const EXPERT_KEY = 'pms_expert_mode';

export function isExpertMode() {
  return document.documentElement.classList.contains('expert-mode');
}

export function setExpertMode(on, persist = true) {
  document.documentElement.classList.toggle('expert-mode', !!on);
  const button = document.getElementById('expertToggle');
  if (button) {
    button.setAttribute('aria-pressed', String(!!on));
    button.classList.toggle('on', !!on);
    button.title = on ? '隐藏专家工具' : '显示全部工具';
  }
  if (persist) {
    try {
      localStorage.setItem(EXPERT_KEY, on ? '1' : '0');
    } catch (e) { /* 隐私模式下忽略 */ }
  }
}

export function toggleExpertMode() {
  setExpertMode(!isExpertMode());
}

export function initExpertMode() {
  let on = false;
  try {
    on = localStorage.getItem(EXPERT_KEY) === '1';
  } catch (e) { /* 隐私模式下保持收起 */ }
  setExpertMode(on, false);
}

function ensureExpertVisible(view) {
  const link = document.querySelector(`.nav a[data-view="${view}"]`);
  if (link && link.classList.contains('expert-only') && !isExpertMode()) {
    setExpertMode(true);
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('hashchange', () => {
    const view = (location.hash || '').replace(/^#/, '');
    if (RENDERERS[view] && state.view !== view) go(view, true);
  });
}

/* 顶栏搜索：按当前视图派发到对应的关键词过滤 */
let searchTimer = null;
export function onSearch(value) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const v = state.view;
    if (v === 'projects') {
      state.projects.keyword = value;
      RENDERERS.projects();
    } else if (v === 'knowledge') {
      state.knowledge.keyword = value;
      state.knowledge.page = 1;
      RENDERERS.knowledge();
    } else if (v === 'toolbox') {
      state.toolboxKeyword = value;
      RENDERERS.toolbox();
    } else if (v === 'map') {
      state.mapKeyword = value;
      RENDERERS.map();
    } else if (v === 'pcf') {
      state.pcf.keyword = value;
      RENDERERS.pcf();
    }
  }, 260);
}
