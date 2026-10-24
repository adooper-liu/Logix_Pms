/* 视图：knowledge */
import { esc, fmtDate, KN_COLOR, KN_LABEL, methodTag, skeleton } from '../core/format.js';
import { toast, openModal, closeModal, modalAlive, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go } from '../core/router.js';
import { AUTH, canManage } from '../core/auth.js';
import { GET, POST } from '../core/api.js';
import { metricHelp } from '../core/metrics.js';
import { actions } from '../core/actions.js';

/* ============================================================ 8. 流程知识库 */

/* 事件委托：模板只写 data-act，不再把处理函数挂到 window。
 * 同名动作在 core/ui.js 的 on() 注册时会被拒绝，避免再次出现全局覆盖。 */
on('knowledge.open', ({ id }) => openKnowledge(Number(id)));
on('knowledge.setType', ({ value }) => setK('type', value));
on('knowledge.setSort', (_data, el) => setK('sort', el.value));
on('knowledge.setTag', (_data, el) => setK('tag', el.value));
on('knowledge.clear', () => clearK());
on('knowledge.page', ({ page }) => setKPage(Number(page)));
on('knowledge.match', () => kbMatch());
on('knowledge.new', () => newKnowledgeModal());
on('knowledge.goWorkflow', () => go('workflow'));
on('knowledge.close', () => closeModal());
on('knowledge.openTool', ({ code }) => {
  closeModal();
  actions['toolbox.openTool'](code);
});
on('knowledge.submit', () => submitKnowledge());

const renderKnowledge = () => {
  const k = state.knowledge;
  const qs = [];
  if (k.type) qs.push('type=' + k.type);
  if (k.tag) qs.push('tag=' + encodeURIComponent(k.tag));
  if (k.keyword) qs.push('keyword=' + encodeURIComponent(k.keyword));
  qs.push('sort=' + k.sort, 'page=' + (k.page || 1), 'page_size=50');

  return renderAsync('knowledge',
    () => Promise.all([GET('/knowledge?' + qs.join('&')), GET('/knowledge/meta/tags')])
      .then(([page, tags]) => ({ page, tags })),
    (d) => {
      const cards = d.page.items.map((it) => `
        <button class="tool" type="button" data-act="knowledge.open" data-id="${it.id}">
          <div class="ico">${it.type === 'CASE' ? '📄' : it.type === 'TEMPLATE' ? '📋' : '💡'}</div>
          <h4>${esc(it.title)}</h4>
          <p>${esc(it.summary)}</p>
          <div class="between" style="margin-top:10px">
            <span>
              <span class="tag ${KN_COLOR[it.type] || 't-blu'}">${KN_LABEL[it.type] || it.type}</span>
              ${it.methodology ? methodTag(it.methodology, state.meta.methodology[it.methodology]) : ''}
            </span>
            <span class="tiny">⬇ ${it.download_count} 次 · ${fmtDate(it.created_at)}</span>
          </div>
        </button>`).join('') || '<div class="empty">没有符合条件的条目</div>';

      const typeTab = (v, label) =>
        '<button class="' + (k.type === v ? 'on' : '') +
        '" data-act="knowledge.setType" data-value="' + v + '">' + label + '</button>';
      const pageSize = d.page.page_size || 50;
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

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between mb">
            <div><h2>流程知识库（${d.page.total} 条）<span class="module-badge">经验沉淀 · 复用</span></h2>
              <div class="desc" style="margin:0">方法论模板、案例复盘、最佳实践沉淀与复用</div></div>
            <div class="gap">
              <a class="link-btn" data-act="knowledge.goWorkflow">方法手册 →</a>
              ${canManage() ? '<button class="btn btn-p" data-act="knowledge.new">+ 新建条目</button>' : ''}
              <select class="sel" data-act="knowledge.setSort">
                <option value="recent"${k.sort === 'recent' ? ' selected' : ''}>按时间</option>
                <option value="hot"${k.sort === 'hot' ? ' selected' : ''}>按热度</option>
              </select>
              <select class="sel" data-act="knowledge.setTag">
                <option value="">全部标签</option>
                ${d.tags.tags.map((t) => '<option value="' + esc(t.tag) + '"' +
                  (k.tag === t.tag ? ' selected' : '') + '>' + esc(t.tag) + '（' + t.count + '）</option>').join('')}
              </select>
              ${(k.type || k.tag || k.keyword)
                ? '<button class="btn-sm" data-act="knowledge.clear">清空筛选</button>' : ''}
            </div>
          </div>
          <div class="tabs" style="margin-bottom:0;max-width:520px">
            ${typeTab('', '全部')}${typeTab('CASE', '案例')}${typeTab('TEMPLATE', '模板')}
            ${typeTab('BEST_PRACTICE', '最佳实践')}${typeTab('STANDARD', '标准制度')}
          </div>
        </div>

        <div class="grid g3">${cards}</div>
        ${pager}

        <div class="card">
          <h2>按问题找工具</h2>
          <div class="desc">知识库解决「怎么做」，工具箱解决「用什么做」——这里把两者连起来</div>
          <div class="gap mb" style="flex-wrap:wrap">
            <input id="kbQ" class="sel" style="flex:1;min-width:260px"
              placeholder="描述你遇到的问题，如：跨部门互相推诿">
            <button class="btn btn-p" id="kbQBtn" data-act="knowledge.match">找工具</button>
          </div>
          <div id="kbMatch"></div>
        </div>`;
    });
};

function setK(key, value) {
  state.knowledge[key] = value;
  state.knowledge.page = 1;
  RENDERERS.knowledge();
}
function setKPage(page) {
  state.knowledge.page = Math.max(1, page);
  RENDERERS.knowledge();
}
function clearK() {
  state.knowledge = { type: '', sort: state.knowledge.sort, keyword: '', tag: '', page: 1 };
  document.getElementById('searchInput').value = '';
  RENDERERS.knowledge();
}

async function openKnowledge(id) {
  const gen = openModal('加载中…', skeleton(4));
  try {
    const it = await GET('/knowledge/' + id);
    if (!modalAlive(gen)) return;
    openModal(it.title, `
      <div class="mb">
        <span class="tag ${KN_COLOR[it.type] || 't-blu'}">${KN_LABEL[it.type] || it.type}</span>
        ${it.methodology ? methodTag(it.methodology, state.meta.methodology[it.methodology]) : ''}
        ${(it.tags || []).map((t) => '<span class="tag t-gry">' + esc(t) + '</span>').join(' ')}
      </div>
      <div class="note mb">${esc(it.summary)}</div>
      <div style="white-space:pre-wrap;font-size:13px;line-height:1.85;color:var(--text)">${esc(it.content)}</div>
      <div class="tiny mt">作者：${esc(it.author || '—')} · ${fmtDate(it.created_at)}
        · ${metricHelp('download_count', '查阅')} ${it.download_count} 次${it.tool_code ? ' · 关联工具 ' + esc(it.tool_code) : ''}</div>`,
      `<button class="btn btn-g" data-act="knowledge.close">关闭</button>
       ${it.tool_code ? `<button class="btn btn-p" data-act="knowledge.openTool"
         data-code="${esc(it.tool_code)}">查看关联工具</button>` : ''}`, true);

    // 查阅计数不阻塞阅读，放在内容渲染之后异步回写
    POST('/knowledge/' + id + '/read', { increment: 1 })
      .then(() => { if (state.view === 'knowledge') RENDERERS.knowledge(); })
      .catch(() => { /* 计数失败不影响阅读 */ });
  } catch (e) {
    if (modalAlive(gen)) openModal('加载失败', '<div class="errbar"><div>' + esc(e.message) + '</div></div>');
  }
}

function newKnowledgeModal() {
  openModal('新建知识条目', `
    <div class="field"><label>标题 *</label>
      <input id="nkTitle" placeholder="如：供应商对账流程复盘"></div>
    <div class="row3">
      <div class="field"><label>类型</label>
        <select id="nkType">
          <option value="CASE">案例</option><option value="TEMPLATE">模板</option>
          <option value="BEST_PRACTICE">最佳实践</option><option value="STANDARD">标准制度</option>
        </select></div>
      <div class="field"><label>方法论</label>
        <select id="nkMethod">
          <option value="">不限定</option><option value="BPR">BPR</option>
          <option value="BPI">BPI</option><option value="LEAN">精益</option>
          <option value="HYBRID">混合</option>
        </select></div>
      <div class="field"><label>关联工具编码</label>
        <input id="nkTool" placeholder="如 RACI（可空）"></div>
    </div>
    <div class="field"><label>标签</label>
      <input id="nkTags" placeholder="用逗号分隔，如：案例, 采购, 周期压缩">
      <div class="hint">标签存关联表，筛选走 SQL，不会再出现「总数随分页变化」的问题</div></div>
    <div class="field"><label>摘要 *</label>
      <input id="nkSummary" placeholder="一句话说明这篇解决什么问题"></div>
    <div class="field"><label>正文 *</label>
      <textarea id="nkContent" style="min-height:160px"
        placeholder="背景 / 方案 / 过程 / 结果 / 踩坑 / 可复用点"></textarea></div>
    <div class="field"><label>作者</label><input id="nkAuthor" placeholder="默认填当前用户"></div>`,
    `<button class="btn btn-g" data-act="knowledge.close">取消</button>
     <button class="btn btn-p" data-act="knowledge.submit">保存</button>`, true);
}

async function submitKnowledge() {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const title = val('nkTitle').trim();
  const summary = val('nkSummary').trim();
  const content = val('nkContent').trim();
  if (!title) return toast('请填写标题', true);
  if (!summary) return toast('请填写摘要', true);
  if (!content) return toast('请填写正文', true);

  const tags = val('nkTags').split(/[,，、\s]+/).map((t) => t.trim()).filter(Boolean);

  try {
    await POST('/knowledge', {
      title,
      type: val('nkType'),
      methodology: val('nkMethod') || null,
      tags,
      summary,
      content,
      tool_code: val('nkTool').trim() || null,
      author: val('nkAuthor').trim() || (AUTH.user ? AUTH.user.display_name : null),
    });
    closeModal();
    toast('知识条目已保存');
    RENDERERS.knowledge();
  } catch (e) {
    toast(e.message, true);
  }
}

async function kbMatch() {
  const q = document.getElementById('kbQ').value.trim();
  if (q.length < 2) return toast('请至少输入 2 个字', true);
  const box = document.getElementById('kbMatch');
  box.innerHTML = skeleton(2);
  try {
    const r = await POST('/tools/match', { problem: q });
    box.innerHTML = r.hits.length
      ? '<table class="tbl"><thead><tr><th>推荐工具</th><th>解决什么问题</th><th>所属阶段</th><th></th></tr></thead>' +
        '<tbody>' + r.hits.slice(0, 5).map((h) => `
          <tr><td><b>${esc(h.tool.name)}</b><div class="tiny">命中：${
            h.matched_on.map(esc).join('、') || '—'}</div></td>
            <td class="muted">${esc(h.tool.purpose)}</td>
            <td><span class="tag t-blu">阶段${h.tool.stage_no}</span></td>
            <td><button class="btn-sm" data-act="knowledge.openTool"
              data-code="${esc(h.tool.code)}">查看</button></td>
          </tr>`).join('') + '</tbody></table>'
      : '<div class="note">没有匹配到工具，换一种说法试试。</div>';
  } catch (e) {
    box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
  }
}


export { renderKnowledge };
