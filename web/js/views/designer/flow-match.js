/* 出边匹配条件：纯 HTML/解析辅助，无画布状态。 */

import { esc } from '../../core/format.js';

export const FLOW_MATCH_OPS = [
  { v: 'eq', l: '等于' },
  { v: 'ne', l: '不等于' },
  { v: 'gt', l: '大于' },
  { v: 'gte', l: '大于等于' },
  { v: 'lt', l: '小于' },
  { v: 'lte', l: '小于等于' },
  { v: 'in', l: '属于' },
  { v: 'contains', l: '包含' },
  { v: 'truthy', l: '为真' },
  { v: 'falsy', l: '为假' },
];

export function flowMatchOpOptions(selected) {
  return FLOW_MATCH_OPS.map((o) =>
    `<option value="${o.v}"${o.v === selected ? ' selected' : ''}>${o.l}</option>`).join('');
}

export function parseFlowMatch(bo) {
  const raw = bo.$attrs && bo.$attrs['pms:match'];
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

export function flowMatchRowHtml(cond) {
  const c = cond || {};
  const op = c.op || 'eq';
  const needsVal = op !== 'truthy' && op !== 'falsy';
  const val = Array.isArray(c.value) ? c.value.join('，')
    : (c.value === null || c.value === undefined ? '' : String(c.value));
  return `<tr class="bp-match-row">
    <td><input class="bp-match-field" value="${esc(c.field || '')}" placeholder="approved"></td>
    <td><select class="sel bp-match-op" data-act="designer.flowMatchOp">${flowMatchOpOptions(op)}</select></td>
    <td><input class="bp-match-value" value="${esc(val)}" placeholder="是"${
      needsVal ? '' : ' disabled'}></td>
    <td><button type="button" class="btn-sm" data-act="designer.removeFlowMatch">删除</button></td>
  </tr>`;
}

export function collectFlowMatchFromDom() {
  const rows = document.querySelectorAll('#bpMatchBody tr.bp-match-row');
  const out = [];
  for (const row of rows) {
    const field = (row.querySelector('.bp-match-field')?.value || '').trim();
    const op = row.querySelector('.bp-match-op')?.value || 'eq';
    const raw = (row.querySelector('.bp-match-value')?.value || '').trim();
    if (!field && !raw) continue;
    if (!field) return { error: '匹配条件缺少字段引用名' };
    const item = { field, op, value: null };
    if (op !== 'truthy' && op !== 'falsy') {
      if (op === 'in') {
        item.value = raw.split(/[,，、;；|]/).map((s) => s.trim()).filter(Boolean);
        if (!item.value.length) return { error: `字段「${field}」请填写属于值` };
      } else {
        item.value = raw;
      }
    }
    out.push(item);
  }
  return { conditions: out };
}
