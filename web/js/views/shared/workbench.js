/* 原画布/分析页直接办理作业；数据只落原方法记录。 */
import { GET, POST } from '../../core/api.js';
import { esc, dtShort } from '../../core/format.js';
import { on, openModal, closeModal, toast, modalAlive } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { RENDERERS, go, urlParams } from '../../core/router.js';
import { AUTH, canWrite } from '../../core/auth.js';

let current = null;
let form = null;
let receiptForm = null;

export function workbenchHtml(data, kind, view) {
  if (!data) return '';
  current={data,kind,view,processId:data.process_id,projectId:Number(urlParams().project) || null};
  const models=data.models || [];
  const latest=models[0];
  const rows=data.records.map(row => `<article class="bpmn-node-row"><div class="between"><b>${esc(data.kind_labels[row.work_context.kind])} #${row.id}</b><span class="tag t-blu">${esc(row.review_label)}</span></div>
    <p class="tiny">原模型 #${row.work_context.model_version_id} · ${esc(data.source_labels[row.work_context.source_kind])}${row.work_context.upstream_sheet_id ? ' · 上游原产物 #'+row.work_context.upstream_sheet_id : ''}</p>
    <p class="tiny">${row.fields.map(f => esc(f.label)+'：'+esc(f.value)).join('；')}</p>
    ${row.review ? `<p class="tiny">${esc(row.review.name)} · ${esc(dtShort(row.review.at))} · ${esc(row.review.evidence)}</p>` : ''}
    ${canWrite() && AUTH.user?.id===row.work_context.reviewer_user_id && row.created_by_id!==AUTH.user?.id ? `<button class="btn-sm" data-act="work.review" data-id="${row.id}" data-process="${data.process_id}" data-revision="${row.revision}">核验本用途产物</button>` : ''}</article>`).join('');
  return `<section class="card" id="workbench"><div class="between"><h3>${esc(data.kind_labels[kind])} · 原产物作业</h3>
    <div class="gap">${view==='designer' && !urlParams().lifecycle ? `<button class="btn-sm" data-act="work.mode" data-kind="${kind==='DESIGN'?'MODELING':'DESIGN'}">切换${esc(data.kind_labels[kind==='DESIGN'?'MODELING':'DESIGN'])}用途</button>` : ''}
    ${canWrite() && data.can_create ? `${view==='designer' ? '<button class="btn-sm" data-act="work.freeze">固定当前模型（不发布）</button>' : ''}<button class="btn-sm" data-act="work.new">记录本步产物</button>` : ''}</div></div>
    <p class="tiny">${latest ? '原模型 v'+latest.version+' · '+(latest.fixed?'已固定':'可变草稿，引用前须固定') : '尚无模型；先在原设计器保存并固定'} · 未关联项目也可办理。</p>
    <p class="tiny muted">${data.limitations.map(esc).join(' ')}</p>
    <details><summary>原作业记录与核验（${data.records.length}）</summary>${rows || '<div class="empty">尚无本流程作业记录。缺证可记录未知，不自动报通过。</div>'}</details>
  </section>`;
}

on('work.mode',({kind}) => { state.designer.workKind=kind;RENDERERS.designer(); });
on('work.freeze',async () => {
  const context=current;
  if (!context || state.view!=='designer' || state.designer.processId!==context.processId) return;
  try {
    const model=await GET('/processes/'+context.processId+'/design');
    if (state.view!=='designer' || state.designer.processId!==context.processId) return;
    await POST('/processes/'+context.processId+'/design/freeze',{expected_version:model.version,note:'固定'+context.data.kind_labels[context.kind]+'作业输入'});
    toast('原模型已固定；继续编辑将产生新工作版，不改变运行版本');RENDERERS.designer();
  } catch(e) {toast(e.message,true);}
});
on('work.new',() => {
  if (!current) return;
  const c=current;
  const models=c.data.models.filter(row=>row.fixed);
  if (!models.length) return toast('请先在原设计器保存并固定模型版本',true);
  const upstream=c.data.records.filter(row=>row.work_context.kind===({ANALYSIS:'MODELING',DESIGN:'ANALYSIS'}[c.kind]));
  const field=(id,label) => `<div class="field"><label>${label}</label><textarea id="wr${id}" rows="2"></textarea></div>`;
  const gen=openModal(c.data.kind_labels[c.kind]+' · 记录原产物',`
    <div class="note">只追加原方法记录；模型/来源和核验用途固定。未知/演练/估算不可接收为真实现状。</div>
    <div class="field"><label>原模型版本 *</label><select id="wrModel">${models.map(row=>`<option value="${row.id}">v${row.version} · #${row.id}</option>`).join('')}</select></div>
    <div class="field"><label>来源类别</label><select id="wrSource">${Object.entries(c.data.source_labels).map(([key,label])=>`<option value="${key}"${key==='UNKNOWN'?' selected':''}>${esc(label)}</option>`).join('')}</select></div>
    <div class="field"><label>原前序产物</label><select id="wrUpstream"><option value="">未引用（核验时需补足）</option>${upstream.map(row=>`<option value="${row.id}">#${row.id} ${esc(row.title)} · ${esc(row.review_label)}</option>`).join('')}</select></div>
    ${field('Customer','客户结果 *')}${field('Problem','本次问题/范围 *')}${field('Findings','发现/结论/现场确认')}${field('Evidence','原来源/样本/反证依据')}${field('Limitations','限制/未知/未决项')}${field('Next','交给谁的什么/下一步')}
    ${c.kind==='DESIGN' ? field('Alternatives','备选（含不改基准）')+field('Choice','选择/排除依据')+field('Controls','硬约束/风险控制')+field('Validation','验证场景/结果/失败')+field('Rollback','实施接收/回退条件') : ''}
    <div class="field"><label>指定非作者接收者 *</label><select id="wrReviewer"><option value="">请选择</option>${c.data.reviewers.filter(row=>row.id!==AUTH.user?.id).map(row=>`<option value="${row.id}">${esc(row.name)}</option>`).join('')}</select></div>
    <div class="field"><label>约定期限</label><input type="date" id="wrDue"></div>`,
    '<button class="btn btn-g" data-act="work.close">取消</button><button class="btn btn-p" data-act="work.save">保存原产物</button>');
  form={...c,gen};
});
on('work.close',()=>closeModal());
on('work.save',async () => {
  const c=form;
  const pid=state.view==='designer'?state.designer.processId:state.cockpit.processId;
  if (!c || !modalAlive(c.gen) || state.view!==c.view || pid!==c.processId) return toast('流程上下文已变化，请重新打开本步作业',true);
  const val=id=>document.getElementById(id)?.value.trim() || '';
  const payload={project_id:c.projectId,kind:c.kind,model_version_id:Number(val('wrModel')),source_kind:val('wrSource'),reviewer_user_id:Number(val('wrReviewer')),upstream_sheet_id:Number(val('wrUpstream')) || null,due_date:val('wrDue') || null,customer_result:val('wrCustomer'),problem:val('wrProblem'),findings:val('wrFindings'),evidence:val('wrEvidence'),limitations:val('wrLimitations'),next_action:val('wrNext'),alternatives:val('wrAlternatives'),choice_reason:val('wrChoice'),controls:val('wrControls'),validation:val('wrValidation'),rollback:val('wrRollback')};
  try {await POST('/processes/'+c.processId+'/work-records',payload);if(modalAlive(c.gen))closeModal();toast('原产物已保存，尚待指定接收者核验');if(state.view===c.view)RENDERERS[c.view]();} catch(e) {toast(e.message,true);}
});
on('work.review',({id,process,revision}) => {
  const decisions=current?.data.decision_labels || {};
  const gen=openModal('核验原产物用途',`<p class="note">只核对该原版本用途；不自动发布、不等于上线或达标。</p><div class="field"><label>决定</label><select id="wvDecision">${Object.entries(decisions).map(([key,label])=>`<option value="${key}">${esc(label)}</option>`).join('')}</select></div><div class="field"><label>核验依据 *</label><textarea id="wvEvidence"></textarea></div>`,
    `<button class="btn btn-g" data-act="work.close">取消</button><button class="btn btn-p" data-act="work.submitReview" data-id="${id}" data-process="${process}" data-revision="${revision}">保存本人决定</button>`);
  receiptForm={id:Number(id),processId:Number(process),revision:Number(revision),view:state.view,gen};
});
on('work.submitReview',async () => {
  const c=receiptForm;
  const pid=state.view==='designer'?state.designer.processId:state.cockpit.processId;
  if (!c || !modalAlive(c.gen) || state.view!==c.view || pid!==c.processId) return toast('流程上下文已变化，请重新打开原核验',true);
  try {await POST('/processes/'+c.processId+'/work-records/'+c.id+'/review',{decision:document.getElementById('wvDecision').value,evidence:document.getElementById('wvEvidence').value,expected_revision:c.revision});if(modalAlive(c.gen))closeModal();toast('本用途决定已记录');if(state.view===c.view && (c.view==='designer'?state.designer.processId:state.cockpit.processId)===c.processId)RENDERERS[c.view]();} catch(e) {toast(e.message,true);}
});
