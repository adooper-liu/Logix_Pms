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
import { register, go, initialView, onSearch, RENDERERS } from './core/router.js';
import { state } from './core/state.js';
import { applyTheme as setTheme, initTheme } from './core/theme.js';
import { closeModal, tab } from './core/ui.js';
import { actions } from './core/actions.js';
import * as templateCopy from './core/template-copy.js';
import {
  markAllNotificationsRead, openNotification, openNotifications, refreshNotifications,
  scanNotifications,
} from './core/notifications.js';

import * as dashboard from './views/dashboard.js';
import * as mapView from './views/map.js';
import * as pcfView from './views/pcf.js';
import * as workflowView from './views/workflow.js';
import * as projectsView from './views/projects.js';
import * as executionView from './views/execution.js';
import * as toolboxView from './views/toolbox.js';
import * as designerView from './views/designer.js';
import * as monitorView from './views/monitor.js';
import * as knowledgeView from './views/knowledge.js';
import * as deliverableView from './views/deliverables.js';
import * as orgsView from './views/orgs.js';
import * as sketchesView from './views/sketches.js';

register('dashboard', dashboard.renderDashboard);
register('map', mapView.renderMap);
register('pcf', pcfView.renderPcf);
register('workflow', workflowView.renderWorkflow);
register('projects', projectsView.renderProjects);
register('execution', executionView.renderExecution);
register('toolbox', toolboxView.renderToolbox);
register('designer', designerView.renderDesigner);
register('monitor', monitorView.renderMonitor);
register('knowledge', knowledgeView.renderKnowledge);
register('deliverables', deliverableView.renderDeliverables);
register('orgs', orgsView.renderOrgs);
register('sketches', sketchesView.renderSketches);

// Canvas 读的是当前主题色，切换主题后要原地重绘，不能等下一次请求
function applyTheme(code) {
  setTheme(code);
  if (state.view === 'monitor' && state.monitorRadar) {
    monitorView.drawRadar(state.monitorRadar);
    if (state.monitorTrend) {
      monitorView.drawOverallTrend(state.monitorTrend.trend, state.monitorTrend.periods);
    }
    state.monitorRadar.series.forEach((series) =>
      monitorView.drawSpark(series.kpi_id, series.points.map((p) => p.value), series.direction));
  }
}

// 交互式登录成功后刷新顶栏未读数（boot 路径在 boot() 里单独刷新）
window.addEventListener('pms:login', () => { refreshNotifications(); });

// 模板里 onclick/onchange 需要的操作面
Object.assign(window, {
  // 框架级
  applyTheme, go, closeModal, tab, state, RENDERERS, logout, actions,
  openNotifications, openNotification, markAllNotificationsRead, scanNotifications,
  // 业务操作
  ...dashboard,
  ...mapView,
  ...pcfView,
  ...workflowView,
  ...projectsView,
  ...executionView,
  ...toolboxView,
  ...designerView,
  ...monitorView,
  ...knowledgeView,
  ...deliverableView,
  ...orgsView,
  ...sketchesView,
  // 跨视图共用：模板库与步骤推荐都从这里发起「复制到项目」
  ...templateCopy,
});

/* -------------------------------------------------- 页面外壳 */

const NAV_COLLAPSED_KEY = 'pms_nav_collapsed';

function applyNavCollapsed(collapsed) {
  document.documentElement.classList.toggle('nav-collapsed', collapsed);
  const button = document.getElementById('navCollapse');
  if (!button) return;
  button.textContent = collapsed ? '›' : '‹';
  button.title = collapsed ? '展开导航' : '收起导航';
  button.setAttribute('aria-label', button.title);
  button.setAttribute('aria-expanded', String(!collapsed));
}

function toggleNav() {
  const collapsed = !document.documentElement.classList.contains('nav-collapsed');
  try {
    localStorage.setItem(NAV_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch (e) { /* 隐私模式下忽略 */ }
  applyNavCollapsed(collapsed);
}

function wireChrome() {
  document.querySelectorAll('.nav a').forEach((a) => {
    const label = a.querySelector('.lbl');
    if (label) a.title = label.textContent.trim();
    a.onclick = () => {
      // 侧栏进入工具箱应看全部工具；步骤页的「只看推荐」是临时状态
      if (a.dataset.view === 'toolbox') state.toolboxFilter = null;
      closeModal();
      go(a.dataset.view);
    };
  });
  const navCollapse = document.getElementById('navCollapse');
  if (navCollapse) navCollapse.onclick = toggleNav;
  try {
    applyNavCollapsed(localStorage.getItem(NAV_COLLAPSED_KEY) === '1');
  } catch (e) {
    applyNavCollapsed(false);
  }
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
  initTheme();
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
    await refreshNotifications();
    go(initialView());
  } catch (e) {
    // 令牌失效时 api() 已经弹过登录框了
    if (!isLoggedIn()) return;
    showLogin(e.message);
  }
}

boot();

// 轻量轮询：只拉未读数，不拉通知正文
setInterval(() => {
  if (isLoggedIn()) refreshNotifications();
}, 60000);
