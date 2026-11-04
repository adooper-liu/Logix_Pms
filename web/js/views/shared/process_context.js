/* 原章程和SIPOC交接的办理组件，不另建业务状态。 */
import { GET, POST, PUT } from '../../core/api.js';
import { esc, dtShort } from '../../core/format.js';
import { on, openModal, closeModal, toast, modalAlive } from '../../core/ui.js';
import { go, RENDERERS } from '../../core/router.js';
import { state } from '../../core/state.js';
import { AUTH, canManage, canWrite } from '../../core/auth.js';
import { openToolSheet } from './tool_sheet.js';

let loaded = null;
let charterForm = null;

export function contextHtml(card, charter) {
  loaded = { card, charter };
  const details = charter?.details || {};
  const rows = (card.handoffs || []).map(row => {
    const h = row.handoff;
    const decisions = h.confirmations || {};
    return `<article class="bpmn-node-row"><b>SIPOC #${row.id} · ${esc(row.confirmation_label)}</b>
      <p class="tiny">提供流程 ${row.process_id} → 接收流程 ${h.receiver_process_id} · 模板版本 #${row.template_version_id || '未固定'}</p>
      <p class="tiny">${row.fields.map(f => esc(f.label) + '：' + esc(f.value)).join('；')}</p>
      <p class="tiny">质量：${esc(h.quality)} · 时间：${esc(h.timing)} · 例外：${esc(h.exception_path)}</p>
      ${h.standard_version_id ? `<p class="tiny">原标准版本 #${h.standard_version_id}</p>` : ''}
      ${['provider','receiver'].map(side => `<div class="tiny">${side === 'provider' ? '提供方' : '接收方'}：${decisions[side] ? esc(decisions[side].name) + ' · ' + esc(decisions[side].evidence) + ' · ' + esc(dtShort(decisions[side].at)) : '待本人确认'}
        ${canWrite() && AUTH.user?.id === h[side + '_user_id'] ? `<button class="btn-sm" data-act="context.confirm" data-id="${row.id}" data-side="${side}" data-revision="${row.revision}">记录本人决定</button>` : ''}</div>`).join('')}
      </article>`;
  }).join('');
  const scope = charter?.charter;
  return `<section id="processContext"><h3>边界与交接</h3>
    <p class="tiny muted">声明、本人接收与授权批准分开；原记录存在不代表业务已通过。</p>
    <div class="card"><div class="between"><b>原流程章程 · ${esc(charter?.verification_label || 'L4范围请查看所属L3章程')}</b>
      ${charter && canManage() ? '<button class="btn-sm" data-act="context.editCharter">维护范围与客户结果</button>' : ''}</div>
      <p>客户：${esc(details.customer || '未记录')} · 客户结果：${esc(details.customer_result || '未记录')}</p>
      <p class="tiny">${scope ? esc(scope.starts_at + ' → ' + scope.ends_at) + '<br>' + esc(scope.in_scope) + '；不含：' + esc(scope.out_of_scope) : '尚无原范围说明'}</p>
      <p class="tiny">Owner：${esc(card.process.owner || '未指定')}（沿用流程目录） · 战略目标 ${details.objective_id ? '#' + details.objective_id : '未关联'}</p>
      <p class="tiny muted">${esc(charter?.reference_label || '')}</p>
      <p class="tiny">授权版本：${details.mandate_version_id || '未固定'} · 资源版本：${details.resource_version_id || '未固定'}<br>资源承诺：${esc(details.resource_commitment || '未记录')} · 复核日期：${esc(details.review_due || '未约定')}</p>
      <div class="gap"><button class="btn-sm" data-act="context.original" data-view="strategy">核对原战略目标</button><button class="btn-sm" data-act="process_card.raci">核对原RACI</button><button class="btn-sm" data-act="context.original" data-view="authorization">核对原授权</button></div></div>
    <div class="between mt"><h4>原SIPOC横向交接</h4>${canWrite() ? '<button class="btn-sm" data-act="context.newHandoff">填写SIPOC并记录交接</button>' : ''}</div>
    ${rows || '<div class="empty">尚无交接记录；先约定提供者、接收者、质量、时间和例外，再由本人确认。</div>'}</section>`;
}

on('context.original', ({view}) => go(view,{params:{process:state.processCard.processId},push:true}));
on('context.newHandoff', () => openToolSheet('SIPOC',state.processCard.processId));
on('context.editCharter', async () => {
  if (!loaded?.charter) return;
  const snapshot = loaded;
  const gen = openModal('加载原章程','<div class="empty">加载中…</div>');
  try {
    const [options, objectives, documents] = await Promise.all([GET('/start/charter-options'),GET('/strategy/objectives'),GET('/process-documents')]);
    if (!modalAlive(gen)) return;
    const c = snapshot.charter.charter || {};
    const d = snapshot.charter.details || {};
    const field = (id,label,value) => `<div class="field"><label>${label}</label><textarea id="cc${id}" rows="2">${esc(value || '')}</textarea></div>`;
    const versionOptions = (documents || []).filter(row => row.current_version?.status === 'EFFECTIVE').map(row => `<option value="${row.current_version.id}">${esc(row.code + ' ' + row.title)} · ${esc(row.current_version.version_label)}</option>`).join('');
    const formGen = openModal('原流程章程 · 范围、客户与依据',`
      <div class="note">Owner沿原目录；这里记录依据，不授系统权限、不自动批准资源。</div>
      ${field('Purpose','流程目的 *',c.purpose)}${field('Starts','开始 *',c.starts_at)}${field('Ends','结束 *',c.ends_at)}${field('In','范围内 *',c.in_scope)}${field('Out','范围外 *',c.out_of_scope)}${field('Stop','停止/升级条件 *',c.stop_condition)}
      <div class="field"><label>Sponsor *</label><select id="ccSponsor">${options.users.map(row => `<option value="${row.id}"${row.id === c.sponsor_user_id ? ' selected' : ''}>${esc(row.display_name)}</option>`).join('')}</select></div>
      ${field('Customer','客户/接收方',d.customer)}${field('Result','客户结果与价值要求',d.customer_result)}
      <div class="field"><label>原战略目标</label><select id="ccObjective"><option value="">未关联</option>${objectives.filter(row => (row.links || []).some(link => snapshot.card.chain.some(node => node.id === link.process_id))).map(row => `<option value="${row.id}"${row.id === d.objective_id ? ' selected' : ''}>${esc(row.code + ' ' + row.name)}</option>`).join('')}</select></div>
      <div class="field"><label>授权依据（已生效标准版本）</label><select id="ccMandate"><option value="">未固定</option>${versionOptions}</select></div>
      <div class="field"><label>资源依据（已生效标准版本）</label><select id="ccResourceVersion"><option value="">未固定</option>${versionOptions}</select></div>
      ${field('Resources','资源承诺/限制',d.resource_commitment)}<div class="field"><label>复核日期</label><input type="date" id="ccReview" value="${esc(d.review_due || '')}"></div>${field('Evidence','原核验依据（不代替批准）',d.verification_evidence)}`,
      '<button class="btn btn-g" data-act="context.close">取消</button><button class="btn btn-p" data-act="context.saveCharter">保存原章程</button>');
    charterForm = {processId:snapshot.charter.process_id,revision:snapshot.charter.revision,gen:formGen};
    for (const [id,value] of [['ccMandate',d.mandate_version_id],['ccResourceVersion',d.resource_version_id]]) {
      const el=document.getElementById(id);
      if (value && ![...el.options].some(row => row.value === String(value))) el.add(new Option('已固定原版本 #' + value,String(value)));
      el.value=value || '';
    }
  } catch(e) { if(modalAlive(gen)) toast(e.message,true); }
});
on('context.close', () => closeModal());
on('context.saveCharter', async () => {
  const val = id => document.getElementById(id)?.value.trim() || '';
  const form = charterForm;
  if (!form || !modalAlive(form.gen) || state.view !== 'process_card' || state.processCard.processId !== form.processId) return toast('流程上下文已变化，请关闭后重新打开原章程',true);
  const pid = form.processId;
  const payload={process_id:pid,expected_revision:form.revision,purpose:val('ccPurpose'),starts_at:val('ccStarts'),ends_at:val('ccEnds'),in_scope:val('ccIn'),out_of_scope:val('ccOut'),stop_condition:val('ccStop'),sponsor_user_id:Number(val('ccSponsor')),
    details:{customer:val('ccCustomer') || null,customer_result:val('ccResult') || null,objective_id:Number(val('ccObjective')) || null,mandate_version_id:Number(val('ccMandate')) || null,resource_version_id:Number(val('ccResourceVersion')) || null,resource_commitment:val('ccResources') || null,review_due:val('ccReview') || null,verification_evidence:val('ccEvidence') || null}};
  try { await PUT('/start/charters/'+pid,payload);closeModal();toast('原章程已保存，授权与资源仍需核对原依据');RENDERERS.process_card(); } catch(e) {toast(e.message,true);}
});
on('context.confirm', ({id,side,revision}) => {
  openModal('本人交接决定',`<p class="note">只记录本人对这份原产物的决定，不代替授权或效果验收。</p><div class="field"><label>决定</label><select id="hcDecision"><option value="ACCEPT">确认接收约定</option><option value="REJECT">存在异议</option></select></div><div class="field"><label>核验依据 *</label><textarea id="hcEvidence" rows="3"></textarea></div>`,
    `<button class="btn btn-g" data-act="context.close">取消</button><button class="btn btn-p" data-act="context.submitConfirm" data-id="${id}" data-side="${side}" data-revision="${revision}">保存本人决定</button>`);
});
on('context.submitConfirm', async ({id,side,revision}) => {
  try { await POST('/tools/SIPOC/sheets/'+id+'/confirm',{side,expected_revision:Number(revision),decision:document.getElementById('hcDecision').value,evidence:document.getElementById('hcEvidence').value});closeModal();toast('本人交接决定已记录');RENDERERS.process_card(); } catch(e) {toast(e.message,true);}
});
