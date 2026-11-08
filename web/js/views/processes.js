/* 视图：流程清单
 *
 * 生产入口：只列已纳入目录的 L3，按编码/名称/Owner 过滤，
 * 点进去进流程资产工作台；不在这里讲方法论。
 */
import { esc } from '../core/format.js';
import { state } from '../core/state.js';
import { renderAsync, go } from '../core/router.js';
import { canManage, canWrite } from '../core/auth.js';
import { GET } from '../core/api.js';
import { on, viewEl } from '../core/ui.js';

const PS = () => (state.processes || (state.processes = { rows: [], keyword: '', only: 'all' }));

function l3Rows(rows) {
  return rows
    .filter((row) => row.level === 3 && !row.is_draft)
    .sort((left, right) => String(left.code).localeCompare(String(right.code)));
}

function matches(row, keyword, only) {
  if (only === 'no-owner' && (row.owner || row.owner_user_id)) return false;
  if (!keyword) return true;
  const text = `${row.code} ${row.name} ${row.owner || ''}`.toLowerCase();
  return text.includes(keyword.toLowerCase());
}

function rowsHtml(rows) {
  if (!rows.length) {
    return `<tr><td colspan="8" class="muted">没有匹配的 L3 流程。</td></tr>`;
  }
  return rows.map((row) => `<tr>
    <td><b>${esc(row.code)}</b></td>
    <td>${esc(row.name)}</td>
    <td>${esc(row.owner || '—')}${row.owner ? '' : ' <span class="tag t-yel">缺 Owner</span>'}</td>
    <td class="tiny">${esc(row.process_type_label || '—')}</td>
    <td class="num">${row.health_score ?? '—'}</td>
    <td class="num">${row.pain_score ?? '—'}</td>
    <td>${row.is_improvement_target ? '<span class="tag t-blu">改善对象</span>' : '—'}</td>
    <td class="gap">
      <button class="btn-sm" data-act="processes.open" data-id="${row.id}">打开</button>
      <button class="btn-sm" data-act="processes.design" data-id="${row.id}">设计器</button>
      ${canManage() ? `<button class="btn-sm" data-act="processes.newActivity"
        data-id="${row.id}">加 L4</button>` : ''}
      ${canWrite() ? `<button class="btn-sm" data-act="processes.project"
        data-id="${row.id}">立项</button>` : ''}
    </td></tr>`).join('');
}

function paint() {
  const rows = l3Rows(PS().rows);
  const visible = rows.filter((row) => matches(row, PS().keyword, PS().only));
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>流程</h2>
          <p class="desc">已纳入目录的 L3 流程；打开后进入资产、模型、证据与日志。</p>
        </div>
        <div class="gap">
          ${canManage() ? `<button class="btn btn-g" data-act="processes.new">新建流程</button>` : ''}
          <button class="btn btn-p" data-act="processes.framework">打开流程框架</button>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="between mb">
        <div class="gap">
          <input class="inp" id="psKeyword" data-act="processes.search"
            placeholder="搜索编码 / 名称 / Owner" value="${esc(PS().keyword)}">
          <select class="sel" id="psOnly" data-act="processes.only">
            <option value="all"${PS().only === 'all' ? ' selected' : ''}>全部</option>
            <option value="no-owner"${PS().only === 'no-owner' ? ' selected' : ''}>只看缺 Owner</option>
          </select>
        </div>
        <span class="tiny muted" id="psCount">${visible.length} / ${rows.length} 条</span>
      </div>
      <table class="tbl">
        <thead><tr><th>编码</th><th>名称</th><th>Owner</th><th>分类</th>
          <th>健康度</th><th>痛点</th><th>状态</th><th>操作</th></tr></thead>
        <tbody id="psRows">${rowsHtml(visible)}</tbody>
      </table>
    </div>`;
}

function refreshRows() {
  const rows = l3Rows(PS().rows);
  const visible = rows.filter((row) => matches(row, PS().keyword, PS().only));
  const body = document.getElementById('psRows');
  const count = document.getElementById('psCount');
  if (body) body.innerHTML = rowsHtml(visible);
  if (count) count.textContent = `${visible.length} / ${rows.length} 条`;
}

const renderProcesses = () => renderAsync(
  'processes',
  () => GET('/process-map/flat'),
  (rows) => {
    PS().rows = rows || [];
    paint();
  },
);

on('processes.search', (_, el) => {
  PS().keyword = el.value.trim();
  refreshRows();
});
on('processes.only', (_, el) => {
  PS().only = el.value;
  refreshRows();
});
on('processes.open', ({ id }) => go('asset', { params: { process: Number(id) } }));
on('processes.design', ({ id }) => go('designer', { params: { process: Number(id) } }));
on('processes.newActivity', ({ id }) => go('workbench', {
  params: { new: 'activity', process: Number(id) },
}));
on('processes.project', ({ id }) => go('projects', { params: { process: Number(id) } }));
on('processes.framework', () => go('map'));
on('processes.new', () => go('workbench', { params: { new: 'process' } }));

export { renderProcesses };
