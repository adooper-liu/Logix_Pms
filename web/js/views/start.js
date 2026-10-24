/* 视图：开始使用
 *
 * 九步启动路径：每一步都显示目标、输入、在系统里做什么、输出与退出条件；
 * readiness 由后端按真实数据计算，不靠人工打勾。
 */

import { esc } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { renderAsync, go } from '../core/router.js';
import { GET } from '../core/api.js';

const STATUS_TONE = {
  READY: 't-grn',
  IN_PROGRESS: 't-yel',
  NOT_STARTED: 't-gry',
};

const EVIDENCE_LABELS = {
  l3_with_owner: '有 Owner 的 L3',
  governance_roles: '治理角色',
  objectives: '目标',
  linked_objectives: '已承接目标',
  l1: 'L1',
  l2: 'L2',
  l3: 'L3',
  benchmark_maps: 'PCF 映射',
  positions: '岗位',
  raci_matters: 'RACI 事项',
  invalid_processes: 'RACI 不完整流程',
  documents: '标准文件',
  effective_documents: '已生效文件',
  l3_published: '已发布 L3 模型',
  forms: '表单',
  rules: '规则',
  node_tools: '工具绑定',
  verified_standards: '已验证工时',
  capacity_rows: '产能记录',
  actual_worklogs: '实际工时记录',
  kpi_cards: '完整 KPI 卡',
  kpi_records: 'KPI 数据点',
  red_yellow: '红/黄 KPI',
  improvement_projects: '改善项目',
  applied_changes: '已应用变更',
  open_findings: '未闭环治理待办',
  knowledge_items: '知识条目',
  kpi_records_30d: '近 30 天数据',
};

on('start.go', ({ view }) => go(view));

const renderStart = () => {
  renderAsync(
    'start',
    () => GET('/start/status'),
    (data) => {
      const next = data.steps.find((step) => step.key === data.next_step) || null;
      const nextCard = next
        ? `<div class="card" style="border-left:4px solid var(--brand)">
            <div class="between mb">
              <div><h3 style="margin:0">下一步 · ${esc(next.title)}</h3>
                <div class="desc" style="margin:2px 0 0">${esc(next.goal)}</div></div>
              <span class="tag t-blu">${esc(next.status_label)}</span>
            </div>
            <div class="tiny mb"><b>输入：</b>${esc(next.input)}</div>
            <div class="tiny mb"><b>输出：</b>${esc(next.output)}</div>
            <div class="tiny mb"><b>退出条件：</b>${esc(next.exit_criteria)}</div>
            ${next.next_hint ? `<div class="note mb">${esc(next.next_hint)}</div>` : ''}
            <div class="gap">
              ${next.actions.map((action) => `<button class="btn btn-p"
                data-act="start.go" data-view="${esc(action.view)}"
                title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
            </div>
          </div>`
        : `<div class="card"><div class="note">九步已全部就绪，可以进入运营监控与流程卡持续运行。</div></div>`;

      const stepCards = data.steps.map((step) => {
        const evidence = Object.entries(step.evidence || {})
          .map(([key, value]) => `<span class="tag t-gry">${
            esc(EVIDENCE_LABELS[key] || key)} ${value}</span>`).join(' ');
        return `
          <div class="card">
            <div class="between mb">
              <div><h3 style="margin:0">${esc(step.title)}
                ${step.key === data.next_step ? '<span class="tag t-blu">下一步</span>' : ''}</h3>
                <div class="desc" style="margin:2px 0 0">${esc(step.goal)}</div></div>
              <span class="tag ${STATUS_TONE[step.status] || 't-gry'}">${esc(step.status_label)}</span>
            </div>
            <div class="gap mb">${evidence || '<span class="tiny muted">暂无数据</span>'}</div>
            <details class="note">
              <summary>输入 / 输出 / 退出条件</summary>
              <div class="tiny mt"><b>输入：</b>${esc(step.input)}</div>
              <div class="tiny"><b>输出：</b>${esc(step.output)}</div>
              <div class="tiny"><b>退出条件：</b>${esc(step.exit_criteria)}</div>
              ${step.next_hint ? `<div class="tiny mt muted">${esc(step.next_hint)}</div>` : ''}
            </details>
            <div class="gap mt">
              ${step.actions.map((action) => `<button class="btn-sm"
                data-act="start.go" data-view="${esc(action.view)}"
                title="${esc(action.hint || '')}">${esc(action.label)}</button>`).join('')}
            </div>
          </div>`;
      }).join('');

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div><h2>开始使用<span class="module-badge">九步启动路径</span></h2>
              <div class="desc">从范围与授权到改善复制，按顺序推进；每步状态由现有数据自动计算</div></div>
            <div class="gap">
              <span class="tag ${data.readiness_pct >= 100 ? 't-grn' : 't-yel'}">
                已完成 ${data.ready_count}/${data.total} 步 · ${data.readiness_pct}%</span>
              <button class="btn btn-g" data-act="start.go" data-view="map">流程地图</button>
            </div>
          </div>
          <div class="pipe" style="margin-top:10px">
            <i class="fill-ok" style="width:${data.readiness_pct}%"></i>
          </div>
        </div>
        ${nextCard}
        <div class="grid g2">${stepCards}</div>`;
    },
  );
};

export { renderStart };
