/* 渲染调度：视图注册表 + 页面切换。
 *
 * 这里刻意**不 import 任何视图模块**——视图注册由 main.js 完成，
 * 这样 router 不会和 auth/views 形成循环依赖。
 */

import { state, TITLES } from './state.js';
import { viewEl, on } from './ui.js';
import { loadLifecycle, destination, taskHtml, stageByKey } from './lifecycle.js';
import { esc, skeleton } from './format.js';

/** 视图名 → 渲染函数，由 main.js 在启动时填充 */
export const RENDERERS = {};

export function register(view, render) {
  RENDERERS[view] = render;
}

let navigating = false;
let renderRevision = 0;
let lifecycleNavigation = 0;

on('lifecycle.process', (_data, el) => {
  const params = { ...urlParams() };
  delete params.project;
  delete params.lifecycle;
  if (el.value) params.process = el.value;
  else delete params.process;
  go(state.view, { params, push: true });
});
on('lifecycle.open', async ({ key }) => {
  const revision = ++lifecycleNavigation;
  const originView = state.view;
  const originHash = location.hash;
  try {
    const data = await loadLifecycle(urlParams());
    if (revision !== lifecycleNavigation || state.view !== originView || location.hash !== originHash) return;
    const target = destination(data, key);
    go(target.view, { params: target.params, push: true });
  } catch (e) {
    if (revision !== lifecycleNavigation || state.view !== originView || location.hash !== originHash) return;
    viewEl().innerHTML = '<div class="errbar">' + esc(e.message) + '</div>';
  }
});
on('lifecycle.reset', () => go('start', { params: {}, push: true }));
on('lifecycle.return', () => {
  const params = urlParams();
  go('start', { params: { process: params.process || '', project: params.project || '' }, push: true });
});
on('lifecycle.method', ({ code }) => {
  const params = urlParams();
  state.toolbox.step = '';
  go('toolbox', { params: { open: code, process: params.process || '', project: params.project || '', lifecycle: params.lifecycle || '' }, push: true });
});

/** 带骨架屏的渲染：首次进入视图显示骨架；同一视图重渲染保留旧内容，避免闪烁和滚动跳动。 */
export async function renderAsync(view, loader, painter, options = {}) {
  const revision = ++renderRevision;
  const el = viewEl();
  const contextParams = { ...urlParams() };
  if (!contextParams.lifecycle) el.querySelector('#lifecycleTask')?.remove();
  const sameView = el.dataset.renderView === view && !options.forceSkeleton;
  if (!sameView) {
    el.innerHTML = '<div class="card">' + skeleton(5) + '</div>';
    el.dataset.renderView = view;
  }
  el.classList.add('is-loading');
  let data;
  let lifecycle = null;
  try {
    if (contextParams.lifecycle) {
      lifecycle = await loadLifecycle(contextParams);
      if (revision !== renderRevision || state.view !== view) return;
      const stage = stageByKey(lifecycle, contextParams.lifecycle);
      const monitoringDrilldown = contextParams.lifecycle === 'monitoring' && view === 'monitor';
      const methodWorkspace = view === 'toolbox';
      if (!stage || (stage.target.view !== view && !monitoringDrilldown && !methodWorkspace)) throw new Error('生命周期任务与当前页面不一致');
      if (stage.requires_process && !lifecycle.context.process) throw new Error('请先选择流程，再进入本步任务');
      if (stage.requires_process && lifecycle.context.process.level < 3) throw new Error('请先选择L3或L4流程，再进入本步任务');
    }
    data = await loader();
  } catch (e) {
    if (revision !== renderRevision || state.view !== view) return;
    el.classList.remove('is-loading');
    el.innerHTML = '<div class="errbar"><div><b>加载失败</b> · ' + esc(e.message) +
      '</div><button class="btn btn-g" data-act="shell.retry" data-view="' + view +
      '">重试</button>' + (contextParams.lifecycle ? '<button class="btn btn-g" data-act="lifecycle.reset">返回生命周期选择流程</button>' : '') + '</div>';
    return;
  }
  if (state.view !== view || revision !== renderRevision) return;
  el.classList.remove('is-loading');
  painter(data);
  if (lifecycle) {
    state.lifecycle = lifecycle;
    el.insertAdjacentHTML('afterbegin', taskHtml(lifecycle, contextParams.lifecycle));
  }
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
    else if (previousView && (previousView !== view || (previousParams.lifecycle && previousParams.lifecycle !== opts.params?.lifecycle))) {
      pushTrail(previousView, previousParams);
    }
  }
  state.view = view;
  const activeView = view === 'monitor' ? 'dashboard' : view;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.view === activeView);
  });
  document.getElementById('pageTitle').textContent = TITLES[view] || view;
  // 先把上下文写进 URL，再渲染：视图的 loader 会同步读取 urlParams()，
  // 如果顺序反过来，会读到上一次的 layer/process，导致上下文跳转失效。
  if (!opts.skipHash) {
    navigating = true;
    try { setUrlState(view, opts.params || {}, { push: opts.push !== false }); }
    finally { navigating = false; }
  }
  updateOriginBar();
  const render = RENDERERS[view];
  if (render) { renderRevision += 1; render(); }
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
  if (!origin || (origin.view === state.view && origin.params.lifecycle === urlParams().lifecycle)) {
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
  const previous = urlParams();
  if (!navigating && state.view === view && previous.lifecycle) {
    params = { ...params };
    if (!('lifecycle' in params)) params.lifecycle = previous.lifecycle;
    if (!('process' in params) && previous.process) params.process = previous.process;
    if (!('project' in params) && previous.project && (!params.process || String(params.process) === previous.process)) params.project = previous.project;
    if (params.process && String(params.process) !== previous.process) delete params.project;
  }
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
