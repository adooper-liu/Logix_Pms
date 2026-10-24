/* BPMN 属性侧栏：节点 / 连线 / 泳道 / 流程 四类元素的面板与就地编辑。
 *
 * 画布实例通过 index.js 注入的 ctx 访问；本文件不 import 其他有状态的
 * designer 子模块（assignment 的渲染同样走 ctx）。
 */

import { esc, NODE_LABEL } from '../../core/format.js';
import { toast, promptDialog, confirmDialog } from '../../core/ui.js';
import { canManage } from '../../core/auth.js';
import { state } from '../../core/state.js';
import { PATCH, POST } from '../../core/api.js';
import { appendBpmnLane, setPmsNodeType } from './xml.js';

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
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      ${bpmnNameEditor(bo, '双击画布元素也可直接改名')}
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
        </div>` : ''}
      ${node ? `
        <div class="row2">
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
        </div>
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
        <div id="bpToolsSlot" class="bpmn-node-extra"><div class="tiny muted">正在加载工具绑定…</div></div>
        <div id="bpDocsSlot" class="bpmn-node-extra"><div class="tiny muted">正在加载标准文件…</div></div>
        <div id="bpMetaSlot" class="bpmn-node-extra"><div class="tiny muted">正在加载表单与规则…</div></div>
        ${pmsEditable
          ? `<div class="between mt"><div class="hint">指标保存后不影响图形；发布后才影响运行时。</div>
              <button class="btn-sm btn-p" data-act="designer.saveMetrics"
                data-node="${esc(node.node_key)}">保存指标</button></div>`
          : '<div class="hint">只读：需要 Owner 或流程管理科权限才能修改。</div>'}`
        : '<div class="tiny muted">该元素没有 PMS 测算数据</div>'}
      ${canConfigExec
        ? '<div id="bpmnAssignSlot" class="bpmn-assign-slot">'
          + '<div class="tiny muted">正在加载执行配置…</div></div>'
        : ''}
      <div class="hint">BPMN 图形修改会自动保存草稿；PMS 指标、执行配置与活动绑定各自单独保存。</div>`;
    if (canConfigExec) ctx.renderBpmnAssignment(bo.id);
    if (node) ctx.hydrateBpmnNodeExtras(bo.id);
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
    const disabled = editable ? '' : ' readonly';
    panel.innerHTML = `
      ${bpmnPanelHeader(bo)}
      <div class="tiny muted mb">${esc(source)} → ${esc(target)}</div>
      <div class="field"><label>标签</label>
        <input id="bpFlowLabel" value="${esc(bo.name || '')}" placeholder="通过 / 驳回"${disabled}></div>
      <div class="row2">
        <div class="field"><label>条件说明</label>
          <input id="bpFlowCondition" value="${esc(condition)}"
            placeholder="预算与需求均合规"${disabled}></div>
        <div class="field"><label>概率（0–1）</label>
          <input id="bpFlowProb" type="number" min="0" max="1" step="0.05"
            value="${esc(probability)}"${disabled}></div>
      </div>
      <div class="between mt">
        <div class="hint">条件与概率写入 BPMN，发布后参与运行时分支。</div>
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
  }

  function closeBpmnSidebar() {
    const sidebar = document.getElementById('bpmnSidebar');
    if (!sidebar) return;
    sidebar.classList.remove('open');
    sidebar.setAttribute('aria-hidden', 'true');
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

  async function saveBpmnMetrics(nodeKey) {
    const st = state.designer;
    if (!st.model.nodes.some((node) => node.node_key === nodeKey)) {
      toast('画布还在保存，请稍后再试', true);
      return;
    }
    const value = (id) => Number(document.getElementById(id).value);
    const positionSelect = document.getElementById('bpPosition');
    try {
      const payload = {
        duration_minutes: value('bpDur'),
        wait_minutes: value('bpWait'),
        cost: value('bpCost'),
        rework_rate: value('bpRework'),
        approval_levels: value('bpApproval'),
        is_value_added: document.getElementById('bpVa').value === 'true',
        expected_version: st.model.version,
      };
      if (positionSelect) {
        const positionId = positionSelect.value ? Number(positionSelect.value) : null;
        const selected = (st.positions || []).find((item) => item.id === positionId);
        payload.owner_position_id = positionId;
        // owner_role 保留为展示兼容字段；选岗位时同步成岗位名称
        if (selected) payload.owner_role = selected.name;
      }
      const response = await PATCH(
        '/processes/' + st.processId + '/design/nodes/' + nodeKey,
        payload,
      );
      st.model = response;
      st.savedModel = ctx.cloneModel(response);
      st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
      ctx.setSaveState('属性已保存 · v' + (response.draft_version || response.version));
      ctx.renderSelection(st.bpmnSelection || []);
      toast('节点属性已保存');
    } catch (e) {
      toast(e.message, true);
    }
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
    try {
      const modeling = modeler.get('modeling');
      const bpmnFactory = modeler.get('bpmnFactory');
      const conditionExpression = condition
        ? bpmnFactory.create('bpmn:FormalExpression', { body: condition })
        : undefined;
      modeling.updateProperties(element, { name: label || undefined, conditionExpression });
      // pms:probability 是 PMS 扩展属性，bpmn-moddle 放在只读 getter 返回的
      // $attrs 对象里；直接改对象内容，保存时由序列化器输出为属性。
      // 不能整体赋值 $attrs（会报 getter-only），也不能走 updateProperties
      //（会把 $attrs 本身序列化成 "[object Object]"）。
      const attrs = element.businessObject.$attrs;
      if (attrs) attrs['pms:probability'] = String(probability);
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
    showSidebarTab: showBpmnSidebarTab,
    toggleSidebar: toggleBpmnSidebar,
    closeSidebar: closeBpmnSidebar,
    saveName: saveBpmnName,
    saveMetrics: saveBpmnMetrics,
    saveFlow: saveBpmnFlow,
    deleteFlow: deleteBpmnFlow,
    changeNodeType: changeBpmnNodeType,
    moveNodeToLane: moveBpmnNodeToLane,
    saveLaneName: saveBpmnLaneName,
    addLane: addBpmnLane,
  };
}
