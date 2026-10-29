/* 模块：knowledge —— 知识资源（案例 / 模板）
 *
 * 知识库页面已并入「方法论工具箱」：这里保留资源卡片、详情弹窗、求真审核与
 * 使用证据等 action，供工具箱和工作流复用。旧的 #knowledge 链接会重定向。
 */
import { esc, fmtDate, num, skeleton } from '../core/format.js';
import {
  toast, openModal, closeModal, modalAlive, on, confirmDialog,
} from '../core/ui.js';
import { state } from '../core/state.js';
import { RENDERERS, go, urlParams } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { GET, PATCH, POST } from '../core/api.js';
import { STATUS_TONE, TYPE_TONE, syncToolboxUrl } from './shared/knowledge_resources.js';

/* ============================================================ 8. 流程知识库 */

export const TYPE_ORDER = ['CASE', 'TEMPLATE'];

on('knowledge.open', ({ id }) => openKnowledge(Number(id)));
on('knowledge.setType', ({ value }) => {
  state.knowledge.type = value;
  state.knowledge.page = 1;
  state.toolbox.section = 'resources';
  state.toolbox.navSection = 'type';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('knowledge.setSort', (_data, el) => {
  state.knowledge.sort = el.value;
  state.knowledge.page = 1;
  state.toolbox.section = 'resources';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('knowledge.setStatus', (_data, el) => {
  state.knowledge.status = el.value;
  state.knowledge.page = 1;
  state.toolbox.section = 'resources';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('knowledge.page', ({ page }) => setKPage(Number(page)));
on('knowledge.clearResourceTool', () => {
  state.knowledge.tool = '';
  state.knowledge.page = 1;
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('knowledge.new', () => newKnowledgeModal());
on('knowledge.goDocuments', () => go('deliverables', { params: { tab: 'document' }, push: true }));
on('knowledge.close', () => closeModal());
on('knowledge.openTool', ({ code }) => {
  closeModal();
  go('toolbox', { params: { open: code }, push: true });
});
on('knowledge.newStepChange', (_data, el) => {
  const stageNo = el.selectedOptions[0]?.dataset.stage;
  const stageSelect = document.getElementById('nkStage');
  if (stageNo && stageSelect) stageSelect.value = stageNo;
});
on('knowledge.submit', () => submitKnowledge());
on('knowledge.saveUsage', ({ id }) => saveUsage(Number(id)));
on('knowledge.applyStep', ({ id }) => openApplyStep(Number(id)));
on('knowledge.applyStepSubmit', ({ id }) => submitApplyStep(Number(id)));
on('knowledge.applyToolStep', ({ code }) => openApplyToolStep(code));
on('knowledge.applyToolStepSubmit', ({ code }) => submitApplyToolStep(code));
on('knowledge.submitReview', ({ id }) => submitForReview(Number(id)));
on('knowledge.review', ({ id, decision }) => reviewKnowledge(Number(id), decision));
on('knowledge.archive', ({ id }) => archiveKnowledge(Number(id)));
on('knowledge.promote', ({ id }) => promoteKnowledge(Number(id)));
on('knowledge.manageScenarios', () => openScenarioManager());
on('knowledge.saveScenario', ({ id }) => saveScenario(Number(id)));
on('knowledge.createScenario', () => createScenario());
on('knowledge.showRecommendLogs', () => openRecommendLogs());
on('knowledge.migrateStandard', ({ id }) => openStandardMigration(Number(id)));
on('knowledge.submitMigration', ({ id }) => submitStandardMigration(Number(id)));

const renderKnowledge = () => {
  // 兼容旧链接：知识库已并入方法论工具箱，参数按 toolbox 的命名映射。
  const params = urlParams();
  const mapped = {};
  const keyword = params.q || params.keyword;
  if (keyword) mapped.q = keyword;
  ['scenario', 'stage', 'step'].forEach((key) => {
    if (params[key]) mapped[key] = params[key];
  });
  if (params.type) mapped.rtype = params.type;
  if (params.sort) mapped.rsort = params.sort;
  if (params.status) mapped.rstatus = params.status;
  if (params.page) mapped.rpage = params.page;
  if (params.tool) mapped.rtool = params.tool;
  mapped.section = params.section
    || (keyword || params.scenario || params.step ? 'reco' : 'resources');
  go('toolbox', { params: mapped, push: false, skipOrigin: true });
};

function setKPage(page) {
  state.knowledge.page = Math.max(1, page);
  state.toolbox.section = 'resources';
  syncToolboxUrl();
  RENDERERS.toolbox();
}

/* -------------------------------------------------- 详情与使用证据 */

async function openKnowledge(id) {
  const gen = openModal('加载中…', skeleton(4), '', true);
  let item = null;
  let usage = [];
  let projects = { items: [] };
  let reviews = [];
  try {
    [item, usage, projects, reviews] = await Promise.all([
      GET('/knowledge/' + id),
      GET('/knowledge/' + id + '/usage').catch(() => []),
      canWrite() ? GET('/projects?page_size=200').catch(() => ({ items: [] })) : { items: [] },
      GET('/knowledge/' + id + '/reviews').catch(() => []),
    ]);
    if (!modalAlive(gen)) return;
    const scenarioNames = (item.scenario_names || []).join('、') || '未标注';
    const projectOptions = (projects.items || []).map((p) =>
      `<option value="${p.id}">${esc(p.code)} ${esc(p.name)}</option>`).join('');
    const usageRows = usage.length
      ? usage.map((row) => `
        <tr>
          <td class="tiny">${fmtDate(row.used_at)}</td>
          <td><span class="tag ${row.outcome === 'EFFECTIVE' ? 't-grn'
            : row.outcome === 'PARTIAL' ? 't-yel' : 't-red'}">${esc(row.outcome_label || row.outcome)}</span></td>
          <td>${esc(row.used_by || '—')}</td>
          <td>${esc(row.step_no || '—')}</td>
          <td class="tiny">${esc(row.note || '—')}</td>
        </tr>`).join('')
      : '<tr><td colspan="5" class="muted">还没有使用记录。用过后回填，知识才会积累证据。</td></tr>';
    const reviewRows = reviews.length
      ? reviews.map((row) => `
        <tr>
          <td class="tiny">${fmtDate(row.created_at)}</td>
          <td><span class="tag ${row.decision === 'APPROVE' ? 't-grn' : 't-red'}">${
            esc(row.decision_label || row.decision)}</span></td>
          <td>${esc(row.reviewer || '—')}</td>
          <td class="tiny">${esc(row.from_status_label || '—')} → ${esc(row.to_status_label || '—')}</td>
          <td class="tiny">${esc(row.note || '—')}</td>
        </tr>`).join('')
      : '<tr><td colspan="5" class="muted">还没有审核记录。</td></tr>';

    const canReview = canManage() && item.status === 'IN_REVIEW';
    const canSubmit = canWrite()
      && item.status === 'DRAFT'
      && (canManage() || (AUTH.user && item.owner_user_id === AUTH.user.id));
    const canArchive = canManage() && ['PUBLISHED', 'VERIFIED'].includes(item.status);
    const promoteRate = item.used_count ? item.effective_count / item.used_count : 0;
    const canPromote = canManage() && item.status === 'VERIFIED' && !item.is_best_practice;
    const promoteEligible = canPromote && item.used_count >= 5 && promoteRate >= 0.7;
    const rate = item.effectiveness_rate === null || item.effectiveness_rate === undefined
      ? '暂无使用记录'
      : `有效率 ${num(item.effectiveness_rate, 1)}%（${item.effective_count}/${item.used_count}）`;

    openModal(item.title, `
      <div class="gap mb" style="flex-wrap:wrap">
        <span class="tag ${TYPE_TONE[item.type] || 't-blu'}">${esc(item.type_label || item.type)}</span>
        <span class="tag ${STATUS_TONE[item.status] || 't-gry'}">${esc(item.status_label || item.status)}</span>
        ${item.is_best_practice ? '<span class="tag t-grn">最佳实践</span>' : ''}
        ${item.review_overdue ? '<span class="tag t-yel">待复核</span>' : ''}
        <span class="tiny">v${item.version} · 维护人 ${esc(item.owner || '—')}
          ${item.last_verified_at ? ' · 验证 ' + fmtDate(item.last_verified_at) : ''}</span>
      </div>
      <div class="note mb">${esc(item.summary)}</div>
      <div class="kb-detail">
        <div><span>适用场景</span><b>${esc(scenarioNames)}</b></div>
        <div><span>适用条件</span><b>${esc(item.applicable_when || '—')}</b></div>
        <div><span>不适用 / 反证</span><b>${esc(item.not_applicable_when || '—')}</b></div>
        <div><span>主张</span><b>${esc(item.claim || '—')}</b></div>
        <div><span>输入条件</span><b>${esc(item.input_conditions || '—')}</b></div>
        <div><span>步骤要点</span><b>${esc(item.steps_summary || '—')}</b></div>
        <div><span>输出物</span><b>${esc(item.outputs || '—')}</b></div>
        <div><span>关联阶段</span><b>${(item.stage_nos || []).length
          ? item.stage_nos.map((no) => '阶段' + no).join('、') : '—'}</b></div>
        <div><span>关联步骤</span><b>${(item.step_nos || []).length
          ? item.step_nos.map(esc).join('、') : '—'}</b></div>
        <div><span>关联工具</span><b>${esc(item.tool_code || '—')}</b></div>
        <div><span>使用证据</span><b>${esc(rate)}</b></div>
      </div>
      ${item.evidence_summary
        ? `<div class="note mb">提交证据：${esc(item.evidence_summary)}</div>` : ''}
      <div class="kb-content">${esc(item.content)}</div>

      <h3 class="mt">使用证据（${usage.length}）</h3>
      <table class="tbl">
        <thead><tr><th>时间</th><th>效果</th><th>使用人</th><th>步骤</th><th>说明</th></tr></thead>
        <tbody>${usageRows}</tbody>
      </table>

      <h3 class="mt">求真审核历史（${reviews.length}）</h3>
      <table class="tbl">
        <thead><tr><th>时间</th><th>裁决</th><th>审核人</th><th>状态变化</th><th>说明</th></tr></thead>
        <tbody>${reviewRows}</tbody>
      </table>

      ${canWrite() ? `
        <h3 class="mt">记录一次使用</h3>
        <div class="row3">
          <div class="field"><label>效果</label>
            <select id="kuOutcome">
              <option value="EFFECTIVE">有效</option>
              <option value="PARTIAL">部分有效</option>
              <option value="INEFFECTIVE">无效</option>
            </select></div>
          <div class="field"><label>关联项目</label>
            <select id="kuProject"><option value="">不关联</option>${projectOptions}</select></div>
          <div class="field"><label>证据链接</label>
            <input id="kuUrl" placeholder="可选，如报告链接"></div>
        </div>
        <div class="field"><label>效果说明</label>
          <input id="kuNote" placeholder="如：审批时长下降 40%，连续 4 周稳定"></div>
        <div class="field"><label>关联工作流步骤（可选）</label>
          <input id="kuStep" value="${esc(state.toolbox.step || state.knowledge.step
            || (item.step_nos && item.step_nos[0]) || '')}"
            placeholder="如 2.1；从工作流步骤进入时会自动带上"></div>
        <div class="gap">
          <button class="btn btn-g" data-act="knowledge.saveUsage" data-id="${item.id}">保存使用记录</button>
        </div>` : ''}`,
      `<button class="btn btn-g" data-act="knowledge.close">关闭</button>
       ${item.tool_code ? `<button class="btn btn-g" data-act="knowledge.openTool"
         data-code="${esc(item.tool_code)}">查看关联工具</button>` : ''}
       ${canSubmit ? `<button class="btn btn-g" data-act="knowledge.submitReview"
         data-id="${item.id}">提交审核</button>` : ''}
       ${canReview ? `<button class="btn btn-g" data-act="knowledge.review"
         data-id="${item.id}" data-decision="REJECT">驳回</button>
         <button class="btn btn-p" data-act="knowledge.review"
         data-id="${item.id}" data-decision="APPROVE">通过审核</button>` : ''}
       ${canArchive ? `<button class="btn btn-g" data-act="knowledge.archive"
         data-id="${item.id}">归档</button>` : ''}
       ${canPromote ? `<button class="btn btn-g" data-act="knowledge.promote"
         data-id="${item.id}" ${promoteEligible ? '' : 'disabled'}
         title="${promoteEligible ? '' : `需要 ≥5 次使用且有效率 ≥70%（当前 ${item.used_count} 次 / ${num(promoteRate * 100, 0)}%）`}">
         晋升最佳实践</button>` : ''}`, true);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

async function saveUsage(id) {
  const val = (key) => {
    const el = document.getElementById(key);
    return el ? el.value.trim() : '';
  };
  try {
    await POST('/knowledge/' + id + '/usage', {
      project_id: val('kuProject') ? Number(val('kuProject')) : null,
      step_no: val('kuStep') || null,
      outcome: val('kuOutcome') || 'EFFECTIVE',
      note: val('kuNote') || null,
      evidence_url: val('kuUrl') || null,
    });
    toast('使用证据已记录');
    await openKnowledge(id);
    if (state.view === 'toolbox') RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

function openApplyStep(id) {
  const step = state.toolbox.step || state.knowledge.step;
  if (!step) return toast('请先从工作流步骤进入知识库', true);
  openModal('用到当前步骤', `
    <div class="note mb">记录一次使用证据，关联工作流步骤 <b>${esc(step)}</b>。
      证据会计入该知识的使用次数与有效率。</div>
    <div class="field"><label>本次效果</label>
      <select id="kaOutcome">
        <option value="EFFECTIVE">有效</option>
        <option value="PARTIAL">部分有效</option>
        <option value="INEFFECTIVE">无效</option>
      </select></div>
    <div class="field"><label>说明</label>
      <input id="kaNote" value="在步骤 ${esc(step)} 应用"></div>`,
  `<button class="btn btn-g" data-act="knowledge.close">取消</button>
   <button class="btn btn-p" data-act="knowledge.applyStepSubmit" data-id="${id}">记录</button>`);
}

async function submitApplyStep(id) {
  const step = state.toolbox.step || state.knowledge.step;
  if (!step) return toast('步骤上下文已丢失，请重新从工作流进入', true);
  const outcome = document.getElementById('kaOutcome')?.value || 'EFFECTIVE';
  const note = document.getElementById('kaNote')?.value.trim() || null;
  try {
    await POST('/knowledge/' + id + '/usage', {
      step_no: step,
      outcome,
      note,
    });
    toast('已记录到步骤 ' + step);
    closeModal();
    if (state.view === 'toolbox') RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

function openApplyToolStep(code) {
  const step = state.toolbox.step || state.knowledge.step;
  if (!step) return toast('请先从工作流步骤进入知识库', true);
  openModal('用到当前步骤 · 工具', `
    <div class="note mb">记录一次工具使用证据，关联工作流步骤 <b>${esc(step)}</b>。</div>
    <div class="field"><label>本次效果</label>
      <select id="ktaOutcome">
        <option value="EFFECTIVE">有效</option>
        <option value="PARTIAL">部分有效</option>
        <option value="INEFFECTIVE">无效</option>
      </select></div>
    <div class="field"><label>说明</label>
      <input id="ktaNote" value="在步骤 ${esc(step)} 使用工具 ${esc(code)}"></div>`,
  `<button class="btn btn-g" data-act="knowledge.close">取消</button>
   <button class="btn btn-p" data-act="knowledge.applyToolStepSubmit"
     data-code="${esc(code)}">记录</button>`);
}

async function submitApplyToolStep(code) {
  const step = state.toolbox.step || state.knowledge.step;
  if (!step) return toast('步骤上下文已丢失，请重新从工作流进入', true);
  const outcome = document.getElementById('ktaOutcome')?.value || 'EFFECTIVE';
  const note = document.getElementById('ktaNote')?.value.trim() || null;
  try {
    await POST('/tools/' + encodeURIComponent(code) + '/usage', {
      step_no: step,
      outcome,
      note,
    });
    toast('已记录到步骤 ' + step);
    closeModal();
    if (state.view === 'toolbox') RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function submitForReview(id) {
  try {
    await POST('/knowledge/' + id + '/submit', {});
    toast('已提交审核');
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function reviewKnowledge(id, decision) {
  try {
    await POST('/knowledge/' + id + '/review', { decision });
    toast(decision === 'APPROVE' ? '已通过审核' : '已驳回，退回草稿');
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function archiveKnowledge(id) {
  const ok = await confirmDialog(
    '归档后该条目不再进入列表与推荐，使用证据和版本记录仍然保留。确定归档？',
    { title: '归档知识条目', okText: '归档', danger: true },
  );
  if (!ok) return;
  try {
    await POST('/knowledge/' + id + '/archive', {});
    toast('已归档');
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function promoteKnowledge(id) {
  const ok = await confirmDialog(
    '晋升后该条目会带「最佳实践」标记，并在推荐排序中获得加权。确定晋升？',
    { title: '晋升最佳实践', okText: '晋升' },
  );
  if (!ok) return;
  try {
    await POST('/knowledge/' + id + '/promote', {});
    toast('已晋升为最佳实践');
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 场景 / 日志 / 制度迁移 */

async function openScenarioManager() {
  let rows = [];
  try {
    rows = await GET('/knowledge/scenarios?include_inactive=1');
  } catch (e) {
    return toast(e.message, true);
  }
  const tableRows = rows.map((row) => `
    <tr>
      <td><b>${esc(row.code)}</b></td>
      <td><input id="scName-${row.id}" value="${esc(row.name)}"></td>
      <td><input id="scDesc-${row.id}" value="${esc(row.description || '')}"></td>
      <td><input id="scSort-${row.id}" type="number" style="width:70px" value="${row.sort_order}"></td>
      <td><input id="scActive-${row.id}" type="checkbox" ${row.is_active ? 'checked' : ''}></td>
      <td><button class="btn-sm" data-act="knowledge.saveScenario" data-id="${row.id}">保存</button></td>
    </tr>`).join('');
  openModal('场景字典管理', `
    <div class="note mb">场景是用户带来的痛点，知识标签是文件属性；停用场景不会删除已有知识关联。</div>
    <table class="tbl">
      <thead><tr><th>编码</th><th>名称</th><th>说明</th><th>排序</th><th>启用</th><th>操作</th></tr></thead>
      <tbody>${tableRows || '<tr><td colspan="6" class="muted">还没有场景</td></tr>'}</tbody>
    </table>
    <h3 class="mt">新增场景</h3>
    <div class="row3">
      <div class="field"><label>编码 *</label><input id="scNewCode" placeholder="如 DELAY"></div>
      <div class="field"><label>名称 *</label><input id="scNewName" placeholder="如 交期延误"></div>
      <div class="field"><label>排序</label><input id="scNewSort" type="number" value="99"></div>
    </div>
    <div class="field"><label>说明</label><input id="scNewDesc" placeholder="一句话解释这个痛点"></div>`,
  `<button class="btn btn-g" data-act="knowledge.close">关闭</button>
   <button class="btn btn-p" data-act="knowledge.createScenario">新增场景</button>`, true);
}

async function saveScenario(id) {
  const val = (key) => {
    const el = document.getElementById(key);
    return el ? el.value.trim() : '';
  };
  try {
    await PATCH('/knowledge/scenarios/' + id, {
      name: val('scName-' + id),
      description: val('scDesc-' + id) || null,
      sort_order: Number(val('scSort-' + id) || 0),
      is_active: !!document.getElementById('scActive-' + id)?.checked,
    });
    toast('场景已保存');
    await openScenarioManager();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function createScenario() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  try {
    await POST('/knowledge/scenarios', {
      code: val('scNewCode').toUpperCase(),
      name: val('scNewName'),
      description: val('scNewDesc') || null,
      sort_order: Number(val('scNewSort') || 99),
    });
    toast('场景已新增');
    await openScenarioManager();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

async function openRecommendLogs() {
  try {
    const rows = await GET('/knowledge/recommend-logs?limit=50');
    openModal('推荐解释日志', `
      <div class="note mb">每次按问题/场景推荐都会记录上下文与返回条目，便于复盘“为什么推了这条”。</div>
      <table class="tbl">
        <thead><tr><th>时间</th><th>用户</th><th>问题</th><th>场景</th><th>步骤</th><th>返回条目</th></tr></thead>
        <tbody>${rows.length ? rows.map((row) => `
          <tr><td class="tiny">${fmtDate(row.created_at)}</td>
            <td>${esc(row.user || '—')}</td>
            <td>${esc(row.problem || '—')}</td>
            <td class="tiny">${esc((row.scenario_codes || []).join('、') || '—')}</td>
            <td class="tiny">${esc(row.step_no || row.stage_no || '—')}</td>
            <td class="tiny">${esc((row.result_ids || []).join(', ') || '—')}</td></tr>`).join('')
          : '<tr><td colspan="6" class="muted">还没有推荐日志</td></tr>'}</tbody>
      </table>`,
    '<button class="btn btn-g" data-act="knowledge.close">关闭</button>', true);
  } catch (e) {
    toast(e.message, true);
  }
}

async function openStandardMigration(id) {
  try {
    const [item, processes, meta] = await Promise.all([
      GET('/knowledge/' + id),
      GET('/process-map/flat'),
      GET('/process-documents/meta'),
    ]);
    const candidates = (processes || []).filter((row) => row.level >= 2);
    const categories = meta.category_labels || {};
    openModal('迁移为流程标准文件', `
      <div class="note mb">会把知识正文写入标准文件说明，并生成 v1.0 草稿；生效仍需走制度审批。</div>
      <div class="field"><label>标题</label>
        <input id="smTitle" value="${esc(item.title)}"></div>
      <div class="row2">
        <div class="field"><label>所属流程 *</label><select id="smProcess">
          ${candidates.map((row) => `<option value="${row.id}">L${row.level} ${esc(row.code)} ${
            esc(row.name)}</option>`).join('')}
        </select></div>
        <div class="field"><label>类型 *</label><select id="smCategory">
          ${Object.entries(categories).map(([code, label]) =>
            `<option value="${code}"${code === 'POLICY' ? ' selected' : ''}>${esc(label)}</option>`).join('')}
        </select></div>
      </div>
      <div class="field"><label>说明</label>
        <textarea id="smDesc" rows="3">${esc(item.content || '')}</textarea></div>`,
    `<button class="btn btn-g" data-act="knowledge.close">取消</button>
     <button class="btn btn-p" data-act="knowledge.submitMigration" data-id="${id}">生成制度草稿</button>`);
  } catch (e) {
    toast(e.message, true);
  }
}

async function submitStandardMigration(id) {
  const val = (key) => {
    const el = document.getElementById(key);
    return el ? el.value.trim() : '';
  };
  try {
    const result = await POST('/knowledge/' + id + '/migrate-to-document', {
      process_id: Number(val('smProcess')),
      title: val('smTitle') || null,
      category: val('smCategory') || 'POLICY',
      description: val('smDesc') || null,
    });
    toast('已生成制度草稿 ' + result.document_code);
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------- 新建与求真审核 */

async function newKnowledgeModal() {
  let meta = state.knowledgeMeta;
  let stages = state.wf || [];
  if (!meta || !stages.length) {
    try {
      [meta, stages] = await Promise.all([GET('/knowledge/meta'), GET('/workflow/stages')]);
      state.knowledgeMeta = meta;
      state.wf = stages;
    } catch (e) {
      return toast(e.message, true);
    }
  }
  const labels = meta.type_labels || {};
  const scenarios = meta.scenarios || [];
  const scenarioChecks = scenarios.map((scenario) => `
    <label class="kb-check"><input type="checkbox" name="kbScenario"
      value="${esc(scenario.code)}"> ${esc(scenario.name)}</label>`).join('');
  const stageOptions = stages.map((stage) =>
    `<option value="${stage.stage_no}">阶段${stage.stage_no} ${esc(stage.stage_name)}</option>`).join('');
  const stepOptions = stages.flatMap((stage) =>
    (stage.steps || []).map((step) =>
      `<option value="${esc(step.step_no)}" data-stage="${stage.stage_no}">${
        esc(step.step_no)} ${esc(step.name)}（阶段${stage.stage_no}）</option>`)).join('');
  openModal('新建知识条目 · 求真审核', `
    <div class="note mb">提交后进入审核，通过后才对外可见。至少要有主张、适用条件、反证、证据和维护人。</div>
    <div class="row2">
      <div class="field"><label>名称 *</label>
        <input id="nkTitle" placeholder="如：供应商对账流程复盘"></div>
      <div class="field"><label>类型 *</label>
        <select id="nkType">
          ${TYPE_ORDER.filter((code) => labels[code]).map((code) =>
            `<option value="${code}">${esc(labels[code])}</option>`).join('')}
        </select></div>
    </div>
    <div class="row3">
      <div class="field"><label>方法论</label>
        <select id="nkMethod">
          <option value="">不限定</option><option value="BPR">BPR</option>
          <option value="BPI">BPI</option><option value="LEAN">精益</option>
          <option value="HYBRID">混合</option>
        </select></div>
      <div class="field"><label>关联工具编码</label>
        <input id="nkTool" placeholder="如 RACI（可空）"></div>
      <div class="field"><label>关联工作流阶段</label>
        <select id="nkStage"><option value="">不关联</option>${stageOptions}</select></div>
    </div>
    <div class="field"><label>关联具体步骤（可选）</label>
      <select id="nkStep" data-act="knowledge.newStepChange">
        <option value="">不关联具体步骤</option>${stepOptions}
      </select></div>
    <div class="field"><label>适用场景 *（至少选一个）</label>
      <div class="kb-checks">${scenarioChecks}</div></div>
    <div class="field"><label>主张 *（解决什么具体问题）</label>
      <input id="nkClaim" placeholder="如：解决跨部门定责扯皮，缩短客诉闭环时间"></div>
    <div class="field"><label>摘要 *</label>
      <input id="nkSummary" placeholder="一句话说明这篇解决什么问题"></div>
    <div class="row2">
      <div class="field"><label>适用条件 *</label>
        <textarea id="nkApplicable" rows="2" placeholder="什么情况下该用"></textarea></div>
      <div class="field"><label>不适用 / 反证 *</label>
        <textarea id="nkNotApplicable" rows="2" placeholder="什么情况下不该用"></textarea></div>
    </div>
    <div class="row3">
      <div class="field"><label>输入条件</label><input id="nkInputs"></div>
      <div class="field"><label>输出物</label><input id="nkOutputs"></div>
      <div class="field"><label>维护人</label>
        <select id="nkOwner"><option value="">当前用户</option></select></div>
    </div>
    <div class="field"><label>步骤要点</label>
      <textarea id="nkSteps" rows="2" placeholder="2–4 条关键动作"></textarea></div>
    <div class="field"><label>使用证据 *（谁用过、效果如何）</label>
      <textarea id="nkEvidence" rows="2"
        placeholder="如：客服中心使用后闭环时间从 72h 降到 21h"></textarea></div>
    <div class="field"><label>正文 *</label>
      <textarea id="nkContent" style="min-height:120px"
        placeholder="背景 / 方案 / 过程 / 结果 / 踩坑 / 可复用点"></textarea></div>
    <div class="field"><label>入库前自检 *（全部勾选才能提交）</label>
      <div class="kb-checks">
        <label class="kb-check"><input type="checkbox" class="kbGate"> 主张明确</label>
        <label class="kb-check"><input type="checkbox" class="kbGate"> 适用条件</label>
        <label class="kb-check"><input type="checkbox" class="kbGate"> 反证条件</label>
        <label class="kb-check"><input type="checkbox" class="kbGate"> 使用证据</label>
        <label class="kb-check"><input type="checkbox" class="kbGate"> 维护人</label>
      </div></div>`,
  `<button class="btn btn-g" data-act="knowledge.close">取消</button>
   <button class="btn btn-p" data-act="knowledge.submit">提交审核</button>`, true);

  GET('/execution/assignees').then((users) => {
    const sel = document.getElementById('nkOwner');
    if (!sel) return;
    users.forEach((user) => {
      const option = document.createElement('option');
      option.value = String(user.id);
      option.textContent = user.display_name + ' · ' + (user.role_label || user.role);
      if (AUTH.user && user.id === AUTH.user.id) option.selected = true;
      sel.appendChild(option);
    });
  }).catch(() => { /* 拿不到用户列表时后端回落到当前用户 */ });
}

async function submitKnowledge() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const title = val('nkTitle');
  const summary = val('nkSummary');
  const content = val('nkContent');
  const claim = val('nkClaim');
  const applicable = val('nkApplicable');
  const notApplicable = val('nkNotApplicable');
  const evidence = val('nkEvidence');
  const scenarios = [...document.querySelectorAll('input[name="kbScenario"]:checked')]
    .map((el) => el.value);
  const gates = [...document.querySelectorAll('.kbGate')];
  if (!title) return toast('请填写名称', true);
  if (!summary) return toast('请填写摘要', true);
  if (!content) return toast('请填写正文', true);
  if (!claim) return toast('请填写主张', true);
  if (!applicable) return toast('请填写适用条件', true);
  if (!notApplicable) return toast('请填写不适用 / 反证条件', true);
  if (!evidence) return toast('请填写使用证据', true);
  if (!scenarios.length) return toast('请至少选择一个适用场景', true);
  if (gates.some((el) => !el.checked)) return toast('请先完成入库自检', true);

  const ownerId = val('nkOwner');
  const stepNo = val('nkStep');
  let stageNo = val('nkStage') ? Number(val('nkStage')) : null;
  if (stepNo) {
    const option = [...document.querySelectorAll('#nkStep option')]
      .find((row) => row.value === stepNo);
    if (option && option.dataset.stage) stageNo = Number(option.dataset.stage);
  }
  try {
    const created = await POST('/knowledge', {
      title,
      type: val('nkType'),
      methodology: val('nkMethod') || null,
      tags: [],
      summary,
      content,
      claim,
      applicable_when: applicable,
      not_applicable_when: notApplicable,
      input_conditions: val('nkInputs') || null,
      steps_summary: val('nkSteps') || null,
      outputs: val('nkOutputs') || null,
      evidence_summary: evidence,
      scenario_codes: scenarios,
      stage_no: stageNo,
      step_no: stepNo || null,
      tool_code: val('nkTool') || null,
      owner_user_id: ownerId ? Number(ownerId) : null,
      author: AUTH.user ? AUTH.user.display_name : null,
    });
    await POST('/knowledge/' + created.id + '/submit', {});
    closeModal();
    toast('已提交求真审核');
    state.knowledge.status = 'IN_REVIEW';
    syncToolboxUrl();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderKnowledge };
