/* 视图：toolbox */
import { esc, num, CAT_ICON, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, go, RENDERERS } from '../core/router.js';
import { GET, POST } from '../core/api.js';

/* ============================================================ 5. 方法论工具箱 */

const renderToolbox = () => renderAsync('toolbox',
  () => GET('/tools/grouped'),
  (groups) => {
    state.toolGroups = groups;
    const active = state.toolboxCat || (groups[0] && groups[0].category);
    state.toolboxCat = active;
    const total = groups.reduce((a, g) => a + g.count, 0);

    const tabs = groups.map((g) => `
      <button class="${g.category === active ? 'on' : ''}"
        onclick="state.toolboxCat='${g.category}';RENDERERS.toolbox()">
        ${CAT_ICON[g.category]} ${esc(g.label)}（${g.count}）
      </button>`).join('');

    const g = groups.find((x) => x.category === active) || { tools: [] };
    const kw = state.toolboxKeyword || '';
    const tools = kw
      ? g.tools.filter((t) => (t.name + t.code + t.purpose + (t.alias || '')).toLowerCase()
          .includes(kw.toLowerCase()))
      : g.tools;

    const cards = tools.map((t) => `
      <div class="tool" onclick="openToolByCode('${t.code}')">
        <div class="ico">${CAT_ICON[t.category] || '⚒'}</div>
        <h4>${esc(t.name)}</h4>
        <p>${esc(t.purpose)}</p>
        <div class="between" style="margin-top:8px">
          <span class="tag ${{ DIAGNOSE: 't-blu', DESIGN: 't-red', DEPLOY: 't-yel', MONITOR: 't-grn' }[t.category]}">
            阶段${t.stage_no}</span>
          <span class="tiny">${t.steps.length} 步</span>
        </div>
      </div>`).join('') || '<div class="empty">没有匹配的工具</div>';

    viewEl().innerHTML = `
      <div class="card">
        <div class="between mb">
          <div><h2 style="margin:0">方法论工具箱（${total} 个工具）</h2>
            <div class="desc" style="margin:0">按用途分类，点击卡片查看适用场景、5 步标准操作与常见误用</div></div>
        </div>
        <div class="tabs" style="margin-bottom:0">${tabs}</div>
      </div>

      <div class="card">
        <h2>按问题找工具</h2>
        <div class="desc">用大白话描述你遇到的问题，系统匹配最合适的工具（关键词 + 文本双重打分）</div>
        <div class="gap mb" style="flex-wrap:wrap">
          <input id="toolQ" class="sel" style="flex:1;min-width:260px"
            placeholder="如：审批太多、周期太长；跨部门互相推诿；方案推不动"
            value="${esc(state.toolQuery || '')}">
          <button class="btn btn-p" id="toolQBtn" onclick="matchTools()">匹配</button>
        </div>
        <div class="gap mb" id="toolChips" style="flex-wrap:wrap">
          ${['审批太多，周期太长', '跨部门互相推诿、权责不清', '方案推行遇到阻力',
             '优化完又退回老样子', '不知道问题出在哪个环节', '返工率高'].map((q) =>
            '<span class="tag t-gry" style="cursor:pointer" onclick="quickMatch(\'' + q + '\')">' + esc(q) + '</span>'
          ).join('')}
        </div>
        <div id="toolMatchResult"></div>
      </div>

      <div class="grid g3">${cards}</div>`;

    if (state.toolMatch) paintToolMatch(state.toolMatch);
  });

function quickMatch(q) {
  document.getElementById('toolQ').value = q;
  matchTools();
}

async function matchTools() {
  const q = document.getElementById('toolQ').value.trim();
  if (q.length < 2) return toast('请至少输入 2 个字', true);
  state.toolQuery = q;
  const box = document.getElementById('toolMatchResult');
  box.innerHTML = skeleton(2);
  try {
    state.toolMatch = await POST('/tools/match', { problem: q });
    paintToolMatch(state.toolMatch);
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}

function paintToolMatch(r) {
  const box = document.getElementById('toolMatchResult');
  if (!box) return;
  if (!r.hits.length) {
    box.innerHTML = '<div class="note">没有匹配到工具。试着换一种说法，' +
      '或者直接在下方分类里浏览。</div>';
    return;
  }
  box.innerHTML = `
    <table class="tbl">
      <thead><tr><th>工具</th><th>解决什么问题</th><th>命中关键词</th><th>匹配分</th><th></th></tr></thead>
      <tbody>${r.hits.map((h) => `
        <tr><td><b>${esc(h.tool.name)}</b><div class="tiny">${esc(h.tool.code)} · 阶段${h.tool.stage_no}</div></td>
          <td class="muted">${esc(h.tool.purpose)}</td>
          <td>${h.matched_on.map((m) => '<span class="tag t-gry">' + esc(m) + '</span> ').join('') || '—'}</td>
          <td><b>${num(h.score, 1)}</b></td>
          <td><button class="btn-sm" onclick="openToolByCode('${h.tool.code}')">查看</button></td>
        </tr>`).join('')}
      </tbody>
    </table>
    <div class="note mt">${esc(r.hint)}</div>`;
}

async function openToolByCode(code) {
  const gen = openModal('加载中…', skeleton(4));
  try {
    const t = await GET('/tools/' + code);
    if (!modalAlive(gen)) return;
    paintTool(t);
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

function paintTool(t) {
  const catLabel = { DIAGNOSE: '诊断工具', DESIGN: '设计工具', DEPLOY: '落地工具', MONITOR: '监控工具' };
  openModal(t.name + (t.alias ? ' · ' + t.alias : ''), `
    <div style="margin-bottom:14px;font-size:13px;color:#3d4759">${esc(t.purpose)}</div>
    <div class="row3 mb">
      <div class="kpi" style="padding:12px 14px"><div class="num" style="font-size:16px">
        ${CAT_ICON[t.category] || ''} ${esc(catLabel[t.category] || t.category)}</div>
        <div class="lab">用途分类</div></div>
      <div class="kpi" style="padding:12px 14px"><div class="num" style="font-size:16px">
        阶段${t.stage_no}</div><div class="lab">主要适用阶段</div></div>
      <div class="kpi" style="padding:12px 14px"><div class="num" style="font-size:16px">
        ${t.steps.length} 步</div><div class="lab">标准操作步骤</div></div>
    </div>

    <h3>什么场景选它</h3>
    <div class="note mb">${esc(t.when_to_use)}</div>

    <h3>标准操作步骤</h3>
    <ol style="padding-left:20px;font-size:13px;line-height:1.95;color:#3d4759;margin-bottom:14px">
      ${t.steps.map((s) => '<li>' + esc(s) + '</li>').join('')}
    </ol>

    ${t.template_ref ? '<h3>模板 / 工具指引</h3><div class="note mb">' + esc(t.template_ref) + '</div>' : ''}
    ${t.pitfalls ? '<h3>常见误用</h3><div class="warnbox">' + esc(t.pitfalls) + '</div>' : ''}`,
    `<button class="btn btn-g" onclick="closeModal()">关闭</button>
     <button class="btn btn-p" onclick="closeModal();go('workflow')">看它在哪一步用</button>`,
    true);
}


export { renderToolbox, matchTools, openToolByCode, paintTool, paintToolMatch, quickMatch };
