/* 视图：workflow */
import { esc, CAT_ICON, methodTag, skeleton, TOOL_LEVEL_TONE } from '../core/format.js';
import { openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go } from '../core/router.js';
import { GET, POST } from '../core/api.js';
import { openToolByCode } from './toolbox.js';

/* ============================================================ 3. 五阶段标准工作流 */

const STAGE_COLORS = [
  'var(--stage-1)', 'var(--stage-2)', 'var(--stage-3)', 'var(--stage-4)', 'var(--stage-5)',
];

const renderWorkflow = () => renderAsync('workflow',
  () => GET('/workflow/stages'),
  (stages) => {
    state.wf = stages;
    const wf = state.workflow || (state.workflow = { tab: 'steps', stage: 1 });
    const total = stages.reduce((a, s) => a + s.steps.length, 0);
    const current = stages.find((s) => s.stage_no === wf.stage) || stages[0];
    const stageIndex = stages.indexOf(current);
    const stageColor = STAGE_COLORS[stageIndex] || STAGE_COLORS[0];

    const pills = stages.map((s, i) => `
      <button class="stage-pill${s.stage_no === current.stage_no ? ' on' : ''}"
              style="--pill:${STAGE_COLORS[i]}" onclick="setWfStage(${s.stage_no})">
        <b>阶段${s.stage_no}</b><span>${esc(s.stage_name)}</span>
        <em>${s.steps.length} 步</em>
      </button>`).join('');

    const steps = current.steps.map((st) => `
      <div class="step wf-step" style="--step-color:${stageColor};border-left-color:${stageColor}"
           onclick="openWfStep('${st.step_no}')">
        <div class="wf-step-hd">
          <span class="wf-step-no" style="background:linear-gradient(135deg,${stageColor},var(--brand2))">
            ${esc(st.step_no)}</span>
          <b>${esc(st.name)}</b>
        </div>
        <span>${esc(st.deliverables)}</span>
        ${st.tools ? `<div class="wf-step-tools">推荐工具：${esc(st.tools)}</div>` : ''}
      </div>`).join('');

    const stepsPane = `
      <div class="stage-pills">${pills}</div>
      <div class="wf-hero" style="background:linear-gradient(120deg,${stageColor},var(--brand2))">
        <div class="wf-hero-ring">${current.stage_no}</div>
        <div class="wf-hero-tx">
          <h3>阶段${current.stage_no} · ${esc(current.stage_name)}</h3>
          <p>${esc(current.stage_goal || '')}</p>
        </div>
        <div class="wf-hero-kpis">
          <div><b>${current.steps.length}</b><span>本阶段步骤</span></div>
          <div><b>${total}</b><span>全流程步骤</span></div>
          <div><b>${stages.length}</b><span>阶段数</span></div>
        </div>
      </div>
      <section class="wf-section">
        <div class="ch">
          <span class="dot"></span><h3>阶段${current.stage_no} 步骤清单</h3>
          <div class="sp"></div>
          <span class="tiny">${current.steps.length} 个步骤 · 点击查看方法、工具与交付物</span>
          <a class="link-btn" style="margin-left:10px" onclick="setWfTab('method')">方法论匹配 →</a>
        </div>
        <div class="wf-grid">${steps}</div>
      </section>`;

    const methodPane = `
      <div class="card">
        <h3>决策门：方法论选择矩阵</h3>
        <div class="desc">根据流程现状与目标自动推荐适配方法 —— 下面的试算会调用后端真正的匹配引擎</div>
        <table class="tbl mb">
          <thead><tr><th>流程现状</th><th>改善目标</th><th>推荐方法</th><th>典型周期</th><th>风险等级</th></tr></thead>
          <tbody>
            <tr><td>流程严重过时、断裂、与战略脱节</td><td>阶跃式突破（≥50%）</td>
              <td>${methodTag('BPR', 'BPR 重组')}</td><td>6–18 个月</td><td><span class="tag t-red">高</span></td></tr>
            <tr><td>流程基本合理但局部堵点</td><td>渐进改善（10–30%）</td>
              <td>${methodTag('BPI', 'BPI 优化')}</td><td>1–3 个月</td><td><span class="tag t-yel">中低</span></td></tr>
            <tr><td>现场/操作层浪费明显</td><td>持续流动、消除浪费</td>
              <td>${methodTag('LEAN', '精益改善')}</td><td>持续改善</td><td><span class="tag t-grn">低</span></td></tr>
            <tr><td>混合状态（多数实际情况）</td><td>架构 + 执行 + 操作分层改善</td>
              <td>${methodTag('HYBRID', '组合拳')}</td><td>持续</td><td><span class="tag t-yel">中</span></td></tr>
          </tbody>
        </table>

        <h3>实时试算</h3>
        <div class="row3">
          <div class="field"><label>流程现状</label>
            <select id="rcState">
              <option value="SEVERE_OUTDATED">严重过时、断裂、与战略脱节</option>
              <option value="SOUND_BUT_INEFFICIENT">基本合理但效率不足、局部堵点</option>
              <option value="SHOPFLOOR_WASTE">现场/操作层浪费明显、波动大</option>
              <option value="MIXED">混合状态</option>
            </select></div>
          <div class="field"><label>目标改善幅度（%）</label>
            <input id="rcPct" type="number" value="30" min="0" max="100"></div>
          <div class="field"><label>范围</label>
            <select id="rcScope">
              <option value="END_TO_END">端到端跨职能</option>
              <option value="LOCAL" selected>单一部门内部</option>
              <option value="SHOPFLOOR">现场/操作层</option>
            </select></div>
        </div>
        <div class="row3">
          <div class="field"><label>是否涉及组织/权责调整</label>
            <select id="rcOrg"><option value="false">否</option><option value="true">是</option></select></div>
          <div class="field"><label>是否有流程数据/日志</label>
            <select id="rcData"><option value="true">是</option><option value="false">否</option></select></div>
          <div class="field"><label>计划周期（月）</label>
            <input id="rcDur" type="number" value="6" min="1" max="36"></div>
        </div>
        <button class="btn btn-p" id="rcBtn" onclick="runRecommend('rcResult')">运行匹配引擎</button>
        <div id="rcResult" class="mt"></div>
      </div>`;

    viewEl().innerHTML = `
      <div class="card page-head">
        <div class="between">
          <div><h2>五阶段标准工作流<span class="module-badge">方法手册 · 教学引导</span></h2>
            <div class="desc">全公司共用的方法手册 · ${total} 个标准步骤；项目实际进度请在「流程项目组合」里推进</div></div>
          <div class="seg">
            <button class="${wf.tab === 'steps' ? 'on' : ''}" onclick="setWfTab('steps')">五阶段步骤</button>
            <button class="${wf.tab === 'method' ? 'on' : ''}" onclick="setWfTab('method')">方法论匹配</button>
          </div>
        </div>
      </div>
      <div class="note mt">这是教学与方法手册，不跟踪具体项目。项目立项后，24 步实例在
        <a class="link" onclick="go('projects')">流程项目组合</a> 的项目详情里推进。</div>
      ${wf.tab === 'method' ? methodPane : stepsPane}`;
  });

function setWfTab(tab) {
  state.workflow = state.workflow || {};
  state.workflow.tab = tab;
  RENDERERS.workflow();
}

function setWfStage(stage) {
  state.workflow = state.workflow || {};
  state.workflow.stage = stage;
  state.workflow.tab = 'steps';
  RENDERERS.workflow();
}

function openWfStep(stepNo) {
  let found = null;
  (state.wf || []).forEach((s) => s.steps.forEach((st) => { if (st.step_no === stepNo) found = st; }));
  if (!found) return;
  openModal(found.step_no + ' ' + found.name + ' · 方法说明', `
    <div class="field"><label>标准动作</label><textarea readonly>${esc(found.action)}</textarea></div>
    <div class="row2">
      <div class="field"><label>方法手册里的工具</label><input value="${esc(found.tools)}" readonly></div>
      <div class="field"><label>关键交付物</label><input value="${esc(found.deliverables)}" readonly></div>
    </div>
    <div class="field"><label>关键要点 / 踩坑提示</label><textarea readonly>${esc(found.key_points)}</textarea></div>
    <div class="field"><label>所属阶段</label>
      <input value="阶段${found.stage_no}" readonly></div>
    <div id="wfRec">${skeleton(3)}</div>`,
    `<button class="btn btn-g" onclick="closeModal()">关闭</button>
     <button class="btn btn-g" onclick="closeModal();openToolboxForStep()">去工具箱看推荐工具</button>
     <button class="btn btn-p" onclick="closeModal();go('deliverables')">去模板库</button>`, true);
  paintStepRecommendations(stepNo);
}

/** 从步骤弹窗进入工具箱：只显示本步骤契约里的工具，并标注使用要求 */
function openToolboxForStep() {
  const rec = state.wfStepRec;
  if (!rec || !rec.tools.length) {
    state.toolboxFilter = null;
    go('toolbox');
    return;
  }
  state.toolboxFilter = {
    label: rec.step_no + ' ' + rec.step_name,
    codes: rec.tools.map((t) => t.code),
    meta: Object.fromEntries(rec.tools.map((t) => [t.code, t])),
  };
  go('toolbox');
}

async function paintStepRecommendations(stepNo) {
  const box = document.getElementById('wfRec');
  if (!box) return;
  try {
    const rec = await GET('/workflow/steps/' + encodeURIComponent(stepNo) + '/recommendations');
    if (!box.isConnected) return;
    state.wfStepRec = rec;
    box.innerHTML = renderStepRecommendations(rec);
    const foot = document.getElementById('mFoot');
    if (foot && rec.tools.length) {
      foot.innerHTML = `<button class="btn btn-g" onclick="closeModal()">关闭</button>
        <button class="btn btn-g" onclick="closeModal();openToolboxForStep()">
          去工具箱（只看本步骤 ${rec.tools.length} 个推荐工具）</button>
        <button class="btn btn-p" onclick="closeModal();go('deliverables')">去模板库</button>`;
    }
  } catch (e) {
    if (box.isConnected) {
      box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
    }
  }
}

function renderTemplateChips(templates) {
  if (!templates.length) return '<span class="tiny">暂无预制模板</span>';
  return templates.map((t) => `
    <div class="between" style="gap:8px;margin-bottom:6px">
      <span>${esc(t.name)} <span class="tag t-gry">${esc(t.format_label)}</span>
        ${t.effective_version
          ? '<span class="tag t-grn">现行 ' + esc(t.effective_version.version_label) + '</span>'
          : '<span class="tag t-gry">无生效版本</span>'}</span>
      <span>${t.effective_version
        ? `<button class="btn-sm" onclick="closeModal();openTemplateCopy(${t.id})">复制到项目</button>`
        : ''}</span>
    </div>`).join('');
}

function renderStepRecommendations(rec) {
  const rows = rec.tools.map((t) => `
    <tr>
      <td><a class="link" onclick="closeModal();openToolByCode('${esc(t.code)}')"><b>${esc(t.name)}</b></a>
        <div class="tiny">${esc(t.code)} · ${esc(t.category_label || '')}</div></td>
      <td><span class="tag ${TOOL_LEVEL_TONE[t.level] || 't-gry'}">${esc(t.level_label)}</span></td>
      <td>${renderTemplateChips(t.templates)}</td>
    </tr>`).join('');

  const extras = rec.deliverable_templates.length
    ? `<h3 class="mt">本步骤交付物可用模板</h3>${renderTemplateChips(rec.deliverable_templates)}`
    : '';

  return `
    <h3 class="mt">推荐工具与预制模板</h3>
    <div class="desc">使用要求来自步骤契约；模板由流程管理科维护，复制到项目后会固定来源版本</div>
    ${rec.tools.length
      ? `<table class="tbl">
          <thead><tr><th>工具</th><th>使用要求</th><th>预制模板</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`
      : '<div class="note">该步骤还没有配置工具。流程管理科可以在步骤契约里补充工具与使用要求。</div>'}
    ${extras}`;
}

/** 方法论匹配试算：复用后端引擎，前端只负责收集参数与呈现 */
async function runRecommend(targetId) {
  const box = document.getElementById(targetId);
  box.innerHTML = skeleton(3);
  try {
    const r = await POST('/projects/recommend-methodology', {
      process_state: document.getElementById('rcState').value,
      target_improvement_pct: Number(document.getElementById('rcPct').value || 0),
      scope: document.getElementById('rcScope').value,
      involves_org_change: document.getElementById('rcOrg').value === 'true',
      data_available: document.getElementById('rcData').value === 'true',
      duration_target_months: Number(document.getElementById('rcDur').value || 6),
    });
    box.innerHTML = renderRecommendation(r);
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

function renderRecommendation(r) {
  const conf = Math.round(r.confidence * 100);
  return `
    <div class="note mb">
      <b style="font-size:14px">${esc(r.headline)}</b>
      <div style="margin-top:6px">
        <div class="pipe" style="max-width:280px"><i class="fill-${
          conf >= 70 ? 'ok' : conf >= 50 ? 'warn' : 'bad'}" style="width:${conf}%"></i></div>
        <span class="tiny">置信度 ${conf}%</span>
      </div>
    </div>

    <h3>判断依据</h3>
    <ol style="padding-left:20px;font-size:13px;line-height:1.9;color:var(--text)">
      ${r.rationale.map((x) => '<li>' + esc(x) + '</li>').join('')}
    </ol>

    <h3 class="mt">分层推进建议</h3>
    <table class="tbl">
      <thead><tr><th style="width:90px">层次</th><th>动作</th></tr></thead>
      <tbody>${r.phase_plan.map((p) => '<tr><td><b>' + esc(p.layer) + '</b></td><td>' +
        esc(p.action) + '</td></tr>').join('')}</tbody>
    </table>

    <h3 class="mt">推荐工具链（${r.recommended_tools.length} 个）</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      ${r.recommended_tools.map((t) => '<span class="tag ' +
        ({ DIAGNOSE: 't-blu', DESIGN: 't-red', DEPLOY: 't-yel', MONITOR: 't-grn' }[t.category] || 't-blu') +
        '" style="cursor:pointer" onclick="openToolByCode(\'' + t.code + '\')">' +
        (CAT_ICON[t.category] || '') + ' ' + esc(t.name) + '</span>').join('')}
    </div>

    <h3 class="mt">风险提示</h3>
    <div class="${r.risks.length && r.risks[0].indexOf('未识别') < 0 ? 'warnbox' : 'note'}">
      ${r.risks.map((x) => '· ' + esc(x)).join('<br>')}
    </div>`;
}


export {
  renderWorkflow, openWfStep, openToolboxForStep, renderStepRecommendations,
  renderRecommendation, runRecommend, setWfStage, setWfTab,
};
