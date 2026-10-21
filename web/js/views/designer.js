/* 视图：designer */
import { esc, num, dur, NODE_LABEL, NODE_CLASS } from '../core/format.js';
import { toast, openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { metricHelp } from '../core/metrics.js';
import { API_BASE, GET, POST, PUT, getToken } from '../core/api.js';
import { openToolByCode } from './toolbox.js';

/* ============================================================ 6. 流程设计器 */

async function openDesigner(processId) {
  state.designer.processId = processId;
  go('designer');
}

const renderDesigner = () => {
  const load = async () => {
    if (!state.designer.processes) {
      const rows = await GET('/process-map/flat');
      state.designer.processes = rows.filter((r) => r.level >= 3);
    }
    const list = state.designer.processes;
    if (!state.designer.processId && list.length) {
      const preferred = list.find((r) => r.code === 'L3-032') || list[0];
      state.designer.processId = preferred.id;
    }
    if (state.designer.processId) {
      const id = state.designer.processId;
      const [model, analysis] = await Promise.all([
        GET('/processes/' + id + '/design'),
        POST('/processes/' + id + '/design/analyze', {}),
      ]);
      state.designer.model = model;
      state.designer.savedModel = cloneModel(model);   // 回滚基准
      state.designer.analysis = analysis;
      state.designer.processCode = (list.find((r) => r.id === id) || {}).code;
    }
  };
  renderAsync('designer', load, () => paintDesigner());
};

function paintDesigner() {
  const st = state.designer;
  const model = st.model;
  if (!model) {
    viewEl().innerHTML = '<div class="card"><div class="empty">请先选择一条流程</div></div>';
    return;
  }
  const opts = st.processes.map((p) =>
    '<option value="' + p.id + '"' + (p.id === st.processId ? ' selected' : '') + '>' +
    'L' + p.level + ' ' + esc(p.code) + ' ' + esc(p.name) + '</option>').join('');

  // 按泳道分组，泳道顺序取该泳道最早出现的节点顺序
  const lanes = [];
  const laneOf = {};
  model.nodes.slice().sort((a, b) => a.sequence_order - b.sequence_order).forEach((n) => {
    if (!laneOf[n.lane]) {
      laneOf[n.lane] = { name: n.lane, nodes: [], first: n.sequence_order };
      lanes.push(laneOf[n.lane]);
    }
    laneOf[n.lane].nodes.push(n);
  });
  lanes.sort((a, b) => a.first - b.first);

  // 按钮用下标引用泳道名，避免把用户输入拼进 onclick 属性
  st.lanes = lanes.map((l) => l.name);

  const proc = (st.processes || []).find((p) => p.id === st.processId) || {};
  const editable = canWrite() && (canManage()
    || (AUTH.user && proc.owner_user_id === AUTH.user.id));

  const bnSet = new Set((st.analysis ? st.analysis.nodes : []).filter((n) => n.is_bottleneck)
    .map((n) => n.node_key));
  const metricOf = {};
  (st.analysis ? st.analysis.nodes : []).forEach((n) => { metricOf[n.node_key] = n; });

  const laneHtml = lanes.map((l, laneIdx) => `
    <div class="lane">
      <div class="lane-hd"><span>${esc(l.name)}</span>
        <span class="tiny">${l.nodes.length} 个活动</span></div>
      <div class="lane-bd">
        ${l.nodes.map((n, i) => `
          <div class="node ${NODE_CLASS[n.node_type] || ''} ${bnSet.has(n.node_key) ? 'bn' : ''}"
               onclick="openNodeEditor('${n.node_key}')">
            ${bnSet.has(n.node_key) ? '<span class="bnbadge">瓶颈</span>' : ''}
            <b>${esc(n.name)}</b>
            <div class="meta">⏱ ${dur(n.duration_minutes)}${n.wait_minutes > 0
              ? ' <span style="color:var(--bad)">+等 ' + dur(n.wait_minutes) + '</span>' : ''}</div>
            <div class="meta">${NODE_LABEL[n.node_type] || n.node_type}
              ${n.owner_role ? ' · ' + esc(n.owner_role) : ''}
              ${n.is_value_added ? '' : ' · <span style="color:var(--warn)">非增值</span>'}</div>
            ${metricOf[n.node_key] && metricOf[n.node_key].visit_count > 1.001
              ? '<div class="meta" style="color:var(--bad)">↻ 期望执行 '
                + num(metricOf[n.node_key].visit_count, 2) + ' 次</div>'
              : ''}
          </div>${i < l.nodes.length - 1 ? '<span style="color:var(--line-strong);font-size:16px">→</span>' : ''}`).join('')}
        <button class="add" onclick="addDesignerNode(${laneIdx})"${editable ? '' : ' disabled style="opacity:.4;cursor:not-allowed"'}>+ 添加活动</button>      </div>
    </div>`).join('') || '<div class="empty">这条流程还没有建模，点击下方「添加泳道节点」开始</div>';

  const tab = st.tab || 'model';
  const tabBar = `
    <div class="seg">
      <button class="${tab === 'model' ? 'on' : ''}" onclick="setDesignerTab('model')">流程模型</button>
      <button class="${tab === 'analysis' ? 'on' : ''}" onclick="setDesignerTab('analysis')">
        指标与建议${st.analysis ? ' · ' + st.analysis.suggestions.length : ''}</button>
    </div>`;

  const modelPane = `
    <div class="card">
      <div class="legend mb">
        <span><i style="background:var(--ok)"></i>开始</span>
        <span><i style="background:var(--warn)"></i>审批/判断门</span>
        <span><i style="background:var(--bad)"></i>结束</span>
        <span><i style="background:var(--line-strong)"></i>等待</span>
        <span><i style="background:var(--line)"></i>普通作业</span>
        <span class="muted">节点右上角「瓶颈」来自测算结果</span>
      </div>
      ${laneHtml}
    </div>`;

  const analysisPane = `
    <div class="grid g2">
      <div class="card">
        <h3>流程指标测算</h3>
        <div class="desc">全部由当前节点数据算出，不是拍脑袋</div>
        ${paintMetrics(st.analysis)}
      </div>
      <div class="card">
        <h3>${metricHelp('suggestion_rules', '改善建议')}</h3>
        <div class="desc">${st.analysis ? st.analysis.suggestions.length : 0} 条 · 按严重度排序，
          ${metricHelp('methodology_pick', '推荐方法论')}：<b>${esc((state.meta.methodology[st.analysis && st.analysis.recommended_methodology] ||
            (st.analysis && st.analysis.recommended_methodology) || '—'))}</b></div>
        ${paintSuggestions(st.analysis)}
      </div>
    </div>`;

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>流程设计器<span class="module-badge">建模与测算</span> · ${esc(model.process_name || '')}</h2>
          <div class="desc">泳道式建模 · 点击节点编辑 · 改动即时保存并重算指标；模型用于流程执行（实例使用启动时快照）</div>
        </div>
        <div class="gap">
          <select class="sel" onchange="switchProcess(this.value)">${opts}</select>
          <button class="btn btn-g" onclick="exportBpmn()">导出 BPMN</button>
          ${editable ? '<button class="btn btn-g" onclick="importBpmn()">导入 BPMN</button>' : ''}
          ${editable
            ? '<button class="btn btn-g" onclick="addLaneNode()">+ 添加泳道节点</button>'
            : '<span class="tiny" style="align-self:center">只读（你不是这条流程的 Owner）</span>'}
          <a class="link" onclick="go('execution')">去流程执行 →</a>
          <button class="btn btn-p" onclick="reanalyze()">重新测算</button>
        </div>
      </div>
      <div class="mt">${tabBar}</div>
    </div>
    ${tab === 'analysis' ? analysisPane : modelPane}`;
}

function setDesignerTab(tab) {
  state.designer.tab = tab;
  RENDERERS.designer();
}

/* -------------------------------------------------- BPMN 导入 / 导出 */

async function exportBpmn() {
  const id = state.designer.processId;
  if (!id) return toast('请先选择一条流程', true);
  try {
    const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
      headers: { Authorization: 'Bearer ' + getToken() },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || ('导出失败（' + res.status + '）'));
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (state.designer.processCode || 'process') + '.bpmn';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('BPMN 已导出');
  } catch (e) {
    toast(e.message, true);
  }
}

function importBpmn() {
  const id = state.designer.processId;
  if (!id) return toast('请先选择一条流程', true);
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.bpmn,.xml,text/xml,application/xml';
  input.onchange = async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    try {
      const xml = await file.text();
      const res = await fetch(API_BASE + '/processes/' + id + '/bpmn', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + getToken(),
        },
        body: JSON.stringify({
          xml,
          expected_version: state.designer.model ? state.designer.model.version : null,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || ('导入失败（' + res.status + '）'));
      state.designer.model = body;
      state.designer.savedModel = cloneModel(body);
      state.designer.analysis = await POST(
        '/processes/' + id + '/design/analyze', {});
      toast('BPMN 已导入并更新模型');
      RENDERERS.designer();
    } catch (e) {
      toast(e.message, true);
    }
  };
  input.click();
}

function paintMetrics(a) {
  if (!a) return '<div class="empty">暂无测算结果</div>';
  const m = a.metrics;

  // ratio 为 null 时不画进度条 —— 没有目标值的指标（周期、成本、移交次数）
  // 画条只能是编出来的百分比，那是误导，不如老实显示数字。
  const row = (label, value, hint, ratio, color) => {
    const hasBar = ratio !== null && ratio !== undefined && isFinite(ratio);
    const w = hasBar ? Math.max(0, Math.min(100, ratio)) : 0;
    return `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <span style="width:112px;font-size:12.5px">${label}</span>
        ${hasBar
          ? '<span style="flex:1;height:7px;background:var(--line-soft);border-radius:4px;overflow:hidden">' +
            '<i style="display:block;height:100%;border-radius:4px;width:' + w + '%;background:' + color + '"></i></span>'
          : '<span style="flex:1"></span>'}
        <span style="width:118px;font-size:12.5px;font-weight:600;text-align:right">${value}
          <span class="tiny" style="display:block;font-weight:400;line-height:1.4">${hint}</span></span>
      </div>`;
  };

  const pce = m.pce * 100;
  const waitShare = m.wait_ratio * 100;
  const workShare = m.lead_time_minutes ? (m.process_time_minutes / m.lead_time_minutes) * 100 : 0;
  const reworkShare = m.process_time_minutes
    ? (m.rework_work_minutes / m.process_time_minutes) * 100 : 0;

  const warn = m.diverged
    ? '<div class="warnbox mb">模型存在无法退出的环路或没有入口，当前已退回「每个节点各算一次」的粗略口径，'
      + '结果不可信。请检查连线与开始节点。</div>'
    : '';

  // 期望值 vs 线性合计：有分支/回路时两者会明显不同，必须让用户看见差别
  const cycleHint = m.has_branch_or_loop
    ? '线性合计 ' + dur(m.linear_lead_time_minutes) + '（旧口径，未计回路）'
    : '无分支回路，与线性合计一致';

  return warn +
    row(metricHelp('pce', '流程周期效率'), num(pce, 1) + '%', '增值 / 期望端到端',
      pce, pce >= 35 ? 'var(--ok)' : pce >= 15 ? 'var(--warn)' : 'var(--bad)') +
    row(metricHelp('wait_ratio', '等待占比'), num(waitShare, 1) + '%', num(m.wait_minutes, 0) + ' 分钟等待',
      waitShare, waitShare >= 50 ? 'var(--bad)' : waitShare >= 30 ? 'var(--warn)' : 'var(--ok)') +
    row(metricHelp('work_share', '作业时间占比'), num(workShare, 1) + '%', num(m.process_time_minutes, 0) + ' 分钟作业',
      workShare, 'var(--brand)') +
    row(metricHelp('rework_loss', '返工损失'), dur(m.rework_loss_minutes),
      '额外作业 ' + dur(m.rework_work_minutes) + ' · 占作业 ' + num(reworkShare, 1) + '%',
      reworkShare, reworkShare >= 15 ? 'var(--bad)' : reworkShare > 0 ? 'var(--warn)' : 'var(--ok)') +
    row(metricHelp('lead_time', '期望端到端周期'), dur(m.lead_time_minutes), cycleHint, null, '') +
    row(metricHelp('handoff_count', '跨泳道移交'), m.handoff_count + ' 次', m.lane_count + ' 个部门/角色', null, '') +
    row(metricHelp('approval_levels', '累计审批层级'), m.total_approval_levels + ' 层',
      m.approval_node_count + ' 个审批节点', null, '') +
    row(metricHelp('unit_cost', '单次执行成本'), num(m.unit_cost, 1) + ' 元', '全部节点的期望成本合计', null, '') +
    '<div class="note" style="margin-top:4px">按月 1000 单估算，' + metricHelp('fte_saved', '可释放人天/月') + '约 <b>' +
      num(m.fte_days_saved_per_month, 0) + ' 人天/月</b>（仅计返工带来的额外作业时间）。</div>';
}

function paintSuggestions(a) {
  if (!a || !a.suggestions.length) return '<div class="empty">暂无建议</div>';
  // 建议里的 related_nodes 是节点键，展示时翻成中文名
  const nameOf = {};
  ((state.designer.model || {}).nodes || []).forEach((n) => { nameOf[n.node_key] = n.name; });

  return a.suggestions.map((s) => `
    <div class="sug ${s.severity}">
      <div class="hd">
        <span>${s.severity === 'HIGH' ? '🔴' : s.severity === 'MEDIUM' ? '🟡' : '🟢'} ${esc(s.title)}</span>
        <span class="tag ${{ HIGH: 't-red', MEDIUM: 't-yel', LOW: 't-blu' }[s.severity]}">
          ${s.severity === 'HIGH' ? '高' : s.severity === 'MEDIUM' ? '中' : '低'}</span>
      </div>
      <div class="bd">${esc(s.detail)}</div>
      ${s.related_nodes && s.related_nodes.length
        ? '<div class="tiny" style="margin-top:6px">涉及节点：' +
          s.related_nodes.map((k) => esc(nameOf[k] || k)).join('、') + '</div>' : ''}
      ${s.suggested_tool ? '<button class="tool" onclick="openToolByCode(\'' + s.suggested_tool +
        '\')">→ 用「' + esc(s.suggested_tool) + '」动手</button>' : ''}
    </div>`).join('');
}

function switchProcess(id) {
  state.designer.processId = Number(id);
  state.designer.processCode = (state.designer.processes.find((p) => p.id === Number(id)) || {}).code;
  RENDERERS.designer();
}

async function reanalyze() {
  try {
    state.designer.analysis = await POST('/processes/' + state.designer.processId + '/design/analyze', {});
    paintDesigner();
    toast('已重新测算');
  } catch (e) {
    toast(e.message, true);
  }
}

function cloneModel(model) {
  return JSON.parse(JSON.stringify(model));
}

/** 把当前内存中的模型整份提交给后端（后端是覆盖式保存）
 *
 *  节点编辑是「先改内存模型，再提交」的乐观更新。一旦后端拒绝（比如唯一键冲突、
 *  连线悬空），必须把模型回滚到最后一个服务端确认过的版本并重绘，
 *  否则内存里的模型和界面显示就分叉了，下次重绘会冒出从未保存成功的节点。
 */
async function persistDesign(successMsg) {
  const st = state.designer;
  const payload = {
    nodes: st.model.nodes.map((n) => ({
      node_key: n.node_key, name: n.name, node_type: n.node_type, lane: n.lane,
      owner_role: n.owner_role, duration_minutes: n.duration_minutes, wait_minutes: n.wait_minutes,
      cost: n.cost, rework_rate: n.rework_rate, approval_levels: n.approval_levels,
      is_value_added: n.is_value_added, sequence_order: n.sequence_order,
      position_x: n.position_x, position_y: n.position_y,
    })),
    edges: st.model.edges.map((e) => ({
      source_key: e.source_key, target_key: e.target_key,
      label: e.label, condition: e.condition, probability: e.probability,
    })),
    // 带上「我编辑时所基于的版本」，服务端据此发现别人的并发修改
    expected_version: st.savedModel ? st.savedModel.version : null,
  };
  try {
    st.model = await PUT('/processes/' + st.processId + '/design', payload);
    st.savedModel = cloneModel(st.model);
    st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
    paintDesigner();
    if (successMsg) toast(successMsg);
  } catch (e) {
    if (e.status === 409) {
      // 别人先保存了：丢弃本地改动并重新载入最新版本，而不是覆盖别人的劳动成果
      toast(e.message + ' 已为你载入最新版本。', true);
      await reloadDesign();
      return;
    }
    st.model = cloneModel(st.savedModel);
    paintDesigner();
    toast('保存失败，已回滚到上次保存的版本：' + e.message, true);
  }
}

/** 丢弃本地改动，重新拉取服务端的最新模型与分析结果 */
async function reloadDesign() {
  const st = state.designer;
  try {
    const [model, analysis] = await Promise.all([
      GET('/processes/' + st.processId + '/design'),
      POST('/processes/' + st.processId + '/design/analyze', {}),
    ]);
    st.model = model;
    st.savedModel = cloneModel(model);
    st.analysis = analysis;
    paintDesigner();
  } catch (e) {
    toast(e.message, true);
  }
}

/** 节点点击入口：有权限就编辑，没权限就看只读详情 */
function openNodeEditor(nodeKey) {
  const st = state.designer;
  const proc = (st.processes || []).find((p) => p.id === st.processId) || {};
  const editable = canWrite() && (canManage()
    || (AUTH.user && proc.owner_user_id === AUTH.user.id));
  if (editable) return editNode(nodeKey);

  const n = (st.model.nodes || []).find((x) => x.node_key === nodeKey);
  if (!n) return;
  const m = (st.analysis ? st.analysis.nodes : []).find((x) => x.node_key === nodeKey) || {};
  openModal(n.name + ' · 节点详情', `
    <div class="row2">
      <div class="field"><label>节点类型</label>
        <input value="${NODE_LABEL[n.node_type] || n.node_type}" readonly></div>
      <div class="field"><label>所属泳道</label><input value="${esc(n.lane)}" readonly></div>
    </div>
    <div class="row2">
      <div class="field"><label>负责人 / 岗位</label>
        <input value="${esc(n.owner_role || '未指定')}" readonly></div>
      <div class="field"><label>是否增值</label>
        <input value="${n.is_value_added ? '增值（VA）' : '非增值（NVA）'}" readonly></div>
    </div>
    <div class="row3">
      <div class="field"><label>作业时间</label><input value="${dur(n.duration_minutes)}" readonly></div>
      <div class="field"><label>等待时间</label><input value="${dur(n.wait_minutes)}" readonly></div>
      <div class="field"><label>返工率</label><input value="${num(n.rework_rate * 100, 0)}%" readonly></div>
    </div>
    <div class="row3">
      <div class="field"><label>审批层级</label><input value="${n.approval_levels}" readonly></div>
      <div class="field"><label>期望执行次数</label>
        <input value="${m.visit_count === undefined ? '—' : num(m.visit_count, 2)}" readonly></div>
      <div class="field"><label>对周期贡献</label>
        <input value="${m.weighted_minutes === undefined ? '—' : dur(m.weighted_minutes)}" readonly></div>
    </div>
    <div class="note">当前角色无编辑权限，如需修改请联系这条流程的 Owner 或流程管理科。</div>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
}

function editNode(nodeKey) {
  const n = state.designer.model.nodes.find((x) => x.node_key === nodeKey);
  if (!n) return;
  const laneList = [...new Set(state.designer.model.nodes.map((x) => x.lane))];
  openModal('编辑活动节点 · ' + n.name, `
    <div class="row2">
      <div class="field"><label>活动名称</label><input id="edName" value="${esc(n.name)}"></div>
      <div class="field"><label>节点类型</label>
        <select id="edType">${Object.keys(NODE_LABEL).map((t) =>
          '<option value="' + t + '"' + (n.node_type === t ? ' selected' : '') + '>' +
          NODE_LABEL[t] + '</option>').join('')}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>所属泳道（部门/角色）</label>
        <input id="edLane" list="laneList" value="${esc(n.lane)}">
        <datalist id="laneList">${laneList.map((l) => '<option value="' + esc(l) + '">').join('')}</datalist></div>
      <div class="field"><label>负责人 / 岗位</label>
        <input id="edOwner" value="${esc(n.owner_role || '')}" placeholder="如：采购计划员"></div>
    </div>
    <div class="row3">
      <div class="field"><label>作业时间（分钟）</label>
        <input id="edDur" type="number" min="0" step="1" value="${n.duration_minutes}"></div>
      <div class="field"><label>等待 / 排队（分钟）</label>
        <input id="edWait" type="number" min="0" step="1" value="${n.wait_minutes}"></div>
      <div class="field"><label>单次执行成本（元）</label>
        <input id="edCost" type="number" min="0" step="0.1" value="${n.cost}"></div>
    </div>
    <div class="row3">
      <div class="field"><label>返工率（0–1）</label>
        <input id="edRework" type="number" min="0" max="1" step="0.05" value="${n.rework_rate}">
        <div class="hint">>0.1 会触发返工损失建议</div></div>
      <div class="field"><label>审批层级数</label>
        <input id="edLevels" type="number" min="0" max="10" step="1" value="${n.approval_levels}">
        <div class="hint">累计 >3 层会触发决策下沉建议</div></div>
      <div class="field"><label>是否增值活动</label>
        <select id="edVa">
          <option value="true"${n.is_value_added ? ' selected' : ''}>增值（VA）</option>
          <option value="false"${!n.is_value_added ? ' selected' : ''}>非增值（NVA）</option>
        </select></div>
    </div>
    <div class="note">节点的「等待时间」是周期效率的主要杀手。真实场景下把它按现场实测填进去，
      右侧测算会立刻反映出来。</div>`,
    `<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"
       onclick="deleteNode('${nodeKey}')">删除节点</button>
     <button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveNode('${nodeKey}')">保存</button>`);
}

function saveNode(nodeKey) {
  const n = state.designer.model.nodes.find((x) => x.node_key === nodeKey);
  if (!n) return;
  const g = (id) => document.getElementById(id).value;
  n.name = g('edName').trim() || n.name;
  n.node_type = g('edType');
  n.lane = g('edLane').trim() || n.lane;
  n.owner_role = g('edOwner').trim() || null;
  n.duration_minutes = Number(g('edDur') || 0);
  n.wait_minutes = Number(g('edWait') || 0);
  n.cost = Number(g('edCost') || 0);
  n.rework_rate = Number(g('edRework') || 0);
  n.approval_levels = Number(g('edLevels') || 0);
  n.is_value_added = g('edVa') === 'true';
  closeModal();
  persistDesign('节点已保存，指标已重算');
}

function deleteNode(nodeKey) {
  const st = state.designer;
  st.model.nodes = st.model.nodes.filter((x) => x.node_key !== nodeKey);
  // 连线引用已删节点会导致后端校验失败，这里一并清掉
  st.model.edges = st.model.edges.filter((e) => e.source_key !== nodeKey && e.target_key !== nodeKey);
  closeModal();
  persistDesign('节点已删除');
}

function addNode(lane) {
  const st = state.designer;
  let seq = 1;
  st.model.nodes.forEach((n) => { seq = Math.max(seq, n.sequence_order + 1); });
  // node_key 只需在流程内唯一，用一个不会被手写数据撞到的前缀
  let key = 'new_' + seq;
  while (st.model.nodes.some((n) => n.node_key === key)) key = 'new_' + (++seq);
  const node = {
    node_key: key, name: '新活动', node_type: 'TASK', lane: lane || '新泳道',
    owner_role: null, duration_minutes: 30, wait_minutes: 0, cost: 0, rework_rate: 0,
    approval_levels: 0, is_value_added: true, sequence_order: seq, position_x: 0, position_y: 0,
  };
  st.model.nodes.push(node);
  // 自动接在同泳道最后一个节点后面，省得新节点悬空
  const inLane = st.model.nodes
    .filter((n) => n.lane === node.lane && n.node_key !== key)
    .sort((a, b) => a.sequence_order - b.sequence_order);
  if (inLane.length) {
    st.model.edges.push({
      source_key: inLane[inLane.length - 1].node_key, target_key: key,
      label: null, condition: null, probability: 1,
    });
  }
  persistDesign('已添加节点「新活动」，点它可以修改');
  setTimeout(() => editNode(key), 260);
}

function addDesignerNode(laneIdx) {
  const lane = (state.designer.lanes || [])[laneIdx];
  addNode(lane);
}

function addLaneNode() {
  const lane = prompt('输入泳道名称（部门 / 角色）：', '新泳道');
  if (lane === null) return;
  addNode(lane.trim() || '新泳道');
}


export { renderDesigner, addDesignerNode, addLaneNode, addNode, cloneModel, deleteNode, editNode, exportBpmn, importBpmn, openDesigner, openNodeEditor, paintDesigner, paintMetrics, paintSuggestions, persistDesign, reanalyze, reloadDesign, saveNode, setDesignerTab, switchProcess };
