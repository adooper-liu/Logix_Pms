/* 视图：APQC PCF 分类框架（学习 / 识别 / 指标） */
import { esc } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS, go } from '../core/router.js';
import { GET } from '../core/api.js';

on('pcf.framework', (_data, el) => setPcfFramework(el.value));
on('pcf.search', (_data, el) => setPcfKeyword(el.value));
on('pcf.select', ({ id }) => selectPcfNode(Number(id)));
on('pcf.expand', ({ id }) => togglePcfBrowseNode(Number(id)));
on('pcf.goMap', () => go('map'));

const LEVELS = {
  1: { label: 'L1 流程类', en: 'Category', desc: '最高层级的流程分类（业务域）' },
  2: { label: 'L2 流程组', en: 'Process Group', desc: '一组流程，不能直接执行' },
  3: { label: 'L3 流程', en: 'Process', desc: '一条端到端流程，可直接运行' },
  4: { label: 'L4 活动', en: 'Activity', desc: '执行流程的关键步骤' },
  5: { label: 'L5 任务', en: 'Task', desc: '活动下的最小工作单元' },
};

let detailToken = 0;

function flatten(nodes, out, parentId) {
  const acc = out || [];
  (nodes || []).forEach((node) => {
    acc.push({ node, parentId: parentId || null });
    flatten(node.children, acc, node.id);
  });
  return acc;
}

function nodeText(node) {
  return [node.code, node.name, node.name_zh, node.name_en, node.external_id]
    .filter(Boolean).join(' ').toLowerCase();
}

function pcfFrameworks() {
  return (state.pcf.frameworks || []).filter(
    (f) => f.code === 'APQC_PCF' || f.base_framework_code === 'APQC_PCF');
}

async function loadPcf() {
  const frameworks = state.pcf.frameworks || await GET('/benchmark/frameworks');
  state.pcf.frameworks = frameworks;
  const available = pcfFrameworks();
  if (!available.length) throw new Error('没有可用的 PCF 框架，请先灌入对标数据');
  if (!available.some((f) => f.code === state.pcf.framework)) {
    state.pcf.framework = available[0].code;
  }
  if (!state.pcf.tree || state.pcf.treeFramework !== state.pcf.framework) {
    const tree = await GET(
      '/benchmark/frameworks/' + encodeURIComponent(state.pcf.framework) + '/tree?max_level=5');
    state.pcf.tree = tree;
    state.pcf.treeFramework = state.pcf.framework;
    state.pcf.expanded = new Set(tree.map((node) => node.id));
    state.pcf.selectedId = null;
  }
  return available;
}

const renderPcf = () => {
  if (state.pcf.tree && state.pcf.treeFramework === state.pcf.framework) {
    paintPcf();
    return;
  }
  renderAsync('pcf', loadPcf, () => paintPcf());
};

function paintPcf() {
  const flat = flatten(state.pcf.tree, [], null);
  state.pcf.flat = flat;
  state.pcf.byId = new Map(flat.map((entry) => [entry.node.id, entry.node]));
  state.pcf.parents = new Map(flat.map((entry) => [entry.node.id, entry.parentId]));
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  flat.forEach(({ node }) => { counts[node.level] = (counts[node.level] || 0) + 1; });

  const levelCards = Object.entries(LEVELS).map(([level, meta]) => `
    <div class="pcf-level">
      <b>${meta.label}</b>
      <div class="tiny">${meta.en} · ${counts[level] || 0} 个</div>
      <div class="tiny">${meta.desc}</div>
    </div>`).join('');

  const frameworkOptions = pcfFrameworks().map((f) =>
    `<option value="${f.code}"${f.code === state.pcf.framework ? ' selected' : ''}>${
      esc(f.name)}${f.version ? ' ' + esc(f.version) : ''}</option>`).join('');

  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between mb">
        <div><h2>APQC PCF 分类框架<span class="module-badge">分类宪法 · 学习与识别</span></h2>
          <div class="desc">L1–L5 分类字典、中英文对照、官方定义与指标；PCF 是分类，不是流程图</div></div>
        <div class="gap">
          <select class="sel" data-act="pcf.framework">${frameworkOptions}</select>
          <a class="link-btn" data-act="pcf.goMap">去流程地图 →</a>
        </div>
      </div>
      <div class="pcf-levels">${levelCards}</div>
    </div>
    <div class="pcf-layout">
      <div class="card pcf-tree-card">
        <div class="between mb">
          <h3 style="margin:0">分类树</h3>
          <span class="tiny" id="pcfVisibleCount"></span>
        </div>
        <input id="pcfQ" class="sel" placeholder="搜索编码、中文名或英文名"
          value="${esc(state.pcf.keyword)}" data-act="pcf.search">
        <div class="pcf-rows" id="pcfRows"></div>
      </div>
      <div class="card pcf-detail" id="pcfDetail"></div>
    </div>`;

  paintPcfRows();
  const selected = state.pcf.selectedId && state.pcf.byId.get(state.pcf.selectedId);
  if (selected) paintPcfDetail(selected);
  else paintPcfIntro();
}

function setPcfFramework(code) {
  state.pcf.framework = code;
  state.pcf.tree = null;
  state.pcf.treeFramework = null;
  state.pcf.expanded = new Set();
  state.pcf.selectedId = null;
  state.pcf.keyword = '';
  RENDERERS.pcf();
}

let searchTimer = null;
function setPcfKeyword(value) {
  state.pcf.keyword = value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => paintPcfRows(), 160);
}

function togglePcfBrowseNode(id) {
  if (state.pcf.expanded.has(id)) state.pcf.expanded.delete(id);
  else state.pcf.expanded.add(id);
  paintPcfRows();
}

function selectPcfNode(id) {
  state.pcf.selectedId = id;
  document.querySelectorAll('#pcfRows .pcf-row').forEach((row) => {
    row.classList.toggle('on', Number(row.dataset.id) === id);
  });
  const node = state.pcf.byId.get(id);
  if (node) paintPcfDetail(node);
}

/** 搜索时把匹配节点的祖先全部展开，保证结果可见。 */
function expandAncestors(id) {
  let parent = state.pcf.parents.get(id);
  while (parent) {
    state.pcf.expanded.add(parent);
    parent = state.pcf.parents.get(parent);
  }
}

function visibleEntries() {
  const flat = state.pcf.flat || [];
  const keyword = (state.pcf.keyword || '').trim().toLowerCase();
  if (!keyword) {
    const rows = [];
    const open = new Set();
    flat.forEach((entry) => {
      const parentId = entry.parentId;
      if (parentId === null || open.has(parentId)) {
        rows.push(entry);
        if (state.pcf.expanded.has(entry.node.id)) open.add(entry.node.id);
      }
    });
    return rows;
  }

  const matched = new Set(
    flat.filter((entry) => nodeText(entry.node).includes(keyword)).map((entry) => entry.node.id));
  matched.forEach(expandAncestors);
  const visible = new Set(matched);
  flat.forEach((entry) => {
    if (entry.parentId && visible.has(entry.parentId)) visible.add(entry.node.id);
  });
  matched.forEach((id) => {
    let parent = state.pcf.parents.get(id);
    while (parent) {
      visible.add(parent);
      parent = state.pcf.parents.get(parent);
    }
  });
  return flat.filter((entry) => visible.has(entry.node.id));
}

function paintPcfRows() {
  const box = document.getElementById('pcfRows');
  if (!box) return;
  const rows = visibleEntries();
  box.innerHTML = rows.map(({ node }) => {
    const hasKids = (node.children || []).length > 0;
    const open = state.pcf.expanded.has(node.id);
    const indent = (node.level - 1) * 18;
    const nameZh = node.name_zh || node.name;
    const showEn = node.name_en && node.name_en !== nameZh;
    return `<div class="pcf-row${node.id === state.pcf.selectedId ? ' on' : ''}"
        data-id="${node.id}" style="padding-left:${indent}px">
      <button class="pcf-caret${hasKids ? '' : ' empty'}"
        data-act="pcf.expand" data-id="${node.id}">${hasKids ? (open ? '▾' : '▸') : '·'}</button>
      <button class="pcf-row-main" type="button" data-act="pcf.select" data-id="${node.id}">
        <span class="map-code">${esc(node.code)}</span>
        <span class="pcf-row-name">${esc(nameZh)}</span>
        ${showEn ? `<span class="pcf-row-en">${esc(node.name_en)}</span>` : ''}
        ${node.metric_count ? `<span class="tag t-gry">${node.metric_count} 指标</span>` : ''}
      </button>
    </div>`;
  }).join('') || '<div class="empty">没有匹配的分类</div>';
  const count = document.getElementById('pcfVisibleCount');
  if (count) count.textContent = `显示 ${rows.length} / ${(state.pcf.flat || []).length} 个元素`;
}

function breadcrumb(node) {
  const names = [];
  let current = node;
  while (current) {
    names.unshift(current.name_zh || current.name);
    const parentId = state.pcf.parents.get(current.id);
    current = parentId ? state.pcf.byId.get(parentId) : null;
  }
  return names.join(' › ');
}

function paintPcfIntro() {
  const box = document.getElementById('pcfDetail');
  if (!box) return;
  box.innerHTML = `
    <h3 style="margin-top:0">怎么用这份分类</h3>
    <div class="desc">在左侧选择任意元素，查看中英文名、PCF ID、官方定义、指标与公司流程覆盖情况。</div>
    <div class="pcf-section"><h4>学习</h4>
      <div class="tiny">L1/L2 是“一组流程”，本质是分类文件夹；L3 才是“一条流程”，从 L3 开始才有流转与端到端闭环。</div></div>
    <div class="pcf-section"><h4>识别</h4>
      <div class="tiny">用 5 位 PCF ID 做跨版本、跨行业识别；Hierarchy ID（如 4.3.1.2）会因行业元素插入而漂移，不能当稳定键。</div></div>
    <div class="pcf-section"><h4>对标</h4>
      <div class="tiny">PCF 指标按 PCF ID 挂载，可直接用于 KPI 口径；公司流程在流程地图里与分类建立映射。</div></div>
    <div class="pcf-note">PCF 不含先后顺序、分支和事件触发——它是业务名词字典。流程图与执行逻辑由 BPMN 设计器维护。</div>`;
}

async function paintPcfDetail(node) {
  const box = document.getElementById('pcfDetail');
  if (!box) return;
  const meta = LEVELS[node.level] || { label: `L${node.level}`, en: '', desc: '' };
  const token = ++detailToken;
  box.innerHTML = `
    <div class="pcf-breadcrumb">${esc(breadcrumb(node))}</div>
    <h3>${esc(node.name_zh || node.name)}</h3>
    ${node.name_en ? `<div class="pcf-en">${esc(node.name_en)}</div>` : ''}
    <div class="gap" style="flex-wrap:wrap">
      <span class="tag t-blu">${esc(meta.label)}</span>
      <span class="tag t-gry">PCF ID ${esc(node.external_id || '—')}</span>
      <span class="tag t-gry">${esc(node.code)}</span>
      ${node.metrics_available ? '<span class="tag t-grn">有指标</span>' : ''}
    </div>
    <div class="pcf-section"><h4>官方定义</h4>
      <div class="tiny" style="line-height:1.7">${esc(node.description || '（该元素没有官方定义）')}</div>
    </div>
    <div class="pcf-section"><h4>公司流程覆盖</h4>
      <div class="tiny">直接映射 ${node.mapped_process_count || 0} 条 · 含下级合计 ${
        node.subtree_mapped_process_count || 0} 条</div>
    </div>
    <div class="pcf-section"><h4>PCF 指标</h4>
      <div id="pcfMetricBox" class="pcf-metrics"><div class="tiny">加载中…</div></div>
    </div>
    <div class="pcf-note">${esc(meta.desc)} · ${esc(meta.en)}</div>`;

  try {
    const data = await GET('/benchmark/categories/' + node.id + '/metrics');
    if (token !== detailToken) return;
    const target = document.getElementById('pcfMetricBox');
    if (!target) return;
    if (!data.metrics.length) {
      target.innerHTML = '<div class="tiny">该分类没有配置 PCF 指标</div>';
      return;
    }
    target.innerHTML = `
      <table class="tbl">
        <thead><tr><th>指标 ID</th><th>指标</th><th>类别</th><th>公式</th><th>单位</th></tr></thead>
        <tbody>${data.metrics.map((m) => `
          <tr><td class="tiny">${esc(m.metric_id)}</td>
            <td>${esc(m.name)}</td>
            <td class="tiny">${esc(m.metric_category || '—')}</td>
            <td class="tiny">${esc(m.formula || '—')}</td>
            <td class="tiny">${esc(m.unit || '—')}</td></tr>`).join('')}</tbody>
      </table>`;
  } catch (e) {
    if (token === detailToken) {
      const target = document.getElementById('pcfMetricBox');
      if (target) target.innerHTML = `<div class="tiny">${esc(e.message)}</div>`;
    }
  }
}

export { renderPcf };
