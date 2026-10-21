/* 主题壳：读取/切换 data-theme，并给 Canvas 图表提供当前主题色。
 *
 * 组件和视图不允许直接写死颜色；新增主题只需在 base.css 里加一组
 * [data-theme="xxx"] 的变量覆盖，再在 THEMES 里登记名称。
 */

export const THEMES = [
  { code: 'default', name: '默认蓝' },
  { code: 'slate', name: '石墨灰' },
];

const STORAGE_KEY = 'pms_theme';

export function applyTheme(code) {
  const theme = THEMES.some((t) => t.code === code) ? code : 'default';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) { /* 隐私模式忽略 */ }
  const sel = document.getElementById('themeSel');
  if (sel) sel.value = theme;
}

export function initTheme() {
  const sel = document.getElementById('themeSel');
  if (sel) {
    // 主题清单只在这里维护，index.html 不再重复写一份
    sel.innerHTML = THEMES.map((t) => '<option value="' + t.code + '">' + t.name + '</option>').join('');
  }
  let saved = 'default';
  try { saved = localStorage.getItem(STORAGE_KEY) || 'default'; } catch (e) { /* ignore */ }
  applyTheme(saved);
}

/** 读取当前主题的 CSS 变量，供 Canvas 2D 等无法用 CSS 的地方使用 */
export function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback || '';
}
