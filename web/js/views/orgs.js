/* 视图：组织与人员
 *
 * 组织树与人员都从接口读取，不在前端写死；写操作只对系统管理员开放。
 */
import { esc, dtShort, emptyRow, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, confirmDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { role } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';

on('orgs.tab', ({ tab }) => setAdminTab(tab));
on('orgs.createOrg', () => openOrgCreate());
on('orgs.editOrg', ({ id }) => openOrgEdit(Number(id)));
on('orgs.toggleOrg', ({ id, active }) => toggleOrgActive(Number(id), active === '1'));
on('orgs.deleteOrg', ({ id, name }) => deleteOrgAction(Number(id), name));
on('orgs.close', () => closeModal());
on('orgs.submitOrgCreate', () => submitOrgCreate());
on('orgs.submitOrgEdit', ({ id }) => submitOrgEdit(Number(id)));
on('orgs.createPosition', () => openPositionCreate());
on('orgs.editPosition', ({ id }) => openPositionEdit(Number(id)));
on('orgs.deletePosition', ({ id }) => deletePositionAction(Number(id)));
on('orgs.submitPositionNew', () => submitPosition(null));
on('orgs.submitPosition', ({ id }) => submitPosition(Number(id)));
on('orgs.createUser', () => openUserCreate());
on('orgs.editUser', ({ id }) => openUserEdit(Number(id)));
on('orgs.submitUserCreate', () => submitUserCreate());
on('orgs.submitUserEdit', ({ id }) => submitUserEdit(Number(id)));
on('orgs.userFilter', ({ filter }, el) => {
  setUserFilter(filter, el.type === 'checkbox' ? el.checked : el.value);
});

function adminState() {
  state.admin = state.admin || {
    tab: 'org', userKeyword: '', userOrgId: '', userRole: '', activeOnly: false,
  };
  return state.admin;
}

function flatten(nodes, depth = 0, out = []) {
  (nodes || []).forEach((node) => {
    out.push({ ...node, depth });
    flatten(node.children || [], depth + 1, out);
  });
  return out;
}

const renderOrgs = () => {
  if (role() !== 'ADMIN') {
    viewEl().innerHTML = `
      <div class="card">
        <h2>组织与人员</h2>
        <div class="note">该页面用于维护组织架构与人员账号，仅系统管理员可操作。</div>
      </div>`;
    return;
  }
  renderAsync('orgs',
    () => Promise.all([
      GET('/org-units/tree'),
      GET('/org-units'),
      GET('/org-units/meta'),
      GET('/auth/users'),
      GET('/auth/meta'),
      GET('/positions?active_only=false'),
    ]),
    ([tree, flat, orgMeta, users, authMeta, positions]) => {
      state.adminTree = tree;
      state.adminOrgs = flat;
      state.adminOrgMeta = orgMeta;
      state.adminUsers = users;
      state.adminAuthMeta = authMeta;
      state.adminPositions = positions;
      paintShell();
    });
};

function paintShell() {
  const a = adminState();
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div><h2>组织与人员<span class="module-badge">主数据 · 权限</span></h2>
          <div class="desc">组织编码与人员账号由系统管理员维护；人员归属组织用于标准文件/模板的继承范围</div></div>
      </div>
      <div class="tabs" style="margin-bottom:0">
        <button class="${a.tab === 'org' ? 'on' : ''}" data-act="orgs.tab" data-tab="org">
          组织架构（${(state.adminOrgs || []).length}）</button>
        <button class="${a.tab === 'user' ? 'on' : ''}" data-act="orgs.tab" data-tab="user">
          人员与角色（${(state.adminUsers || []).length}）</button>
        <button class="${a.tab === 'position' ? 'on' : ''}" data-act="orgs.tab" data-tab="position">
          岗位（${(state.adminPositions || []).length}）</button>
      </div>
    </div>
    <div id="adminBody"></div>`;
  if (a.tab === 'org') paintOrgTab();
  else if (a.tab === 'position') paintPositionTab();
  else paintUserTab();
}

function setAdminTab(tab) {
  adminState().tab = tab;
  paintShell();
}

/* -------------------------------------------------- 组织架构 */

function paintOrgTab() {
  const body = document.getElementById('adminBody');
  const rows = flatten(state.adminTree || []).map((org) => `
    <tr>
      <td><span style="display:inline-block;width:${org.depth * 18}px"></span>
        <b>${esc(org.name)}</b>
        <div class="tiny">${esc(org.code)} · ${esc(org.type_label || org.type)}</div></td>
      <td>${esc(org.path)}</td>
      <td>${org.child_count || 0}</td>
      <td>${org.is_active
        ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
      <td>${esc(org.description || '—')}</td>
      <td>
        <button class="btn-sm" data-act="orgs.editOrg" data-id="${org.id}">编辑</button>
        <button class="btn-sm" data-act="orgs.toggleOrg" data-id="${org.id}"
          data-active="${org.is_active ? '0' : '1'}">
          ${org.is_active ? '停用' : '启用'}</button>
        <button class="btn-sm" data-act="orgs.deleteOrg" data-id="${org.id}"
          data-name="${esc(org.name)}">删除</button>
      </td>
    </tr>`).join('') || emptyRow(6, '还没有组织，先新建集团/公司/部门');

  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <h3 style="margin:0">组织树</h3>
        <button class="btn btn-p" data-act="orgs.createOrg">+ 新建组织</button>
      </div>
      <table class="tbl">
        <thead><tr><th>组织</th><th>路径</th><th>下级</th><th>状态</th><th>说明</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="note mt">组织编码一旦使用不建议修改；有下级、标准文件或模板引用时只能停用，不能删除。</div>
    </div>`;
}

function orgOptions(selected) {
  return (state.adminOrgs || []).map((org) =>
    `<option value="${org.id}" ${String(selected) === String(org.id) ? 'selected' : ''}>
      ${'　'.repeat(0)}${esc(org.code)} · ${esc(org.name)}（${esc(org.type_label || org.type)}）</option>`).join('');
}

function openOrgCreate() {
  const types = (state.adminOrgMeta && state.adminOrgMeta.type_labels) || {};
  openModal('新建组织', `
    <div class="row2">
      <div class="field"><label>组织编码</label><input id="aoCode" placeholder="如 CO-EAST"></div>
      <div class="field"><label>名称</label><input id="aoName" placeholder="如 华东分公司"></div>
    </div>
    <div class="row2">
      <div class="field"><label>类型</label><select class="sel" id="aoType">
        ${Object.entries(types).map(([code, label]) =>
          `<option value="${code}">${esc(label)}</option>`).join('')}
      </select></div>
      <div class="field"><label>上级组织</label><select class="sel" id="aoParent">
        <option value="">无（根组织）</option>${orgOptions(null)}
      </select></div>
    </div>
    <div class="field"><label>说明</label><textarea id="aoDesc"></textarea></div>
    <div class="note">编码由系统内维护，全局唯一；后续可接 ERP/HR 同步。</div>`,
  `<button class="btn btn-g" data-act="orgs.close">取消</button>
   <button class="btn btn-p" data-act="orgs.submitOrgCreate">创建</button>`);
}

async function submitOrgCreate() {
  const code = document.getElementById('aoCode').value.trim();
  const name = document.getElementById('aoName').value.trim();
  if (!code || !name) return toast('请填写组织编码与名称', true);
  const parent = document.getElementById('aoParent').value;
  const payload = {
    code,
    name,
    type: document.getElementById('aoType').value,
    description: document.getElementById('aoDesc').value.trim() || null,
  };
  if (parent) payload.parent_id = Number(parent);
  try {
    const org = await POST('/org-units', payload);
    toast('已创建组织 ' + org.name);
    closeModal();
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

function openOrgEdit(orgId) {
  const org = (state.adminOrgs || []).find((row) => row.id === orgId);
  if (!org) return;
  const types = (state.adminOrgMeta && state.adminOrgMeta.type_labels) || {};
  openModal('编辑组织 · ' + org.code, `
    <div class="field"><label>名称</label><input id="aeName" value="${esc(org.name)}"></div>
    <div class="field"><label>类型</label><select class="sel" id="aeType">
      ${Object.entries(types).map(([code, label]) =>
        `<option value="${code}" ${org.type === code ? 'selected' : ''}>${esc(label)}</option>`).join('')}
    </select></div>
    <div class="field"><label>说明</label><textarea id="aeDesc">${esc(org.description || '')}</textarea></div>
    <div class="field"><label>状态</label><select class="sel" id="aeActive">
      <option value="true" ${org.is_active ? 'selected' : ''}>启用</option>
      <option value="false" ${org.is_active ? '' : 'selected'}>停用</option>
    </select></div>
    <div class="note">上级组织与编码不支持在这里修改，避免破坏继承路径。</div>`,
  `<button class="btn btn-g" data-act="orgs.close">取消</button>
   <button class="btn btn-p" data-act="orgs.submitOrgEdit" data-id="${org.id}">保存</button>`);
}

async function submitOrgEdit(orgId) {
  const name = document.getElementById('aeName').value.trim();
  if (!name) return toast('请填写组织名称', true);
  try {
    await PATCH('/org-units/' + orgId, {
      name,
      type: document.getElementById('aeType').value,
      description: document.getElementById('aeDesc').value.trim() || null,
      is_active: document.getElementById('aeActive').value === 'true',
    });
    toast('组织已更新');
    closeModal();
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

async function toggleOrgActive(orgId, active) {
  try {
    await PATCH('/org-units/' + orgId, { is_active: active });
    toast(active ? '组织已启用' : '组织已停用');
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteOrgAction(orgId, name) {
  const ok = await confirmDialog(
    `确认删除组织「${name}」？有下级或资产引用时会被拒绝。`,
    { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/org-units/' + orgId);
    toast('组织已删除');
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 岗位 */

function positionOptions(selected) {
  return (state.adminPositions || []).filter((row) => row.is_active)
    .map((row) => `<option value="${row.id}" ${
      String(selected) === String(row.id) ? 'selected' : ''}>${esc(row.code)} · ${
      esc(row.name)}</option>`).join('');
}

function paintPositionTab() {
  const body = document.getElementById('adminBody');
  const rows = state.adminPositions || [];
  const table = rows.map((row) => `
    <tr>
      <td><span class="map-code">${esc(row.code)}</span></td>
      <td><b>${esc(row.name)}</b>${row.description
        ? `<div class="tiny">${esc(row.description)}</div>` : ''}</td>
      <td>${esc(row.org_unit_name || '集团通用')}</td>
      <td>${row.is_active
        ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
      <td><button class="btn-sm" data-act="orgs.editPosition" data-id="${row.id}">编辑</button>
        <button class="btn-sm" data-act="orgs.deletePosition" data-id="${row.id}">删除</button></td>
    </tr>`).join('') || emptyRow(5, '还没有岗位，先建一个岗位再绑定人员和流程节点');

  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <div><h3 style="margin:0">岗位主数据</h3>
          <div class="tiny">岗位连接人员与流程活动；被引用时只能停用，不能删除</div></div>
        <button class="btn btn-p" data-act="orgs.createPosition">+ 新建岗位</button>
      </div>
      <table class="tbl">
        <thead><tr><th>编码</th><th>岗位</th><th>所属组织</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>${table}</tbody>
      </table>
    </div>`;
}

function positionModal(row) {
  return `
    <div class="row2">
      <div class="field"><label>岗位编码 *</label>
        <input id="posCode" value="${esc(row ? row.code : '')}" ${row ? 'readonly' : ''}
          placeholder="如 POS-009"></div>
      <div class="field"><label>岗位名称 *</label>
        <input id="posName" value="${esc(row ? row.name : '')}" placeholder="如 采购计划员"></div>
    </div>
    <div class="row2">
      <div class="field"><label>所属组织</label>
        <select class="sel" id="posOrg"><option value="">集团通用</option>${
          orgOptions(row ? row.org_unit_id : null)}</select></div>
      <div class="field"><label>状态</label>
        <select class="sel" id="posActive">
          <option value="true" ${!row || row.is_active ? 'selected' : ''}>启用</option>
          <option value="false" ${row && !row.is_active ? 'selected' : ''}>停用</option>
        </select></div>
    </div>
    <div class="field"><label>说明</label>
      <textarea id="posDesc">${esc(row ? row.description || '' : '')}</textarea></div>
    <div class="note">岗位被人员或流程节点引用后不能删除；组织调整时优先停用。</div>`;
}

function openPositionCreate() {
  openModal('新建岗位', positionModal(null),
    `<button class="btn btn-g" data-act="orgs.close">取消</button>
     <button class="btn btn-p" data-act="orgs.submitPositionNew">创建</button>`);
}

function openPositionEdit(positionId) {
  const row = (state.adminPositions || []).find((item) => item.id === positionId);
  if (!row) return;
  openModal('编辑岗位 · ' + row.code, positionModal(row),
    `<button class="btn btn-g" data-act="orgs.close">取消</button>
     <button class="btn btn-p" data-act="orgs.submitPosition" data-id="${row.id}">保存</button>`);
}

async function submitPosition(positionId) {
  const code = document.getElementById('posCode').value.trim();
  const name = document.getElementById('posName').value.trim();
  if (!name) return toast('岗位名称必填', true);
  const org = document.getElementById('posOrg').value;
  const payload = {
    name,
    org_unit_id: org ? Number(org) : null,
    description: document.getElementById('posDesc').value.trim() || null,
    is_active: document.getElementById('posActive').value === 'true',
  };
  try {
    if (positionId) {
      await PATCH('/positions/' + positionId, payload);
      toast('岗位已更新');
    } else {
      if (!code) return toast('岗位编码必填', true);
      await POST('/positions', { code, ...payload });
      toast('岗位已创建');
    }
    closeModal();
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deletePositionAction(positionId) {
  const row = (state.adminPositions || []).find((item) => item.id === positionId);
  if (!row) return;
  const ok = await confirmDialog(`删除岗位「${row.name}」？`, { danger: true, okText: '删除' });
  if (!ok) return;
  try {
    await DEL('/positions/' + positionId);
    toast('岗位已删除');
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 人员与角色 */

function filteredUsers() {
  const a = adminState();
  const keyword = (a.userKeyword || '').toLowerCase();
  return (state.adminUsers || []).filter((user) => {
    if (a.userOrgId && String(user.org_unit_id) !== String(a.userOrgId)) return false;
    if (a.userRole && user.role !== a.userRole) return false;
    if (a.activeOnly && !user.is_active) return false;
    if (keyword) {
      const text = [user.username, user.display_name, user.department || '', user.org_unit_name || '']
        .join(' ').toLowerCase();
      if (!text.includes(keyword)) return false;
    }
    return true;
  });
}

function paintUserTab() {
  const body = document.getElementById('adminBody');
  const a = adminState();
  const roles = (state.adminAuthMeta && state.adminAuthMeta.roles) || [];
  const users = filteredUsers();
  const rows = users.map((user) => `
    <tr>
      <td><b>${esc(user.display_name)}</b><div class="tiny">${esc(user.username)}</div></td>
      <td><span class="tag t-blu">${esc(user.role_label || user.role)}</span></td>
      <td>${esc(user.org_unit_name || '未分配')}</td>
      <td>${esc(user.position_name || '未分配')}</td>
      <td>${esc(user.department || '—')}</td>
      <td>${user.is_active
        ? '<span class="tag t-grn">启用</span>' : '<span class="tag t-gry">停用</span>'}</td>
      <td>${user.last_login_at ? dtShort(user.last_login_at) : '从未登录'}</td>
      <td><button class="btn-sm" data-act="orgs.editUser" data-id="${user.id}">编辑</button></td>
    </tr>`).join('') || emptyRow(8, '没有符合条件的人员');

  body.innerHTML = `
    <div class="card">
      <div class="between mb">
        <h3 style="margin:0">人员与角色</h3>
        <button class="btn btn-p" data-act="orgs.createUser">+ 新建人员</button>
      </div>
      <div class="gap mb" style="flex-wrap:wrap">
        <input class="sel" style="min-width:200px" placeholder="搜索用户名 / 姓名 / 部门"
          value="${esc(a.userKeyword || '')}" data-act="orgs.userFilter"
          data-filter="userKeyword">
        <select class="sel" data-act="orgs.userFilter" data-filter="userRole">
          <option value="">全部角色</option>
          ${roles.map((r) => `<option value="${r.value}"
            ${a.userRole === r.value ? 'selected' : ''}>${esc(r.label)}</option>`).join('')}
        </select>
        <select class="sel" data-act="orgs.userFilter" data-filter="userOrgId">
          <option value="">全部组织</option>
          ${(state.adminOrgs || []).map((org) => `<option value="${org.id}"
            ${String(a.userOrgId) === String(org.id) ? 'selected' : ''}>
            ${esc(org.code)} · ${esc(org.name)}</option>`).join('')}
        </select>
        <label class="tiny gap" style="gap:6px">
          <input type="checkbox" ${a.activeOnly ? 'checked' : ''}
            data-act="orgs.userFilter" data-filter="activeOnly">只看启用
        </label>
        <span class="tiny">${users.length} / ${(state.adminUsers || []).length} 人</span>
      </div>
      <table class="tbl">
        <thead><tr><th>人员</th><th>角色</th><th>组织</th><th>岗位</th><th>部门</th><th>状态</th><th>最近登录</th><th>操作</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="note mt">停用账号不会删除历史审计；最后一个启用的管理员不能被停用或降级。</div>
    </div>`;
}

function setUserFilter(key, value) {
  adminState()[key] = value;
  paintUserTab();
}

function roleOptions(selected) {
  const roles = (state.adminAuthMeta && state.adminAuthMeta.roles) || [];
  return roles.map((r) => `<option value="${r.value}"
    ${selected === r.value ? 'selected' : ''}>${esc(r.label)}</option>`).join('');
}

function openUserCreate() {
  openModal('新建人员', `
    <div class="row2">
      <div class="field"><label>用户名</label><input id="auUsername" placeholder="登录名"></div>
      <div class="field"><label>姓名</label><input id="auName" placeholder="显示名称"></div>
    </div>
    <div class="row2">
      <div class="field"><label>初始口令</label><input id="auPassword" type="password"
        placeholder="至少 6 位"></div>
      <div class="field"><label>角色</label><select class="sel" id="auRole">
        ${roleOptions('VIEWER')}
      </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>归属组织</label><select class="sel" id="auOrg">
        <option value="">未分配</option>${orgOptions(null)}
      </select></div>
      <div class="field"><label>岗位</label><select class="sel" id="auPosition">
        <option value="">未分配</option>${positionOptions(null)}
      </select></div>
    </div>
    <div class="field"><label>部门（可选）</label><input id="auDept" placeholder="部门标签"></div>
    <div class="note">人员归属组织决定其可见的集团/分公司标准，不影响项目归属权限。</div>`,
  `<button class="btn btn-g" data-act="orgs.close">取消</button>
   <button class="btn btn-p" data-act="orgs.submitUserCreate">创建</button>`);
}

async function submitUserCreate() {
  const username = document.getElementById('auUsername').value.trim();
  const displayName = document.getElementById('auName').value.trim();
  const password = document.getElementById('auPassword').value;
  if (!username || !displayName || password.length < 6) {
    return toast('请填写用户名、姓名，口令至少 6 位', true);
  }
  const org = document.getElementById('auOrg').value;
  const position = document.getElementById('auPosition').value;
  const payload = {
    username,
    display_name: displayName,
    password,
    role: document.getElementById('auRole').value,
    department: document.getElementById('auDept').value.trim() || null,
    org_unit_id: org ? Number(org) : null,
    position_id: position ? Number(position) : null,
  };
  try {
    const user = await POST('/auth/users', payload);
    toast('已创建人员 ' + user.display_name);
    closeModal();
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

function openUserEdit(userId) {
  const user = (state.adminUsers || []).find((row) => row.id === userId);
  if (!user) return;
  openModal('编辑人员 · ' + user.username, `
    <div class="field"><label>姓名</label><input id="ueName" value="${esc(user.display_name)}"></div>
    <div class="row2">
      <div class="field"><label>角色</label><select class="sel" id="ueRole">
        ${roleOptions(user.role)}
      </select></div>
      <div class="field"><label>归属组织</label><select class="sel" id="ueOrg">
        <option value="">未分配</option>
        <option value="" disabled></option>
        ${orgOptions(user.org_unit_id)}
      </select></div>
    </div>
    <div class="row2">
      <div class="field"><label>岗位</label><select class="sel" id="uePosition">
        <option value="">未分配</option>${positionOptions(user.position_id)}
      </select></div>
      <div class="field"><label>部门（可选）</label>
        <input id="ueDept" value="${esc(user.department || '')}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>状态</label><select class="sel" id="ueActive">
        <option value="true" ${user.is_active ? 'selected' : ''}>启用</option>
        <option value="false" ${user.is_active ? '' : 'selected'}>停用</option>
      </select></div>
      <div class="field"><label>重置口令（可选）</label><input id="uePassword" type="password"
        placeholder="留空表示不修改"></div>
    </div>
    <div class="note">用户名不可修改；停用后无法登录，但历史审计与项目归属保留。</div>`,
  `<button class="btn btn-g" data-act="orgs.close">取消</button>
   <button class="btn btn-p" data-act="orgs.submitUserEdit" data-id="${user.id}">保存</button>`);
}

async function submitUserEdit(userId) {
  const payload = {
    display_name: document.getElementById('ueName').value.trim(),
    role: document.getElementById('ueRole').value,
    org_unit_id: document.getElementById('ueOrg').value
      ? Number(document.getElementById('ueOrg').value) : null,
    position_id: document.getElementById('uePosition').value
      ? Number(document.getElementById('uePosition').value) : null,
    department: document.getElementById('ueDept').value.trim() || null,
    is_active: document.getElementById('ueActive').value === 'true',
  };
  const password = document.getElementById('uePassword').value;
  if (password) payload.password = password;
  if (!payload.display_name) return toast('姓名不能为空', true);
  try {
    await PATCH('/auth/users/' + userId, payload);
    toast('人员信息已更新');
    closeModal();
    RENDERERS.orgs();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderOrgs };
