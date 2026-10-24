/* 应用入口：注册视图与 actions、接线 DOM、启动。
 *
 * 模板不再依赖 window 上的函数：视图统一用 data-act + 委托，
 * 跨视图动作用 `actions['view.action']`。window 只保留最小操作面，
 * 方便调试与控制台调用，不再把每个视图的导出摊平。
 */

import { GET } from './core/api.js';
import {
  AUTH, doLogin, enterDefaultView, hideLogin, isLoggedIn, loadMeta, logout, renderUserChip,
  showLogin,
} from './core/auth.js';
import { initExpertMode, register, go, toggleExpertMode, onSearch } from './core/router.js';
import { state } from './core/state.js';
import { applyTheme as setTheme, initTheme } from './core/theme.js';
import { closeModal, on } from './core/ui.js';
import { actions, registerActions } from './core/actions.js';
import { openNotifications, refreshNotifications } from './core/notifications.js';

import * as dashboard from './views/dashboard.js';
import * as startView from './views/start.js';
import * as pilotView from './views/pilot.js';
import * as strategyView from './views/strategy.js';
import * as mapView from './views/map.js';
import * as processCardView from './views/process_card.js';
import * as authorizationView from './views/authorization.js';
import * as pcfView from './views/pcf.js';
import * as workflowView from './views/workflow.js';
import * as projectsView from './views/projects.js';
import * as executionView from './views/execution.js';
import * as toolboxView from './views/toolbox.js';
import * as designerView from './views/designer.js';
import * as monitorView from './views/monitor.js';
import * as dataView from './views/data.js';
import * as knowledgeView from './views/knowledge.js';
import * as deliverableView from './views/deliverables.js';
import * as orgsView from './views/orgs.js';
import * as sketchesView from './views/sketches.js';

register('dashboard', dashboard.renderDashboard);
register('start', startView.renderStart);
register('pilot', pilotView.renderPilot);
register('strategy', strategyView.renderStrategy);
register('map', mapView.renderMap);
register('process_card', processCardView.renderProcessCard);
register('authorization', authorizationView.renderAuthorization);
register('pcf', pcfView.renderPcf);
register('workflow', workflowView.renderWorkflow);
register('projects', projectsView.renderProjects);
register('execution', executionView.renderExecution);
register('toolbox', toolboxView.renderToolbox);
register('designer', designerView.renderDesigner);
register('monitor', monitorView.renderMonitor);
register('data', dataView.renderData);
register('knowledge', knowledgeView.renderKnowledge);
register('deliverables', deliverableView.renderDeliverables);
register('orgs', orgsView.renderOrgs);
register('sketches', sketchesView.renderSketches);

// 跨视图动作：视图只导出自己的 action map，由组合根统一注册。
registerActions({
  ...projectsView.actions,
  ...designerView.actions,
  ...toolboxView.actions,
}, 'views');

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

// 框架壳动作（顶栏、模态框、错误重试）
on('shell.notifications', () => openNotifications());
on('shell.theme', (_data, el) => applyTheme(el.value));
on('shell.logout', () => logout());
on('shell.retry', ({ view }) => go(view));

// 仅保留最小操作面；模板不再依赖这些全局函数。
Object.assign(window, { go, closeModal, state, actions });

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
  const expertToggle = document.getElementById('expertToggle');
  if (expertToggle) expertToggle.onclick = toggleExpertMode;
  try {
    applyNavCollapsed(localStorage.getItem(NAV_COLLAPSED_KEY) === '1');
  } catch (e) {
    applyNavCollapsed(false);
  }
  initExpertMode();
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
    await enterDefaultView();
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
