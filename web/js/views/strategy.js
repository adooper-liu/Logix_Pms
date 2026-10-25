/* 视图：战略目标
 *
 * 一张目标卡 + 承接关系：目标 → L1/L2/L3 流程 → 可选 KPI。
 * 流程卡按祖先继承反查，L3/L4 能看到挂在 L1/L2 的目标。
 */

import { esc, num } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, modalAlive, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go } from '../core/router.js';
import { canManage, canWrite } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';

on('strategy.year', (_data, el) => setStrategyYear(Number(el.value)));
on('strategy.new', () => objectiveModal());
on('strategy.edit', ({ id }) => editObjective(Number(id)));
on('strategy.submit', ({ id }) => submitObjective(id ? Number(id) : null));
on('strategy.close', () => closeModal());
on('strategy.link', ({ id }) => linkModal(Number(id)));
on('strategy.submitLink', ({ id }) => submitLink(Number(id)));
on('strategy.initiate', ({ id }) => initiateProject(Number(id)));
on('strategy.submitInitiate', ({ id }) => submitInitiate(Number(id)));
on('strategy.unlink', ({ id, link }) => unlinkObjective(Number(id), Number(link)));
on('strategy.archive', ({ id }) => archiveObjective(Number(id)));
on('strategy.openProcess', ({ code }) => {
  state.map.pendingJump = code;
  go('map', { params: { process: code }, push: true });
});

function setStrategyYear(year) {
  state.strategy.year = year;
  RENDERERS.strategy();
}

const renderStrategy = () => {
  const year = state.strategy.year || new Date().getFullYear();
  return renderAsync(
    'strategy',
    () => Promise.all([
      GET('/strategy/objectives?year=' + year),
      GET('/strategy/meta'),
      GET('/strategy/summary?year=' + year),
    ]).then(([objectives, meta, summary]) => ({ objectives, meta, summary })),
    (d) => {
      state.strategyYear = year;
      state.strategyMeta = d.meta;
      state.strategyObjectives = d.objectives;
      const s = d.summary;
      const yearOptions = [year - 1, year, year + 1].map((value) =>
        `<option value="${value}"${value === year ? ' selected' : ''}>${value} 年</option>`).join('');

      const cards = d.objectives.map((obj) => {
        const links = obj.links.map((link) => `
          <div class="between bpmn-node-row">
            <span class="tiny">L${link.process_level || ''} ${esc(link.process_code || '')}
              ${esc(link.process_name || '')}${
                link.kpi_code ? ` · KPI ${esc(link.kpi_code)} ${esc(link.kpi_name || '')}` : ''}</span>
            <span class="gap">
              ${link.process_code
                ? `<button class="btn-sm" data-act="strategy.openProcess"
                    data-code="${esc(link.process_code)}">看流程</button>` : ''}
              ${canManage()
                ? `<button class="btn-sm" data-act="strategy.unlink"
                    data-id="${obj.id}" data-link="${link.id}">移除</button>` : ''}
            </span>
          </div>`).join('') || '<div class="tiny muted">尚未承接流程或 KPI</div>';
        return `
          <div class="card">
            <div class="between mb">
              <div>
                <h3 style="margin:0">${esc(obj.name)}
                  <span class="tag ${obj.status === 'ACTIVE' ? 't-grn' : 't-gry'}">${
                    esc(obj.status_label)}</span></h3>
                <div class="desc" style="margin:2px 0 0">
                  ${esc(obj.code)} · ${obj.year} ${esc(obj.period_label)}
                  · 责任人 ${esc(obj.owner || '未指派')}
                  ${obj.source_document ? ' · 来源 ' + esc(obj.source_document) : ''}</div>
              </div>
              <div class="gap">
                ${canWrite() ? `
                  <button class="btn-sm btn-p" data-act="strategy.initiate"
                    data-id="${obj.id}">选流程 / 立项</button>` : ''}
                ${canManage() ? `
                  <button class="btn-sm" data-act="strategy.link" data-id="${obj.id}">承接</button>
                  <button class="btn-sm" data-act="strategy.edit" data-id="${obj.id}">编辑</button>
                  ${obj.status === 'ACTIVE'
                    ? `<button class="btn-sm btn-g" data-act="strategy.archive"
                        data-id="${obj.id}">归档</button>` : ''}` : ''}
              </div>
            </div>
            ${obj.description ? `<div class="tiny muted mb">${esc(obj.description)}</div>` : ''}
            <div class="mb">
              <b>目标值</b>
              <span class="tag t-blu">${obj.baseline_value === null ? '—' : num(obj.baseline_value, 2)}
                → ${obj.target_value === null ? '—' : num(obj.target_value, 2)}
                ${esc(obj.unit || '')}</span>
              <span class="tiny muted">承接 ${obj.process_count} 条流程 · ${obj.kpi_count} 个 KPI</span>
            </div>
            ${links}
          </div>`;
      }).join('') || '<div class="card"><div class="empty">该年度还没有战略目标</div></div>';

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>战略目标<span class="module-badge">目标 → 流程 → KPI</span></h2>
              <div class="desc">目标只写“赢什么、目标值、责任人、来源”；
                承接关系按流程层级继承，L3/L4 能看到挂在 L1/L2 的目标</div></div>
            <div class="gap">
              <select class="sel sel-sm" data-act="strategy.year">${yearOptions}</select>
              ${canManage() ? '<button class="btn btn-p" data-act="strategy.new">+ 新建目标</button>' : ''}
            </div>
          </div>
        </div>
        <div class="grid g4 stat-row">
          <div class="kpi stat"><div class="num">${s.objective_count}</div><div class="lab">年度目标</div></div>
          <div class="kpi stat"><div class="num">${s.active_count}</div><div class="lab">进行中</div></div>
          <div class="kpi stat"><div class="num">${s.linked_count}</div><div class="lab">已承接流程</div></div>
          <div class="kpi stat"><div class="num">${s.unlinked_count}</div><div class="lab">未承接（需补）</div></div>
        </div>
        <div class="grid g2">${cards}</div>`;
    },
  );
};

async function editObjective(objectiveId) {
  try {
    const obj = await GET('/strategy/objectives/' + objectiveId);
    objectiveModal(obj);
  } catch (e) {
    toast(e.message, true);
  }
}

function objectiveModal(obj = null) {
  const meta = state.strategyMeta || { period_labels: {}, status_labels: {} };
  const value = (key) => (obj && obj[key] !== null && obj[key] !== undefined ? obj[key] : '');
  const options = (labels, selected) => Object.entries(labels || {}).map(([code, label]) =>
    `<option value="${esc(code)}"${code === selected ? ' selected' : ''}>${esc(label)}</option>`)
    .join('');
  const year = state.strategy.year || new Date().getFullYear();
  openModal(obj ? '编辑战略目标 · ' + obj.code : '新建战略目标', `
    <div class="row2">
      <div class="field"><label>目标名称 *</label>
        <input id="soName" value="${esc(value('name'))}" placeholder="如 采购周期缩短 50%"></div>
      <div class="field"><label>目标编码</label>
        <input id="soCode" value="${esc(value('code'))}" placeholder="留空自动生成"></div>
    </div>
    <div class="field"><label>目标描述</label>
      <textarea id="soDesc" rows="2" placeholder="目标的口径、边界与取舍">${esc(value('description'))}</textarea></div>
    <div class="row3">
      <div class="field"><label>年度 *</label>
        <input id="soYear" type="number" min="2000" max="2100" value="${value('year') || year}"></div>
      <div class="field"><label>周期</label>
        <select id="soPeriod">${options(meta.period_labels, value('period') || 'ANNUAL')}</select></div>
      <div class="field"><label>状态</label>
        <select id="soStatus">${options(meta.status_labels, value('status') || 'ACTIVE')}</select></div>
    </div>
    <div class="row3">
      <div class="field"><label>基线值</label>
        <input id="soBase" type="number" step="0.01" value="${value('baseline_value')}"></div>
      <div class="field"><label>目标值</label>
        <input id="soTarget" type="number" step="0.01" value="${value('target_value')}"></div>
      <div class="field"><label>单位</label>
        <input id="soUnit" value="${esc(value('unit'))}" placeholder="天 / % / 元"></div>
    </div>
    <div class="row2">
      <div class="field"><label>责任人</label>
        <select id="soOwner"><option value="">未指派</option></select></div>
      <div class="field"><label>来源文件</label>
        <input id="soSource" value="${esc(value('source_document'))}" placeholder="如 2026 年度经营计划"></div>
    </div>
    <div class="note">目标本身不直接改流程；承接关系在目标卡上维护。</div>`,
    `<button class="btn btn-g" data-act="strategy.close">取消</button>
     <button class="btn btn-p" data-act="strategy.submit"
       data-id="${obj ? obj.id : ''}">${obj ? '保存' : '创建'}</button>`);

  GET('/execution/assignees').then((users) => {
    const sel = document.getElementById('soOwner');
    if (!sel) return;
    users.forEach((user) => {
      const o = document.createElement('option');
      o.value = String(user.id);
      o.textContent = user.display_name + ' · ' + (user.role_label || user.role);
      o.selected = !!obj && obj.owner_user_id === user.id;
      sel.appendChild(o);
    });
  }).catch(() => {});
}

async function submitObjective(objectiveId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numOrNull = (id) => (val(id).trim() === '' ? null : Number(val(id)));
  const textOrNull = (id) => val(id).trim() || null;
  const name = val('soName').trim();
  const year = Number(val('soYear'));
  if (!name) return toast('请填写目标名称', true);
  if (!year) return toast('请填写年度', true);
  const ownerId = val('soOwner');
  const payload = {
    name,
    description: textOrNull('soDesc'),
    year,
    period: val('soPeriod'),
    status: val('soStatus'),
    baseline_value: numOrNull('soBase'),
    target_value: numOrNull('soTarget'),
    unit: textOrNull('soUnit'),
    source_document: textOrNull('soSource'),
    owner_user_id: ownerId ? Number(ownerId) : null,
  };
  if (val('soCode').trim()) payload.code = val('soCode').trim();
  try {
    if (objectiveId) {
      await PATCH('/strategy/objectives/' + objectiveId, payload);
      toast('战略目标已更新');
    } else {
      await POST('/strategy/objectives', payload);
      toast('战略目标已创建');
    }
    closeModal();
    RENDERERS.strategy();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 选流程 / 立项 */

function initiateProject(objectiveId) {
  const objective = (state.strategyObjectives || []).find((row) => row.id === objectiveId);
  if (!objective) return;
  const gen = openModal('从战略目标立项', '<div class="empty">加载流程…</div>');
  GET('/process-map/flat')
    .then((rows) => {
      if (!modalAlive(gen)) return;
      const linked = new Set((objective.links || []).map((link) => link.process_id));
      const candidates = rows
        .filter((row) => row.level >= 3)
        .sort((a, b) => {
          const linkedOrder = (linked.has(b.id) ? 1 : 0) - (linked.has(a.id) ? 1 : 0);
          return linkedOrder || a.level - b.level || a.code.localeCompare(b.code);
        });
      const options = candidates.map((row) =>
        `<option value="${row.id}" data-name="${esc(row.name)}">L${row.level} ${esc(row.code)} ${
          esc(row.name)}${linked.has(row.id) ? ' · 已承接' : ''}</option>`).join('');
      const target = objective.baseline_value === null && objective.target_value === null
        ? ''
        : ` · 目标 ${objective.baseline_value === null ? '—' : num(objective.baseline_value, 2)}
          → ${objective.target_value === null ? '—' : num(objective.target_value, 2)}
          ${esc(objective.unit || '')}`;
      openModal('从战略目标选流程 / 立项', `
        <div class="note mb">承接目标：<b>${esc(objective.code)} ${esc(objective.name)}</b>${target}</div>
        ${options ? `
          <div class="field"><label>要改善的流程（L3/L4）*</label>
            <select id="siProcess">${options}</select>
            <div class="hint">已承接的流程排在前面；选定后进入立项向导，目标值会自动预填</div></div>`
          : '<div class="empty">还没有可立项的 L3/L4 流程，请先到流程地图建立架构。</div>'}`,
        `${options
          ? `<button class="btn btn-g" data-act="strategy.close">取消</button>
             <button class="btn btn-p" data-act="strategy.submitInitiate"
               data-id="${objective.id}">进入立项</button>`
          : '<button class="btn btn-g" data-act="strategy.close">关闭</button>'}`);
    })
    .catch((e) => {
      if (!modalAlive(gen)) return;
      openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
    });
}

function submitInitiate(objectiveId) {
  const sel = document.getElementById('siProcess');
  if (!sel || !sel.value) return toast('请选择流程', true);
  const option = sel.selectedOptions[0];
  const processName = option ? option.dataset.name || '' : '';
  closeModal();
  go('projects', {
    params: {
      new_process: Number(sel.value),
      new_name: processName,
      new_objective: objectiveId,
    },
    push: true,
  });
}

function linkModal(objectiveId) {
  openModal('承接流程 / KPI', `
    <div class="field"><label>流程（L1–L4）*</label>
      <select id="slProcess"><option value="">请选择</option></select></div>
    <div class="field"><label>KPI（可选）</label>
      <select id="slKpi"><option value="">只承接流程</option></select>
      <div class="hint">选中 KPI 时，KPI 必须挂在该流程或其下级</div></div>
    <div class="field"><label>说明</label>
      <input id="slNote" placeholder="如 端到端周期主指标"></div>`,
    `<button class="btn btn-g" data-act="strategy.close">取消</button>
     <button class="btn btn-p" data-act="strategy.submitLink"
       data-id="${objectiveId}">新增承接</button>`);

  Promise.all([GET('/process-map/flat'), GET('/monitor/kpis')])
    .then(([processes, kpis]) => {
      const procSel = document.getElementById('slProcess');
      if (procSel) {
        processes.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = 'L' + row.level + ' ' + row.code + ' ' + row.name;
          procSel.appendChild(o);
        });
      }
      const kpiSel = document.getElementById('slKpi');
      if (kpiSel) {
        kpis.forEach((row) => {
          const o = document.createElement('option');
          o.value = String(row.id);
          o.textContent = row.code + ' ' + row.name;
          kpiSel.appendChild(o);
        });
      }
    })
    .catch(() => {});
}

async function submitLink(objectiveId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  if (!val('slProcess')) return toast('请选择流程', true);
  try {
    await POST('/strategy/objectives/' + objectiveId + '/links', {
      process_id: Number(val('slProcess')),
      kpi_id: val('slKpi') ? Number(val('slKpi')) : null,
      note: val('slNote').trim() || null,
    });
    closeModal();
    toast('承接关系已新增');
    RENDERERS.strategy();
  } catch (e) {
    toast(e.message, true);
  }
}

async function unlinkObjective(objectiveId, linkId) {
  try {
    await DEL('/strategy/objectives/' + objectiveId + '/links/' + linkId);
    toast('承接关系已移除');
    RENDERERS.strategy();
  } catch (e) {
    toast(e.message, true);
  }
}

async function archiveObjective(objectiveId) {
  const ok = await confirmDialog('归档后目标仍保留承接关系与历史，但不再计入进行中。继续？',
    { title: '归档战略目标', okText: '归档' });
  if (!ok) return;
  try {
    await PATCH('/strategy/objectives/' + objectiveId, { status: 'ARCHIVED' });
    toast('目标已归档');
    RENDERERS.strategy();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderStrategy };
