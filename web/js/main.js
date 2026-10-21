/* 应用入口：注册视图、接线 DOM、暴露模板需要的全局函数、启动。
 *
 * 为什么要往 window 上挂一堆函数？
 * 模板里的 `onclick="openProject(3)"` 是**在全局作用域求值**的，
 * ES 模块的作用域是隔离的，这些函数不挂到 window 上就点不动。
 * 这里集中声明一次，作为唯一的"对外操作面"；后续如果改成事件委托，
 * 只需要删掉这一段，不用动各个视图模块。
 */

import { GET } from './core/api.js';
import {
  AUTH, doLogin, hideLogin, isLoggedIn, loadMeta, logout, renderUserChip, showLogin,
} from './core/auth.js';
import { register, go, onSearch, RENDERERS } from './core/router.js';
import { state } from './core/state.js';
import { closeModal, tab } from './core/ui.js';

import * as dashboard from './views/dashboard.js';
import * as mapView from './views/map.js';
import * as workflowView from './views/workflow.js';
import * as projectsView from './views/projects.js';
import * as toolboxView from './views/toolbox.js';
import * as designerView from './views/designer.js';
import * as monitorView from './views/monitor.js';
import * as knowledgeView from './views/knowledge.js';

register('dashboard', dashboard.renderDashboard);
register('map', mapView.renderMap);
register('workflow', workflowView.renderWorkflow);
register('projects', projectsView.renderProjects);
register('toolbox', toolboxView.renderToolbox);
register('designer', designerView.renderDesigner);
register('monitor', monitorView.renderMonitor);
register('knowledge', knowledgeView.renderKnowledge);

// 模板里 onclick/onchange 需要的操作面
Object.assign(window, {
  // 框架级
  go, closeModal, tab, state, RENDERERS, logout,
  // 业务操作
  ...mapView,
  ...workflowView,
  ...projectsView,
  ...toolboxView,
  ...designerView,
  ...monitorView,
  ...knowledgeView,
});

/* -------------------------------------------------- 页面外壳 */

function wireChrome() {
  document.querySelectorAll('.nav a').forEach((a) => {
    a.onclick = () => { closeModal(); go(a.dataset.view); };
  });
  document.getElementById('mask').onclick = (e) => {
    if (e.target.id === 'mask') closeModal();
  };
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
  document.getElementById('searchInput').oninput = (e) => onSearch(e.target.value.trim());

  document.getElementById('loginBtn').onclick = doLogin;
  ['loginUser', 'loginPass'].forEach((id) => {
    document.getElementById(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doLogin();
    });
  });
}

async function boot() {
  wireChrome();

  if (!isLoggedIn()) {
    showLogin('');
    return;
  }

  try {
    AUTH.user = await GET('/auth/me');
    hideLogin();
    renderUserChip();
    await loadMeta();
    go('dashboard');
  } catch (e) {
    // 令牌失效时 api() 已经弹过登录框了
    if (!isLoggedIn()) return;
    showLogin(e.message);
  }
}

boot();
