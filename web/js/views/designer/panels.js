/* BPMN 属性侧栏：节点、连线、泳道、流程；跨模块能力经 ctx 注入。 */

import { esc, NODE_LABEL, tipHelp } from '../../core/format.js';
import { toast, promptDialog, confirmDialog } from '../../core/ui.js';
import { canManage } from '../../core/auth.js';
import { state } from '../../core/state.js';
import { PATCH, POST } from '../../core/api.js';
import { appendBpmnLane, setPmsNodeType } from './xml.js';
import {
  parseFlowMatch,
  flowMatchRowHtml,
  collectFlowMatchFromDom,
} from './flow-match.js';

/** PMS 节点类型 ↔ 标准 BPMN 元素类型。 */
const PMS_TO_BPMN_TYPE = {
  START: 'bpmn:StartEvent',
  END: 'bpmn:EndEvent',
  TASK: 'bpmn:Task',
  APPROVAL: 'bpmn:UserTask',
  WAIT: 'bpmn:IntermediateCatchEvent',
  DECISION: 'bpmn:ExclusiveGateway',
  HANDOFF: 'bpmn:ManualTask',
};
const BPMN_TO_PMS_TYPE = Object.fromEntries(
  Object.entries(PMS_TO_BPMN_TYPE).map(([pms, bpmn]) => [bpmn, pms]),
);

export function createPanels(ctx) {
  function bpmnLanes() {
    const modeler = ctx.getModeler();
    if (!modeler) return [];
    return modeler.get('elementRegistry').filter((element) => element.type === 'bpmn:Lane')
      .sort((a, b) => a.y - b.y);
  }

  function bpmnLaneOf(element) {
    return element && element.parent && element.parent.type === 'bpmn:Lane'
      ? element.parent : null;
  }

  function bpmnNodeTypeOf(bo, node) {
    if (node && node.node_type) return node.node_type;
    return BPMN_TO_PMS_TYPE[bo && bo.$type] || 'TASK';
  }

  function bpmnPanelHeader(bo) {
    const type = String((bo && bo.$type) || '').replace('bpmn:', '');
    return `<div class="between mb">
      <b>${esc((bo && (bo.name || bo.id)) || '未命名元素')}</b>
      <span class="tag t-blu">${esc(type)}</span>
    </div>`;
  }

  function bpmnDocText(bo) {
    const docs = bo && bo.documentation;
    return docs && docs.length ? (docs[0].text || '') : '';
  }

  function bpmnDocEditor(bo) {
    const editable = !!state.designer.editable;
    return `
      <div class="field"><label>元素说明</label>
        <textarea id="bpDoc" rows="2" placeholder="补充这个元素的目的、边界或注意事项"
          ${editable ? '' : ' readonly'}>${esc(bpmnDocText(bo))}</textarea>
        ${editable ? `<button class="btn-sm" data-act="designer.saveDescription"
          data-id="${esc(bo.id)}" style="margin-top:6px">保存说明</button>` : ''}
      </div>`;
  }

  function bpmnNameEditor(bo, hint) {
    const editable = !!state.designer.editable;
    return `
      <div class="field"><label>名称</label>
        <input id="bpName" value="${esc(bo.name || '')}" placeholder="未命名"${
          editable ? '' : ' readonly'}></div>
      ${editable
        ? `<div class="between mb"><span class="tiny muted">${esc(hint)}</span>
            <button class="btn-sm" data-act="designer.saveName"
              data-id="${esc(bo.id)}">保存名称</button></div>`
        : '<div class="hint">只读：需要 Owner 或流程管理科权限才能修改。</div>'}`;
  }

  // 方法工具挂五阶段步骤；节点侧只保留作业支撑（文件/执行）与测算。
  // 旧「工具/配套」状态落到执行页的可选设计证据区。
  const NODE_PROP_SECTIONS = [
    { id: 'basic', label: '基本' },
    { id: 'duty', label: '责任' },
    { id: 'metrics', label: '测算' },
    { id: 'docs', label: '文件' },
    { id: 'exec', label: '执行' },
    { id: 'binding', label: '绑定' },
  ];
  const NODE_PROP_SECTION_ALIAS = { runtime: 'exec', tools: 'exec' };

  function nodePropSection() {
    const raw = NODE_PROP_SECTION_ALIAS[state.designer.propSection]
      || state.designer.propSection
      || 'basic';
    return NODE_PROP_SECTIONS.some((item) => item.id === raw) ? raw : 'basic';
  }

  function setNodePropSection(section) {
    if (!NODE_PROP_SECTIONS.some((item) => item.id === section)) return;
    state.designer.propSection = section;
    renderBpmnSelection(state.designer.bpmnSelection || []);
  }

  function renderBpmnNodePanel(panel, element) {
    const st = state.designer;
    const bo = element.businessObject;
    const node = ((st.model || {}).nodes || []).find((item) => item.node_key === bo.id);
    const editable = !!st.editable;
    const pmsEditable = editable && !!node;
    // 分派配置的写接口要求 MANAGER+，权限比 PMS 指标更窄
    const canConfigExec = pmsEditable && canManage();
    const ro = pmsEditable ? '' : ' readonly';
    const isFlowNode = !!(bo.$instanceOf && bo.$instanceOf('bpmn:FlowNode'));
    const lanes = isFlowNode ? bpmnLanes() : [];
    const currentLane = bpmnLaneOf(element);
    const currentLaneName = currentLane ? (currentLane.businessObject.name || currentLane.id) : '';
    const pmsType = bpmnNodeTypeOf(bo, node);
    const section = nodePropSection();
    const typeOpts = Object.keys(PMS_TO_BPMN_TYPE).map((key) =>
      `<option value="${key}"${key === pmsType ? ' selected' : ''}>${
        esc(NODE_LABEL[key] || key)}</option>`).join('');
    const laneOpts = lanes.map((lane) => {
      const name = lane.businessObject.name || lane.id;
      return `<option value="${esc(name)}"${name === currentLaneName ? ' selected' : ''}>${
        esc(name)}</option>`;
    }).join('');
    const activities = (st.processes || []).filter(
      (item) => item.level === 4 && item.parent_id === st.processId,
    );
    const activityOpts = activities.map((item) =>
      `<option value="${item.id}"${item.id === (node && node.process_arch_id) ? ' selected' : ''}>${
        esc(item.code)} · ${esc(item.name)}</option>`).join('');
    const positions = st.positions || [];
    const positionOpts = positions.map((item) =>
      `<option value="${item.id}"${item.id === (node && node.owner_position_id)
        ? ' selected' : ''}>${esc(item.code)} · ${esc(item.name)}</option>`).join('');
    const legacyPosition = node && node.owner_role && !node.owner_position_id
      ? `<option value="" selected>${esc(node.owner_role)}（未关联岗位）</option>` : '';
    const sectionTabs = `<div class="seg bpmn-prop-tabs" role="tablist">
      ${NODE_PROP_SECTIONS.map((item) =>
        `<button type="button" role="tab" class="${item.id === section ? 'on' : ''}"
          data-act="designer.propSection" data-section="${item.id}"
          aria-selected="${item.id === section ? 'true' : 'false'}">${item.label}</button>`
      ).join('')}
    </div>`;
    const noPms = '<div class="tiny muted">该元素没有 PMS 测算数据</div>';
    let body = '';
    if (section === 'basic') {
      body = `
        ${bpmnNameEditor(bo, '双击画布元素也可直接改名')}
        ${bpmnDocEditor(bo)}
        ${isFlowNode ? `
          <div class="row2">
            <div class="field"><label>节点类型</label>
              <div class="gap">
                <select id="bpNodeType"${editable ? '' : ' disabled'}>${typeOpts}</select>
                ${editable
                  ? `<button class="btn-sm" data-act="designer.changeType"
                    data-id="${esc(bo.id)}">应用类型</button>`
                  : ''}
              </div></div>
            <div class="field"><label>所属泳道</label>
              <div class="gap">
                <select id="bpNodeLane"${editable && lanes.length ? '' : ' disabled'}>
                  ${lanes.length ? laneOpts : '<option value="">没有泳道</option>'}
                </select>
                ${editable && lanes.length
                  ? `<button class="btn-sm" data-act="designer.moveLane"
                    data-id="${esc(bo.id)}">移动</button>`
                  : ''}
              </div></div>
          </div>` : ''}`;
    } else if (section === 'duty') {
      body = node ? `
        <div class="hint mb">活动归属与岗位（汇总/治理用）。运行谁处理任务见「执行」；
          关键事项 RACI 见顶栏「权责」。</div>
        <div class="field"><label>L4 活动（统一活动 ID）</label>
          <div class="gap">
            <select id="bpActivity"${pmsEditable ? '' : ' disabled'}>
              <option value="">未关联</option>${activityOpts}
            </select>
            ${pmsEditable
              ? `<button class="btn-sm" data-act="designer.saveActivity"
                data-node="${esc(node.node_key)}">关联</button>`
              : ''}
          </div>
          ${node.process_arch_id
            ? '' : '<div class="hint">未关联活动：工作量/绩效无法按活动汇总</div>'}
        </div>
        <div class="field"><label>负责人岗位</label>
          <select id="bpPosition"${pmsEditable ? '' : ' disabled'}>
            <option value="">未分配</option>${legacyPosition}${positionOpts}
          </select>
          ${positions.length ? '' : '<div class="hint">请先在「组织与人员 → 岗位」维护岗位</div>'}
        </div>
        ${pmsEditable
          ? `<div class="between mt"><div class="hint">岗位与活动各自单独保存。</div>
              <button class="btn-sm btn-p" data-act="designer.savePosition"
                data-node="${esc(node.node_key)}">保存岗位</button></div>`
          : '<div class="hint">只读：需要 Owner 或流程管理科权限才能修改。</div>'}` : noPms;
    } else if (section === 'metrics') {
      body = node ? `
        <div class="hint mb">设计估计值，供 PCE/瓶颈分析；不是运营实测 KPI
          （实测见工作量测量与 KPI）。</div>
        <div class="grid g3">
          <div class="field"><label>作业时间（分钟）</label>
            <input id="bpDur" type="number" min="0" value="${node.duration_minutes}"${ro}></div>
          <div class="field"><label>等待时间（分钟）</label>
            <input id="bpWait" type="number" min="0" value="${node.wait_minutes}"${ro}></div>
          <div class="field"><label>单次成本（元）</label>
            <input id="bpCost" type="number" min="0" step="0.1" value="${node.cost}"${ro}></div>
          <div class="field"><label>返工率（0–1）</label>
            <input id="bpRework" type="number" min="0" max="1" step="0.05" value="${node.rework_rate}"${ro}></div>
          <div class="field"><label>审批层级</label>
            <input id="bpApproval" type="number" min="0" max="10" value="${node.approval_levels}"${ro}></div>
          <div class="field"><label>增值活动</label>
            <select id="bpVa"${pmsEditable ? '' : ' disabled'}>
              <option value="true"${node.is_value_added ? ' selected' : ''}>是</option>
              <option value="false"${!node.is_value_added ? ' selected' : ''}>否</option>
            </select></div>
        </div>
        ${pmsEditable
          ? `<div class="between mt"><div class="hint">保存后重算分析；不改 BPMN 图形。</div>
              <button class="btn-sm btn-p" data-act="designer.saveMetrics"
                data-node="${esc(node.node_key)}">保存指标</button></div>`
          : '<div class="hint">只读：需要 Owner 或流程管理科权限才能修改。</div>'}` : noPms;
    } else if (section === 'docs') {
      body = node ? `
        <div class="hint mb">作业支撑：SOP/标准文件挂本活动，执行点可查阅。
          方法论工具（SIPOC/FMEA 等）请在五阶段步骤或工具箱挂接。</div>
        <div id="bpDocsSlot" class="bpmn-node-extra first"><div class="tiny muted">正在加载标准文件…</div></div>`
        : noPms;
    } else if (section === 'binding') {
      body = ctx.renderNodeBinding(bo.id);
    } else if (section === 'exec') {
      body = node ? `
        <div class="hint mb">与「流程执行 → 运行配置」同口径：本页可就地改
          <b>节点分派 / 时限</b>；<b>任务表单</b>在运行配置维护；
          <b>分支路由</b>在连线「运行匹配条件」（设计定语义）。岗位归属见「责任」。</div>
        <div id="bpMetaSlot" class="bpmn-node-extra first"><div class="tiny muted">正在加载任务表单与出口…</div></div>
        ${canConfigExec
          ? '<div id="bpmnAssignSlot" class="bpmn-assign-slot">'
            + '<div class="tiny muted">正在加载节点分派…</div></div>'
          : '<div class="hint">节点分派需 MANAGER 及以上权限。</div>'}
        <details class="bpmn-design-tools mt">
          <summary class="tiny">设计证据：方法工具绑定（可选）</summary>
          <div class="hint mt">计入阶段 5 绑定计数；不进待办作业指导。
            日常请优先任务表单与标准文件。
            <a class="link-btn link-btn-sm" data-act="designer.goToolbox">去方法论工具箱</a>
          </div>
          <div id="bpToolsSlot" class="bpmn-node-extra first">
            <div class="tiny muted">正在加载工具绑定…</div></div>
        </details>` : noPms;
    } else {
      body = noPms;
    }
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      ${sectionTabs}
      ${body}
      <div class="hint">BPMN 图形修改会自动保存草稿；PMS 指标、执行配置与活动绑定各自单独保存。</div>`;
    if (node && (section === 'docs' || section === 'exec')) {
      if (section === 'exec' && canConfigExec) ctx.renderBpmnAssignment(bo.id);
      ctx.hydrateBpmnNodeExtras(bo.id);
    }
  }

  function renderBpmnFlowPanel(panel, element) {
    const bo = element.businessObject;
    const editable = !!state.designer.editable;
    const condition = bo.conditionExpression && bo.conditionExpression.body
      ? bo.conditionExpression.body : '';
    const rawProbability = bo.$attrs && bo.$attrs['pms:probability'];
    const probability = rawProbability === undefined || rawProbability === null
      ? '1' : rawProbability;
    const source = bo.sourceRef ? (bo.sourceRef.name || bo.sourceRef.id) : '?';
    const target = bo.targetRef ? (bo.targetRef.name || bo.targetRef.id) : '?';
    const isDefault = !!(bo.sourceRef && bo.sourceRef.default === bo);
    const sourceIsGateway = !!(bo.sourceRef && String(bo.sourceRef.$type || '').includes('Gateway'));
    const disabled = editable ? '' : ' readonly';
    const matchRows = parseFlowMatch(bo);
    const matchHtml = matchRows.length
      ? matchRows.map(flowMatchRowHtml).join('')
      : '';
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      <div class="tiny muted mb">${esc(source)} → ${esc(target)}</div>
      <div class="note mb">路由语义在<strong>出边</strong>配置；发布后执行引擎按匹配条件分支。
        任务表单/分派/SLA 仍在流程执行补绑定。${tipHelp(
          '匹配条件读任务表单字段（引用名）。无匹配且非默认时，多出边需办理人显式选下一步。',
          '出边路由')}</div>
      <div class="field"><label>标签</label>
        <input id="bpFlowLabel" value="${esc(bo.name || '')}" placeholder="通过 / 驳回"${disabled}></div>
      <div class="field mb">
        <div class="between mb">
          <label style="margin:0">运行匹配条件${tipHelp(
            '全部满足才走本边；留空表示不自动命中（可作默认流或人工选择）。',
            '运行匹配')}</label>
          ${editable
            ? '<button type="button" class="btn-sm" data-act="designer.addFlowMatch">+ 条件</button>'
            : ''}
        </div>
        <div class="ef-fields-wrap">
          <table class="tbl ef-fields er-conds">
            <thead><tr><th>字段</th><th>运算</th><th>值</th><th></th></tr></thead>
            <tbody id="bpMatchBody">${matchHtml}</tbody>
          </table>
        </div>
      </div>
      <div class="row2">
        <div class="field"><label>条件说明（给人看）</label>
          <input id="bpFlowCondition" value="${esc(condition)}"
            placeholder="预算与需求均合规"${disabled}></div>
        <div class="field"><label>概率（0–1，测算用）</label>
          <input id="bpFlowProb" type="number" min="0" max="1" step="0.05"
            value="${esc(probability)}"${disabled}></div>
      </div>
      ${bpmnDocEditor(bo)}
      <label class="gap" style="margin-bottom:8px">
        <input id="bpFlowDefault" type="checkbox" ${isDefault ? 'checked' : ''}
          ${editable && sourceIsGateway ? '' : 'disabled'}>
        设为网关的默认分支${sourceIsGateway ? '' : '（只有网关出边可以设置）'}
      </label>
      <div class="between mt">
        <div class="hint">匹配条件写入 pms:match，发布后优先于执行页旧规则。</div>
        ${editable
          ? `<div class="gap">
              <button class="btn-sm btn-g" data-act="designer.deleteFlow"
                data-id="${esc(bo.id)}">删除连线</button>
              <button class="btn-sm btn-p" data-act="designer.saveFlow"
                data-id="${esc(bo.id)}">保存连线</button>
            </div>` : ''}
      </div>`;
  }

  function renderBpmnLanePanel(panel, element) {
    const bo = element.businessObject;
    const editable = !!state.designer.editable;
    const refs = bo.flowNodeRef || [];
    const names = refs.map((ref) => ref.name || ref.id);
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      <div class="field"><label>泳道名称</label>
        <input id="bpLaneName" value="${esc(bo.name || '')}" placeholder="部门 / 角色"${
          editable ? '' : ' readonly'}></div>
      ${editable
        ? `<div class="between mb"><span class="tiny muted">节点 ${refs.length} 个</span>
            <button class="btn-sm btn-p" data-act="designer.saveLaneName"
              data-id="${esc(bo.id)}">保存名称</button></div>`
        : ''}
      <div class="hint">${names.length
        ? '包含：' + names.map((name) => esc(name)).join('、')
        : '泳道里还没有节点'}</div>
      ${editable ? '<button class="btn-sm btn-g" data-act="designer.addLane">+ 添加泳道</button>' : ''}`;
  }

  function renderBpmnProcessPanel(panel, element) {
    const bo = element.businessObject;
    const lanes = bpmnLanes();
    const rows = lanes.map((lane) => {
      const laneBo = lane.businessObject;
      const count = (laneBo.flowNodeRef || []).length;
      return `<div class="tiny">${esc(laneBo.name || laneBo.id)} · ${count} 节点</div>`;
    }).join('') || '<div class="tiny muted">还没有泳道</div>';
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      <div class="field"><label>流程名称</label>
        <input value="${esc(bo.name || '')}" readonly></div>
      <div class="mb"><div class="tiny muted mb">泳道</div>${rows}</div>
      ${state.designer.editable
        ? '<button class="btn-sm btn-g" data-act="designer.addLane">+ 添加泳道</button>' : ''}`;
  }

  function renderBpmnSelection(selection) {
    const panel = document.getElementById('bpmnPropsPanel');
    if (!panel) return;
    const element = (selection || [])[0];
    const bo = element && element.businessObject;
    if (!bo) {
      panel.innerHTML = '<div class="tiny muted">选中一个元素查看/编辑属性</div>';
      return;
    }
    const type = bo.$type || '';
    if (type === 'bpmn:SequenceFlow') {
      renderBpmnFlowPanel(panel, element);
    } else if (type === 'bpmn:Lane') {
      renderBpmnLanePanel(panel, element);
    } else if (type === 'bpmn:Process' || type === 'bpmn:Collaboration') {
      renderBpmnProcessPanel(panel, element);
    } else {
      renderBpmnNodePanel(panel, element);
    }
  }

  function syncDrawerRail() {
    const card = document.getElementById('bpmnCard');
    const rail = document.getElementById('bpmnPropsToggle');
    const sidebar = document.getElementById('bpmnSidebar');
    if (!rail || !sidebar) return;
    const open = sidebar.classList.contains('open');
    card?.classList.toggle('sidebar-open', open);
    rail.setAttribute('aria-expanded', open ? 'true' : 'false');
    rail.title = open ? '收起属性栏' : '展开属性栏';
    const mark = rail.querySelector('.bpmn-drawer-rail-mark');
    const text = rail.querySelector('.bpmn-drawer-rail-text');
    if (mark) mark.textContent = open ? '›' : '‹';
    if (text) text.textContent = open ? '收起' : '属性';
  }

  function showBpmnSidebarTab(tab) {
    const sidebar = document.getElementById('bpmnSidebar');
    if (!sidebar) return;
    state.designer.bpmnSidebarTab = tab;
    sidebar.classList.add('open');
    sidebar.setAttribute('aria-hidden', 'false');
    const props = tab === 'props';
    const propsPanel = document.getElementById('bpmnPropsPanel');
    const lintPanel = document.getElementById('bpmnLintPanel');
    const propsTab = document.getElementById('bpmnTabProps');
    const lintTab = document.getElementById('bpmnTabLint');
    if (propsPanel) propsPanel.classList.toggle('hide', !props);
    if (lintPanel) lintPanel.classList.toggle('hide', props);
    if (propsTab) propsTab.classList.toggle('on', props);
    if (lintTab) lintTab.classList.toggle('on', !props);
    syncDrawerRail();
  }

  function closeBpmnSidebar() {
    const sidebar = document.getElementById('bpmnSidebar');
    if (!sidebar) return;
    sidebar.classList.remove('open');
    sidebar.setAttribute('aria-hidden', 'true');
    syncDrawerRail();
  }

  function toggleBpmnSidebar(tab) {
    const sidebar = document.getElementById('bpmnSidebar');
    if (!sidebar) return;
    const open = sidebar.classList.contains('open');
    if (!open) {
      showBpmnSidebarTab(tab || state.designer.bpmnSidebarTab || 'props');
      return;
    }
    if (tab && tab !== state.designer.bpmnSidebarTab) {
      showBpmnSidebarTab(tab);
      return;
    }
    closeBpmnSidebar();
  }

  async function saveBpmnName(elementId) {
    const st = state.designer;
    const modeler = ctx.getModeler();
    const input = document.getElementById('bpName');
    if (!modeler || !input) return;
    const element = ctx.getElement(elementId);
    if (!element) return;
    try {
      const name = input.value.trim();
      modeler.get('modeling').updateProperties(element, { name: name || undefined });
      // updateProperties 会触发防抖保存；这里立即保存并清掉定时器，避免重复提交
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('名称已更新');
      ctx.renderSelection(st.bpmnSelection || []);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function patchBpmnNode(nodeKey, payload, okMessage) {
    const st = state.designer;
    if (!st.model.nodes.some((node) => node.node_key === nodeKey)) {
      toast('画布还在保存，请稍后再试', true);
      return;
    }
    try {
      const response = await PATCH(
        '/processes/' + st.processId + '/design/nodes/' + nodeKey,
        { ...payload, expected_version: st.model.version },
      );
      st.model = response;
      st.savedModel = ctx.cloneModel(response);
      st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
      await ctx.refreshBinding();
      ctx.setSaveState('属性已保存 · v' + (response.draft_version || response.version));
      ctx.renderSelection(st.bpmnSelection || []);
      toast(okMessage);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function saveBpmnPosition(nodeKey) {
    const st = state.designer;
    const positionSelect = document.getElementById('bpPosition');
    if (!positionSelect) return;
    const positionId = positionSelect.value ? Number(positionSelect.value) : null;
    const selected = (st.positions || []).find((item) => item.id === positionId);
    const payload = { owner_position_id: positionId };
    // owner_role 保留为展示兼容字段；选岗位时同步成岗位名称
    if (selected) payload.owner_role = selected.name;
    await patchBpmnNode(nodeKey, payload, '负责人岗位已保存');
  }

  async function saveBpmnMetrics(nodeKey) {
    const value = (id) => Number(document.getElementById(id).value);
    await patchBpmnNode(nodeKey, {
      duration_minutes: value('bpDur'),
      wait_minutes: value('bpWait'),
      cost: value('bpCost'),
      rework_rate: value('bpRework'),
      approval_levels: value('bpApproval'),
      is_value_added: document.getElementById('bpVa').value === 'true',
    }, '节点属性已保存');
  }

  async function saveDescription(elementId) {
    const modeler = ctx.getModeler();
    const element = ctx.getElement(elementId);
    if (!modeler || !element) return;
    const text = (document.getElementById('bpDoc')?.value || '').trim();
    try {
      const factory = modeler.get('bpmnFactory');
      const documentation = text
        ? [factory.create('bpmn:Documentation', { text })]
        : [];
      modeler.get('modeling').updateProperties(element, { documentation });
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('元素说明已保存');
      ctx.renderSelection(state.designer.bpmnSelection || []);
    } catch (e) {
      toast(e.message, true);
    }
  }

  function addFlowMatchRow() {
    const body = document.getElementById('bpMatchBody');
    if (!body) return;
    body.insertAdjacentHTML('beforeend', flowMatchRowHtml({ field: '', op: 'eq', value: '' }));
  }

  function removeFlowMatchRow(el) {
    const row = el.closest('tr');
    if (row) row.remove();
  }

  function syncFlowMatchOp(opEl) {
    const row = opEl.closest('tr');
    const val = row && row.querySelector('.bp-match-value');
    if (!val) return;
    const needs = opEl.value !== 'truthy' && opEl.value !== 'falsy';
    val.disabled = !needs;
    if (!needs) val.value = '';
  }

  async function saveBpmnFlow(flowId) {
    const modeler = ctx.getModeler();
    const element = ctx.getElement(flowId);
    if (!element) return;
    const label = (document.getElementById('bpFlowLabel')?.value || '').trim();
    const condition = (document.getElementById('bpFlowCondition')?.value || '').trim();
    const probability = Number(document.getElementById('bpFlowProb')?.value);
    if (!Number.isFinite(probability) || probability < 0 || probability > 1) {
      toast('概率必须在 0–1 之间', true);
      return;
    }
    const collected = collectFlowMatchFromDom();
    if (collected.error) return toast(collected.error, true);
    try {
      const modeling = modeler.get('modeling');
      const bpmnFactory = modeler.get('bpmnFactory');
      const conditionExpression = condition
        ? bpmnFactory.create('bpmn:FormalExpression', { body: condition })
        : undefined;
      modeling.updateProperties(element, { name: label || undefined, conditionExpression });
      const source = element.source;
      const asDefault = !!document.getElementById('bpFlowDefault')?.checked;
      if (source && source.businessObject
        && String(source.businessObject.$type || '').includes('Gateway')) {
        modeling.updateProperties(source, {
          default: asDefault ? element.businessObject : undefined,
        });
      }
      // pms:probability / pms:match 是 PMS 扩展属性，写在 $attrs 里由序列化器输出。
      const attrs = element.businessObject.$attrs;
      if (attrs) {
        attrs['pms:probability'] = String(probability);
        if (collected.conditions && collected.conditions.length) {
          attrs['pms:match'] = JSON.stringify(collected.conditions);
        } else {
          delete attrs['pms:match'];
        }
      }
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('连线属性已保存');
      ctx.renderSelection(state.designer.bpmnSelection || []);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function deleteBpmnFlow(flowId) {
    const ok = await confirmDialog('删除这条连线？', { danger: true, okText: '删除' });
    if (!ok) return;
    const modeler = ctx.getModeler();
    const element = ctx.getElement(flowId);
    if (!element) return;
    try {
      state.designer.bpmnSelection = [];
      ctx.select([]);
      modeler.get('modeling').removeElements([element]);
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('连线已删除');
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function changeBpmnNodeType(nodeId) {
    const st = state.designer;
    const modeler = ctx.getModeler();
    const element = ctx.getElement(nodeId);
    const select = document.getElementById('bpNodeType');
    if (!element || !select) return;
    const pmsType = select.value;
    const targetType = PMS_TO_BPMN_TYPE[pmsType];
    if (!targetType || element.businessObject.$type === targetType) return;
    try {
      const replaced = modeler.get('bpmnReplace').replaceElement(element, { type: targetType });
      if (replaced) {
        ctx.select(replaced);
        st.bpmnSelection = [replaced];
      }
      const { xml } = await modeler.saveXML({ format: true });
      const patched = setPmsNodeType(xml, nodeId, pmsType);
      ctx.clearSaveTimer();
      const saved = await ctx.postXml(patched);
      if (saved) {
        showBpmnSidebarTab('props');
        toast('节点类型已更新');
      }
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function moveBpmnNodeToLane(nodeId) {
    const modeler = ctx.getModeler();
    const element = ctx.getElement(nodeId);
    const select = document.getElementById('bpNodeLane');
    if (!element || !select) return;
    const lane = bpmnLanes().find(
      (item) => (item.businessObject.name || item.id) === select.value,
    );
    if (!lane) return;
    if (element.parent === lane) {
      toast('节点已经在该泳道');
      return;
    }
    try {
      const dx = lane.x + Math.max(40, (lane.width - element.width) / 2) - element.x;
      const dy = lane.y + Math.max(30, (lane.height - element.height) / 2) - element.y;
      modeler.get('modeling').moveElements([element], { x: dx, y: dy }, lane);
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('节点已移动到「' + (lane.businessObject.name || lane.id) + '」');
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function saveBpmnLaneName(laneId) {
    const modeler = ctx.getModeler();
    const element = ctx.getElement(laneId);
    const input = document.getElementById('bpLaneName');
    if (!element || !input) return;
    const name = input.value.trim();
    if (!name) {
      toast('泳道名称不能为空', true);
      return;
    }
    try {
      modeler.get('modeling').updateProperties(element, { name });
      ctx.clearSaveTimer();
      const saved = await ctx.saveNow();
      if (saved) toast('泳道名称已更新');
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function addBpmnLane() {
    const st = state.designer;
    const modeler = ctx.getModeler();
    if (!modeler) return;
    const input = await promptDialog('输入泳道名称（部门 / 角色）：', {
      title: '添加泳道', value: '新泳道', okText: '添加',
    });
    if (input === null) return;
    const name = input.trim() || '新泳道';
    if (bpmnLanes().some((lane) => (lane.businessObject.name || '') === name)) {
      toast('泳道已存在', true);
      return;
    }
    try {
      const { xml } = await modeler.saveXML({ format: true });
      const patched = appendBpmnLane(
        xml, name, ((state.designer.model || {}).nodes || []).map((node) => node.node_key));
      if (!patched) throw new Error('无法添加泳道：BPMN 中没有 process 元素');
      st.bpmnImporting = true;
      await modeler.importXML(patched.xml);
      st.bpmnImporting = false;
      ctx.fit();
      const saved = await ctx.saveNow();
      if (!saved) return;
      const added = modeler.get('elementRegistry').get(patched.taskId);
      if (added) {
        ctx.select(added);
        st.bpmnSelection = [added];
      }
      showBpmnSidebarTab('props');
      toast('泳道「' + name + '」已添加');
    } catch (e) {
      st.bpmnImporting = false;
      toast(e.message, true);
    }
  }

  return {
    renderSelection: renderBpmnSelection,
    setPropSection: setNodePropSection,
    showSidebarTab: showBpmnSidebarTab,
    toggleSidebar: toggleBpmnSidebar,
    closeSidebar: closeBpmnSidebar,
    saveName: saveBpmnName,
    saveDescription: saveDescription,
    savePosition: saveBpmnPosition,
    saveMetrics: saveBpmnMetrics,
    saveFlow: saveBpmnFlow,
    deleteFlow: deleteBpmnFlow,
    addFlowMatch: addFlowMatchRow,
    removeFlowMatch: removeFlowMatchRow,
    flowMatchOp: syncFlowMatchOp,
    changeNodeType: changeBpmnNodeType,
    moveNodeToLane: moveBpmnNodeToLane,
    saveLaneName: saveBpmnLaneName,
    addLane: addBpmnLane,
  };
}
