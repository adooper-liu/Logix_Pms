/* 节点执行配置：分派、SLA、工具绑定、标准文件与表单/规则摘要。
 *
 * 这些接口的写权限比 PMS 指标更窄（MANAGER+），只读用户只看到摘要。
 * 跨模块动作走 index.js 注入的 ctx，本文件不 import 其他 designer 子模块。
 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal } from '../../core/ui.js';
import { canManage } from '../../core/auth.js';
import { state } from '../../core/state.js';
import { GET, POST, PATCH, PUT, DEL } from '../../core/api.js';
import { go } from '../../core/router.js';

function roleOptionHtml(roles, selected) {
  return roles.map((role) =>
    `<option value="${esc(role.value)}"${selected === role.value ? ' selected' : ''}>${
      esc(role.label)}</option>`).join('');
}

function orgOptionHtml(orgs, selected) {
  return orgs.map((org) =>
    `<option value="${org.id}"${selected === org.id ? ' selected' : ''}>${
      esc(org.name)}</option>`).join('');
}

function userOptionHtml(users, selected) {
  return users.map((user) =>
    `<option value="${user.id}"${selected === user.id ? ' selected' : ''}>${
      esc(user.display_name)} · ${esc(user.role_label || user.role)}</option>`).join('');
}

async function fetchAssignmentContext(processId) {
  const [assignments, users, orgs, meta] = await Promise.all([
    GET('/execution/assignments?process_id=' + processId),
    GET('/execution/assignees'),
    GET('/org-units'),
    GET('/auth/meta'),
  ]);
  return {
    processId,
    assignments: new Map(assignments.map((item) => [item.node_key, item])),
    users,
    orgs,
    roles: meta.roles || [],
  };
}

/** 分派配置是流程级数据：选中节点时按需加载并缓存，避免每次改选都打四个接口。 */
function assignmentContext(processId) {
  const st = state.designer;
  if (st.assignmentCtx && st.assignmentCtx.processId === processId) {
    return Promise.resolve(st.assignmentCtx);
  }
  if (st.assignmentPending && st.assignmentPending.processId === processId) {
    return st.assignmentPending.promise;
  }
  const clearPending = () => {
    if (st.assignmentPending && st.assignmentPending.processId === processId) {
      st.assignmentPending = null;
    }
  };
  const promise = fetchAssignmentContext(processId)
    .then((loaded) => {
      clearPending();
      // 加载期间可能已经切到别的流程，别把旧流程的配置写进缓存
      if (state.designer.processId === processId) st.assignmentCtx = loaded;
      return loaded;
    })
    .catch((error) => {
      clearPending();
      throw error;
    });
  st.assignmentPending = { processId, promise };
  return promise;
}

function readAssignmentPayload(nodeKey, ids) {
  const value = (id) => document.getElementById(id).value;
  const numOrNull = (id) => {
    const raw = value(id).trim();
    if (raw === '') return null;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 8760) {
      throw new Error('时限应为 0–8760 小时');
    }
    return parsed;
  };
  const idOrNull = (id) => (value(id) ? Number(value(id)) : null);
  return {
    process_id: state.designer.processId,
    node_key: nodeKey,
    role: value(ids.role) || null,
    org_unit_id: idOrNull(ids.org),
    default_assignee_user_id: idOrNull(ids.assignee),
    due_hours: numOrNull(ids.due),
    escalation_hours: numOrNull(ids.escalationHours),
    escalation_user_id: idOrNull(ids.escalationUser),
  };
}

async function persistAssignment(nodeKey, ids) {
  const payload = readAssignmentPayload(nodeKey, ids);
  const saved = await PUT('/execution/assignments', payload);
  const st = state.designer;
  if (saved && st.assignmentCtx && st.assignmentCtx.processId === payload.process_id) {
    st.assignmentCtx.assignments.set(nodeKey, saved);
  }
  return saved;
}

export function createAssignment(ctx) {
  async function renderBpmnAssignment(nodeKey) {
    const st = state.designer;
    const processId = st.processId;
    const slot = document.getElementById('bpmnAssignSlot');
    if (!slot) return;
    // 加载或保存期间用户可能改选了别的元素：只更新仍然属于当前选中的槽位
    const stillSelected = () => {
      const current = (st.bpmnSelection || [])[0];
      const currentId = current && current.businessObject ? current.businessObject.id : null;
      return slot.isConnected && currentId === nodeKey && st.processId === processId;
    };
    let loaded;
    try {
      loaded = await assignmentContext(processId);
    } catch (e) {
      if (stillSelected()) {
        slot.innerHTML = `<div class="note">执行配置加载失败：${esc(e.message)}</div>`;
      }
      return;
    }
    if (!stillSelected()) return;
    const assignment = loaded.assignments.get(nodeKey) || {};
    slot.innerHTML = `
      <div class="designer-exec-config bpmn-assign">
        <div class="between mb"><h3 style="margin:0">执行配置</h3>
          <button class="btn-sm btn-p" data-act="designer.saveAssignment"
            data-node="${esc(nodeKey)}">保存执行配置</button></div>
        <div class="desc" style="margin:0 0 8px">候选角色 / 组织 / 默认处理人 / 节点时限 / 升级；
          只影响发布后的新实例</div>
        <div class="row2">
          <div class="field"><label>候选角色</label>
            <select id="baRole"><option value="">不限</option>${
              roleOptionHtml(loaded.roles, assignment.role)}</select></div>
          <div class="field"><label>限定组织</label>
            <select id="baOrg"><option value="">不限</option>${
              orgOptionHtml(loaded.orgs, assignment.org_unit_id)}</select></div>
        </div>
        <div class="row2">
          <div class="field"><label>默认处理人</label>
            <select id="baAssignee"><option value="">公共队列</option>${
              userOptionHtml(loaded.users, assignment.default_assignee_user_id)}</select></div>
          <div class="field"><label>节点时限（小时）</label>
            <input id="baDue" type="number" min="0" max="8760"
              value="${assignment.due_hours ?? ''}" placeholder="跟随流程"></div>
        </div>
        <div class="row2">
          <div class="field"><label>升级时限（小时）</label>
            <input id="baEscHours" type="number" min="0" max="8760"
              value="${assignment.escalation_hours ?? ''}" placeholder="跟随流程"></div>
          <div class="field"><label>升级处理人</label>
            <select id="baEscUser"><option value="">跟随流程</option>${
              userOptionHtml(loaded.users, assignment.escalation_user_id)}</select></div>
        </div>
      </div>`;
  }

  function renderBpmnNodeTools(nodeKey, rows) {
    const slot = document.getElementById('bpToolsSlot');
    if (!slot) return;
    const st = state.designer;
    const editable = !!st.editable;
    const bound = new Set(rows.map((row) => row.tool_code));
    const toolOptions = (st.tools || [])
      .filter((tool) => !bound.has(tool.code))
      .map((tool) => `<option value="${esc(tool.code)}">${esc(tool.code)} · ${
        esc(tool.name)}</option>`).join('');
    const levelLabels = (st.toolMeta && st.toolMeta.level_labels) || {};
    const levelOptions = Object.entries(levelLabels)
      .map(([value, label]) => `<option value="${value}"${
        value === 'RECOMMENDED' ? ' selected' : ''}>${esc(label)}</option>`).join('');
    const list = rows.map((row) => `
      <div class="between bpmn-node-row">
        <span>${esc(row.tool_name || row.tool_code)}</span>
        <span class="gap">
          <span class="tag t-gry">${esc(row.level_label || row.level)}</span>
          ${editable ? `<button class="btn-sm" data-act="designer.removeNodeTool"
            data-node="${esc(nodeKey)}" data-code="${esc(row.tool_code)}">移除</button>` : ''}
        </span>
      </div>`).join('') || '<div class="tiny muted">还没有绑定推荐工具</div>';
    slot.innerHTML = `
      <div class="between mb"><b>推荐工具</b><span class="tiny muted">${rows.length} 个</span></div>
      ${list}
      ${editable ? `
        <div class="gap mt">
          <select id="bpToolCode"><option value="">选择工具</option>${toolOptions}</select>
          <select id="bpToolLevel">${levelOptions}</select>
          <button class="btn-sm btn-p" data-act="designer.addNodeTool"
            data-node="${esc(nodeKey)}">绑定</button>
        </div>` : ''}`;
  }

  function renderBpmnNodeDocs(nodeKey, rows) {
    const slot = document.getElementById('bpDocsSlot');
    if (!slot) return;
    const list = rows.map((row) => `
      <div class="between bpmn-node-row">
        <span>${esc(row.title)}</span>
        <span class="tag t-gry">${esc(row.category_label || row.category)}</span>
      </div>`).join('') || '<div class="tiny muted">该活动还没有标准文件</div>';
    slot.innerHTML = `
      <div class="between mb"><b>标准文件</b><span class="tiny muted">${rows.length} 份</span></div>
      ${list}
      <div class="gap mt">
        ${canManage()
          ? `<button class="btn-sm" data-act="designer.openNodeDoc"
              data-node="${esc(nodeKey)}">+ 新增标准文件</button>` : ''}
        <a class="link-btn link-btn-sm" data-act="designer.goDeliverables">去交付物与模板库</a>
      </div>`;
  }

  function renderBpmnNodeMeta(forms, rules) {
    const slot = document.getElementById('bpMetaSlot');
    if (!slot) return;
    const formRows = forms.length
      ? forms.map((form) => `<div class="tiny">${esc(form.name)}
          <span class="tag t-blu">${esc(form.status_label || form.status || '')}</span></div>`).join('')
      : '<div class="tiny muted">未配置表单</div>';
    const ruleRows = rules.length
      ? rules.map((rule) => `<div class="tiny">${esc(rule.name || rule.code || rule.id)}
          <span class="tag t-gry">${esc(rule.status_label || rule.status || '')}</span></div>`).join('')
      : '<div class="tiny muted">未配置分支规则</div>';
    const nodeKey = (state.designer.bpmnSelection || [])[0]?.businessObject?.id || '';
    slot.innerHTML = `
      <div class="between mb"><b>表单与分支规则</b>
        ${canManage()
          ? `<button class="btn-sm" data-act="designer.executionConfig"
              data-node="${esc(nodeKey)}">去执行页配置</button>` : ''}
      </div>
      <div class="tiny muted">表单（${forms.length}）</div>${formRows}
      <div class="tiny muted mt">分支规则（${rules.length}）</div>${ruleRows}`;
  }

  async function hydrateBpmnNodeExtras(nodeKey) {
    const st = state.designer;
    const pid = st.processId;
    const [toolsRes, docsRes, formsRes, rulesRes] = await Promise.allSettled([
      GET('/processes/' + pid + '/design/nodes/' + nodeKey + '/tools'),
      GET('/process-documents?process_id=' + pid + '&node_key=' + encodeURIComponent(nodeKey)),
      GET('/execution/forms?process_id=' + pid + '&node_key=' + encodeURIComponent(nodeKey)),
      GET('/execution/rules?process_id=' + pid + '&node_key=' + encodeURIComponent(nodeKey)),
    ]);
    const current = (st.bpmnSelection || [])[0];
    const currentId = current && current.businessObject ? current.businessObject.id : null;
    if (st.processId !== pid || currentId !== nodeKey) return;
    renderBpmnNodeTools(nodeKey, toolsRes.status === 'fulfilled' ? toolsRes.value : []);
    renderBpmnNodeDocs(nodeKey, docsRes.status === 'fulfilled' ? docsRes.value : []);
    renderBpmnNodeMeta(
      formsRes.status === 'fulfilled' ? formsRes.value : [],
      rulesRes.status === 'fulfilled' ? rulesRes.value : [],
    );
  }

  async function saveBpmnNodeActivity(nodeKey) {
    const st = state.designer;
    const select = document.getElementById('bpActivity');
    if (!select) return;
    const value = select.value ? Number(select.value) : null;
    try {
      const response = await PATCH(
        '/processes/' + st.processId + '/design/nodes/' + nodeKey,
        { process_arch_id: value, expected_version: st.model.version },
      );
      st.model = response;
      st.savedModel = ctx.cloneModel(response);
      st.analysis = await POST('/processes/' + st.processId + '/design/analyze', {});
      ctx.renderSelection(st.bpmnSelection || []);
      toast(value ? '已关联 L4 活动' : '已解除活动关联');
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function addBpmnNodeTool(nodeKey) {
    const code = document.getElementById('bpToolCode')?.value;
    if (!code) return toast('请选择工具', true);
    const level = document.getElementById('bpToolLevel')?.value || 'RECOMMENDED';
    try {
      await POST(
        '/processes/' + state.designer.processId + '/design/nodes/' + nodeKey + '/tools',
        { tool_code: code, level },
      );
      toast('工具已绑定');
      hydrateBpmnNodeExtras(nodeKey);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function removeBpmnNodeTool(nodeKey, toolCode) {
    try {
      await DEL(
        '/processes/' + state.designer.processId + '/design/nodes/' + nodeKey +
        '/tools/' + encodeURIComponent(toolCode),
      );
      toast('已解除工具绑定');
      hydrateBpmnNodeExtras(nodeKey);
    } catch (e) {
      toast(e.message, true);
    }
  }

  function openNodeDocumentModal(nodeKey) {
    const labels = (state.docMeta && state.docMeta.category_labels) || {};
    const options = Object.entries(labels).map(([value, label]) =>
      `<option value="${value}"${value === 'SOP' ? ' selected' : ''}>${esc(label)}</option>`).join('');
    openModal('新增活动标准文件', `
      <div class="field"><label>标题 *</label>
        <input id="ndTitle" placeholder="如：需求审批单"></div>
      <div class="row2">
        <div class="field"><label>类型</label><select id="ndCategory">${options}</select></div>
        <div class="field"><label>说明</label><input id="ndDesc"></div>
      </div>
      <div class="note">文件会挂到当前活动；版本、审批与上传在「交付物与模板库」里继续维护。</div>`,
    `<button class="btn btn-g" data-act="designer.close">取消</button>
     <button class="btn btn-p" data-act="designer.submitNodeDoc"
       data-node="${esc(nodeKey)}">创建</button>`);
  }

  async function submitNodeDocument(nodeKey) {
    const title = document.getElementById('ndTitle')?.value.trim();
    if (!title) return toast('标题必填', true);
    try {
      await POST('/process-documents', {
        process_id: state.designer.processId,
        node_key: nodeKey,
        title,
        category: document.getElementById('ndCategory')?.value || 'SOP',
        description: document.getElementById('ndDesc')?.value.trim() || null,
      });
      closeModal();
      toast('标准文件已创建');
      hydrateBpmnNodeExtras(nodeKey);
    } catch (e) {
      toast(e.message, true);
    }
  }

  function openExecutionConfig() {
    const nodeKey = (state.designer.bpmnSelection || [])[0]?.businessObject?.id || '';
    go('execution', {
      params: {
        process: state.designer.processId || '',
        tab: 'config',
        node: nodeKey,
      },
      push: true,
    });
  }

  async function saveBpmnAssignment(nodeKey) {
    try {
      await persistAssignment(nodeKey, {
        role: 'baRole',
        org: 'baOrg',
        assignee: 'baAssignee',
        due: 'baDue',
        escalationHours: 'baEscHours',
        escalationUser: 'baEscUser',
      });
      toast('节点执行配置已保存');
    } catch (e) {
      toast(e.message, true);
    }
  }

  return {
    renderBpmnAssignment,
    hydrateBpmnNodeExtras,
    saveBpmnNodeActivity,
    addBpmnNodeTool,
    removeBpmnNodeTool,
    openNodeDocumentModal,
    submitNodeDocument,
    openExecutionConfig,
    saveBpmnAssignment,
  };
}
