/* 视图：toolbox —— 问题驱动的工具匹配工作台
 *
 * 工具箱回答「我该用什么、为什么、怎么验证用对了」；
 * 知识库回答「有没有案例、模板和参考」。两者通过 tool_code 双向连接。
 */
import { esc, num, CAT_ICON, skeleton, TOOL_LEVEL_TONE, fmtDate, dateShort, tipHelp } from '../core/format.js';
import {
  toast, openModal, closeModal, closeAllModals, modalAlive, viewEl, on, confirmDialog, promptDialog,
} from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS, urlParams, setUrlState } from '../core/router.js';
import { GET, POST, PATCH } from '../core/api.js';
import { canWrite, canManage } from '../core/auth.js';

/* ============================================================ 5. 方法论工具箱 */

on('toolbox.match', () => matchTools());
on('toolbox.quick', ({ scenario, query }) => {
  state.toolbox.scenario = state.toolbox.scenario === scenario ? '' : scenario;
  state.toolbox.q = state.toolbox.scenario ? (query || '') : '';
  state.toolbox.sort = 'fit';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.setSort', (_data, el) => {
  state.toolbox.sort = el.value;
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.toggleCategory', ({ category }) => {
  const current = new Set(state.toolbox.categories || []);
  if (current.has(category)) current.delete(category);
  else current.add(category);
  state.toolbox.categories = [...current];
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.stageLink', ({ stage }) => {
  state.toolbox.stage = Number(stage) || null;
  state.toolbox.sort = 'fit';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.clear', () => {
  state.toolbox = {
    q: '', scenario: '', categories: [], stage: null, step: '', sort: 'fit', open: '', status: '',
  };
  const input = document.getElementById('searchInput');
  if (input) input.value = '';
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.clearFilter', () => clearToolboxFilter());
on('toolbox.open', ({ code, stack }) => openToolByCode(code, stack === '1'));
on('toolbox.applyStep', ({ code }) => openToolApply(code));
on('toolbox.applyStepSubmit', ({ code }) => submitToolApply(code));
on('toolbox.setStatus', (_data, el) => {
  state.toolbox.status = el.value;
  syncToolboxUrl();
  RENDERERS.toolbox();
});
on('toolbox.newTool', () => openToolForm(null));
on('toolbox.editTool', () => openToolForm(state.toolboxCurrent));
on('toolbox.saveTool', ({ code }) => submitToolForm(code || ''));
on('toolbox.submitTool', ({ code }) => submitToolReviewFlow(code, 'submit'));
on('toolbox.reviewTool', ({ code, decision }) => submitToolReviewFlow(code, decision));
on('toolbox.archiveTool', ({ code }) => archiveTool(code));
on('toolbox.planTool', ({ code }) => openToolPlan(code));
on('toolbox.savePlan', ({ code }) => submitToolPlan(code));
on('toolbox.planStatus', ({ id, status }) => updateToolPlan(Number(id), status));
on('toolbox.goKnowledge', ({ code }) => {
  closeAllModals();
  go('knowledge', { params: { tool: code, sort: 'match' }, push: true });
});
on('toolbox.goWorkflow', () => {
  closeAllModals();
  go('workflow');
});
on('toolbox.selectTool', ({ code }) => {
  state.toolbox.selected = code || '';
  RENDERERS.toolbox();
});
on('toolbox.clearSelected', () => {
  state.toolbox.selected = '';
  RENDERERS.toolbox();
});
on('toolbox.close', () => closeModal());
on('toolbox.closeGoWorkflow', () => {
  closeAllModals();
  go('workflow');
});

function syncToolboxUrl() {
  const tb = state.toolbox;
  setUrlState('toolbox', {
    q: tb.q,
    scenario: tb.scenario,
    category: (tb.categories || []).join(','),
    stage: tb.stage || '',
    step: tb.step || '',
    sort: tb.sort,
    open: tb.open || '',
    status: tb.status || '',
  }, { push: false });
}

const renderToolbox = () => {
  const tb = state.toolbox;
  const params = urlParams();
  if ('q' in params) tb.q = params.q;
  if ('scenario' in params) tb.scenario = params.scenario;
  if ('category' in params) {
    tb.categories = params.category ? params.category.split(',').filter(Boolean) : [];
  }
  if ('stage' in params) tb.stage = Number(params.stage) || null;
  if ('step' in params) tb.step = params.step;
  if ('sort' in params) tb.sort = params.sort;
  if ('open' in params) {
    tb.open = params.open;
    tb.selected = params.open || tb.selected;
  }
  if ('status' in params) tb.status = params.status;
  // 顶栏搜索写入的是 toolboxKeyword，这里消费一次后转入 toolbox.q
  if (state.toolboxKeyword) {
    tb.q = state.toolboxKeyword;
    state.toolboxKeyword = '';
  }
  syncToolboxUrl();

  const hasQuery = !!(tb.q || tb.scenario || tb.stage || tb.step);
  const payload = {
    scenario_codes: tb.scenario ? [tb.scenario] : [],
    category_filters: tb.categories || [],
    stage_no: tb.stage || null,
    step_no: tb.step || null,
    sort: tb.sort,
  };

  return renderAsync('toolbox',
    () => Promise.all([
      GET('/tools/meta'),
      GET('/tools/grouped' + (tb.status ? '?status=' + encodeURIComponent(tb.status) : '')),
      POST('/tools/match', { ...payload, limit: 33 }),
      hasQuery ? POST('/tools/match', { ...payload, problem: tb.q || null, limit: 8 })
        : Promise.resolve(null),
      GET('/workflow/stages'),
      tb.selected
        ? GET('/tools/' + encodeURIComponent(tb.selected)).catch(() => null)
        : Promise.resolve(null),
    ]).then(([meta, groups, catalog, match, stages, detail]) => ({
      meta, groups, catalog, match, stages, detail,
    })),
    (d) => paint(d));
};

function paint(d) {
  const tb = state.toolbox;
  const meta = d.meta;
  state.toolboxMeta = meta;
  const scenarios = meta.scenarios || [];
  const categoryLabels = meta.category_labels || {};
  const difficultyLabels = meta.difficulty_labels || {};
  const filter = state.toolboxFilter;
  const allowed = filter ? new Set(filter.codes) : null;
  const filterHit = (hit) => !allowed || allowed.has(hit.tool.code);

  const catalogHits = (d.catalog.hits || []).filter(filterHit);
  const matchHits = d.match ? (d.match.hits || []).filter(filterHit) : null;
  const hasQuery = !!(tb.q || tb.scenario || tb.stage || tb.step);

  const scenarioChips = scenarios.map((scenario) => `
    <button class="tb-qchip${tb.scenario === scenario.code ? ' on' : ''}"
      data-act="toolbox.quick" data-scenario="${esc(scenario.code)}"
      data-query="${esc(scenario.name)}">${esc(scenario.name)}</button>`).join('');

  const matchCards = matchHits
    ? (matchHits.length
      ? matchHits.map((hit, index) =>
        toolCard(hit, meta, {
          showFit: true,
          recommended: index < 3,
          level: filter && filter.meta ? filter.meta[hit.tool.code] : null,
        })).join('')
      : '<div class="empty">没有匹配到工具。换一种说法，或清空筛选后浏览全部工具。</div>')
    : `<div class="note">先描述一个问题，或点选上方快捷痛点。</div>`;

  const categoryCounts = {};
  (d.groups || []).forEach((group) => {
    categoryCounts[group.category] = group.count;
  });
  const categoryRows = Object.entries(categoryLabels).map(([code, label]) => `
    <button class="tb-quad${(tb.categories || []).includes(code) ? ' on' : ''}"
      data-act="toolbox.toggleCategory" data-category="${esc(code)}">
      <span class="sw"></span><span>${esc(label)}</span>
      <span class="n">${categoryCounts[code] || 0}</span>
    </button>`).join('');

  const stageLinks = (d.stages || []).map((stage) => `
    <button class="tb-stage-link" data-act="toolbox.stageLink" data-stage="${stage.stage_no}">
      <span class="num">${stage.stage_no}</span>
      <span><b>${esc(stage.stage_name)}</b><small>${esc(stage.stage_goal || '')}</small></span>
    </button>`).join('');

  const filterBanner = filter
    ? `<div class="note mb between">
        <div>只显示 <b>${esc(filter.label)}</b> 的推荐工具（${filter.codes.length} 个），
          已按步骤契约排序</div>
        <button class="btn-sm" data-act="toolbox.clearFilter">显示全部工具</button>
      </div>` : '';

  const hasFilter = tb.q || tb.scenario || (tb.categories || []).length || tb.stage || tb.step;
  const toolCount = filter ? filter.codes.length : d.catalog.hits.length;
  const sortOptions = [
    ['fit', '按适配度'],
    ['difficulty', '按难度（低→高）'],
    ['duration', '按周期（短→长）'],
    ['usage', '按使用频率'],
  ].map(([value, label]) =>
    `<option value="${value}"${tb.sort === value ? ' selected' : ''}>${label}</option>`).join('');

  const statusOptions = canManage()
    ? `<select class="sel sel-sm" data-act="toolbox.setStatus">
        <option value=""${!tb.status ? ' selected' : ''}>公开工具</option>
        <option value="DRAFT"${tb.status === 'DRAFT' ? ' selected' : ''}>草稿</option>
        <option value="IN_REVIEW"${tb.status === 'IN_REVIEW' ? ' selected' : ''}>待审核</option>
        <option value="VERIFIED"${tb.status === 'VERIFIED' ? ' selected' : ''}>已验证</option>
        <option value="ARCHIVED"${tb.status === 'ARCHIVED' ? ' selected' : ''}>已归档</option>
      </select>` : '';

  const detail = d.detail;
  const toolNav = catalogHits.map((hit) => `
    <button class="tb-nav-item${tb.selected === hit.tool.code ? ' on' : ''}"
      data-act="toolbox.selectTool" data-code="${esc(hit.tool.code)}">
      <span class="tb-nav-name">${esc(hit.tool.name)}</span>
      <span class="tiny">${esc(hit.tool.category_label || '')}</span>
    </button>`).join('') || '<div class="tiny muted">没有工具</div>';

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div><h2>方法论工具箱（${toolCount} 个工具）
          <span class="module-badge">问题驱动 · 验证标准</span></h2>
          <div class="desc">工具箱回答「该用什么、为什么、怎么验证」；知识库回答「有没有案例、模板和参考」</div></div>
        <div class="gap">
          ${canWrite() ? '<button class="btn btn-p" data-act="toolbox.newTool">+ 新建工具</button>' : ''}
          <a class="link-btn" data-act="toolbox.goWorkflow">回到五阶段步骤 →</a>
        </div>
      </div>
      ${filterBanner}
    </div>

    <div class="tb-shell">
      <aside class="tb-nav-col">
        <div class="card tb-nav-card">
          <h3>快捷痛点</h3>
          <div class="tb-chips">${scenarioChips}</div>
          <h3 class="mt">工具四象限</h3>
          <div class="tb-quads">${categoryRows}</div>
          <h3 class="mt">五阶段</h3>
          <div class="tb-stage-list">${stageLinks}</div>
          <h3 class="mt">全部工具（${catalogHits.length}）</h3>
          <div class="tb-tool-nav">${toolNav}</div>
        </div>
      </aside>

      <main class="tb-main">
        ${detail
          ? `<div class="card tb-detail-card">${toolDetailHtml(detail)}</div>`
          : `<section class="card tb-hero">
              <div class="between mb">
                <div><h3 style="margin:0">① 我遇到了什么问题？${
                  tipHelp('描述问题或点选痛点。系统按「问题匹配 + 场景 + 使用证据」排序，'
                    + '而不是按工具属性分类，也不是让你在工具卡里自己找。')}</h3></div>
                <span class="tag t-blu">左侧四象限是辅助筛选</span>
              </div>
              <div class="tb-match">
                <input id="toolQ" class="sel" style="flex:1;min-width:260px"
                  value="${esc(tb.q)}"
                  placeholder="例如：审批节点太多，一个采购单要走五个人，周期总是超期">
                <button class="btn btn-p" data-act="toolbox.match">匹配工具</button>
                ${hasFilter ? '<button class="btn btn-g" data-act="toolbox.clear">清空</button>' : ''}
              </div>
              <div class="tb-result-head">
                <h3>${d.match ? '匹配结果' : '匹配结果（等待输入）'}${
                  tipHelp('先描述一个问题，或点选左侧快捷痛点。系统会按「问题匹配 + 场景 + 使用证据」'
                    + '排序；没有输入时显示等待状态，不会用默认排序假装已经匹配。')}</h3>
                ${d.match ? `<span class="tiny">已按适配度排序 · ${matchHits.length} 个工具匹配</span>` : ''}
                <select class="sel sel-sm" data-act="toolbox.setSort">${sortOptions}</select>
              </div>
              <div class="tb-cards">${matchCards}</div>
            </section>`}
      </main>

      <aside class="tb-side">
        <div class="card">
          <h3>${detail ? '工具操作' : '匹配与操作'}</h3>
          ${detail
            ? `<div class="gap" style="flex-wrap:wrap">${toolDetailActions(detail, true)}</div>`
            : `<div class="desc">在中间输入问题，或从左侧工具列表选择。</div>
               <div class="gap">
                 <a class="link-btn" data-act="toolbox.goWorkflow">回到五阶段步骤</a>
               </div>`}
        </div>
        ${statusOptions ? `<div class="card"><h3>维护状态</h3>${statusOptions}</div>` : ''}
        <div class="card">
          <h3>求真校验</h3>
          <div class="desc">每个工具都应能回答：主张、证据、适用条件、反证、维护人</div>
          <div class="tb-audit">
            <div>✓ 主张：解决什么问题</div>
            <div>✓ 证据：谁用过、效果如何</div>
            <div>✓ 适用条件：什么时候有效</div>
            <div>✓ 反证：什么时候不该用</div>
            <div>✓ 维护人 + 最后验证日期</div>
          </div>
        </div>
      </aside>
    </div>`;
}

function toolCard(hit, meta, options = {}) {
  const tool = hit.tool;
  const usage = hit.usage || {};
  const usageText = usage.used
    ? `已用 ${usage.used} 次 · 有效 ${usage.effective} 次（${num(usage.rate, 0)}%）`
    : '暂无使用记录';
  const fit = options.showFit && hit.score !== undefined && hit.score !== null
    ? Math.max(0, Math.min(100, hit.score))
    : null;
  const verify = tool.verification_standard
    ? esc(tool.verification_standard)
    : '<span class="muted">待补充：维护人还没有写验证标准</span>';
  const levelTag = options.level
    ? `<span class="tag ${TOOL_LEVEL_TONE[options.level.level] || 't-gry'}">${
      esc(options.level.level_label || options.level.level)}</span>`
    : '';
  return `
    <article class="tb-card${options.recommended ? ' rec' : ''}">
      <div class="tb-card-head">
        <span class="tb-ic">${CAT_ICON[tool.category] || '⚒'}</span>
        <div class="tb-card-title">
          <b>${esc(tool.name)}</b>
          <div class="tiny">${esc(tool.code)} · ${esc(tool.category_label || meta.category_labels[tool.category] || tool.category)}</div>
        </div>
        ${levelTag}
        ${tool.review_overdue ? '<span class="tag t-red">待复核</span>' : ''}
        ${fit === null ? '' : `<span class="tb-fit">适配 ${num(fit, 0)}</span>`}
      </div>
      ${fit === null ? '' : `<div class="tb-fit-bar"><i style="width:${fit}%"></i></div>`}
      <p class="tb-why">${esc(tool.purpose)}</p>
      <div class="tb-meta">
        <span><b>难度</b> ${esc(tool.difficulty_label || meta.difficulty_labels[tool.difficulty] || '—')}</span>
        <span><b>周期</b> ${esc(tool.typical_duration || '待补充')}</span>
        <span><b>阶段</b> ${tool.stage_no}</span>
        <span><b>${tool.steps.length} 步</b></span>
        ${tool.knowledge_count ? `<span><b>关联知识</b> ${tool.knowledge_count}</span>` : ''}
      </div>
      <div class="tb-verify"><b>验证标准：</b>${verify}</div>
      <div class="tb-evidence">
        <span>${esc(usageText)}</span>
        <span>维护：${esc(tool.owner || '—')}</span>
        ${tool.last_verified_at ? `<span>验证：${fmtDate(tool.last_verified_at)}</span>` : ''}
      </div>
      ${hit.matched_on && hit.matched_on.length
        ? `<div class="tiny">命中：${hit.matched_on.map(esc).join(' · ')}</div>` : ''}
      <div class="tb-actions">
        <button class="btn-sm" data-act="toolbox.open" data-code="${esc(tool.code)}">查看详情</button>
        ${state.toolbox.step ? `<button class="btn-sm" data-act="toolbox.applyStep"
          data-code="${esc(tool.code)}">用到 ${esc(state.toolbox.step)}</button>` : ''}
        <button class="btn-sm" data-act="toolbox.goKnowledge" data-code="${esc(tool.code)}">相关案例/模板</button>
      </div>
    </article>`;
}

function matchTools() {
  const input = document.getElementById('toolQ');
  const value = input ? input.value.trim() : '';
  if (!value && !state.toolbox.scenario) {
    return toast('请描述一个问题，或先选一个快捷痛点', true);
  }
  state.toolbox.q = value;
  state.toolbox.sort = 'fit';
  syncToolboxUrl();
  RENDERERS.toolbox();
}

function clearToolboxFilter() {
  state.toolboxFilter = null;
  state.toolbox.step = '';
  state.toolbox.stage = null;
  syncToolboxUrl();
  RENDERERS.toolbox();
}

/* -------------------------------------------------- 工具详情 */

async function openToolByCode(code, keepPrevious) {
  // 加载层若嵌套在向导里，关闭后要回到向导；内容返回时只替换加载层，不再压栈。
  const gen = openModal('加载中…', skeleton(4), '', true, { keepPrevious });
  try {
    const t = await GET('/tools/' + code);
    if (!modalAlive(gen)) return;
    paintTool(t);
  } catch (e) {
    if (modalAlive(gen)) {
      openModal(
        '加载失败',
        '<div class="errbar"><div>' + esc(e.message) + '</div></div>',
        '', false, { replace: true },
      );
    }
  }
}

function toolDetailHtml(t) {
  const usage = t.usage || {};
  const usageText = usage.used
    ? `已用 ${usage.used} 次 · 有效 ${usage.effective} 次（${num(usage.rate, 0)}%）`
    : '暂无使用记录';
  const knowledge = t.knowledge || [];
  const knowledgeHtml = knowledge.length
    ? `<div class="tb-related">${knowledge.map((item) => `
        <div class="tb-related-item">
          <div><b>${esc(item.title)}</b>
            <span class="tag ${item.type === 'CASE' ? 't-red' : item.type === 'TEMPLATE' ? 't-blu' : 't-pur'}">${
              esc(item.type_label || item.type)}</span>
            <div class="tiny">${esc(item.summary)}</div></div>
          <button class="btn-sm" data-act="knowledge.open" data-id="${item.id}">查看</button>
        </div>`).join('')}</div>`
    : '<div class="note">还没有关联的案例/模板。流程管理科可以在知识库里通过 tool_code 关联。</div>';
  const steps = (t.workflow_steps || []);
  const stepHtml = steps.length
    ? steps.map((step) => `<span class="tag t-blu">${esc(step.step_no)} ${esc(step.name)}</span>`).join(' ')
    : '<span class="tiny muted">还没有步骤契约引用这个工具</span>';
  state.toolboxCurrent = t;
  const statusTone = {
    DRAFT: 't-gry', IN_REVIEW: 't-yel', PUBLISHED: 't-blu',
    VERIFIED: 't-grn', ARCHIVED: 't-gry',
  }[t.status] || 't-gry';
  const usageRows = (t.usage_events || []).map((row) => `
    <tr><td class="tiny">${fmtDate(row.used_at)}</td>
      <td><span class="tag ${row.outcome === 'EFFECTIVE' ? 't-grn'
        : row.outcome === 'PARTIAL' ? 't-yel' : 't-red'}">${esc(row.outcome_label || row.outcome)}</span></td>
      <td>${esc(row.step_no || '—')}</td><td>${esc(row.used_by || '—')}</td>
      <td class="tiny">${esc(row.note || '—')}</td></tr>`).join('');
  const usageTable = usageRows
    ? `<h3 class="mt">直接使用记录</h3>
       <table class="tbl"><thead><tr><th>时间</th><th>效果</th><th>步骤</th>
         <th>使用人</th><th>说明</th></tr></thead><tbody>${usageRows}</tbody></table>`
    : '';
  const planRows = (t.plans || []).map((plan) => `
    <tr><td class="tiny">${fmtDate(plan.planned_at)}</td>
      <td>${esc(plan.step_no || '—')}</td>
      <td><span class="tag ${plan.status === 'DONE' ? 't-grn'
        : plan.status === 'CANCELLED' ? 't-gry' : 't-blu'}">${esc(plan.status_label || plan.status)}</span></td>
      <td class="tiny">${esc(plan.target || plan.note || '—')}</td>
      <td>${esc(plan.planned_by || '—')}</td>
      <td class="gap">
        ${plan.status === 'PLANNED' ? `<button class="btn-sm"
          data-act="toolbox.planStatus" data-id="${plan.id}" data-status="IN_PROGRESS">开始</button>` : ''}
        ${plan.status === 'IN_PROGRESS' ? `<button class="btn-sm"
          data-act="toolbox.planStatus" data-id="${plan.id}" data-status="DONE">完成</button>` : ''}
        ${['PLANNED', 'IN_PROGRESS'].includes(plan.status) ? `<button class="btn-sm"
          data-act="toolbox.planStatus" data-id="${plan.id}" data-status="CANCELLED">取消</button>` : ''}
      </td></tr>`).join('');
  const plansTable = planRows
    ? `<h3 class="mt">使用计划</h3>
       <table class="tbl"><thead><tr><th>计划时间</th><th>步骤</th><th>状态</th>
         <th>目标 / 说明</th><th>创建人</th><th>操作</th></tr></thead>
         <tbody>${planRows}</tbody></table>`
    : '';

  return `
    <div class="gap mb" style="flex-wrap:wrap">
      <span class="tag t-blu">${esc(t.category_label || t.category)}</span>
      <span class="tag ${statusTone}">${esc(t.status_label || t.status)}</span>
      <span class="tag t-gry">难度 ${esc(t.difficulty_label || t.difficulty || '—')}</span>
      <span class="tag t-gry">周期 ${esc(t.typical_duration || '待补充')}</span>
      <span class="tag t-gry">阶段 ${t.stage_no}</span>
      ${t.review_overdue ? '<span class="tag t-red">待复核</span>' : ''}
      <span class="tiny">v${t.version} · 维护人 ${esc(t.owner || '—')}
        ${t.last_verified_at ? ' · 验证 ' + fmtDate(t.last_verified_at) : ''}
        ${t.review_due_at ? ' · 复审 ' + dateShort(t.review_due_at) : ''}</span>
    </div>
    <div class="note mb">${esc(t.purpose)}</div>
    <div class="tb-detail">
      <div><span>适用场景</span><b>${(t.scenario_names || []).length
        ? t.scenario_names.map(esc).join('、') : '—'}</b></div>
      <div><span>适用条件</span><b>${esc(t.when_to_use || '—')}</b></div>
      <div><span>不适用 / 反证</span><b>${esc(t.not_applicable_when || '待补充')}</b></div>
      <div><span>前置条件</span><b>${esc(t.prerequisites || '待补充')}</b></div>
      <div><span>验证标准</span><b>${esc(t.verification_standard || '待补充')}</b></div>
      <div><span>使用证据</span><b>${esc(usageText)}</b></div>
      <div><span>关联工作流步骤</span><b>${stepHtml}</b></div>
    </div>

    <h3>标准操作步骤</h3>
    <ol style="padding-left:20px;font-size:13px;line-height:1.95;color:var(--text);margin-bottom:14px">
      ${t.steps.map((step) => '<li>' + esc(step) + '</li>').join('')}
    </ol>

    ${t.template_ref ? '<h3>模板 / 工具指引</h3><div class="note mb">' + esc(t.template_ref) + '</div>' : ''}
    ${t.pitfalls ? '<h3>常见误用</h3><div class="warnbox">' + esc(t.pitfalls) + '</div>' : ''}

    <h3 class="mt">相关案例 / 模板 / 知识</h3>
    ${knowledgeHtml}
    ${usageTable}
    ${plansTable}`;
}

function toolDetailActions(t, inline = false) {
  const stepCtx = state.toolbox.step;
  const applyButton = stepCtx
    ? `<button class="btn btn-p" data-act="toolbox.applyStep" data-code="${esc(t.code)}">
         用到步骤 ${esc(stepCtx)}</button>`
    : '';
  const canEdit = canWrite() && ['DRAFT', 'IN_REVIEW'].includes(t.status);
  const canReview = canManage() && t.status === 'IN_REVIEW';
  const canArchive = canManage() && t.status !== 'ARCHIVED';
  return `${inline
    ? '<button class="btn btn-g" data-act="toolbox.clearSelected">返回匹配</button>'
    : '<button class="btn btn-g" data-act="toolbox.close">关闭</button>'}
     ${applyButton}
     ${canWrite() ? `<button class="btn btn-g" data-act="toolbox.planTool"
       data-code="${esc(t.code)}">加入使用计划</button>` : ''}
     ${canEdit ? `<button class="btn btn-g" data-act="toolbox.editTool"
       data-code="${esc(t.code)}">编辑</button>` : ''}
     ${canEdit && t.status === 'DRAFT' ? `<button class="btn btn-g"
       data-act="toolbox.submitTool" data-code="${esc(t.code)}">提交审核</button>` : ''}
     ${canReview ? `<button class="btn btn-g" data-act="toolbox.reviewTool"
       data-code="${esc(t.code)}" data-decision="REJECT">驳回</button>
       <button class="btn btn-p" data-act="toolbox.reviewTool"
       data-code="${esc(t.code)}" data-decision="APPROVE">通过审核</button>` : ''}
     ${canArchive ? `<button class="btn btn-g" data-act="toolbox.archiveTool"
       data-code="${esc(t.code)}">归档</button>` : ''}
     <button class="btn btn-g" data-act="toolbox.goKnowledge"
       data-code="${esc(t.code)}">在知识库查看</button>`;
}

function paintTool(t) {
  state.toolboxCurrent = t;
  openModal(t.name + (t.alias ? ' · ' + t.alias : ''),
    toolDetailHtml(t), toolDetailActions(t), true, { replace: true });
}

async function openToolApply(code) {
  const step = state.toolbox.step;
  if (!step) return toast('请先从工作流步骤进入工具箱', true);
  let tool = state.toolboxCurrent;
  if (!tool || tool.code !== code) {
    try {
      tool = await GET('/tools/' + code);
      state.toolboxCurrent = tool;
    } catch (e) {
      return toast(e.message, true);
    }
  }
  const related = (tool.knowledge || []).find((item) => item.type === 'TOOL')
    || (tool.knowledge || [])[0];
  openModal('用到当前步骤 · ' + tool.name, `
    <div class="note mb">记录一次工具使用证据，关联工作流步骤 <b>${esc(step)}</b>。
      ${related ? `关联参考：《${esc(related.title)}》` : '该工具暂时没有关联知识，但仍可记录现场使用。'}</div>
    <div class="field"><label>本次效果</label>
      <select id="taOutcome">
        <option value="EFFECTIVE">有效</option>
        <option value="PARTIAL">部分有效</option>
        <option value="INEFFECTIVE">无效</option>
      </select></div>
    <div class="field"><label>说明</label>
      <input id="taNote" value="在步骤 ${esc(step)} 使用 ${esc(tool.name)}"></div>`,
  `<button class="btn btn-g" data-act="toolbox.close">取消</button>
   <button class="btn btn-p" data-act="toolbox.applyStepSubmit" data-code="${esc(tool.code)}">记录</button>`);
}

async function submitToolApply(code) {
  const step = state.toolbox.step;
  if (!step) return toast('步骤上下文已丢失，请重新从工作流进入', true);
  const outcome = document.getElementById('taOutcome')?.value || 'EFFECTIVE';
  const note = document.getElementById('taNote')?.value.trim() || null;
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

function toolFormFields(t) {
  const meta = state.toolboxMeta || {};
  const categories = meta.category_labels || {};
  const difficulties = meta.difficulty_labels || {};
  const scenarios = meta.scenarios || [];
  const current = t || {};
  const selected = new Set(current.scenario_codes || []);
  return `
    <div class="row2">
      <div class="field"><label>工具编码 *</label>
        <input id="tfCode" value="${esc(current.code || '')}" ${t ? 'readonly' : ''}
          placeholder="如 SIPOC"></div>
      <div class="field"><label>名称 *</label>
        <input id="tfName" value="${esc(current.name || '')}" placeholder="如 SIPOC 流程范围图"></div>
    </div>
    <div class="row3">
      <div class="field"><label>象限 *</label><select id="tfCategory">
        ${Object.entries(categories).map(([code, label]) =>
          `<option value="${code}"${current.category === code ? ' selected' : ''}>${esc(label)}</option>`).join('')}
      </select></div>
      <div class="field"><label>适用阶段 *</label><select id="tfStage">
        ${[1, 2, 3, 4, 5].map((n) =>
          `<option value="${n}"${current.stage_no === n ? ' selected' : ''}>阶段${n}</option>`).join('')}
      </select></div>
      <div class="field"><label>难度</label><select id="tfDifficulty">
        ${Object.entries(difficulties).map(([code, label]) =>
          `<option value="${code}"${(current.difficulty || 'MEDIUM') === code ? ' selected' : ''}>${esc(label)}</option>`).join('')}
      </select></div>
    </div>
    <div class="field"><label>解决什么问题 *</label>
      <textarea id="tfPurpose" rows="2">${esc(current.purpose || '')}</textarea></div>
    <div class="field"><label>适用条件 *</label>
      <textarea id="tfWhen" rows="2">${esc(current.when_to_use || '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>不适用 / 反证</label>
        <textarea id="tfNotApplicable" rows="2">${esc(current.not_applicable_when || '')}</textarea></div>
      <div class="field"><label>前置条件</label>
        <textarea id="tfPrereq" rows="2">${esc(current.prerequisites || '')}</textarea></div>
    </div>
    <div class="field"><label>验证标准</label>
      <input id="tfVerify" value="${esc(current.verification_standard || '')}"
        placeholder="怎么判断用对了"></div>
    <div class="row2">
      <div class="field"><label>预计周期</label>
        <input id="tfDuration" value="${esc(current.typical_duration || '')}" placeholder="如 2–3 周"></div>
      <div class="field"><label>模板 / 工具指引</label>
        <input id="tfTemplate" value="${esc(current.template_ref || '')}"></div>
    </div>
    <div class="field"><label>标准步骤（每行一条）</label>
      <textarea id="tfSteps" rows="5">${esc((current.steps || []).join('\n'))}</textarea></div>
    <div class="field"><label>常见误用</label>
      <textarea id="tfPitfalls" rows="2">${esc(current.pitfalls || '')}</textarea></div>
    <div class="field"><label>适用场景</label>
      <div class="kb-checks">${scenarios.map((scenario) => `
        <label class="kb-check"><input type="checkbox" name="tfScenario"
          value="${esc(scenario.code)}"${selected.has(scenario.code) ? ' checked' : ''}>
          ${esc(scenario.name)}</label>`).join('')}</div></div>`;
}

function openToolForm(tool) {
  const meta = state.toolboxMeta;
  if (!meta) return toast('工具箱元数据未加载，请刷新后重试', true);
  const t = tool || null;
  openModal(t ? '编辑工具 · ' + t.name : '新建工具草稿', toolFormFields(t),
    `<button class="btn btn-g" data-act="toolbox.close">取消</button>
     <button class="btn btn-p" data-act="toolbox.saveTool"
       data-code="${esc(t ? t.code : '')}">${t ? '保存' : '创建草稿'}</button>`, true);
}

async function submitToolForm(code) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  const name = val('tfName');
  const purpose = val('tfPurpose');
  const when = val('tfWhen');
  if (!code && !/^[A-Za-z0-9_-]{2,32}$/.test(val('tfCode'))) {
    return toast('工具编码需为 2–32 位字母、数字、下划线或连字符', true);
  }
  if (!name || !purpose || !when) return toast('名称、问题、适用条件不能为空', true);
  const payload = {
    name,
    category: val('tfCategory'),
    stage_no: Number(val('tfStage')),
    purpose,
    when_to_use: when,
    difficulty: val('tfDifficulty') || 'MEDIUM',
    not_applicable_when: val('tfNotApplicable') || null,
    prerequisites: val('tfPrereq') || null,
    verification_standard: val('tfVerify') || null,
    typical_duration: val('tfDuration') || null,
    template_ref: val('tfTemplate') || null,
    steps: val('tfSteps').split('\n').map((row) => row.trim()).filter(Boolean),
    pitfalls: val('tfPitfalls') || null,
    scenario_codes: [...document.querySelectorAll('input[name="tfScenario"]:checked')]
      .map((el) => el.value),
  };
  try {
    const saved = code
      ? await PATCH('/tools/' + encodeURIComponent(code), payload)
      : await POST('/tools', { ...payload, code: val('tfCode') });
    toast(code ? '已保存' : '已创建草稿');
    state.toolbox.status = code ? state.toolbox.status : 'DRAFT';
    closeModal();
    RENDERERS.toolbox();
    openToolByCode(saved.code);
  } catch (e) {
    toast(e.message, true);
  }
}

async function submitToolReviewFlow(code, action) {
  const tool = state.toolboxCurrent;
  try {
    if (action === 'submit') {
      await POST('/tools/' + encodeURIComponent(code) + '/submit', {});
      toast('已提交审核');
    } else {
      const note = await promptDialog(
        action === 'APPROVE' ? '审核通过说明（可选）' : '驳回原因（可选）',
        { title: action === 'APPROVE' ? '通过审核' : '驳回工具', okText: '确定' },
      );
      if (note === null) return;
      await POST('/tools/' + encodeURIComponent(code) + '/review', {
        decision: action,
        note: note || null,
      });
      toast(action === 'APPROVE' ? '已通过审核' : '已驳回，退回草稿');
    }
    closeModal();
    RENDERERS.toolbox();
    if (tool) openToolByCode(code);
  } catch (e) {
    toast(e.message, true);
  }
}

async function archiveTool(code) {
  const ok = await confirmDialog('归档后该工具不再出现在匹配与全部工具中，确定归档？',
    { title: '归档工具', okText: '归档', danger: true });
  if (!ok) return;
  try {
    await POST('/tools/' + encodeURIComponent(code) + '/archive', {});
    toast('已归档');
    closeModal();
    RENDERERS.toolbox();
  } catch (e) {
    toast(e.message, true);
  }
}

function openToolPlan(code) {
  const tool = state.toolboxCurrent;
  if (!tool || tool.code !== code) return toast('请先打开工具详情', true);
  openModal('加入使用计划 · ' + tool.name, `
    <div class="note mb">计划用于在项目/步骤上下文中提前约定使用工具，执行后再把状态改为完成。</div>
    <div class="field"><label>关联步骤</label>
      <input id="tpStep" value="${esc(state.toolbox.step || '')}" placeholder="如 2.1"></div>
    <div class="field"><label>目标 / 验证标准</label>
      <textarea id="tpTarget" rows="2"
        placeholder="如：找到 3 个以上非增值等待环节">${esc(tool.verification_standard || '')}</textarea></div>
    <div class="field"><label>说明</label><textarea id="tpNote" rows="2"></textarea></div>`,
  `<button class="btn btn-g" data-act="toolbox.close">取消</button>
   <button class="btn btn-p" data-act="toolbox.savePlan" data-code="${esc(code)}">保存计划</button>`);
}

async function submitToolPlan(code) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };
  try {
    await POST('/tools/' + encodeURIComponent(code) + '/plans', {
      step_no: val('tpStep') || null,
      target: val('tpTarget') || null,
      note: val('tpNote') || null,
    });
    toast('使用计划已创建');
    closeModal();
    RENDERERS.toolbox();
    openToolByCode(code);
  } catch (e) {
    toast(e.message, true);
  }
}

async function updateToolPlan(planId, status) {
  try {
    await PATCH('/tools/plans/' + planId, { status });
    toast('计划状态已更新');
    if (state.toolboxCurrent) openToolByCode(state.toolboxCurrent.code);
  } catch (e) {
    toast(e.message, true);
  }
}

export const actions = { 'toolbox.openTool': openToolByCode };
export { renderToolbox };
