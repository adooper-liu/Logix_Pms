/* 方法论匹配结果的纯渲染组件：workflow 手册与立项向导共用。
 *
 * 放在 views/shared/ 而不是某个视图里，避免 projects → workflow 的跨视图 import。
 * 工具链按钮通过 toolbox.open 委托打开工具详情。
 */
import { esc, CAT_ICON } from '../../core/format.js';

export function renderRecommendation(r) {
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
      ${r.recommended_tools.map((t) => '<button type="button" class="tag ' +
        ({ DIAGNOSE: 't-blu', DESIGN: 't-red', DEPLOY: 't-yel', MONITOR: 't-grn' }[t.category] || 't-blu') +
        ' tag-button" data-act="toolbox.open" data-code="' + esc(t.code) + '">' +
        (CAT_ICON[t.category] || '') + ' ' + esc(t.name) + '</button>').join('')}
    </div>

    <h3 class="mt">风险提示</h3>
    <div class="${r.risks.length && r.risks[0].indexOf('未识别') < 0 ? 'warnbox' : 'note'}">
      ${r.risks.map((x) => '· ' + esc(x)).join('<br>')}
    </div>`;
}
