/* 视图：map */
import { esc, num, bar, HEAT_CLASS, HEAT_LABEL, emptyRow } from '../core/format.js';
import { metricHelp } from '../core/metrics.js';
import { toast, openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { openDesigner } from './designer.js';

/* ============================================================ 2. 企业流程地图 */

const LEVEL_LABELS = { 1: 'L1 价值链', 2: 'L2 流程类别', 3: 'L3 流程', 4: 'L4 活动' };

/** 左侧架构导航：只展开当前路径，避免一屏铺开 148 个节点 */
function renderOutline(list, path) {
  return (list || []).filter((n) => n.level <= 3).map((n) => {
    const inPath = path.includes(n.code);
    const on = path[path.length - 1] === n.code;
    const kids = inPath && n.level < 3 ? renderOutline(n.children || [], path) : '';
    return `
      <div class="tree-item lv${n.level}${inPath ? ' in-path' : ''}${on ? ' on' : ''}"
           onclick="mapSelect('${n.code}')">
        <span class="tree-dot${n.is_improvement_target ? ' target' : ''}"></span>
        <span class="tree-name">${esc(n.name)}</span>
        <span class="cnt">${(n.children || []).length || ''}</span>
      </div>${kids}`;
  }).join('');
}

function findPathTo(code, list, trail) {
  const path = trail || [];
  for (const n of list || []) {
    if (n.code === code) return path.concat([n.code]);
    const hit = findPathTo(code, n.children, path.concat([n.code]));
    if (hit) return hit;
  }
  return null;
}

const renderMap = () => {
  const paint = () => {
    const tree = state.map.tree || [];
    const path = state.map.path;
    let nodes = tree;
    let current = null;
    for (const code of path) {
      const found = nodes.find((n) => n.code === code);
      if (!found) break;
      current = found;
      nodes = found.children || [];
    }

    const kw = state.mapKeyword || '';
    const improvementOnly = !!state.map.improvementOnly;
    let shown = nodes;
    if (kw) {
      shown = shown.filter((n) => (n.name + n.code + (n.owner || '')).includes(kw));
    }
    if (improvementOnly) shown = shown.filter((n) => n.is_improvement_target);

    const flat = flattenTree(tree);
    const levelCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    flat.forEach((n) => { levelCounts[n.level] = (levelCounts[n.level] || 0) + 1; });
    const targetCount = flat.filter((n) => n.is_improvement_target).length;
    const healthValues = flat
      .map((n) => n.health_score)
      .filter((v) => v !== null && v !== undefined);
    const avgHealth = healthValues.length
      ? Math.round(healthValues.reduce((a, b) => a + b, 0) / healthValues.length)
      : '—';

    const childWord = current && current.level === 3 ? '活动' : '流程';
    const title = current ? current.name : '全部价值链';
    const desc = current
      ? `${LEVEL_LABELS[current.level] || ''} · ${(current.children || []).length} 个${childWord}` +
        (kw ? ` · 匹配 ${shown.length} 项` : '')
      : `L1 价值链 · ${tree.length} 条主线，点击任一行逐级下钻` +
        (kw ? ` · 匹配 ${shown.length} 项` : '');

    const crumbs = ['<a onclick="mapGo(-1)">全部价值链</a>']
      .concat(path.map((code, i) =>
        '<span>/</span><a onclick="mapGo(' + i + ')">' + esc(state.map.names[code] || code) + '</a>'));
    const treeHtml = `
      <div class="tree-item root${path.length === 0 ? ' on' : ''}" onclick="mapGo(-1)">
        <span class="tree-dot"></span>
        <span class="tree-name">全部价值链</span>
        <span class="cnt">${tree.length}</span>
      </div>` + renderOutline(tree, path);

    const rows = shown.map((n) => {
      // 热度由后端统一判定（见 app/api/v1/process_map.py 的阈值），前端不再各算一套
      const heat = n.heat_level || 'LOW';
      const heatClass = HEAT_CLASS[heat] || HEAT_CLASS.LOW;
      const hasKids = (n.children || []).length > 0;
      return `
        <tr class="clk map-row" onclick="mapClick('${n.code}', ${hasKids})">
          <td>
            <div class="map-name">
              <span class="map-code">${esc(n.code)}</span>
              <b>${esc(n.name)}</b>
              ${n.is_improvement_target ? '<span class="tag t-red">待改善</span>' : ''}
            </div>
            ${n.description ? '<div class="tiny map-desc">' + esc(n.description) + '</div>' : ''}
          </td>
          <td><div>Owner: ${esc(n.owner || '未指定')}</div>
            <div class="tiny">${esc(n.department || '—')}</div></td>
          <td>${n.health_score === null
            ? '<span class="muted">未评估</span>' : bar(n.health_score, null, 70)}</td>
          <td><div>${num(n.pain_score, 1)} / 5</div>
            <div class="tiny">改善空间 ${num(n.improvement_space, 1)}</div></td>
          <td><span class="tag ${heatClass}">
            ${HEAT_LABEL[heat]} ${num(n.priority_score, 0)}</span></td>
          <td>${hasKids ? (n.children || []).length + ' 项' : '—'}</td>
          <td class="map-go">${hasKids ? '进入 ›' : '详情 ›'}</td>
        </tr>`;
    }).join('') || emptyRow(7, improvementOnly
      ? '该层级没有待改善流程，点击「显示全部」恢复'
      : '该层级下没有流程（或没有匹配结果）');

    const heat = (state.map.heat || []).slice(0, 6).map((h) => `
      <tr class="clk" onclick="mapJump('${h.code}')">
        <td><b>${esc(h.name)}</b><div class="tiny">${esc(h.code)} · ${esc(h.owner || '未指定 Owner')}</div></td>
        <td><span class="tag ${HEAT_CLASS[h.heat_level] || HEAT_CLASS.LOW}">
          ${HEAT_LABEL[h.heat_level]}</span></td>
        <td><b>${num(h.priority_score, 0)}</b></td>
        <td>${h.health_score === null ? '—' : num(h.health_score, 0)}</td>
      </tr>`).join('') || emptyRow(4, '暂无待改善项');

    const bench = state.map.benchmark;
    const frameworkOptions = (state.map.frameworks || []).map((f) =>
      '<option value="' + f.code + '"' +
      (state.map.benchmarkFramework === f.code ? ' selected' : '') + '>' +
      esc(f.name) + (f.version ? ' ' + esc(f.version) : '') + '</option>').join('');
    const benchCard = state.map.benchmarkFramework && bench ? `
      <div class="card">
        <div class="between mb">
          <div>
            <h3 style="margin:0">${metricHelp('benchmark_coverage', '对标覆盖')} · ${esc(bench.framework_name)}${
              bench.framework_version ? ' ' + esc(bench.framework_version) : ''}</h3>
            <div class="desc" style="margin:2px 0 0">L3 流程 ${bench.mapped_processes}/${bench.total_processes}
              能被该框架覆盖 · 切换只换对标视图</div>
          </div>
          ${bar(bench.coverage_rate * 100, null, 120)}
        </div>
        <div class="map-bench-pills">${bench.by_top_category.map((c, i) => `
          <button class="map-bench-pill" onclick="openCoverageCategory(${i})" title="${esc(c.name)}">
            <b>${esc(c.code)}</b><span>${esc(c.name)}</span><i>${c.mapped_count}</i>
          </button>`).join('')}</div>
        ${bench.unmapped_processes.length
          ? '<div class="note">未覆盖：' + bench.unmapped_processes
            .map((p) => esc(p.code) + ' ' + esc(p.name)).join('、') +
            '（不在该框架的适用范围）</div>'
          : '<div class="note">所有 L3 流程都能在该框架中找到对应分类。</div>'}
        <div class="note">覆盖率按后代聚合；点击分类可查看明细。</div>
      </div>` : '';

    viewEl().innerHTML = `
      <div class="card map-head">
        <div class="between map-head-top">
          <div>
            <h2 style="margin:0">企业流程地图<span class="module-badge">流程资产 · 定位与优先级</span></h2>
            <div class="desc" style="margin:4px 0 0">
              从 L1 价值链逐级下钻到 L4 活动 · 先定位结构，再决定改善对象</div>
          </div>
          <div class="gap">
            <a class="link" onclick="go('projects')">去立项 →</a>
            <select class="sel" onchange="setBenchmarkFramework(this.value)" title="切换对标框架">
              <option value="">不对标</option>
              ${frameworkOptions}
            </select>
            ${canManage()
              ? '<button class="btn btn-p" onclick="newProcessModal()">+ 新建流程</button>'
              : '<span class="tiny">当前角色只读</span>'}
          </div>
        </div>
        <div class="map-stats">
          <span class="map-stat"><b>${flat.length}</b> ${metricHelp('process_total', '流程资产')}</span>
          <button class="map-stat${improvementOnly ? ' on' : ''}" onclick="toggleImprovement()">
            <b>${targetCount}</b> ${metricHelp('improvement_targets', '待改善')}</button>
          <span class="map-stat"><b>${avgHealth}</b> ${metricHelp('map_avg_health', '平均健康度')}</span>
          <span class="map-stat">${metricHelp('level_counts', 'L1')} <b>${levelCounts[1]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L2')} <b>${levelCounts[2]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L3')} <b>${levelCounts[3]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L4')} <b>${levelCounts[4]}</b></span>
        </div>
      </div>

      <div class="map-layout">
        <aside class="map-side card">
          <div class="map-side-hd">架构导航</div>
          <div class="map-tree">${treeHtml}</div>
          <div class="map-side-foot tiny">点击层级展开；L4 活动在右侧列表中查看。</div>
        </aside>

        <div class="map-main">
          <div class="card">
            <div class="between mb">
              <div style="min-width:0">
                <div class="crumb" style="margin-bottom:6px">${crumbs.join(' ')}</div>
                <h2 style="margin:0">${esc(title)}</h2>
                <div class="desc" style="margin:4px 0 0">${esc(desc)}</div>
              </div>
              <button class="btn-sm${improvementOnly ? ' on' : ''}" onclick="toggleImprovement()">
                ${improvementOnly ? '显示全部' : '只看待改善'}</button>
            </div>
            <div class="legend mb">
              <span><i style="background:var(--bad)"></i>紧急</span>
              <span><i style="background:var(--warn)"></i>高</span>
              <span><i style="background:var(--brand)"></i>中</span>
              <span><i style="background:var(--ok)"></i>低</span>
              <span class="muted">优先级 = 战略 × 痛点 × 改善空间</span>
            </div>
            <table class="tbl map-table">
              <thead><tr><th>流程</th><th>Owner / 部门</th><th>${metricHelp('health_score', '健康度')}</th>
                <th>${metricHelp('pain_space', '痛点 / 改善空间')}</th>
                <th>${metricHelp('priority_score', '优先级')}</th><th>${metricHelp('child_count', '下级')}</th><th></th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>

          <div class="map-bottom${benchCard ? '' : ' single'}">
            <div class="card">
              <div class="between mb">
                <div><h3 style="margin:0">改善优先级</h3>
                  <div class="desc" style="margin:2px 0 0">L3 Top 6 · 按综合得分排序，点击定位</div></div>
              </div>
              <table class="tbl">
                <thead><tr><th>流程</th><th>优先级</th><th>得分</th><th>健康度</th></tr></thead>
                <tbody>${heat}</tbody>
              </table>
            </div>
            ${benchCard}
          </div>
        </div>
      </div>`;
  };

  const start = async () => {
    if (!state.map.frameworks) {
      state.map.frameworks = await GET('/benchmark/frameworks');
    }
    if (!state.map.tree) {
      const [tree, heat] = await Promise.all([
        GET('/process-map/tree'),
        GET('/process-map/heatmap?level=3&limit=12'),
      ]);
      state.map.tree = tree;
      state.map.heat = heat;
      state.map.names = {};
      const walk = (list) => list.forEach((n) => {
        state.map.names[n.code] = n.name;
        walk(n.children || []);
      });
      walk(tree);
    }
    if (state.map.benchmarkFramework && !state.map.benchmark) {
      state.map.benchmark = await GET(
        '/benchmark/frameworks/' + state.map.benchmarkFramework + '/coverage?process_level=3');
    }
    paint();
  };

  renderAsync('map', start, () => paint());
};

function mapClick(code, hasKids) {
  if (hasKids) {
    state.map.path = state.map.path.concat([code]);
    RENDERERS.map();
  } else {
    const node = (() => {
      let nodes = state.map.tree || [];
      for (const c of state.map.path) {
        const f = nodes.find((n) => n.code === c);
        if (!f) return null;
        nodes = f.children || [];
      }
      return nodes.find((n) => n.code === code);
    })();
    if (!node) return;
    openModal(node.name + ' · ' + node.code, `
      <div class="row2">
        <div class="field"><label>流程层级</label><input value="L${node.level}" readonly></div>
        <div class="field"><label>流程 Owner</label><input value="${esc(node.owner || '未指定')}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>责任部门</label><input value="${esc(node.department || '—')}" readonly></div>
        <div class="field"><label>综合优先级得分</label><input value="${num(node.priority_score, 1)}" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>战略重要性</label><input value="${num(node.strategic_importance, 1)} / 5" readonly></div>
        <div class="field"><label>痛点严重度</label><input value="${num(node.pain_score, 1)} / 5" readonly></div>
      </div>
      <div class="row2">
        <div class="field"><label>改善空间</label><input value="${num(node.improvement_space, 1)} / 5" readonly></div>
        <div class="field"><label>流程健康度</label><input value="${node.health_score === null ? '未评估' : num(node.health_score, 0) + ' 分'}" readonly></div>
      </div>
      ${node.description ? '<div class="field"><label>流程说明</label><textarea readonly>' + esc(node.description) + '</textarea></div>' : ''}
      <div class="note">在「流程设计器」里可以对这条流程做泳道建模与周期效率测算。</div>`,
      `${canManage()
        ? '<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"'
          + ' onclick="deleteProcess(' + node.id + ', \'' + esc(node.code) + '\')">删除</button>'
        : ''}
       <button class="btn btn-g" onclick="closeModal()">关闭</button>
       ${canManage() ? '<button class="btn btn-g" onclick="editProcessModal(' + node.id + ')">编辑</button>' : ''}
       <button class="btn btn-p" onclick="closeModal();openDesigner(${node.id})">去设计器分析</button>`);
  }
}

function mapGo(index) {
  state.map.path = index < 0 ? [] : state.map.path.slice(0, index + 1);
  RENDERERS.map();
}

/** 左侧导航入口：选中某层后，主区展示它的下级 */
function mapSelect(code) {
  const path = findPathTo(code, state.map.tree || [], []);
  if (!path) return;
  state.map.path = path;
  state.mapKeyword = '';
  const search = document.getElementById('searchInput');
  if (search) search.value = '';
  RENDERERS.map();
}

function toggleImprovement() {
  state.map.improvementOnly = !state.map.improvementOnly;
  RENDERERS.map();
}

/* -------------------------------------------------- 对标框架切换 */

async function setBenchmarkFramework(code) {
  state.map.benchmarkFramework = code;
  state.map.benchmark = null;
  if (code) {
    try {
      state.map.benchmark = await GET(
        '/benchmark/frameworks/' + code + '/coverage?process_level=3');
    } catch (e) {
      toast(e.message, true);
    }
  }
  RENDERERS.map();
}

function openCoverageCategory(index) {
  const bench = state.map.benchmark;
  if (!bench) return;
  const c = bench.by_top_category[index];
  if (!c) return;
  const rows = c.processes.map((p) => `
    <tr><td>${esc(p.code)}</td><td>${esc(p.name)}</td><td>L${p.level}</td></tr>`).join('');
  openModal(`${c.code} ${c.name} · 覆盖流程`, c.processes.length ? `
    <table class="tbl">
      <thead><tr><th>编码</th><th>流程</th><th>层级</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>` : '<div class="empty">该分类下没有已映射流程</div>',
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
}

/** 从热力图跳转：逐级展开到该编码所在层级 */
function mapJump(code) {
  const path = [];
  let nodes = state.map.tree || [];
  let guard = 0;
  while (guard++ < 8) {
    const hit = nodes.find((n) => n.code === code);
    if (hit) {
      state.map.path = path;
      state.mapKeyword = '';
      document.getElementById('searchInput').value = '';
      RENDERERS.map();
      setTimeout(() => mapClick(code, false), 30);
      return;
    }
    const parent = nodes.find((n) => (n.children || []).some((c) => c.code === code));
    if (!parent) break;
    path.push(parent.code);
    nodes = parent.children;
  }
  toast('未在地图中定位到 ' + code, true);
}

/* -------------------------------------------------- 流程架构的写入口 */

/** 写操作会让地图树、设计器下拉的缓存失效 */
function invalidateProcessCaches() {
  state.map.tree = null;
  state.map.heat = null;
  state.map.benchmark = null;
  state.designer.processes = null;
  state.designer.model = null;
  state.designer.analysis = null;
}

function flattenTree(list, out) {
  const acc = out || [];
  (list || []).forEach((n) => { acc.push(n); flattenTree(n.children, acc); });
  return acc;
}

function processParentOptions(level) {
  const all = flattenTree(state.map.tree || [])
    .filter((n) => n.level < level)
    .sort((a, b) => a.code.localeCompare(b.code));
  return '<option value="">无（作为顶层）</option>' + all.map((n) =>
    '<option value="' + n.id + '">L' + n.level + ' ' + esc(n.code) + ' ' + esc(n.name) + '</option>'
  ).join('');
}

function refreshParentOptions(level, keepId) {
  const sel = document.getElementById('pfParent');
  if (!sel) return;
  sel.innerHTML = processParentOptions(Number(level));
  if (keepId) sel.value = String(keepId);
}

function newProcessModal() {
  openModal('新建流程', `
    <div class="row2">
      <div class="field"><label>流程编码 *</label>
        <input id="pfCode" placeholder="如 L3-090"><div class="hint">全局唯一，建议沿用 L层级-序号 规则</div></div>
      <div class="field"><label>流程名称 *</label><input id="pfName" placeholder="如：供应商对账"></div>
    </div>
    <div class="row2">
      <div class="field"><label>层级 *</label>
        <select id="pfLevel" onchange="refreshParentOptions(this.value)">
          <option value="1">L1 价值链</option>
          <option value="2">L2 流程类别</option>
          <option value="3" selected>L3 流程</option>
          <option value="4">L4 活动</option>
        </select></div>
      <div class="field"><label>上级流程</label>
        <select id="pfParent">${processParentOptions(3)}</select></div>
    </div>
    <div class="row2">
      <div class="field"><label>流程 Owner</label><input id="pfOwner" placeholder="如：采购部-陈经理"></div>
      <div class="field"><label>责任部门</label><input id="pfDepartment" placeholder="如：采购部"></div>
    </div>
    <div class="field"><label>流程说明</label><textarea id="pfDesc" placeholder="这条流程从哪开始、到哪结束"></textarea></div>
    <div class="row3">
      <div class="field"><label>战略重要性（0–5）</label>
        <input id="pfSi" type="number" min="0" max="5" step="0.1" value="3"></div>
      <div class="field"><label>痛点严重度（0–5）</label>
        <input id="pfPain" type="number" min="0" max="5" step="0.1" value="3"></div>
      <div class="field"><label>改善空间（0–5）</label>
        <input id="pfSpace" type="number" min="0" max="5" step="0.1" value="3"></div>
    </div>
    <div class="field"><label>是否为待改善项</label>
      <select id="pfTarget"><option value="false">否</option><option value="true">是</option></select>
      <div class="hint">勾选后会出现在驾驶舱的「待改善流程」统计里</div></div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveProcess(null)">创建</button>`);
}

function editProcessModal(processId) {
  const node = flattenTree(state.map.tree || []).find((n) => n.id === processId);
  if (!node) return toast('未找到该流程，请刷新后重试', true);
  openModal('编辑流程 · ' + node.code, `
    <div class="row2">
      <div class="field"><label>流程编码</label><input value="${esc(node.code)}" readonly></div>
      <div class="field"><label>层级</label><input value="L${node.level}" readonly></div>
    </div>
    <div class="field"><label>流程名称</label><input id="pfName" value="${esc(node.name)}"></div>
    <div class="row2">
      <div class="field"><label>流程 Owner</label>
        <input id="pfOwner" value="${esc(node.owner || '')}"></div>
      <div class="field"><label>责任部门</label>
        <input id="pfDepartment" value="${esc(node.department || '')}"></div>
    </div>
    <div class="field"><label>流程说明</label>
      <textarea id="pfDesc">${esc(node.description || '')}</textarea></div>
    <div class="row3">
      <div class="field"><label>战略重要性</label>
        <input id="pfSi" type="number" min="0" max="5" step="0.1" value="${node.strategic_importance}"></div>
      <div class="field"><label>痛点严重度</label>
        <input id="pfPain" type="number" min="0" max="5" step="0.1" value="${node.pain_score}"></div>
      <div class="field"><label>改善空间</label>
        <input id="pfSpace" type="number" min="0" max="5" step="0.1" value="${node.improvement_space}"></div>
    </div>
    <div class="row2">
      <div class="field"><label>流程健康度（0–100）</label>
        <input id="pfHealth" type="number" min="0" max="100" step="1"
          value="${node.health_score === null ? '' : node.health_score}"></div>
      <div class="field"><label>是否为待改善项</label>
        <select id="pfTarget">
          <option value="false"${node.is_improvement_target ? '' : ' selected'}>否</option>
          <option value="true"${node.is_improvement_target ? ' selected' : ''}>是</option>
        </select></div>
    </div>`,
    `<button class="btn btn-g" onclick="closeModal()">取消</button>
     <button class="btn btn-p" onclick="saveProcess(${processId})">保存</button>`);
}

async function saveProcess(processId) {
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : '';
  };
  const numOrNull = (id) => {
    const v = val(id);
    return v === '' ? null : Number(v);
  };

  const payload = {
    name: val('pfName').trim(),
    owner: val('pfOwner').trim() || null,
    department: val('pfDepartment').trim() || null,
    description: val('pfDesc').trim() || null,
    strategic_importance: Number(val('pfSi') || 3),
    pain_score: Number(val('pfPain') || 3),
    improvement_space: Number(val('pfSpace') || 3),
    is_improvement_target: val('pfTarget') === 'true',
  };
  if (processId === null) {
    payload.code = val('pfCode').trim();
    payload.level = Number(val('pfLevel'));
    payload.parent_id = val('pfParent') ? Number(val('pfParent')) : null;
  } else {
    payload.health_score = numOrNull('pfHealth');
  }

  if (!payload.name) return toast('请填写流程名称', true);
  if (processId === null && !payload.code) return toast('请填写流程编码', true);

  try {
    if (processId === null) {
      const created = await POST('/process-map', payload);
      // 新建的是顶层流程就回到根层级，否则留在当前层级（用户刚在父节点下创建）
      if (!payload.parent_id) {
        state.map.path = [];
        state.mapKeyword = '';
        const search = document.getElementById('searchInput');
        if (search) search.value = '';
      }
      closeModal();
      invalidateProcessCaches();
      toast('流程已创建：' + created.code);
    } else {
      await PATCH('/process-map/' + processId, payload);
      closeModal();
      invalidateProcessCaches();
      toast('流程已更新');
    }
    RENDERERS.map();
  } catch (e) {
    toast(e.message, true);
  }
}

async function deleteProcess(processId, code) {
  if (!confirm('确定删除流程 ' + code + '？其下级流程与流程模型会一并删除，且不可恢复。')) return;
  try {
    await DEL('/process-map/' + processId);
    closeModal();
    invalidateProcessCaches();
    toast('流程已删除');
    RENDERERS.map();
  } catch (e) {
    toast(e.message, true);
  }
}


export { renderMap, deleteProcess, editProcessModal, flattenTree, invalidateProcessCaches, mapClick, mapGo, mapJump, mapSelect, newProcessModal, openCoverageCategory, processParentOptions, refreshParentOptions, saveProcess, setBenchmarkFramework, toggleImprovement };
