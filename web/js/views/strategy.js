/* 视图：战略目标
 *
 * 目标之间没有上下级。左边先列目标，流程层级收在目标下面，默认只露出 L1。
 * 中间只展开当前这一条。右边是行动，以及要接着做的流程 / KPI。
 * 挂在上层的目标，下层流程卡按祖先继承能看见，不另建一条目标。
 */

import { esc, num, tipHelp } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, modalAlive, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { pageShell } from '../core/layout.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { canManage, canWrite } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { toolMountHtml } from './shared/tool_mount.js';

on('strategy.year', (_data, el) => setStrategyYear(Number(el.value)));
on('strategy.select', ({ id }) => selectObjective(Number(id)));
on('strategy.goMap', () => go('map'));
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
on('strategy.context', ({id}) => go('process_card',{params:{process:id,module:'context'},push:true}));
on('strategy.openProcess', ({ code, id, level }) => {
  // L3/L4 落到单流程 360 视图；L1/L2 仍回地图看架构上下文。
  if (Number(level) >= 3 && Number(id)) {
    go('process_card', { params: { process: id }, push: true });
    return;
  }
  state.map.pendingJump = code;
  go('map', { params: { process: code }, push: true });
});

function setStrategyYear(year) {
  state.strategy.year = year;
  state.strategy.selectedId = null;
  RENDERERS.strategy();
}

function selectObjective(id) {
  if (!id) return;
  state.strategy.selectedId = id;
  setUrlState('strategy', { ...urlParams(), objective: id });
  RENDERERS.strategy();
}

function ancestorChain(processId, byId) {
  const chain = [];
  const seen = new Set();
  let cursor = byId.get(processId);
  while (cursor && !seen.has(cursor.id)) {
    seen.add(cursor.id);
    chain.push(cursor);
    cursor = cursor.parent_id ? byId.get(cursor.parent_id) : null;
  }
  return chain.reverse();
}

function processTree(obj, processes) {
  const byId = new Map((processes || []).map((row) => [row.id, row]));
  const roots = new Map();
  (obj.links || []).forEach((link) => {
    const chain = ancestorChain(link.process_id, byId);
    let level = roots;
    let bucket = null;
    chain.forEach((node) => {
      if (!level.has(node.id)) {
        level.set(node.id, { node, children: new Map(), linked: false });
      }
      bucket = level.get(node.id);
      level = bucket.children;
    });
    if (bucket) bucket.linked = true;
  });
  return roots;
}

function objectiveButton(obj, selectedId) {
  const on = obj.id === selectedId;
  return `<button type="button" class="so-node${on ? ' on' : ''}"
    data-act="strategy.select" data-id="${obj.id}"
    ${on ? 'aria-current="true"' : ''}>
    <b>${esc(obj.name)}</b>
    <small>${esc(obj.owner || '未指派')} · ${esc(obj.status_label)}</small>
  </button>`;
}

function renderProcessNodes(map, depth) {
  return [...map.values()]
    .sort((a, b) => a.node.level - b.node.level
      || String(a.node.code).localeCompare(String(b.node.code)))
    .map((branch) => {
      const node = branch.node;
      const label = `L${node.level} ${esc(node.code)} ${esc(node.name)}${
        branch.linked ? ' · 已挂' : ''}`;
      const kids = renderProcessNodes(branch.children, depth + 1);
      if (!kids) {
        return `<div class="so-branch" style="--so-depth:${depth}">${label}</div>`;
      }
      return `<details class="so-fold" style="--so-depth:${depth}">
        <summary>${label}</summary>${kids}</details>`;
    }).join('');
}

function renderObjectiveTree(objectives, processes, selectedId) {
  if (!objectives.length) return '<div class="empty">该年度还没有战略目标</div>';
  return objectives.map((obj) => {
    const branches = renderProcessNodes(processTree(obj, processes), 1);
    return `<div class="so-obj">
      ${objectiveButton(obj, selectedId)}
      ${branches || '<div class="so-branch" style="--so-depth:1">还没挂到流程</div>'}
    </div>`;
  }).join('');
}

function inheritedConsumers(obj, processes) {
  const byParent = new Map();
  (processes || []).forEach((row) => {
    if (row.is_draft) return;
    const list = byParent.get(row.parent_id) || [];
    list.push(row);
    byParent.set(row.parent_id, list);
  });
  const direct = new Set((obj.links || []).map((link) => link.process_id));
  const seen = new Set();
  const out = [];
  const queue = [];
  direct.forEach((id) => {
    (byParent.get(id) || []).forEach((row) => queue.push(row));
  });
  while (queue.length) {
    const row = queue.shift();
    if (seen.has(row.id) || direct.has(row.id)) continue;
    seen.add(row.id);
    out.push(row);
    (byParent.get(row.id) || []).forEach((child) => queue.push(child));
  }
  out.sort((a, b) => a.level - b.level || String(a.code).localeCompare(String(b.code)));
  return out;
}

const renderStrategy = () => {
  const year = state.strategy.year || new Date().getFullYear();
  return renderAsync(
    'strategy',
    () => Promise.all([
      GET('/strategy/objectives?year=' + year),
      GET('/strategy/meta'),
      GET('/strategy/summary?year=' + year),
      GET('/tools').catch(() => []),
      GET('/process-map/flat').catch(() => []),
    ]).then(([objectives, meta, summary, tools, processes]) => ({
      objectives, meta, summary, tools, processes,
    })),
    (d) => {
      state.strategyYear = year;
      state.strategyMeta = d.meta;
      state.strategyObjectives = d.objectives;
      const s = d.summary;
      const params = urlParams();
      if (params.lifecycle && params.process) {
        const byId = new Map(d.processes.map((row) => [row.id, row]));
        const scope = new Set(ancestorChain(Number(params.process), byId).map((row) => row.id));
        d.objectives = d.objectives.filter((obj) => (obj.links || []).some((link) => scope.has(link.process_id)));
      }
      const wanted = Number(params.objective) || state.strategy.selectedId;
      const selected = d.objectives.find((row) => row.id === wanted) || d.objectives[0] || null;
      state.strategy.selectedId = selected ? selected.id : null;
      if (selected && String(params.objective || '') !== String(selected.id)) {
        setUrlState('strategy', { ...params, objective: selected.id });
      }
      const yearOptions = [year - 1, year, year + 1].map((value) =>
        `<option value="${value}"${value === year ? ' selected' : ''}>${value} 年</option>`).join('');
      const treeHtml = renderObjectiveTree(
        d.objectives, d.processes, state.strategy.selectedId);

      const shell = pageShell({
        title: '战略目标',
        badge: '<span class="module-badge">目标 → 流程 → KPI</span>',
        subtitle: '选一条目标，看它的指标、承接流程和下一步行动。',
        tip: tipHelp(
          '左边先点目标，流程层级收在这条目标下面，默认只露出 L1。'
          + '挂到流程或 KPI 的链接不进入总览优先级，三个分数在地图节点上改。',
          '本页说明',
        ),
        actions: `<button class="btn btn-g" data-act="strategy.goMap">去地图改优先级</button>
          <select class="sel sel-sm" data-act="strategy.year">${yearOptions}</select>
          ${canManage() ? '<button class="btn btn-p" data-act="strategy.new">+ 新建目标</button>' : ''}`,
        sections: [{
          key: 'main',
          html: `<div class="so-shell">
            <div class="so-side">
              <div class="card">
                <div class="so-count">${year} 年 · ${s.objective_count} 条目标 · 进行中 ${s.active_count}
                  · 未承接 ${s.unlinked_count}</div>
                <div class="so-tree">${treeHtml}</div>
              </div>
            </div>
            <div class="so-main-col">
              ${urlParams().lifecycle
                ? '<div class="tiny muted">当前目标列表已按流程及祖先承接筛选；以下年度汇总仍为全公司范围。</div>'
                : ''}
              ${detailHtml(selected)}
            </div>
            ${asideHtml(selected, d.tools, d.processes)}
          </div>`,
        }],
        active: 'main',
        mode: 'plain',
      });
      viewEl().innerHTML = shell.html;
    },
  );
};

function detailHtml(obj) {
  if (!obj) {
    return `<div class="card so-main"><div class="empty">这一年还没有目标。先新建一条，写清赢什么和目标值。</div></div>`;
  }
  const base = obj.baseline_value === null ? '—' : num(obj.baseline_value, 2);
  const target = obj.target_value === null ? '—' : num(obj.target_value, 2);
  return `
    <div class="card so-main">
      <div class="between mb">
        <h3>${esc(obj.name)}</h3>
        <span class="tag ${obj.status === 'ACTIVE' ? 't-grn' : 't-gry'}">${esc(obj.status_label)}</span>
      </div>
      <div class="desc" style="margin:0 0 12px">${esc(obj.code)} · ${obj.year} ${esc(obj.period_label)}</div>
      ${obj.description ? `<p class="tiny" style="line-height:1.65;margin:0 0 14px;white-space:pre-line">${esc(obj.description)}</p>` : ''}
      <div class="wb-meta">
        <div><label>目标值</label><span>${base} → ${target} ${esc(obj.unit || '')}</span></div>
        <div><label>责任人</label><span>${esc(obj.owner || '未指派')}</span></div>
        <div><label>来源</label><span>${esc(obj.source_document || '未填写')}</span></div>
        <div><label>承接</label><span>${obj.process_count} 条流程 · ${obj.kpi_count} 个 KPI</span></div>
      </div>
    </div>`;
}

function asideHtml(obj, tools, processes) {
  const linked = obj && (obj.links || []).find((link) => link.process_id);
  const mounted = toolMountHtml(tools, 'strategy', linked ? linked.process_id : null);
  const actions = obj ? `
    <div class="gap" style="flex-wrap:wrap">
      ${canWrite() ? `<button class="btn btn-p" data-act="strategy.initiate" data-id="${obj.id}">选流程 / 立项</button>` : ''}
      ${canManage() ? `
        <button class="btn btn-g" data-act="strategy.link" data-id="${obj.id}">承接</button>
        <button class="btn btn-g" data-act="strategy.edit" data-id="${obj.id}">编辑</button>
        ${obj.status === 'ACTIVE'
          ? `<button class="btn btn-g" data-act="strategy.archive" data-id="${obj.id}">归档</button>` : ''}` : ''}
    </div>` : '<div class="tiny muted">先在左侧点开一条目标。</div>';
  return `
    <div class="so-aside">
      <div class="card">
        <h3 style="margin:0 0 8px">行动</h3>
        ${actions}
        ${mounted}
      </div>
      <div class="card">
        <h3 style="margin:0 0 8px">谁要接着做</h3>
        ${consumerHtml(obj, processes)}
      </div>
    </div>`;
}

function consumerHtml(obj, processes) {
  if (!obj) return '<div class="tiny muted">选中目标后，这里列出承接的流程和 KPI。</div>';
  const links = (obj.links || []).map((link) => `
    <div class="bpmn-node-row">
      <div class="tiny">L${link.process_level || ''} ${esc(link.process_code || '')}
        ${esc(link.process_name || '')}${
          link.kpi_code ? `<br>KPI ${esc(link.kpi_code)} ${esc(link.kpi_name || '')}` : ''}${
          link.note ? `<br>${esc(link.note)}` : ''}</div>
      <div class="gap" style="margin-top:4px">
        ${link.process_code
          ? `<button class="btn-sm" data-act="strategy.openProcess"
              data-code="${esc(link.process_code)}" data-id="${link.process_id}"
              data-level="${link.process_level || ''}">核对流程</button>` : ''}
        ${Number(link.process_level) === 3 ? `<button class="btn-sm" data-act="strategy.context" data-id="${link.process_id}">边界与交接</button>` : ''}
        ${canManage()
          ? `<button class="btn-sm" data-act="strategy.unlink"
              data-id="${obj.id}" data-link="${link.id}">移除</button>` : ''}
      </div>
    </div>`).join('');
  if (!links) {
    return '<div class="tiny muted">还没有流程要接这条目标。先点「承接」。</div>';
  }
  const inherited = inheritedConsumers(obj, processes).length;
  const extra = inherited
    ? `<div class="tiny muted" style="margin-top:8px">下面还有 ${inherited} 条活动，跟上面的流程一起看。</div>`
    : '';
  return links + extra;
}

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
