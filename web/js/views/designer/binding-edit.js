/* 设计器活动绑定办理；只引用原RACI/资源，不复制主数据。 */
import { esc } from '../../core/format.js';
import { GET, POST, DEL } from '../../core/api.js';
import { state } from '../../core/state.js';
import { canManage } from '../../core/auth.js';
import { openModal, modalAlive, on, toast } from '../../core/ui.js';

export function createBindingEdit(ctx) {
  let active = null;
  async function open(activity, node = '') {
    if (!canManage()) return;
    const process = state.designer.processId;
    const modelVersion = state.designer.model?.version;
    const token = {};
    active = token;
    try {
      const [matrix, resources, options, roles, meta] = await Promise.all([
        GET('/governance/raci?process_id=' + process),
        GET('/processes/' + process + '/resource-links'),
        GET('/processes/' + process + '/resource-link-options?activity_id=' + activity + (node ? '&node_key=' + encodeURIComponent(node) : '')),
        GET('/governance/roles?active_only=true'), GET('/governance/meta'),
      ]);
      if (active !== token || state.view !== 'designer' || state.designer.processId !== process) return;
      const activities = state.designer.binding?.activities || [];
      const selected = activities.find(item => item.activity_id === Number(activity));
      const modal = openModal('维护活动绑定', `
        <p class="tiny">在原活动登记责任与资源引用；不修改模型图形，不自动确认冻结依据。</p>
        <div id="bindingEditError" class="hint"></div>
        <div class="field"><label>活动</label><select id="bindingActivity" disabled>
          <option value="${activity}">${esc(selected?.activity_code || '')} ${esc(selected?.activity_name || '')}</option></select></div>
        <div class="row2"><div class="field"><label>治理角色</label><select id="bindingRole">
          ${roles.map(row => `<option value="${row.id}">${esc(row.name)}</option>`).join('')}</select></div>
          <div class="field"><label>RACI</label><select id="bindingRaci">${Object.entries(meta.raci_labels).map(([key,label]) => `<option value="${esc(key)}">${esc(label)}</option>`).join('')}</select></div></div>
        <button class="btn-sm" data-act="designer.bindingSaveRaci">保存活动责任</button>
        <div class="field mt"><label>引用已有资源</label><select id="bindingResource"><option value="">请选择原资源</option>
          ${options.options.map(row => `<option value="${esc(row.ref_key)}">${esc(row.resource_type_label)} · ${esc(row.label)}</option>`).join('')}</select></div>
        <div class="field"><label>外部设备/量具（仅登记引用）</label><select id="bindingExternalType"><option value="">不登记外部引用</option>
          ${['EQUIPMENT','MEASURE'].map(key => `<option value="${key}">${esc(options.resource_type_labels[key])}</option>`).join('')}</select>
          <input id="bindingExternalKey" placeholder="EQUIP:PUMP-01 / MEASURE:GAUGE-01"></div>
        <button class="btn-sm" data-act="designer.bindingSaveResource">保存资源引用</button>
        <div id="bindingEditRecords" class="mt"></div>`,
      '<button class="btn btn-g" data-act="ui.close">关闭</button>');
      active = {token, process, modelVersion, activity:Number(activity), node, modal, options:options.options, matrix, resources};
      paintRecords();
    } catch (error) { toast(error.message, true); }
  }
  function valid() {
    const a = active;
    if (!a || !modalAlive(a.modal)) return false;
    if (state.view !== 'designer' || state.designer.processId !== a.process || state.designer.model?.version !== a.modelVersion) {
      document.getElementById('bindingEditError').textContent = '流程或模型已变化，请关闭后重新办理';
      return false;
    }
    return true;
  }
  function paintRecords() {
    if (!active || !modalAlive(active.modal)) return;
    const {matrix, resources, activity} = active;
    const entries = matrix.matters.flatMap(group => group.entries).filter(row => row.activity_id === activity);
    document.getElementById('bindingEditRecords').innerHTML = `
      <h4>活动责任</h4>${entries.map(row => `<div class="between"><span>${esc(row.raci_label)} · ${esc(row.role_name)}</span>
        <button class="btn-sm" data-act="designer.bindingRemoveRaci" data-id="${row.id}">移除</button></div>`).join('') || '<p class="tiny">尚无活动责任</p>'}
      <h4>资源引用</h4>${resources.filter(row => row.activity_id === activity).map(row => `<div class="between"><span>${esc(row.resource_type_label)} · ${esc(row.source_label)}
        ${row.source_valid ? '' : '<b>已失效</b>'}</span><button class="btn-sm" data-act="designer.bindingRemoveResource" data-id="${row.id}">停用引用</button></div>`).join('') || '<p class="tiny">尚无资源引用</p>'}`;
  }
  async function reload(a) {
    const [matrix, resources] = await Promise.all([GET('/governance/raci?process_id=' + a.process), GET('/processes/' + a.process + '/resource-links')]);
    if (active !== a || !valid()) return;
    a.matrix = matrix; a.resources = resources;
    state.designer.raci = matrix;
    paintRecords();
    await ctx.refreshBinding();
  }
  async function write(kind, id) {
    if (!valid()) return;
    const a = active;
    document.getElementById('bindingEditError').textContent = '';
    try {
      if (kind === 'raci') {
        await POST('/governance/raci', {process_id:a.process, activity_id:a.activity, node_key:a.node || null,
          matter:'活动责任', role_id:Number(document.getElementById('bindingRole').value), raci:document.getElementById('bindingRaci').value});
      } else if (kind === 'resource') {
        const external = document.getElementById('bindingExternalType').value;
        const option = a.options.find(row => row.ref_key === document.getElementById('bindingResource').value);
        if (!external && !option) throw new Error('请选择原资源或规范外部引用');
        await POST('/processes/' + a.process + '/resource-links', {activity_id:a.activity, node_key:a.node || null,
          resource_type:external || option.resource_type, ref_id:external ? null : option.ref_id,
          ref_key:external ? document.getElementById('bindingExternalKey').value.trim() : option.ref_key});
      } else {
        await DEL(kind === 'removeRaci' ? '/governance/raci/' + id : '/processes/' + a.process + '/resource-links/' + id);
      }
      await reload(a);
    } catch (error) {
      if (active === a && modalAlive(a.modal)) document.getElementById('bindingEditError').textContent = error.message;
    }
  }
  on('designer.bindingEdit', ({activity,node}) => open(Number(activity),node || ''));
  on('designer.bindingSaveRaci', () => write('raci'));
  on('designer.bindingSaveResource', () => write('resource'));
  on('designer.bindingRemoveRaci', ({id}) => write('removeRaci',Number(id)));
  on('designer.bindingRemoveResource', ({id}) => write('removeResource',Number(id)));
  return {open};
}
