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

/** 带骨架屏的渲染：首次进入视图显示骨架；同一视图重渲染保留旧内容，避免闪烁和滚动跳动。 */
export async function renderAsync(view, loader, painter, options = {}) {
  const el = viewEl();
  const sameView = el.dataset.renderView === view && !options.forceSkeleton;
  if (!sameView) {
    el.innerHTML = '<div class="card">' + skeleton(5) + '</div>';
    el.dataset.renderView = view;
  }
  el.classList.add('is-loading');
  let data;
  try {
    data = await loader();
  } catch (e) {
    el.classList.remove('is-loading');
    el.innerHTML = '<div class="errbar"><div><b>加载失败</b> · ' + esc(e.message) +
      '</div><button class="btn btn-g" data-act="shell.retry" data-view="' + view +
      '">重试</button></div>';
    return;
  }
  if (state.view !== view) return;   // 用户在加载期间切换了页面
  el.classList.remove('is-loading');
  painter(data);
}

export function go(view, options = {}) {
  const opts = typeof options === 'boolean' ? { skipHash: options } : options;
  const previousView = state.view;
  const previousParams = urlParams();
  if (!RENDERERS[view]) view = 'dashboard';
  // 跨页面跳转记录来源；侧栏切换（skipOrigin）清空来源栈，
  // 「返回来源」使用 keepTrail 出栈后不再把当前页压回去。
  if (!opts.keepTrail) {
    if (opts.skipOrigin) state.navTrail = [];
    else if (previousView && previousView !== view) {
      pushTrail(previousView, previousParams);
    }
  }
  ensureExpertVisible(view);
  state.view = view;
  const activeView = view === 'monitor' ? 'dashboard' : view;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.view === activeView);
  });
  document.getElementById('pageTitle').textContent = TITLES[view] || view;
  // 先把上下文写进 URL，再渲染：视图的 loader 会同步读取 urlParams()，
  // 如果顺序反过来，会读到上一次的 layer/process，导致上下文跳转失效。
  if (!opts.skipHash) {
    setUrlState(view, opts.params || {}, { push: opts.push !== false });
  }
  updateOriginBar();
  const render = RENDERERS[view];
  if (render) render();
}

/** 来源栈最多保留 10 层，避免长时间使用后无限增长。 */
function pushTrail(view, params) {
  const trail = state.navTrail || (state.navTrail = []);
  const top = trail[trail.length - 1];
  const same = top && top.view === view
    && JSON.stringify(top.params || {}) === JSON.stringify(params || {});
  if (same) return;
  trail.push({ view, params: params || {} });
  while (trail.length > 10) trail.shift();
}

/**
 * 返回来源页：优先回到应用内记录的上一个视图（保留其 URL 上下文），
 * 没有来源栈时退回浏览器历史，再兜底到驾驶舱。
 */
export function goBackToOrigin() {
  const trail = state.navTrail || (state.navTrail = []);
  const origin = trail.pop();
  if (origin) {
    go(origin.view, { params: origin.params, push: true, keepTrail: true });
    return;
  }
  if (typeof history !== 'undefined' && history.length > 1) {
    history.back();
    return;
  }
  go('dashboard', { push: true, skipOrigin: true });
}

function updateOriginBar() {
  const back = document.getElementById('originBack');
  const context = document.getElementById('originContext');
  if (!back) return;
  const trail = state.navTrail || [];
  const origin = trail[trail.length - 1];
  if (!origin || origin.view === state.view) {
    back.classList.add('hide');
    if (context) context.textContent = '';
    return;
  }
  back.classList.remove('hide');
  back.textContent = '← 返回 ' + (TITLES[origin.view] || origin.view);
  const parts = Object.entries(origin.params || {});
  if (context) {
    context.textContent = parts.length
      ? '来源上下文：' + parts.map(([key, value]) => `${key}=${value}`).join(' · ')
      : '';
  }
}

/** 读取当前 hash 里的上下文参数：#view?key=value */
export function urlParams() {
  const raw = (location.hash || '').replace(/^#/, '');
  const query = raw.includes('?') ? raw.slice(raw.indexOf('?') + 1) : '';
  const params = {};
  new URLSearchParams(query).forEach((value, key) => {
    params[key] = value;
  });
  return params;
}

/** 把视图和上下文写进 URL；不触发 hashchange，避免重复渲染。 */
export function setUrlState(view, params = {}, { push = false } = {}) {
  if (typeof history === 'undefined') return;
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  const target = '#' + view + (query ? '?' + query : '');
  if (location.hash === target) return;
  history[push ? 'pushState' : 'replaceState'](null, '', target);
}

/** URL 明确指定的视图；没有则为 null（用于区分“用户点名”与“默认落地”） */
export function explicitView() {
  const hash = (location.hash || '').replace(/^#/, '').split('?')[0];
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
    const view = explicitView();
    if (!view) return;
    if (state.view !== view) go(view, { skipHash: true, push: false, skipOrigin: true });
    else RENDERERS[view]();
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
      setUrlState('projects', {
        methodology: state.projects.filter.methodology,
        status: state.projects.filter.status,
        stage: state.projects.filter.stage,
        type: state.projects.filter.projectType,
        keyword: value,
        project: state.projects.openId || '',
        new_process: state.projects.newProcess || '',
        new_name: state.projects.newName || '',
        new_objective: state.projects.newObjective || '',
      }, { push: false });
      RENDERERS.projects();
    } else if (v === 'knowledge') {
      state.knowledge.keyword = value;
      state.knowledge.page = 1;
      setUrlState('knowledge', {
        type: state.knowledge.type,
        tag: state.knowledge.tag,
        q: value,
        sort: state.knowledge.sort,
        scenario: state.knowledge.scenario,
        stage: state.knowledge.stage || '',
        step: state.knowledge.step,
        status: state.knowledge.status,
        tool: state.knowledge.tool,
      }, { push: false });
      RENDERERS.knowledge();
    } else if (v === 'toolbox') {
      state.toolbox.q = value;
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
