/* 格式化与展示辅助：纯函数，不碰 DOM，也不发请求。
 *
 * 视图模块里拼 HTML 用到的转义、数值格式、标签、进度条都在这里，
 * 保证同一类数据在整个界面上长得一致。
 */

export function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/** 数值保留 n 位后去掉多余的 0：12.30 → 12.3，12.00 → 12 */
export function num(v, digits) {
  if (v === null || v === undefined || v === '') return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  const d = digits === undefined ? 1 : digits;
  return String(parseFloat(n.toFixed(d)));
}

export function pct(v, digits) {
  if (v === null || v === undefined) return '—';
  return num(v, digits === undefined ? 1 : digits) + '%';
}

/** 分钟 → 人类可读的工时表述 */
export function dur(minutes) {
  const m = Number(minutes) || 0;
  if (m < 60) return num(m, 0) + ' 分钟';
  if (m < 60 * 24) return num(m / 60, 1) + ' 小时';
  return num(m / 60 / 24, 1) + ' 天';
}

export const _p2 = (n) => String(n).padStart(2, '0');

/**
 * 后端返回的时间一律是带 +00:00 的 UTC，这里按**浏览器本地时区**显示。
 * 不能直接截字符串——那会把 UTC 当成当地时间，东八区会差 8 小时。
 */
export function dtShort(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso).slice(0, 16).replace('T', ' ');
  return _p2(d.getMonth() + 1) + '-' + _p2(d.getDate()) + ' ' +
    _p2(d.getHours()) + ':' + _p2(d.getMinutes());
}

export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso).slice(0, 16).replace('T', ' ');
  return d.getFullYear() + '-' + _p2(d.getMonth() + 1) + '-' + _p2(d.getDate()) + ' ' +
    _p2(d.getHours()) + ':' + _p2(d.getMinutes());
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.getFullYear() + '-' + _p2(d.getMonth() + 1) + '-' + _p2(d.getDate());
}

/**
 * 纯日期字段（KPI 期间、计划开始/结束）形如 2026-04-01，不带时区。
 * 这种值**不能**用 new Date() 解析——会被当成 UTC 零点，西半球会差一天。
 */
export function dateShort(iso) {
  if (!iso) return '—';
  return String(iso).slice(5, 10);
}

/* -------------------------------------------------- 配色映射 */

export const M_COLOR = { BPR: 't-red', BPI: 't-yel', LEAN: 't-grn', HYBRID: 't-pur' };
export const M_ICON = { BPR: '🔴', BPI: '🟡', LEAN: '🟢', HYBRID: '🔵' };
export const S_COLOR = {
  ACTIVE: 't-blu', PLANNING: 't-yel', ON_HOLD: 't-gry', CLOSED: 't-grn', CANCELLED: 't-red',
};
/** 热度统一走 CSS 类，具体色值由主题令牌决定 */
export const HEAT_CLASS = {
  CRITICAL: 'heat-critical', HIGH: 'heat-high', MEDIUM: 'heat-medium', LOW: 'heat-low',
};
export const HEAT_LABEL = { CRITICAL: '紧急', HIGH: '高', MEDIUM: '中', LOW: '低' };
export const SEV_COLOR = { CRITICAL: 't-red', HIGH: 't-red', MEDIUM: 't-yel', LOW: 't-grn' };
export const SEV_LABEL = { CRITICAL: '紧急', HIGH: '高', MEDIUM: '中', LOW: '低' };
export const EXC_COLOR = { OPEN: 't-red', IN_PROGRESS: 't-blu', RESOLVED: 't-yel', CLOSED: 't-grn' };
export const EXC_LABEL = { OPEN: '待处理', IN_PROGRESS: '处理中', RESOLVED: '已解决', CLOSED: '已闭环' };
export const CAT_ICON = { DIAGNOSE: '🔍', DESIGN: '🎨', DEPLOY: '🚀', MONITOR: '📊' };
export const KPI_DIM_ICON = { EFFICIENCY: '⚡', QUALITY: '✓', COST: '¥', FLEXIBILITY: '⤾' };
export const KN_COLOR = { CASE: 't-red', TEMPLATE: 't-blu', BEST_PRACTICE: 't-grn', STANDARD: 't-yel' };
export const KN_LABEL = { CASE: '案例', TEMPLATE: '模板', BEST_PRACTICE: '最佳实践', STANDARD: '标准制度' };
export const NODE_LABEL = {
  START: '开始', END: '结束', TASK: '作业', APPROVAL: '审批', WAIT: '等待',
  DECISION: '判断', HANDOFF: '移交',
};
export const NODE_CLASS = {
  START: 'start', END: 'end', APPROVAL: 'gate', DECISION: 'gate', WAIT: 'wait',
};
/** 交付物/模板版本状态的视觉色调；中文标签一律用后端下发的 status_label */
export const DLV_TONE = {
  MISSING: 't-red', DRAFT: 't-gry', IN_REVIEW: 't-yel', APPROVED: 't-blu',
  EFFECTIVE: 't-grn', SUPERSEDED: 't-gry', RETIRED: 't-gry',
};
/** 步骤契约里工具使用要求的色调；标签用后端 level_label */
export const TOOL_LEVEL_TONE = { REQUIRED: 't-red', RECOMMENDED: 't-blu', OPTIONAL: 't-gry' };

export function methodTag(m, label) {
  return '<span class="tag ' + (M_COLOR[m] || 't-blu') + '">' + esc(label || m) + '</span>';
}

export function statusTag(s, label) {
  return '<span class="tag ' + (S_COLOR[s] || 't-blu') + '">' + esc(label || s) + '</span>';
}

export function bar(value, color, width) {
  const w = Math.max(0, Math.min(100, Number(value) || 0));
  const tone = color || (w >= 70 ? 'ok' : w >= 40 ? 'warn' : 'bad');
  return '<div style="width:' + (width || 80) + 'px"><div class="pipe">' +
    '<i class="fill-' + tone + '" style="width:' + w + '%"></i></div>' +
    '<span class="tiny">' + num(w, 0) + '%</span></div>';
}

export function emptyRow(cols, msg) {
  return '<tr><td colspan="' + cols + '" class="empty">' + esc(msg || '暂无数据') + '</td></tr>';
}

export function skeleton(rows) {
  let s = '';
  for (let i = 0; i < (rows || 4); i++) s += '<div class="skel"></div>';
  return s;
}
