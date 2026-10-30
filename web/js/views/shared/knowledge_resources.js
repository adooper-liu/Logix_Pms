/* 知识资源卡片与区块 —— 方法论工具箱和知识库 action 共用。
 *
 * 放在 views/shared/ 下，避免视图之间互相 import（结构测试会拦截）。
 */
import { esc, fmtDate, num } from '../../core/format.js';
import { state } from '../../core/state.js';
import { setUrlState } from '../../core/router.js';
import { canManage } from '../../core/auth.js';

export const STATUS_TONE = {
  DRAFT: 't-gry',
  IN_REVIEW: 't-yel',
  PUBLISHED: 't-blu',
  VERIFIED: 't-grn',
  ARCHIVED: 't-gry',
};
export const TYPE_TONE = {
  CASE: 't-red',
  TEMPLATE: 't-blu',
  METHOD: 't-pur',
  TOOL: 't-yel',
  BEST_PRACTICE: 't-pur',
  STANDARD: 't-gry',
};
export const SCENARIO_ICON = {
  FLOW: '🔀', CYCLE: '⏱️', ERROR: '⚠️', RACI: '👤', COST: '💰', STANDARD: '📐',
};

/** 工具箱（工具 + 知识资源）的 URL 同步；改状态的动作必须先 sync 再 render。 */
export function syncToolboxUrl() {
  const tb = state.toolbox;
  const k = state.knowledge;
  setUrlState('toolbox', {
    q: tb.q,
    scenario: tb.scenario,
    category: (tb.categories || []).join(','),
    stage: tb.stage || '',
    step: tb.step || '',
    sort: tb.sort,
    open: tb.open || '',
    status: tb.status || '',
    section: tb.section || 'none',
    nav: tb.navSection || 'none',
    rtype: k.type || '',
    rsort: k.sort || '',
    rstatus: k.status || '',
    rpage: k.page > 1 ? k.page : '',
    rtool: k.tool || '',
  }, { push: false });
}

export function resourceCard(item, labels, statusLabels, scenarioNames) {
  return cardHtml(item, labels, statusLabels, scenarioNames);
}

export function relatedResourceCard(item, labels, statusLabels, scenarioNames) {
  return recoCard(item, labels, statusLabels, scenarioNames);
}

export function resourcePagerHtml(page, pageSize = 24) {
  const total = page.total || 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, page.page || 1), pages);
  if (pages <= 1) return '';
  return `
    <div class="pager">
      <button class="btn-sm" ${current <= 1 ? 'disabled' : ''}
        data-act="knowledge.page" data-page="${current - 1}">上一页</button>
      <span class="tiny">第 ${current} / ${pages} 页 · 共 ${total} 条</span>
      <button class="btn-sm" ${current >= pages ? 'disabled' : ''}
        data-act="knowledge.page" data-page="${current + 1}">下一页</button>
    </div>`;
}

export function resourceQuery(toolbox = state.toolbox) {
  const k = state.knowledge;
  const qs = [];
  if (k.type && k.type !== 'TOOL') qs.push('type=' + k.type);
  if (k.tag) qs.push('tag=' + encodeURIComponent(k.tag));
  if (toolbox.q) qs.push('keyword=' + encodeURIComponent(toolbox.q));
  if (toolbox.scenario) qs.push('scenario=' + encodeURIComponent(toolbox.scenario));
  if (toolbox.stage) qs.push('stage_no=' + toolbox.stage);
  if (toolbox.step) qs.push('step_no=' + encodeURIComponent(toolbox.step));
  if (k.status) qs.push('status=' + k.status);
  if (k.tool) qs.push('tool_code=' + encodeURIComponent(k.tool));
  qs.push('sort=' + k.sort, 'page=' + (k.page || 1), 'page_size=12');
  return '/knowledge?' + qs.join('&');
}

export function resourceManagerCards({
  archiveCandidates = [], effectStats = null, standardCandidates = [],
} = {}) {
  if (!canManage()) return '';
  const archiveHtml = `
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
    </div>`;

  const effectHtml = effectStats ? `
    <div class="card">
      <h3>使用效果</h3>
      <div class="desc">只统计有使用证据的公开知识；按使用人回填的效果汇总</div>
      <div class="grid g2 stat-row">
        <div class="kpi stat"><div class="num">${effectStats.usage_total}</div>
          <div class="lab">累计使用</div></div>
        <div class="kpi stat"><div class="num">${
          effectStats.effectiveness_rate === null || effectStats.effectiveness_rate === undefined
            ? '—' : num(effectStats.effectiveness_rate, 0) + '<small>%</small>'}</div>
          <div class="lab">有效率 · 有效 ${effectStats.effective_count}
            / 部分 ${effectStats.partial_count} / 无效 ${effectStats.ineffective_count}</div></div>
      </div>
      ${effectStats.by_type.length ? `<div class="kb-eff-types">${
        effectStats.by_type.map((row) => `
          <div class="kb-eff-row">
            <span>${esc(row.type_label)}</span>
            <span>${row.used_count} 次 · 有效率 ${
              row.effectiveness_rate === null ? '—' : num(row.effectiveness_rate, 0) + '%'}</span>
          </div>`).join('')}</div>` : ''}
      ${effectStats.top_items.length ? `<div class="kb-eff-top">
        <div class="tiny muted">使用最多</div>
        ${effectStats.top_items.slice(0, 3).map((item) => `
          <button class="kb-eff-item" data-act="knowledge.open" data-id="${item.id}">
            <b>${esc(item.title)}</b>
            <span>${item.used_count} 次 · 有效率 ${
              item.effectiveness_rate === null ? '—' : num(item.effectiveness_rate, 0) + '%'}</span>
          </button>`).join('')}</div>`
        : '<div class="tiny muted">还没有使用记录。用过后回填，统计才会积累。</div>'}
    </div>` : '';

  const standardHtml = standardCandidates.length ? `
    <div class="card">
      <h3>旧制度迁移</h3>
      <div class="desc">这些条目仍是 STANDARD 类型且已归档；确认归属流程后
        可一键生成制度中心的标准文件草稿。</div>
      <div class="kb-archive-list">${standardCandidates.map((item) => `
        <div class="kb-archive-item">
          <div><b>${esc(item.title)}</b>
            <div class="tiny">${esc(item.summary || '')}</div></div>
          <button class="btn-sm" data-act="knowledge.migrateStandard"
            data-id="${item.id}">迁移</button>
        </div>`).join('')}</div>
    </div>` : '';

  return archiveHtml + effectHtml + standardHtml;
}

function recoCard(item, labels, statusLabels, scenarioNames) {
  const isTool = item.kind === 'tool';
  const rate = item.effectiveness_rate === null || item.effectiveness_rate === undefined
    ? '暂无使用记录'
    : `有效率 ${num(item.effectiveness_rate, 0)}%（${item.effective_count}/${item.used_count}）`;
  const step = state.toolbox.step || state.knowledge.step;
  const openAction = isTool
    ? `<button class="btn-sm" data-act="knowledge.openTool"
        data-code="${esc(item.code)}">查看工具</button>`
    : `<button class="btn-sm" data-act="knowledge.open" data-id="${item.id}">查看</button>`;
  const applyAction = step
    ? (isTool
      ? `<button class="btn-sm" data-act="knowledge.applyToolStep"
          data-code="${esc(item.code)}">用到 ${esc(step)}</button>`
      : `<button class="btn-sm" data-act="knowledge.applyStep"
          data-id="${item.id}">用到 ${esc(step)}</button>`)
    : '';
  return `
    <div class="kb-reco-item">
      <div class="kb-score ${item.match_level}">${num(item.score, 0)}</div>
      <div class="kb-reco-body">
        <div class="between">
          <b>${esc(item.title)}</b>
          <span>
            <span class="tag ${TYPE_TONE[item.type] || 't-blu'}">${
              esc(isTool ? '工具' : (labels[item.type] || item.type))}</span>
            ${item.code ? `<span class="tiny">${esc(item.code)}</span>` : ''}
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
        ${openAction}
        ${applyAction}
        ${!isTool && item.tool_code ? `<button class="btn-sm" data-act="knowledge.openTool"
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
