/* 视图：工作台
 *
 * 生产入口只回答「今天先做哪件事」：
 * 从流程框架开始 / 从一个流程开始 / 从一个项目开始。
 * 不铺方法论、不画体系图；数据都来自现有接口。
 */
import { esc } from '../core/format.js';
import { toast, openModal, closeModal, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, urlParams, setUrlState } from '../core/router.js';
import { AUTH, canManage, canWrite } from '../core/auth.js';
import { GET, POST } from '../core/api.js';

const WB = () => (state.workbench || (state.workbench = {
  rows: [], projects: null, activeTotal: 0,
}));

const RECENT_KEY = 'pms_recent';

function errorText(error) {
  const raw = error && error.message ? error.message : '操作失败';
  try {
    const detail = JSON.parse(raw);
    if (detail && detail.message) return detail.message;
  } catch (_) { /* 不是 JSON */ }
  return raw;
}

function readRecent() {
  try {
    const rows = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]');
    return Array.isArray(rows) ? rows.slice(0, 6) : [];
  } catch (_) {
    return [];
  }
}

function pushRecent(kind, id, label) {
  const rows = readRecent().filter((row) => !(row.kind === kind && row.id === id));
  rows.unshift({ kind, id, label, at: Date.now() });
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(rows.slice(0, 6)));
  } catch (_) { /* 隐私模式忽略 */ }
}

function counts(rows) {
  const result = { 1: 0, 2: 0, 3: 0, 4: 0, draft: 0, noOwner: 0 };
  rows.forEach((row) => {
    result[row.level] = (result[row.level] || 0) + 1;
    if (row.is_draft) result.draft += 1;
    if (row.level === 3 && !row.owner && !row.owner_user_id) result.noOwner += 1;
  });
  return result;
}

function l3Rows(rows) {
  return rows
    .filter((row) => row.level === 3 && !row.is_draft)
    .sort((left, right) => String(left.code).localeCompare(String(right.code)));
}

function projectLabel(row) {
  return `${row.code || ''} ${row.name || ''}`.trim();
}

function entryCard(no, title, subtitle, metrics, actions) {
  return `<div class="card wb-card">
    <div class="wb-card-no">${no}</div>
    <h3>${esc(title)}</h3>
    <p class="tiny muted">${esc(subtitle)}</p>
    <div class="wb-metrics">${metrics}</div>
    <div class="wb-actions">${actions}</div>
  </div>`;
}

function paint(rows, projects, activeTotal) {
  WB().rows = rows || [];
  WB().projects = projects;
  WB().activeTotal = activeTotal;
  const stat = counts(WB().rows);
  const l3 = l3Rows(WB().rows);
  const recent = readRecent();
  const projectTotal = (projects && projects.total) || 0;
  const todo = [];
  const todoCount = (stat.draft ? 1 : 0) + stat.noOwner;

  if (stat.draft) {
    todo.push(`<li><span>${stat.draft} 条流程草稿待确认</span>
      <button class="btn-sm" data-act="workbench.go" data-view="map">去确认</button></li>`);
  }
  if (stat.noOwner) {
    const rows = WB().rows
      .filter((row) => row.level === 3 && !row.owner && !row.owner_user_id)
      .slice(0, 3)
      .map((row) => `<li><span>${esc(row.code)} ${esc(row.name)} 缺 Owner</span>
        <button class="btn-sm" data-act="workbench.openProcess"
          data-id="${row.id}">去补</button></li>`)
      .join('');
    todo.push(rows);
  }
  if (!todo.length) {
    todo.push('<li class="muted">没有待处理项。</li>');
  }

  const processOptions = l3.map((row) => (
    `<option value="${row.id}">${esc(row.code)} ${esc(row.name)}${
      row.owner ? ' · ' + esc(row.owner) : ' · 缺 Owner'}</option>`
  )).join('');

  viewEl().innerHTML = `
    <div class="card page-head wb-head">
      <div class="between">
        <div>
          <h2>工作台</h2>
          <p class="desc">从流程框架、一条流程或一个项目开始；这里只列要办的事。</p>
        </div>
        <span class="tag t-blu">${esc((AUTH.user && AUTH.user.display_name) || '当前用户')}</span>
      </div>
    </div>
    <div class="wb-grid">
      ${entryCard(
        '01', '流程框架',
        '先有 L1-L4 的稳定目录，流程才有归属。',
        `<b>${stat[1]}</b><span>L1</span><b>${stat[2]}</b><span>L2</span>
         <b>${stat[3]}</b><span>L3</span><b>${stat[4]}</b><span>L4</span>`,
        `<button class="btn btn-p" data-act="workbench.go" data-view="map">打开流程框架</button>
         ${canManage()
    ? '<button class="btn btn-g" data-act="workbench.newNode" data-level="1">新建节点</button>'
    : ''}`,
      )}
      ${entryCard(
        '02', '一条流程',
        '选一条 L3，进入它的模型、活动、资产与证据。',
        `<b>${l3.length}</b><span>条 L3</span>
         <b>${stat.noOwner}</b><span>缺 Owner</span>`,
        `<select class="sel" id="wbProcess" ${l3.length ? '' : 'disabled'}>
           ${processOptions || '<option value="">还没有 L3 流程</option>'}
         </select>
         <button class="btn btn-p" data-act="workbench.openProcess"
           ${l3.length ? '' : 'disabled'}>打开流程</button>
         ${canManage() ? `<button class="btn btn-g" data-act="workbench.newProcess">新建 L3</button>
         <button class="btn btn-g" data-act="workbench.newActivity"
           ${l3.length ? '' : 'disabled'}>新建 L4 活动</button>` : ''}`,
      )}
      ${entryCard(
        '03', '一个项目',
        '把一条流程的改善变成有阶段、有证据的工程。',
        `<b>${projectTotal}</b><span>个项目</span>
         <b>${activeTotal}</b><span>进行中</span>`,
        `<button class="btn btn-p" data-act="workbench.go" data-view="projects">打开项目</button>
         ${canWrite() ? '<button class="btn btn-g" data-act="workbench.newProject">新建项目</button>' : ''}`,
      )}
    </div>
    <div class="grid mt2" style="grid-template-columns:1.2fr .8fr;gap:14px;align-items:start">
      <div class="card wb-todo">
        <div class="between"><h3>待我处理</h3>
          <span class="tiny muted">${todoCount} 项</span></div>
        <ul>${todo.join('')}</ul>
      </div>
      <div class="card wb-recent">
        <div class="between"><h3>最近打开</h3>
          <span class="tiny muted">${recent.length} 项</span></div>
        <ul>${recent.map((row) => `<li>
          <button class="link" data-act="${row.kind === 'project'
            ? 'workbench.openProject' : 'workbench.openProcess'}"
            data-id="${row.id}">${esc(row.label)}</button>
        </li>`).join('') || '<li class="muted">还没有打开记录。</li>'}</ul>
      </div>
    </div>`;
}

const renderWorkbench = () => renderAsync(
  'workbench',
  () => Promise.all([
    GET('/process-map/flat'),
    GET('/projects?page=1&page_size=5'),
    GET('/projects?status=ACTIVE&page=1&page_size=1'),
  ]),
  ([rows, projects, active]) => {
    paint(rows, projects, active.total || 0);
    const params = urlParams();
    if (params.new === 'process' && canManage()) {
      setTimeout(() => {
        openNodeModal(3);
        setUrlState('workbench', {});
      }, 0);
    } else if (params.new === 'activity' && canManage()) {
      setTimeout(() => {
        openNodeModal(4, Number(params.process) || null);
        setUrlState('workbench', {});
      }, 0);
    }
  },
);

/* -------------------------------------------------- 新建流程节点 */

function fillParentOptions(level) {
  const field = document.getElementById('wbParentField');
  const select = document.getElementById('wbNodeParent');
  const hint = document.getElementById('wbNodeHint');
  if (!field || !select) return;
  if (level <= 1) {
    field.classList.add('hide');
    select.innerHTML = '';
    if (hint) hint.textContent = 'L1 是价值链，不需要上级。';
    return;
  }
  field.classList.remove('hide');
  const parents = WB().rows
    .filter((row) => row.level === level - 1 && !row.is_draft)
    .sort((left, right) => String(left.code).localeCompare(String(right.code)));
  select.innerHTML = parents.map((row) => (
    `<option value="${row.id}">${esc(row.code)} ${esc(row.name)}</option>`
  )).join('') || `<option value="">请先创建 L${level - 1}</option>`;
  if (hint) {
    hint.textContent = parents.length
      ? `上级必须选一条已确认的 L${level - 1}。`
      : `还没有可用的 L${level - 1}，请先创建上一层。`;
  }
}

function openNodeModal(level = 1, parentId = null) {
  const levels = [1, 2, 3, 4].map((value) => (
    `<option value="${value}"${value === level ? ' selected' : ''}>L${value} ${
      ['价值链', '流程类别', '流程', '活动'][value - 1]}</option>`
  )).join('');
  openModal('新建流程节点', `
    <div class="row3">
      <div class="field"><label>层级</label>
        <select class="sel" id="wbNodeLevel" data-act="workbench.level">${levels}</select></div>
      <div class="field"><label>编码 *</label>
        <input id="wbNodeCode" placeholder="如 L3-041"></div>
      <div class="field"><label>名称 *</label>
        <input id="wbNodeName" placeholder="如 生产计划排程"></div>
    </div>
    <div class="field" id="wbParentField"><label>上级 *</label>
      <select class="sel" id="wbNodeParent"></select></div>
    <div class="field"><label>Owner</label>
      <input id="wbNodeOwner" value="${esc((AUTH.user && AUTH.user.display_name) || '')}"></div>
    <div class="field"><label>边界 / 说明</label>
      <textarea id="wbNodeDesc" rows="2" placeholder="这条流程从哪开始、到哪结束"></textarea></div>
    <div class="tiny muted" id="wbNodeHint"></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="workbench.submitNode">创建</button>`);
  fillParentOptions(level);
  if (parentId) {
    const select = document.getElementById('wbNodeParent');
    if (select) select.value = String(parentId);
  }
}

async function submitNode() {
  const value = (id) => (document.getElementById(id)?.value || '').trim();
  const level = Number(value('wbNodeLevel') || 1);
  const code = value('wbNodeCode');
  const name = value('wbNodeName');
  const parent = Number(value('wbNodeParent') || 0);
  if (!code || !name) return toast('编码和名称必填', true);
  if (level > 1 && !parent) return toast(`请先选择 L${level - 1} 上级`, true);
  try {
    await POST('/process-map', {
      code,
      name,
      level,
      parent_id: level > 1 ? parent : null,
      owner: value('wbNodeOwner') || null,
      description: value('wbNodeDesc') || null,
    });
    closeModal();
    toast(`已创建 ${code} ${name}`);
    renderWorkbench();
  } catch (error) {
    toast(errorText(error), true);
  }
}

/* -------------------------------------------------- 新建项目 */

function openProjectModal() {
  const methods = Object.entries(state.meta.methodology || {});
  const methodOptions = (methods.length ? methods : [['BPI', 'BPI']])
    .map(([code, label]) => `<option value="${code}">${esc(label)}</option>`)
    .join('');
  const processOptions = l3Rows(WB().rows).map((row) => (
    `<option value="${row.id}">${esc(row.code)} ${esc(row.name)}</option>`
  )).join('');
  openModal('新建项目', `
    <div class="field"><label>项目名称 *</label>
      <input id="wbProjectName" placeholder="如 采购需求提报流程优化"></div>
    <div class="row3">
      <div class="field"><label>方法</label>
        <select class="sel" id="wbProjectMethod">${methodOptions}</select></div>
      <div class="field"><label>关联流程（可选）</label>
        <select class="sel" id="wbProjectProcess">
          <option value="">暂不关联</option>${processOptions}
        </select></div>
      <div class="field"><label>Owner</label>
        <input id="wbProjectOwner" value="${esc((AUTH.user && AUTH.user.display_name) || '')}"></div>
    </div>
    <div class="field"><label>目标（可选）</label>
      <textarea id="wbProjectObjective" rows="2" placeholder="要改善什么，期望到什么水平"></textarea></div>`,
  `<button class="btn btn-g" data-act="ui.close">取消</button>
   <button class="btn btn-p" data-act="workbench.submitProject">创建并打开</button>`);
}

async function submitProject() {
  const value = (id) => (document.getElementById(id)?.value || '').trim();
  const name = value('wbProjectName');
  if (!name) return toast('项目名称必填', true);
  try {
    const created = await POST('/projects', {
      name,
      methodology: value('wbProjectMethod') || 'BPI',
      owner: value('wbProjectOwner') || '',
      process_id: Number(value('wbProjectProcess')) || null,
      objective: value('wbProjectObjective') || null,
    });
    pushRecent('project', created.id, projectLabel(created));
    closeModal();
    toast(`已创建 ${created.code || created.name}`);
    go('projects', { params: { project: created.id } });
  } catch (error) {
    toast(errorText(error), true);
  }
}

/* -------------------------------------------------- 交互 */

function openProcess(ident) {
  const id = Number(ident) || Number(document.getElementById('wbProcess')?.value || 0);
  if (!id) return toast('请先选择一条流程', true);
  const row = WB().rows.find((item) => item.id === id);
  pushRecent('process', id, row ? `${row.code} ${row.name}` : String(id));
  go('asset', { params: { process: id } });
}

on('workbench.go', ({ view }) => {
  if (view) go(view);
});
on('workbench.openProcess', ({ id }) => openProcess(id));
on('workbench.openProject', ({ id }) => {
  const projectId = Number(id);
  const row = WB().projects?.items?.find((item) => item.id === projectId);
  pushRecent('project', projectId, row ? projectLabel(row) : String(projectId));
  go('projects', { params: { project: projectId } });
});
on('workbench.newNode', ({ level }) => openNodeModal(Number(level) || 1));
on('workbench.newProcess', () => openNodeModal(3));
on('workbench.newActivity', () => {
  const parent = Number(document.getElementById('wbProcess')?.value || 0);
  if (!parent) return toast('请先选择一条 L3 流程', true);
  openNodeModal(4, parent);
});
on('workbench.newProject', () => openProjectModal());
on('workbench.level', (_, el) => fillParentOptions(Number(el.value) || 1));
on('workbench.submitNode', () => submitNode());
on('workbench.submitProject', () => submitProject());

export { renderWorkbench };
