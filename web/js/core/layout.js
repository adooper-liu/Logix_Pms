/* 生产页面外壳：标题 + 左侧目录动线 + 中间主题内容 + 右侧上下文。
 *
 * 只负责布局，不持有业务状态；视图把选中 tab 传给 sectionNav。
 */
import { esc } from './format.js';

export function sectionNav(items, active, act) {
  return items.map(({ key, label, count }) => `
    <button class="ws-nav-item${key === active ? ' on' : ''}"
      data-act="${act}" data-tab="${key}">
      <span>${esc(label)}</span>
      ${count === null || count === undefined ? '' : `<em>${esc(String(count))}</em>`}
    </button>`).join('');
}

export function sectionTabs(items, active, act) {
  return `<div class="ws-tabs">${items.map(({ key, label, count }) => `
    <button class="ws-tab${key === active ? ' on' : ''}"
      data-act="${act}" data-tab="${key}">
      ${esc(label)}${count === null || count === undefined ? '' : ` <em>${esc(String(count))}</em>`}
    </button>`).join('')}</div>`;
}

export function workspaceHtml({
  title, badge = '', subtitle = '', tip = '', actions = '',
  nav = '', main = '', aside = '', navAct = '',
}) {
  const three = !!aside;
  const layoutClass = `ws-layout${nav ? '' : ' no-nav'}${aside ? '' : ' no-aside'}`;
  return `
    <div class="card page-head ws-head">
      <div class="between">
        <div>
          <h2>${title}${badge}</h2>
          ${subtitle ? `<p class="desc">${subtitle}${tip ? ' ' + tip : ''}</p>` : ''}
        </div>
        <div class="gap">${actions}</div>
      </div>
    </div>
    <div class="${layoutClass}">
      ${nav ? `<aside class="card ws-nav"${navAct ? ` data-nav="${esc(navAct)}"` : ''}>${nav}</aside>` : ''}
      <section class="ws-main">${main}</section>
      ${three ? `<aside class="ws-aside">${aside}</aside>` : ''}
    </div>`;
}

export function foldCard(title, body, { open = true, tip = '' } = {}) {
  return `<details class="fold-card"${open ? ' open' : ''}>
    <summary><span>${esc(title)}</span>${tip}</summary>
    <div class="fold-body">${body}</div>
  </details>`;
}

export function sideCard(title, body, { actions = '' } = {}) {
  return `<div class="card ws-side-card">
    <div class="between"><h3>${esc(title)}</h3>${actions}</div>
    ${body}
  </div>`;
}

/**
 * 页面外壳：页面只提供 sections 与 aside，不再手写标题/目录/三栏。
 *
 * sections: [{ key, label, count?, html }]
 * active:   当前主题 key；不在 sections 内时回落到第一项
 * mode:     'nav' 左目录（默认）/ 'tabs' 顶部 Tab
 * tabAct:   目录/Tab 的 data-act，页面只注册一个切换 handler
 */
export function pageShell({
  title, badge = '', subtitle = '', tip = '', actions = '',
  sections = [], active = '', tabAct = 'page.tab', mode = 'nav', aside = '',
}) {
  const keys = sections.map((item) => item.key);
  const current = keys.includes(active) ? active : keys[0];
  const currentSection = sections.find((item) => item.key === current);
  const navHtml = mode === 'tabs'
    ? sectionTabs(sections, current, tabAct)
    : mode === 'nav'
      ? sectionNav(sections, current, tabAct)
      : '';
  return {
    active: current,
    html: workspaceHtml({
      title,
      badge,
      subtitle,
      tip,
      actions,
      nav: mode === 'nav' ? navHtml : '',
      navAct: tabAct,
      main: `${mode === 'tabs' ? navHtml : ''}${currentSection ? currentSection.html : ''}`,
      aside,
    }),
  };
}
