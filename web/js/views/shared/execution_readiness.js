/* 原执行配置的上线准备，不建立独立部署台账。 */
import { PUT, POST } from '../../core/api.js';
import { esc, dtShort } from '../../core/format.js';
import { on, openModal, closeModal, modalAlive, toast } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { go, RENDERERS } from '../../core/router.js';
import { AUTH, canManage, canWrite } from '../../core/auth.js';

let current = null;
let form = null;
const alive = c => c && state.view === 'execution' && state.execution.tab === 'config'
  && Number(state.execution.configProcess) === c.processId;

export function executionReadinessHtml(data) {
  if (!data) return '';
  current = { data, processId: data.process_id };
  const saved = data.readiness;
  const decision = saved?.confirmation;
  const rows = Object.entries(data.requirement_labels).map(([key, label]) => {
    const req = saved?.requirements[key];
    return `<tr><td>${esc(label)}</td><td>${data.facts[key] ? '原配置已齐' : '原配置未齐'}</td><td>${req ? esc(data.mode_labels[req.mode]) : '待约定'}</td><td>${esc(req?.reason || '—')}</td></tr>`;
  }).join('');
  return `<section class="card mt" id="executionReadiness"><div class="between"><h3>上线准备</h3><div class="gap">
    ${canManage() ? '<button class="btn-sm" data-act="ready.edit">维护准备约定</button>' : ''}
    ${canWrite() && saved?.reviewer_user_id === AUTH.user?.id && saved?.edited_by_id !== AUTH.user?.id ? '<button class="btn-sm" data-act="ready.confirm">记录本人决定</button>' : ''}</div></div>
    <p><b>${esc(data.state_label)}</b> · 原发布模型 #${data.published_model_version_id || '未发布'} · 修订 ${data.revision}</p>
    ${data.binding_gate ? `<div data-execution-binding-gate><p><b>${esc(data.binding_gate.profile_label)}</b> · ${esc(data.binding_gate.consistency_label)}</p>
      ${data.binding_gate.blockers.map(b => `<p class="tiny">${esc(b.message)}</p>`).join('')}
      ${data.nodes.map(n => `<button class="btn-sm btn-g" data-act="ready.bindingNode" data-node="${esc(n.node_key)}">回原节点 ${esc(n.name)}</button>`).join(' ')}</div>` : ''}
    <table class="tbl"><thead><tr><th>条件</th><th>当前事实</th><th>约定</th><th>依据</th></tr></thead><tbody>${rows}</tbody></table>
    <details><summary>逐任务适用性与配置</summary>${data.nodes.map(n => `<p class="tiny"><b>${esc(n.name)} · ${esc(n.node_key)}</b>：${Object.entries(data.requirement_labels).map(([key,label]) => { const req=saved?.node_requirements?.[n.node_key]?.[key] || saved?.requirements[key]; return esc(label)+' '+(req?esc(data.mode_labels[req.mode]):'待约定')+' · '+(n.facts[key]?'已配置':'未配置')+(req?.reason?'（'+esc(req.reason)+'）':''); }).join('；')}</p>`).join('')}</details>
    ${data.missing.length ? `<p class="warnbox">待补：${data.missing.map(esc).join('；')}</p>` : ''}
    ${saved ? `<p class="tiny">准备依据：${esc(saved.evidence)}<br>回退准备：${esc(saved.rollback_note)}</p>` : ''}
    ${decision ? `<p class="tiny">${esc(decision.name)} · ${esc(data.decision_labels[decision.decision])} · ${esc(dtShort(decision.at))} · ${esc(decision.evidence)}</p>` : ''}
    <p class="tiny muted">${data.limitations.map(esc).join(' ')}</p></section>`;
}

on('ready.edit', () => {
  const c = current;
  if (!alive(c)) return;
  const d = c.data, saved = d.readiness;
  const gen = openModal('维护上线准备约定', `
    <div class="note">只维护当前原发布的准备条件；不适用必须说明理由，保存后清除原本人决定。</div>
    <div class="field"><label>指定非编辑者核对 *</label><select id="erReviewer"><option value="">请选择</option>${d.reviewers.filter(u => u.id !== AUTH.user?.id).map(u => `<option value="${u.id}"${u.id === saved?.reviewer_user_id ? ' selected' : ''}>${esc(u.name)}</option>`).join('')}</select></div>
    ${Object.entries(d.requirement_labels).map(([key, label]) => `<div class="field"><label>${esc(label)} *</label><select id="erMode-${key}">${Object.entries(d.mode_labels).map(([mode, text]) => `<option value="${mode}"${mode === saved?.requirements[key]?.mode ? ' selected' : ''}>${esc(text)}</option>`).join('')}</select><textarea id="erReason-${key}" placeholder="适用性依据">${esc(saved?.requirements[key]?.reason || '')}</textarea></div>`).join('')}
    <details><summary>逐任务覆盖默认约定（未覆盖则继承上方）</summary>${d.nodes.map((n,i) => `<h4>${esc(n.name)} · ${esc(n.node_key)}</h4>${Object.entries(d.requirement_labels).map(([key,label]) => {const req=saved?.node_requirements?.[n.node_key]?.[key];return `<div class="field"><label>${esc(label)}</label><select id="erNodeMode-${i}-${key}"><option value="">继承默认约定</option>${Object.entries(d.mode_labels).map(([mode,text])=>`<option value="${mode}"${req?.mode===mode?' selected':''}>${esc(text)}</option>`).join('')}</select><textarea id="erNodeReason-${i}-${key}" placeholder="覆盖依据">${esc(req?.reason || '')}</textarea></div>`;}).join('')}`).join('')}</details>
    <div class="field"><label>核对依据 *</label><textarea id="erEvidence">${esc(saved?.evidence || '')}</textarea></div>
    <div class="field"><label>失败与回退准备 *</label><textarea id="erRollback">${esc(saved?.rollback_note || '')}</textarea></div>`,
  '<button class="btn btn-g" data-act="ui.close">取消</button><button class="btn btn-p" data-act="ready.save">保存准备约定</button>', true);
  form = { ...c, gen, revision: d.revision, busy: false };
});

on('ready.confirm', () => {
  const c = current;
  if (!alive(c)) return;
  const gen = openModal('本人核对上线准备', `<p class="note">核对当前发布和原配置；准备确认不代表运行有效或改善达标。</p><div class="field"><label>决定</label><select id="erDecision">${Object.entries(c.data.decision_labels).map(([key, label]) => `<option value="${key}">${esc(label)}</option>`).join('')}</select></div><div class="field"><label>本人核对依据 *</label><textarea id="erDecisionEvidence"></textarea></div>`,
    '<button class="btn btn-g" data-act="ui.close">取消</button><button class="btn btn-p" data-act="ready.submitConfirm">保存本人决定</button>');
  form = { ...c, gen, revision: c.data.revision, busy: false };
});

async function submit(confirm) {
  const c = form;
  if (!alive(c) || !modalAlive(c.gen)) return toast('流程上下文已变化，请重新打开准备约定', true);
  if (c.busy) return;
  const val = id => document.getElementById(id)?.value.trim() || '';
  const payload = confirm ? { expected_revision: c.revision, decision: val('erDecision'), evidence: val('erDecisionEvidence') }
    : { expected_revision: c.revision, reviewer_user_id: Number(val('erReviewer')),
      requirements: Object.fromEntries(Object.keys(c.data.requirement_labels).map(key => [key, { mode: val('erMode-' + key), reason: val('erReason-' + key) }])),
      node_requirements: Object.fromEntries(c.data.nodes.map((n,i) => [n.node_key, Object.fromEntries(Object.keys(c.data.requirement_labels).filter(key=>val(`erNodeMode-${i}-${key}`)).map(key=>[key,{mode:val(`erNodeMode-${i}-${key}`),reason:val(`erNodeReason-${i}-${key}`)}]))]).filter(([,items])=>Object.keys(items).length)),
      evidence: val('erEvidence'), rollback_note: val('erRollback') };
  c.busy = true;
  try {
    await (confirm ? POST : PUT)('/execution/readiness' + (confirm ? '/confirm' : '') + '?process_id=' + c.processId, payload);
    if (modalAlive(c.gen)) closeModal();
    toast(confirm ? '本人准备决定已记录' : '准备约定已保存，待本人确认');
    if (alive(c)) RENDERERS.execution();
  } catch (e) { toast(e.message, true); }
  finally { c.busy = false; }
}
on('ready.save', () => submit(false));
on('ready.submitConfirm', () => submit(true));

on('ready.bindingNode', ({ node }) => {
  const c = current;
  if (!alive(c)) return;
  go('designer', { params: { process: c.processId, node, basis: c.data.published_model_version_id, tab: 'model' }, push: true });
});
