/* 视图：knowledge —— 场景驱动的知识工作台
 *
 * 页面首先回答「我现在想解决什么」，而不是展示文件分类。
 * 推荐依据是场景匹配 + 使用证据 + 工作流位置；浏览量只作为阅读统计。
 */
import { esc, fmtDate, num, skeleton } from '../core/format.js';
import {
  toast, openModal, closeModal, modalAlive, viewEl, on, confirmDialog,
} from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go, urlParams, setUrlState } from '../core/router.js';
import { AUTH, canWrite, canManage } from '../core/auth.js';
import { GET, POST } from '../core/api.js';

/* ============================================================ 8. 流程知识库 */

const STATUS_TONE = {
  DRAFT: 't-gry',
  IN_REVIEW: 't-yel',
  PUBLISHED: 't-blu',
  VERIFIED: 't-grn',
  ARCHIVED: 't-gry',
};
const TYPE_TONE = {
  CASE: 't-red',
  TEMPLATE: 't-blu',
  METHOD: 't-pur',
  TOOL: 't-yel',
  BEST_PRACTICE: 't-pur',
  STANDARD: 't-gry',
};
const SCENARIO_ICON = {
  FLOW: '🔀', CYCLE: '⏱️', ERROR: '⚠️', RACI: '👤', COST: '💰', STANDARD: '📐',
};
const TYPE_ORDER = ['CASE', 'TEMPLATE', 'METHOD', 'TOOL'];

on('knowledge.open', ({ id }) => openKnowledge(Number(id)));
on('knowledge.setType', ({ value }) => setK('type', value));
on('knowledge.setSort', (_data, el) => setK('sort', el.value));
on('knowledge.setStatus', (_data, el) => setK('status', el.value));
on('knowledge.setStage', (_data, el) => setK('stage', el.value ? Number(el.value) : null));
on('knowledge.scenario', ({ code }) => {
  state.knowledge.scenario = state.knowledge.scenario === code ? '' : code;
  state.knowledge.page = 1;
  syncKnowledgeUrl();
  RENDERERS.knowledge();
});
on('knowledge.stageLink', ({ stage }) => {
  state.knowledge.stage = Number(stage) || null;
  state.knowledge.page = 1;
  state.knowledge.sort = 'match';
  syncKnowledgeUrl();
  RENDERERS.knowledge();
});
on('knowledge.match', () => {
  const input = document.getElementById('kbQ');
  state.knowledge.keyword = input ? input.value.trim() : state.knowledge.keyword;
  state.knowledge.page = 1;
  if (!state.knowledge.scenario && state.knowledge.keyword.length < 2) {
    return toast('请先选一个痛点，或至少输入 2 个字描述问题', true);
  }
  syncKnowledgeUrl();
  RENDERERS.knowledge();
});
on('knowledge.clear', () => clearK());
on('knowledge.page', ({ page }) => setKPage(Number(page)));
on('knowledge.new', () => newKnowledgeModal());
on('knowledge.goWorkflow', () => go('workflow'));
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
on('knowledge.submitReview', ({ id }) => submitForReview(Number(id)));
on('knowledge.review', ({ id, decision }) => reviewKnowledge(Number(id), decision));
on('knowledge.archive', ({ id }) => archiveKnowledge(Number(id)));
on('knowledge.promote', ({ id }) => promoteKnowledge(Number(id)));

const renderKnowledge = () => {
  const k = state.knowledge;
  const params = urlParams();
  if ('scenario' in params) k.scenario = params.scenario;
  if ('q' in params) k.keyword = params.q;
  else if ('keyword' in params) k.keyword = params.keyword;
  if ('stage' in params) k.stage = Number(params.stage) || null;
  if ('step' in params) k.step = params.step;
  if ('type' in params) k.type = params.type;
  if ('sort' in params) k.sort = params.sort;
  if ('status' in params) k.status = params.status;
  if ('tag' in params) k.tag = params.tag;
  if ('tool' in params) k.tool = params.tool;
  if ('page' in params) k.page = Number(params.page) || 1;

  const qs = [];
  if (k.type) qs.push('type=' + k.type);
  if (k.tag) qs.push('tag=' + encodeURIComponent(k.tag));
  if (k.keyword) qs.push('keyword=' + encodeURIComponent(k.keyword));
  if (k.scenario) qs.push('scenario=' + encodeURIComponent(k.scenario));
  if (k.stage) qs.push('stage_no=' + k.stage);
  if (k.step) qs.push('step_no=' + encodeURIComponent(k.step));
  if (k.status) qs.push('status=' + k.status);
  if (k.tool) qs.push('tool_code=' + encodeURIComponent(k.tool));
  qs.push('sort=' + k.sort, 'page=' + (k.page || 1), 'page_size=24');

  const shouldRecommend = !!(k.scenario || k.keyword || k.stage || k.step);
  return renderAsync('knowledge',
    () => Promise.all([
      GET('/knowledge?' + qs.join('&')),
      GET('/knowledge/meta'),
      GET('/workflow/stages'),
      shouldRecommend
        ? POST('/knowledge/recommend', {
          problem: k.keyword || null,
          scenario_codes: k.scenario ? [k.scenario] : [],
          stage_no: k.stage || null,
          step_no: k.step || null,
          limit: 6,
        })
        : Promise.resolve(null),
      canManage() ? GET('/knowledge/archive-candidates?limit=8').catch(() => []) : Promise.resolve([]),
      canManage() ? GET('/knowledge/effect-stats').catch(() => null) : Promise.resolve(null),
    ]).then(([page, meta, stages, recommend, archiveCandidates, effectStats]) =>
      ({ page, meta, stages, recommend, archiveCandidates, effectStats })),
    (d) => paint(d));
};

function paint(d) {
  const k = state.knowledge;
  const meta = d.meta;
  state.knowledgeMeta = meta;
  if (d.stages) state.wf = d.stages;
  const stats = meta.stats || {};
  const labels = meta.type_labels || {};
  const statusLabels = meta.status_labels || {};
  const scenarios = meta.scenarios || [];
  const scenarioNames = Object.fromEntries(scenarios.map((s) => [s.code, s.name]));
  if (k.status && !canManage()) k.status = '';

  const scenarioButtons = scenarios.map((scenario) => `
    <button class="kb-pain${k.scenario === scenario.code ? ' on' : ''}"
      data-act="knowledge.scenario" data-code="${esc(scenario.code)}"
      aria-pressed="${k.scenario === scenario.code ? 'true' : 'false'}">
      <span class="ic">${SCENARIO_ICON[scenario.code] || '•'}</span>
      <span><b>${esc(scenario.name)}</b><small>${esc(scenario.description || '')}</small></span>
    </button>`).join('');

  const reco = d.recommend;
  const recoHtml = reco
    ? (reco.items.length
      ? `<div class="kb-reco-head">为你推荐 <b>${reco.items.length}</b> 项
          <span class="tiny">按「场景匹配 + 使用证据 + 工作流位置」排序，浏览量不参与</span></div>
        <div class="kb-reco-list">${reco.items.map((item) => recoCard(item, labels, statusLabels, scenarioNames)).join('')}</div>`
      : '<div class="note">没有匹配到知识。换一个痛点，或直接新建一条并走求真审核。</div>')
    : `<div class="kb-reco-empty">先选一个痛点，或在输入框描述你遇到的问题。
        <span class="tiny">例：供应商交期经常延误，采购和仓储互相推</span></div>`;

  const typeChips = [
    `<button class="chip${!k.type ? ' on' : ''}" data-act="knowledge.setType" data-value="">全部</button>`,
    ...TYPE_ORDER.filter((code) => labels[code]).map((code) =>
      `<button class="chip${k.type === code ? ' on' : ''}" data-act="knowledge.setType"
        data-value="${code}">${esc(labels[code])}</button>`),
  ].join('');

  const statusOptions = canManage()
    ? `<select class="sel sel-sm" data-act="knowledge.setStatus">
        <option value="">全部公开</option>
        ${['VERIFIED', 'PUBLISHED', 'IN_REVIEW', 'DRAFT', 'ARCHIVED'].map((code) =>
          `<option value="${code}"${k.status === code ? ' selected' : ''}>${
            esc(statusLabels[code] || code)}</option>`).join('')}
      </select>`
    : '';

  const stageOptions = (d.stages || []).map((stage) =>
    `<option value="${stage.stage_no}"${k.stage === stage.stage_no ? ' selected' : ''}>`
    + `阶段${stage.stage_no} ${esc(stage.stage_name)}</option>`).join('');

  const cards = d.page.items.map((item) =>
    cardHtml(item, labels, statusLabels, scenarioNames)).join('')
    || '<div class="empty">没有符合条件的知识。换个场景或类型试试。</div>';

  const pageSize = d.page.page_size || 24;
  const pages = Math.max(1, Math.ceil(d.page.total / pageSize));
  const current = Math.min(Math.max(1, d.page.page || k.page || 1), pages);
  const pager = pages > 1 ? `
    <div class="pager">
      <button class="btn-sm" ${current <= 1 ? 'disabled' : ''}
        data-act="knowledge.page" data-page="${current - 1}">上一页</button>
      <span class="tiny">第 ${current} / ${pages} 页 · 共 ${d.page.total} 条</span>
      <button class="btn-sm" ${current >= pages ? 'disabled' : ''}
        data-act="knowledge.page" data-page="${current + 1}">下一页</button>
    </div>` : '';

  const hasFilter = k.scenario || k.keyword || k.type || k.status || k.stage || k.tag || k.tool;
  const stageLinks = (d.stages || []).map((stage) => `
    <button class="kb-stage-link" data-act="knowledge.stageLink" data-stage="${stage.stage_no}">
      <span class="num">${stage.stage_no}</span>
      <span><b>${esc(stage.stage_name)}</b><small>${esc(stage.stage_goal || '')}${
        stage.knowledge_count ? ' · ' + stage.knowledge_count + ' 条推荐知识' : ''}</small></span>
    </button>`).join('');

  const archiveCandidates = d.archiveCandidates || [];
  const archiveHtml = canManage() ? `
        <div class="card">
          <div class="between">
            <h3 style="margin:0">归档候选</h3>
            <span class="tag ${archiveCandidates.length ? 't-yel' : 't-gry'}">${
              archiveCandidates.length}</span>
          </div>
          <div class="desc">超过 12 个月没有使用证据的公开知识。归档后不再进入列表与推荐，
            记录仍然保留，便于追溯。</div>
          ${archiveCandidates.length
            ? `<div class="kb-archive-list">${archiveCandidates.map((item) => `
                <div class="kb-archive-item">
                  <div><b>${esc(item.title)}</b>
                    <div class="tiny">${item.unused_days} 天未使用${
                      item.last_used_at ? ' · 最近使用 ' + fmtDate(item.last_used_at) : ''}</div></div>
                  <div class="gap">
                    <button class="btn-sm" data-act="knowledge.open" data-id="${item.id}">查看</button>
                    <button class="btn-sm" data-act="knowledge.archive" data-id="${item.id}">归档</button>
                  </div>
                </div>`).join('')}</div>`
            : '<div class="tiny muted">暂无候选。长期未使用的条目会自动出现在这里。</div>'}
        </div>` : '';

  const effects = d.effectStats;
  const effectHtml = canManage() && effects ? `
        <div class="card">
          <h3>使用效果</h3>
          <div class="desc">只统计有使用证据的公开知识；按使用人回填的效果汇总</div>
          <div class="grid g2 stat-row">
            <div class="kpi stat"><div class="num">${effects.usage_total}</div>
              <div class="lab">累计使用</div></div>
            <div class="kpi stat"><div class="num">${
              effects.effectiveness_rate === null || effects.effectiveness_rate === undefined
                ? '—' : num(effects.effectiveness_rate, 0) + '<small>%</small>'}</div>
              <div class="lab">有效率 · 有效 ${effects.effective_count}
                / 部分 ${effects.partial_count} / 无效 ${effects.ineffective_count}</div></div>
          </div>
          ${effects.by_type.length ? `<div class="kb-eff-types">${effects.by_type.map((row) => `
            <div class="kb-eff-row">
              <span>${esc(row.type_label)}</span>
              <span>${row.used_count} 次 · 有效率 ${
                row.effectiveness_rate === null ? '—' : num(row.effectiveness_rate, 0) + '%'}</span>
            </div>`).join('')}</div>` : ''}
          ${effects.top_items.length ? `<div class="kb-eff-top">
            <div class="tiny muted">使用最多</div>
            ${effects.top_items.slice(0, 3).map((item) => `
              <button class="kb-eff-item" data-act="knowledge.open" data-id="${item.id}">
                <b>${esc(item.title)}</b>
                <span>${item.used_count} 次 · 有效率 ${
                  item.effectiveness_rate === null ? '—' : num(item.effectiveness_rate, 0) + '%'}</span>
              </button>`).join('')}</div>`
            : '<div class="tiny muted">还没有使用记录。用过后回填，统计才会积累。</div>'}
        </div>` : '';

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div><h2>流程知识库<span class="module-badge">场景驱动 · 使用证据</span></h2>
          <div class="desc">已收录 ${stats.total || 0} 条 · 已验证 ${stats.verified || 0} 条
            · 待复核 ${stats.review_overdue || 0} 条 · 待审核 ${stats.pending_review || 0} 条</div></div>
        <div class="gap">
          <a class="link-btn" data-act="knowledge.goDocuments">制度中心 →</a>
          <a class="link-btn" data-act="knowledge.goWorkflow">五阶段工作流 →</a>
          ${canWrite() ? '<button class="btn btn-p" data-act="knowledge.new">+ 新建条目</button>' : ''}
        </div>
      </div>
    </div>

    <div class="kb-layout">
      <main>
        <section class="card kb-scenario">
          <div class="between mb">
            <div><h3 style="margin:0">① 我先想解决什么？</h3>
              <div class="desc" style="margin:2px 0 0">选痛点或描述问题，系统按场景和使用证据推荐，
                不是让你翻卡片</div></div>
            <span class="tag t-blu">推荐依据：匹配度 + 证据</span>
          </div>
          <div class="kb-pains" role="group" aria-label="痛点场景">${scenarioButtons}</div>
          <div class="kb-match">
            <input id="kbQ" class="sel" style="flex:1;min-width:240px"
              value="${esc(k.keyword)}"
              placeholder="或自由描述问题，如：供应商交期经常延误，采购和仓储互相推">
            <button class="btn btn-p" data-act="knowledge.match">按痛点匹配</button>
            ${hasFilter ? '<button class="btn btn-g" data-act="knowledge.clear">清空</button>' : ''}
          </div>
          ${recoHtml}
        </section>

        <section class="card">
          <div class="between mb">
            <div><h3 style="margin:0">② 全部资源</h3>
              <div class="desc" style="margin:2px 0 0">知识库只放可参考、可改编的案例、模板、方法与工具指南；
                强制制度已移到制度中心</div></div>
            <div class="gap">
              <select class="sel sel-sm" data-act="knowledge.setStage">
                <option value="">全部阶段</option>${stageOptions}
              </select>
              <select class="sel sel-sm" data-act="knowledge.setSort">
                <option value="match"${k.sort === 'match' ? ' selected' : ''}>按匹配度</option>
                <option value="effect"${k.sort === 'effect' ? ' selected' : ''}>按使用效果</option>
                <option value="recent"${k.sort === 'recent' ? ' selected' : ''}>按最近更新</option>
              </select>
              ${statusOptions}
            </div>
          </div>
          <div class="kb-chips">${typeChips}</div>
          ${k.tool ? `<div class="note mb">只显示关联工具 <b>${esc(k.tool)}</b> 的知识。
            <button class="btn-sm" data-act="knowledge.clear">显示全部</button></div>` : ''}
          <div class="grid g3 kb-grid">${cards}</div>
          ${pager}
        </section>

        <section class="card kb-standard">
          <div class="between">
            <div><h3 style="margin:0">标准制度：已独立为制度中心</h3>
              <div class="desc" style="margin:2px 0 0">制度是强制遵守，知识是可参考。
                流程标准文件带生效状态、版本和适用范围。</div></div>
            <button class="btn btn-g" data-act="knowledge.goDocuments">去制度中心 →</button>
          </div>
        </section>
      </main>

      <aside class="kb-side">
        <div class="card">
          <h3>与五阶段工作流打通</h3>
          <div class="desc">在工作现场直接推送，不用离开工作台来翻库</div>
          <div class="kb-stage-list">${stageLinks}</div>
        </div>
        ${archiveHtml}
        ${effectHtml}
        <div class="card">
          <h3>每条知识的固定字段</h3>
          <ul class="kb-fields">
            <li>名称 / 类型 / 适用场景 / 不适用场景</li>
            <li>主张 / 输入条件 / 步骤要点 / 输出物</li>
            <li>使用证据（谁用过、效果如何）</li>
            <li>维护人 / 版本 / 最后验证日期</li>
            <li>关联工作流阶段 / 关联工具</li>
          </ul>
        </div>
        <div class="card">
          <h3>入库求真审核</h3>
          <div class="desc">主张 → 反证 → 证据 → 裁决；未通过审核不对外可见</div>
          <div class="kb-audit">
            <div>✓ <b>主张</b>：解决什么具体问题</div>
            <div>✓ <b>适用条件</b>：什么时候该用</div>
            <div>✓ <b>反证</b>：什么时候不该用</div>
            <div>✓ <b>证据</b>：谁用过、效果如何</div>
            <div>✓ <b>维护人</b>：谁负责复核</div>
          </div>
        </div>
      </aside>
    </div>`;
}

function recoCard(item, labels, statusLabels, scenarioNames) {
  const rate = item.effectiveness_rate === null || item.effectiveness_rate === undefined
    ? '暂无使用记录'
    : `有效率 ${num(item.effectiveness_rate, 0)}%（${item.effective_count}/${item.used_count}）`;
  return `
    <div class="kb-reco-item">
      <div class="kb-score ${item.match_level}">${num(item.score, 0)}</div>
      <div class="kb-reco-body">
        <div class="between">
          <b>${esc(item.title)}</b>
          <span>
            <span class="tag ${TYPE_TONE[item.type] || 't-blu'}">${esc(labels[item.type] || item.type)}</span>
            ${item.is_best_practice ? '<span class="tag t-grn">最佳实践</span>' : ''}
          </span>
        </div>
        <p>${esc(item.summary)}</p>
        <div class="kb-evidence">
          ${item.scenarios.map((scenario) =>
            `<span class="tag t-gry">${esc(scenario.name || scenarioNames[scenario.code] || '')}</span>`).join(' ')}
          <span>${rate}</span>
          <span>${esc(item.owner || '—')}</span>
          ${item.review_overdue ? '<span class="tag t-yel">待复核</span>' : ''}
        </div>
        ${item.matched_on && item.matched_on.length
          ? `<div class="tiny">命中：${item.matched_on.map(esc).join(' · ')}</div>` : ''}
      </div>
      <div class="kb-reco-act">
        <button class="btn-sm" data-act="knowledge.open" data-id="${item.id}">查看</button>
        ${state.knowledge.step ? `<button class="btn-sm" data-act="knowledge.applyStep"
          data-id="${item.id}">用到 ${esc(state.knowledge.step)}</button>` : ''}
        ${item.tool_code ? `<button class="btn-sm" data-act="knowledge.openTool"
          data-code="${esc(item.tool_code)}">关联工具</button>` : ''}
      </div>
    </div>`;
}

function cardHtml(item, labels, statusLabels, scenarioNames) {
  const rate = item.effectiveness_rate === null || item.effectiveness_rate === undefined
    ? '暂无使用记录'
    : `有效率 ${num(item.effectiveness_rate, 0)}%（${item.effective_count}/${item.used_count}）`;
  const date = item.last_verified_at ? '验证 ' + fmtDate(item.last_verified_at)
    : '更新 ' + fmtDate(item.updated_at || item.created_at);
  return `
    <button class="tool kb-card" type="button" data-act="knowledge.open" data-id="${item.id}">
      <div class="between">
        <span class="tag ${TYPE_TONE[item.type] || 't-blu'}">${esc(labels[item.type] || item.type)}</span>
        <span class="tag ${STATUS_TONE[item.status] || 't-gry'}">${
          esc(statusLabels[item.status] || item.status)}</span>
      </div>
      <h4>${esc(item.title)}</h4>
      <p>${esc(item.summary)}</p>
      <div class="kb-fit">${(item.scenario_names || []).map((name) =>
        `<span>${esc(name)}</span>`).join('') || '<span>未标注场景</span>'}</div>
      <div class="kb-evidence">
        <span>${rate}</span>
        ${item.is_best_practice ? '<span class="tag t-grn">最佳实践</span>' : ''}
        ${item.review_overdue ? '<span class="tag t-yel">待复核</span>' : ''}
      </div>
      <div class="kb-meta"><span>${esc(item.owner || '—')}</span><span>${esc(date)}</span></div>
    </button>`;
}

function syncKnowledgeUrl() {
  const k = state.knowledge;
  setUrlState('knowledge', {
    scenario: k.scenario,
    q: k.keyword,
    type: k.type,
    sort: k.sort,
    page: k.page > 1 ? k.page : '',
    stage: k.stage || '',
    step: k.step || '',
    status: k.status,
    tag: k.tag,
    tool: k.tool,
  }, { push: false });
}

function setK(key, value) {
  state.knowledge[key] = value;
  state.knowledge.page = 1;
  syncKnowledgeUrl();
  RENDERERS.knowledge();
}

function setKPage(page) {
  state.knowledge.page = Math.max(1, page);
  syncKnowledgeUrl();
  RENDERERS.knowledge();
}

function clearK() {
  state.knowledge = {
    type: '', sort: 'recent', keyword: '', tag: '', page: 1,
    scenario: '', stage: null, step: '', status: '', tool: '',
  };
  document.getElementById('searchInput').value = '';
  syncKnowledgeUrl();
  RENDERERS.knowledge();
}

/* -------------------------------------------------- 详情与使用证据 */

async function openKnowledge(id) {
  const gen = openModal('加载中…', skeleton(4), '', true);
  let item = null;
  let usage = [];
  let projects = { items: [] };
  try {
    [item, usage, projects] = await Promise.all([
      GET('/knowledge/' + id),
      GET('/knowledge/' + id + '/usage').catch(() => []),
      canWrite() ? GET('/projects?page_size=200').catch(() => ({ items: [] })) : { items: [] },
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
          <td class="tiny">${esc(row.note || '—')}</td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="muted">还没有使用记录。用过后回填，知识才会积累证据。</td></tr>';

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
        <thead><tr><th>时间</th><th>效果</th><th>使用人</th><th>说明</th></tr></thead>
        <tbody>${usageRows}</tbody>
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
          <input id="kuStep" value="${esc(state.knowledge.step || (item.step_nos && item.step_nos[0]) || '')}"
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
    if (state.view === 'knowledge') RENDERERS.knowledge();
  } catch (e) {
    toast(e.message, true);
  }
}

function openApplyStep(id) {
  const step = state.knowledge.step;
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
  const step = state.knowledge.step;
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
    if (state.view === 'knowledge') RENDERERS.knowledge();
  } catch (e) {
    toast(e.message, true);
  }
}

async function submitForReview(id) {
  try {
    await POST('/knowledge/' + id + '/submit', {});
    toast('已提交审核');
    closeModal();
    RENDERERS.knowledge();
  } catch (e) {
    toast(e.message, true);
  }
}

async function reviewKnowledge(id, decision) {
  try {
    await POST('/knowledge/' + id + '/review', { decision });
    toast(decision === 'APPROVE' ? '已通过审核' : '已驳回，退回草稿');
    closeModal();
    RENDERERS.knowledge();
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
    RENDERERS.knowledge();
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
    RENDERERS.knowledge();
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
    syncKnowledgeUrl();
    RENDERERS.knowledge();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderKnowledge };
