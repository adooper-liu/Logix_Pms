/* 视图：帮助中心 —— 定位→价值→边界→原理→场景→实操→术语 */

import { esc } from '../core/format.js';
import { on, viewEl } from '../core/ui.js';
import { go, urlParams, setUrlState } from '../core/router.js';
import { TITLES } from '../core/state.js';
import {
  HELP_GROUPS, GLOSSARY, getTopic, allTopicIds,
} from '../help/catalog.js';

on('help.topic', ({ topic }) => selectTopic(topic));
on('help.openView', ({ view, tab }) => {
  const params = {};
  if (tab) params.tab = tab;
  go(view, { params, push: true });
});
on('help.related', ({ topic }) => selectTopic(topic));

function selectTopic(topic) {
  const id = allTopicIds().includes(topic) ? topic : 'intro';
  setUrlState('help', { topic: id }, { push: false });
  renderHelp();
}

function currentTopicId() {
  const raw = urlParams().topic || 'intro';
  return allTopicIds().includes(raw) ? raw : 'intro';
}

function renderParagraphs(text) {
  if (!text) return '';
  return String(text).split('\n').filter(Boolean)
    .map((line) => `<p>${esc(line)}</p>`).join('');
}

function renderHowto(steps) {
  if (!steps || !steps.length) return '';
  return `<ol class="help-howto">${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`;
}

function renderGlossary() {
  return `
    <div class="help-glossary">
      ${GLOSSARY.map((row) => `
        <div class="help-gloss-row">
          <b>${esc(row.term)}</b>
          <span>${esc(row.def)}</span>
        </div>`).join('')}
    </div>`;
}

function section(title, bodyHtml) {
  if (!bodyHtml) return '';
  return `
    <section class="help-sec">
      <h4>${esc(title)}</h4>
      ${bodyHtml}
    </section>`;
}

const renderHelp = () => {
  const topicId = currentTopicId();
  const t = getTopic(topicId);
  const toc = HELP_GROUPS.map((g) => `
    <div class="help-toc-group">
      <div class="help-toc-label">${esc(g.title)}</div>
      ${g.topics.map((id) => {
        const item = getTopic(id);
        return `<button type="button" class="help-toc-item${id === topicId ? ' on' : ''}"
          data-act="help.topic" data-topic="${esc(id)}">${esc(item.title)}</button>`;
      }).join('')}
    </div>`).join('');

  const related = (t.related || [])
    .map((id) => {
      const item = getTopic(id);
      return `<button type="button" class="btn-sm" data-act="help.related"
        data-topic="${esc(id)}">${esc(item.title)}</button>`;
    }).join('');

  const openParams = t.openParams || {};
  const pageName = t.openView ? (TITLES[t.openView] || t.openView) : '';

  viewEl().innerHTML = `
    <div class="help-layout">
      <aside class="help-toc card">${toc}</aside>
      <article class="help-article card">
        <div class="between mb" style="align-items:flex-start;gap:12px;flex-wrap:wrap">
          <div>
            <div class="tiny muted">帮助中心 · 定位 → 价值 → 边界 → 原理 → 场景 → 实操 → 术语</div>
            <h2 style="margin:4px 0 0">${esc(t.title)}</h2>
            ${t.summary ? `<p class="desc" style="margin:8px 0 0">${esc(t.summary)}</p>` : ''}
          </div>
          ${t.openView ? `<button class="btn btn-p" data-act="help.openView"
            data-view="${esc(t.openView)}"
            ${openParams.tab ? `data-tab="${esc(openParams.tab)}"` : ''}>
            打开「${esc(pageName)}」</button>` : ''}
        </div>
        ${section('原理', renderParagraphs(t.principle))}
        ${section('价值', renderParagraphs(t.value))}
        ${section('边界', renderParagraphs(t.boundary))}
        ${section('场景', renderParagraphs(t.scenario))}
        ${section('实操', renderHowto(t.howto))}
        ${topicId === 'glossary' ? section('术语', renderGlossary()) : ''}
        ${related ? `<div class="help-related"><div class="tiny muted mb">相关</div>
          <div class="gap">${related}</div></div>` : ''}
      </article>
    </div>`;
};

export { renderHelp };
