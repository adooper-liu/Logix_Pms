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
      '</div><button class="btn btn-g" onclick="go(\'' + view + '\')">重试</button></div>';
    return;
  }
  if (state.view !== view) return;   // 用户在加载期间切换了页面
  painter(data);
}

export function go(view) {
  state.view = view;
  document.querySelectorAll('.nav a').forEach((a) => {
    a.classList.toggle('active', a.dataset.view === view);
  });
  document.getElementById('pageTitle').textContent = TITLES[view] || view;
  const render = RENDERERS[view];
  if (render) render();
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
      RENDERERS.knowledge();
    } else if (v === 'toolbox') {
      state.toolboxKeyword = value;
      RENDERERS.toolbox();
    } else if (v === 'map') {
      state.mapKeyword = value;
      RENDERERS.map();
    }
  }, 260);
}
