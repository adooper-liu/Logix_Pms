/* 视图：map */
import { esc, num, bar, HEAT_CLASS, HEAT_LABEL, emptyRow } from '../core/format.js';
import { metricHelp } from '../core/metrics.js';
import { toast, openModal, closeModal, modalAlive, confirmDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { canManage, canWrite } from '../core/auth.js';
import { go, urlParams, setUrlState } from '../core/router.js';
import { GET, POST, PATCH, DEL, download } from '../core/api.js';
import { openDocumentCopy } from '../core/template-copy.js';
import { actions } from '../core/actions.js';

/* ============================================================ 2. 企业流程地图 */

on('map.select', ({ code }) => mapSelect(code));
on('map.go', ({ index }) => mapGo(Number(index)));
on('map.row', ({ code, kids }) => mapClick(code, kids === '1'));
on('map.coverage', ({ index }) => openCoverageCategory(Number(index)));
on('map.categoryMetrics', ({ index }) => openCategoryMetrics(Number(index)));
on('map.goProjects', () => go('projects'));
on('map.benchmarkFramework', (_data, el) => setBenchmarkFramework(el.value));
on('map.pcfWizard', () => openPcfDraftWizard());
on('map.promoteAll', () => promoteAllDrafts());
on('map.promoteOne', ({ id }) => promoteDrafts([Number(id)]));
on('map.newProcess', () => newProcessModal());
on('map.toggleImprovement', () => toggleImprovement());
on('map.toggleNav', () => toggleMapNav());
on('map.close', () => closeModal());

if (typeof window !== 'undefined') {
  window.addEventListener('pms:modal-closed', () => {
    if (state.view !== 'map' || !state.map.openCode) return;
    if (document.getElementById('mask').classList.contains('show')) return;
    state.map.openCode = null;
    setUrlState('map', {}, { push: false });
  });
}
on('map.deleteProcess', ({ id, code }) => deleteProcess(Number(id), code));
on('map.editProcess', ({ id }) => editProcessModal(Number(id)));
on('map.startProject', ({ id, name }) => startProjectFromProcess(Number(id), name));
on('map.openDesigner', ({ process }) => {
  closeModal();
  actions['designer.open'](Number(process));
});
on('map.openDocs', ({ process }) => openDocManager(Number(process)));
on('map.downloadDoc', ({ doc, version, label }) =>
  dlMapDocument(Number(doc), Number(version), label));
on('map.copyDoc', ({ doc }) => {
  closeModal();
  openDocumentCopy(Number(doc));
});
on('map.pcfFramework', (_data, el) => setPcfDraftFramework(el.value));
on('map.pcfSearch', (_data, el) => filterPcfDraftTree(el.value));
on('map.pcfCheck', ({ external }, el) => togglePcfNode(external, el.checked));
on('map.pcfPreview', () => previewPcfDraft());
on('map.pcfGenerate', () => generatePcfDraft());
on('map.pcfMode', ({ mode }) => setPcfDraftMode(mode));
on('map.guidedL1', ({ external }, el) => {
  if (el.checked) selectGuidedL1(external);
});
on('map.guidedL2', ({ external }, el) => toggleGuidedL2(external, el.checked));
on('map.guidedL3', ({ external }, el) => toggleGuidedL3(external, el.checked));
on('map.guidedRecommend', () => applyGuidedRecommendation());
on('map.refreshParents', (_data, el) => refreshParentOptions(el.value));
on('map.saveProcessNew', () => saveProcess(null));
on('map.saveProcess', ({ id }) => saveProcess(Number(id)));

const LEVEL_LABELS = {
  1: 'L1 价值链', 2: 'L2 流程类别', 3: 'L3 流程', 4: 'L4 活动', 5: 'L5 子活动',
};

/** 统计一个节点的全部下级（不含自身），按层级拆分；树的计数取 L4 活动数 */
function subtreeStats(node) {
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  const walk = (current) => {
    (current.children || []).forEach((child) => {
      counts[child.level] = (counts[child.level] || 0) + 1;
      walk(child);
    });
  };
  walk(node);
  return {
    total: counts[1] + counts[2] + counts[3] + counts[4] + counts[5],
    leaves: counts[4],
    counts,
  };
}

function subtreeTitle(stats) {
  const parts = [
    stats.counts[2] ? `L2 ${stats.counts[2]}` : '',
    stats.counts[3] ? `L3 ${stats.counts[3]}` : '',
    stats.counts[4] ? `L4 ${stats.counts[4]}` : '',
    stats.counts[5] ? `L5 ${stats.counts[5]}` : '',
  ].filter(Boolean);
  return `含 ${stats.leaves} 个 L4 活动${parts.length ? '（' + parts.join(' / ') + '）' : ''}`;
}

/** 左侧架构导航：只展开当前路径，避免一屏铺开 148 个节点 */
function renderOutline(list, path) {
  return (list || []).filter((n) => n.level <= 3).map((n) => {
    const inPath = path.includes(n.code);
    const on = path[path.length - 1] === n.code;
    const kids = inPath && n.level < 3 ? renderOutline(n.children || [], path) : '';
    const stats = subtreeStats(n);
    return `
      <button class="tree-item lv${n.level}${inPath ? ' in-path' : ''}${on ? ' on' : ''}"
           type="button" data-act="map.select" data-code="${esc(n.code)}"
           title="${esc(LEVEL_LABELS[n.level] || ('L' + n.level))}">
        <span class="tree-level">L${n.level}</span>
        <span class="tree-dot${n.is_improvement_target ? ' target' : ''}"></span>
        <span class="tree-name">${esc(n.name)}</span>
        <span class="cnt has-tip" tabindex="0"
              data-tip="${esc(subtreeTitle(stats))}">${stats.leaves || ''}</span>
      </button>${kids}`;
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
    const levelCounts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    flat.forEach((n) => { levelCounts[n.level] = (levelCounts[n.level] || 0) + 1; });
    const targetCount = flat.filter((n) => n.is_improvement_target).length;
    const draftCount = flat.filter((n) => n.is_draft).length;
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

    const crumbs = ['<a data-act="map.go" data-index="-1">全部价值链</a>']
      .concat(path.map((code, i) =>
        '<span>/</span><a data-act="map.go" data-index="' + i + '">' +
        esc(state.map.names[code] || code) + '</a>'));
    const treeHtml = `
      <button class="tree-item root${path.length === 0 ? ' on' : ''}" type="button"
        data-act="map.go" data-index="-1">
        <span class="tree-level" aria-hidden="true"></span>
        <span class="tree-dot"></span>
        <span class="tree-name">全部价值链</span>
        <span class="cnt">${tree.length}</span>
      </button>` + renderOutline(tree, path);

    const rows = shown.map((n) => {
      // 热度由后端统一判定（见 app/api/v1/process_map.py 的阈值），前端不再各算一套
      const heat = n.heat_level || 'LOW';
      const heatClass = HEAT_CLASS[heat] || HEAT_CLASS.LOW;
      const hasKids = (n.children || []).length > 0;
      return `
        <tr class="clk map-row">
          <td>
            <div class="map-name">
              <span class="tag t-gry">L${n.level}</span>
              <span class="map-code">${esc(n.code)}</span>
              <button class="map-open" type="button" data-act="map.row"
                data-code="${esc(n.code)}" data-kids="${hasKids ? '1' : '0'}">
                <b>${esc(n.name)}</b></button>
              ${n.is_improvement_target ? '<span class="tag t-red">待改善</span>' : ''}
              ${n.is_draft ? '<span class="tag t-pur">PCF 草稿</span>' : ''}
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
          <td class="map-go">
            ${n.is_draft && canManage()
              ? `<a class="link" data-act="map.promoteOne" data-id="${n.id}">确认</a> · ` : ''}
            ${n.level === 3 && canWrite()
              ? `<a class="link" data-act="map.startProject" data-id="${n.id}"
                data-name="${esc(n.name)}">立项</a> · ` : ''}
            ${hasKids ? '进入 ›' : '详情 ›'}
          </td>
        </tr>`;
    }).join('') || emptyRow(7, improvementOnly
      ? '该层级没有待改善流程，点击「显示全部」恢复'
      : '该层级下没有流程（或没有匹配结果）');

    const bench = state.map.benchmark;
    const selectedFramework = (state.map.frameworks || []).find(
      (f) => f.code === state.map.benchmarkFramework);
    const frameworkOptions = (state.map.frameworks || []).map((f) =>
      '<option value="' + f.code + '"' +
      (state.map.benchmarkFramework === f.code ? ' selected' : '') + '>' +
      esc(f.name) + (f.is_primary ? ' · 主框架' : '') +
      (f.version ? ' ' + esc(f.version) : '') + '</option>').join('');
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
          <button class="map-bench-pill" data-act="map.coverage" data-index="${i}"
            title="${esc(c.name)}${c.name_en ? ' / ' + esc(c.name_en) : ''}${
              c.metric_count ? ' · ' + c.metric_count + ' 项指标' : ''}">
            <b>${esc(c.code)}</b><span>${esc(c.name)}</span><i>${c.mapped_count}</i>
          </button>`).join('')}</div>
        ${bench.unmapped_processes.length
          ? '<div class="note">未覆盖：' + bench.unmapped_processes
            .map((p) => esc(p.code) + ' ' + esc(p.name)).join('、') +
            '（不在该框架的适用范围）</div>'
          : '<div class="note">所有 L3 流程都能在该框架中找到对应分类。</div>'}
        <div class="note">覆盖率按后代聚合；点击分类可查看明细与 PCF 指标。</div>
        ${selectedFramework && selectedFramework.description
          ? `<div class="note">${esc(selectedFramework.description)}</div>` : ''}
        ${selectedFramework && selectedFramework.attribution
          ? `<details class="note"><summary>分类框架来源与署名</summary>
              <div class="tiny" style="white-space:pre-wrap;margin-top:6px">${
                esc(selectedFramework.attribution)}</div></details>` : ''}
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
            <a class="link-btn" data-act="map.goProjects">去立项 →</a>
            <select class="sel" data-act="map.benchmarkFramework" title="切换对标框架">
              <option value="">不对标</option>
              ${frameworkOptions}
            </select>
            ${canManage()
              ? '<button class="btn-sm" data-act="map.pcfWizard">+ 从 PCF 生成</button>'
                + (draftCount
                  ? `<button class="btn-sm" data-act="map.promoteAll">确认全部草稿（${
                    draftCount}）</button>`
                  : '')
                + '<button class="btn btn-p" data-act="map.newProcess">+ 新建流程</button>'
              : '<span class="tiny">当前角色只读</span>'}
          </div>
        </div>
        <div class="map-stats">
          <span class="map-stat"><b>${flat.length}</b> ${metricHelp('process_total', '流程资产')}</span>
          <button class="map-stat${improvementOnly ? ' on' : ''}" data-act="map.toggleImprovement">
            <b>${targetCount}</b> ${metricHelp('improvement_targets', '待改善')}</button>
          <span class="map-stat"><b>${avgHealth}</b> ${metricHelp('map_avg_health', '平均健康度')}</span>
          <span class="map-stat">${metricHelp('level_counts', 'L1')} <b>${levelCounts[1]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L2')} <b>${levelCounts[2]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L3')} <b>${levelCounts[3]}</b></span>
          <span class="map-stat">${metricHelp('level_counts', 'L4')} <b>${levelCounts[4]}</b></span>
        </div>
      </div>

      <div class="map-layout${state.map.navCollapsed ? ' nav-collapsed' : ''}">
        <aside class="map-side card">
          <div class="map-side-hd">
            <span class="map-side-title">架构导航</span>
            <button class="map-side-toggle" data-act="map.toggleNav"
              title="${state.map.navCollapsed ? '展开架构导航' : '收起架构导航'}">
              <span class="map-side-toggle-icon">${state.map.navCollapsed ? '›' : '‹'}</span>
              <span class="map-side-toggle-label">${state.map.navCollapsed ? '展开' : '收起'}</span>
            </button>
          </div>
          <div class="map-tree">${treeHtml}</div>
          <div class="map-side-foot tiny">每行左侧标注 L1–L5 层级；点击层级展开；数字为本分支 L4 活动数；更深层活动在右侧列表查看。</div>
        </aside>

        <div class="map-main">
          <div class="card">
            <div class="between mb">
              <div style="min-width:0">
                <div class="crumb" style="margin-bottom:6px">${crumbs.join(' ')}</div>
                <h2 style="margin:0">${esc(title)}</h2>
                <div class="desc" style="margin:4px 0 0">${esc(desc)}</div>
              </div>
              <button class="btn-sm${improvementOnly ? ' on' : ''}" data-act="map.toggleImprovement">
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
          ${benchCard}
        </div>
      </div>`;
  };

  const start = async () => {
    const params = urlParams();
    if (params.process) state.map.pendingJump = params.process;
    else if (state.map.openCode) {
      state.map.openCode = null;
      closeModal();
    }
    if (!state.map.frameworks) {
      state.map.frameworks = await GET('/benchmark/frameworks');
    }
    if (!state.map.tree) {
      const tree = await GET('/process-map/tree');
      state.map.tree = tree;
      state.map.names = {};
      const walk = (list) => list.forEach((n) => {
        state.map.names[n.code] = n.name;
        walk(n.children || []);
      });
      walk(tree);
    }
    if (!state.map.orgs) {
      state.map.orgs = await GET('/org-units');
    }
    if (state.map.benchmarkFramework && !state.map.benchmark) {
      state.map.benchmark = await GET(
        '/benchmark/frameworks/' + state.map.benchmarkFramework + '/coverage?process_level=3');
    }
    if (state.map.openGuidedPcf) {
      state.map.openGuidedPcf = false;
      openPcfDraftWizard('guided');
    }
    const pending = state.map.pendingJump;
    state.map.pendingJump = null;
    if (pending) {
      const path = findPathTo(pending, state.map.tree || []);
      if (path) {
        state.map.path = path.slice(0, -1);
        paint();
        setTimeout(() => mapClick(pending, false), 30);
        return;
      }
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
    state.map.openCode = code;
    setUrlState('map', { process: code }, { push: true });
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
      <div id="mapDocs"></div>
      <div class="note">在「流程设计器」里可以对这条流程做泳道建模与周期效率测算。</div>`,
      `${canManage()
        ? '<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"'
          + ` data-act="map.deleteProcess" data-id="${node.id}" data-code="${esc(node.code)}">删除</button>`
        : ''}
       <button class="btn btn-g" data-act="map.close">关闭</button>
       ${canManage() ? `<button class="btn btn-g" data-act="map.editProcess" data-id="${node.id}">编辑</button>` : ''}
       ${canWrite() ? `<button class="btn btn-g" data-act="map.startProject" data-id="${node.id}"
         data-name="${esc(node.name)}">以此流程立项</button>` : ''}
       <button class="btn btn-p" data-act="map.openDesigner" data-process="${node.id}">去设计器分析</button>`);
    loadProcessDocs(node.id);
  }
}

/** 详情弹窗里的「配套文件」：本节点 + 上级继承，只读查看/下载，管理入口跳到标准文件页签 */
async function loadProcessDocs(processId) {
  const box = document.getElementById('mapDocs');
  if (!box) return;
  box.innerHTML = '<div class="tiny mt">加载配套文件…</div>';
  try {
    const rows = await GET(
      '/process-documents?process_id=' + processId + '&include_ancestors=true');
    if (!box.isConnected) return;
    const header = `<div class="between mt mb">
      <h3 style="margin:0">配套文件（标准）</h3>
      <button class="btn-sm" data-act="map.openDocs" data-process="${processId}">管理配套文件 →</button></div>`;
    if (!rows.length) {
      box.innerHTML = header + `<div class="note">该流程及其上级还没有标准文件。
        可以在「交付物与模板库 → 流程标准文件」创建并审批，生效后这里会出现复制入口。</div>`;
      return;
    }
    box.innerHTML = header + `
      <table class="tbl">
        <thead><tr><th>文件</th><th>类型</th><th>现行版本</th><th>归属流程</th><th>操作</th></tr></thead>
        <tbody>${rows.map((doc) => {
          const v = doc.effective_version;
          return `<tr>
            <td><b>${esc(doc.title)}</b><div class="tiny">${esc(doc.code)}</div></td>
            <td><span class="tag t-gry">${esc(doc.category_label || doc.category)}</span></td>
            <td>${v
              ? `<b>${esc(v.version_display)}</b> <span class="tag t-grn">${esc(v.status_label)}</span>`
              : '<span class="tag t-gry">无生效版本</span>'}</td>
            <td>${esc(doc.process_code || '')} ${esc(doc.process_name || '')}
              ${doc.process_id !== processId ? '<div class="tiny">上级继承</div>' : ''}</td>
            <td>${v && v.has_file
              ? `<span class="gap" style="gap:6px">
                  <button class="btn-sm" data-act="map.downloadDoc" data-doc="${doc.id}"
                    data-version="${v.id}" data-label="${esc(v.version_display)}">下载</button>
                  ${canWrite()
                    ? `<button class="btn-sm" data-act="map.copyDoc"
                      data-doc="${doc.id}">复制到项目</button>`
                    : ''}
                </span>`
              : '—'}</td>
          </tr>`;
        }).join('')}</tbody>
      </table>
      <div class="tiny mt">「复制到项目」会固定当前生效版本；只对已生效且有文件的版本开放。</div>`;
  } catch (e) {
    if (box.isConnected) {
      box.innerHTML = '<div class="errbar"><div>' + esc(e.message) + '</div></div>';
    }
  }
}

function openDocManager(processId) {
  state.deliverables.tab = 'document';
  state.deliverables.documentProcessId = processId;
  closeModal();
  go('deliverables');
}

async function dlMapDocument(documentId, versionId, label) {
  try {
    await download(
      '/process-documents/' + documentId + '/versions/' + versionId + '/download',
      '标准文件' + (label || ''),
    );
    toast('已开始下载');
  } catch (e) {
    toast(e.message, true);
  }
}

/** 地图 → 立项：带着流程进入项目向导 */
function startProjectFromProcess(processId, processName) {
  go('projects', {
    params: { new_process: processId, new_name: processName },
    push: true,
  });
}

function mapGo(index) {
  state.map.path = index < 0 ? [] : state.map.path.slice(0, index + 1);
  RENDERERS.map();
}

/** 折叠/展开左侧架构导航；状态保存在 state.map，切换路由后仍保持 */
function toggleMapNav() {
  state.map.navCollapsed = !state.map.navCollapsed;
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

/* -------------------------------------------------- 从 PCF 生成架构草稿 */

const pcfDraft = {
  gen: 0,
  framework: 'APQC_PCF',
  tree: [],
  selected: new Set(),
  open: new Set(),
  keyword: '',
  mode: 'expert',
  guidedL1: null,
  guidedL2: new Set(),
};

function pcfFrameworkOptions() {
  return (state.map.frameworks || [])
    .filter((f) => f.code === 'APQC_PCF' || f.base_framework_code === 'APQC_PCF')
    .map((f) => `<option value="${f.code}"${
      f.code === pcfDraft.framework ? ' selected' : ''}>${esc(f.name)}${
      f.version ? ' ' + esc(f.version) : ''}</option>`)
    .join('');
}

function openPcfDraftWizard(mode = 'expert') {
  const primary = (state.map.frameworks || []).find((f) => f.is_primary);
  pcfDraft.framework = primary ? primary.code : 'APQC_PCF';
  pcfDraft.selected = new Set();
  pcfDraft.open = new Set();
  pcfDraft.keyword = '';
  pcfDraft.tree = [];
  pcfDraft.mode = mode === 'guided' ? 'guided' : 'expert';
  pcfDraft.guidedL1 = null;
  pcfDraft.guidedL2 = new Set();
  pcfDraft.gen = openModal('从 PCF 生成流程架构草稿', `
    <div class="row2">
      <div class="field"><label>分类框架</label>
        <select class="sel" id="pcfFramework" data-act="map.pcfFramework">
          ${pcfFrameworkOptions()}
        </select></div>
      <div class="field"><label>生成范围</label>
        <label class="pcf-label"><input type="checkbox" id="pcfActivities" checked>
          <span>同时生成 L4 活动（不勾选只生成 L3）</span></label></div>
    </div>
    <div class="seg mb">
      <button class="${pcfDraft.mode === 'expert' ? 'on' : ''}"
        data-act="map.pcfMode" data-mode="expert">专家模式</button>
      <button class="${pcfDraft.mode === 'guided' ? 'on' : ''}"
        data-act="map.pcfMode" data-mode="guided">1+3+10 引导</button>
    </div>
    <div id="pcfExpertPanel" class="${pcfDraft.mode === 'guided' ? 'hide' : ''}">
      <div class="field"><label>搜索分类</label>
        <input id="pcfSearch" placeholder="按编码、中文名或英文名过滤"
          data-act="map.pcfSearch"></div>
      <div id="pcfTree" class="pcf-tree"><div class="empty">加载中…</div></div>
      <div class="tiny muted">勾选 L1/L2 会选中其下全部 L3；生成时自动补齐上级 L1/L2。</div>
    </div>
    <div id="pcfGuidedPanel" class="${pcfDraft.mode === 'guided' ? '' : 'hide'}">
      <div class="note mb">推荐先选 <b>1 个 L1、3 个 L2、10 个 L3</b>，
        少选也能生成；目标不是一次建全，而是先跑通一段。</div>
      <div id="pcfGuided"><div class="empty">加载中…</div></div>
    </div>
    <div id="pcfPreview" class="pcf-preview">生成时会自动补齐上级 L1/L2。</div>`,
  `<button class="btn btn-g" data-act="map.close">取消</button>
   <button class="btn btn-g" data-act="map.pcfPreview">预览</button>
   <button class="btn btn-p" data-act="map.pcfGenerate">生成草稿</button>`, true);
  loadPcfDraftTree(pcfDraft.gen);
}

async function loadPcfDraftTree(gen) {
  try {
    const tree = await GET(
      '/benchmark/frameworks/' + encodeURIComponent(pcfDraft.framework) + '/tree?max_level=3');
    if (!modalAlive(gen)) return;
    pcfDraft.tree = tree;
    renderPcfDraftTree();
    renderGuidedPanel();
    resetPcfPreview();
  } catch (e) {
    if (modalAlive(gen)) {
      document.getElementById('pcfTree').innerHTML =
        `<div class="empty">${esc(e.message)}</div>`;
    }
  }
}

function setPcfDraftFramework(code) {
  pcfDraft.framework = code;
  pcfDraft.selected = new Set();
  pcfDraft.tree = [];
  const box = document.getElementById('pcfTree');
  if (box) box.innerHTML = '<div class="empty">加载中…</div>';
  resetPcfPreview();
  loadPcfDraftTree(pcfDraft.gen);
}

function pcfNodeMatches(node, keyword) {
  if (!keyword) return true;
  const text = [node.code, node.name, node.name_en, node.external_id]
    .filter(Boolean).join(' ').toLowerCase();
  return text.includes(keyword);
}

/** 取节点下全部 L3 的 PCF ID；L3 自身返回自己。 */
function pcfLeafIds(node, out) {
  if (node.level === 3) {
    if (node.external_id) out.push(node.external_id);
    return out;
  }
  (node.children || []).forEach((child) => pcfLeafIds(child, out));
  return out;
}

function pcfGroupSelected(node) {
  const ids = pcfLeafIds(node, []);
  return ids.length > 0 && ids.every((id) => pcfDraft.selected.has(id));
}

function pcfLeafHtml(node) {
  const checked = pcfDraft.selected.has(node.external_id) ? ' checked' : '';
  return `<div class="pcf-leaf"><label class="pcf-label" data-pcf-stop>
    <input type="checkbox"${checked} data-act="map.pcfCheck"
      data-external="${esc(node.external_id)}">
    <span class="map-code">${esc(node.code)}</span><span>${esc(node.name)}</span>
    ${node.name_en ? `<span class="tiny">${esc(node.name_en)}</span>` : ''}
  </label></div>`;
}

function pcfGroupHtml(node, keyword) {
  const selfMatch = pcfNodeMatches(node, keyword);
  const children = (node.children || []).filter((child) =>
    selfMatch || pcfNodeMatches(child, keyword)
    || (child.children || []).some((leaf) => pcfNodeMatches(leaf, keyword)));
  if (!children.length) return '';
  const checked = pcfGroupSelected(node) ? ' checked' : '';
  const body = children.map((child) => (child.level === 3
    ? (selfMatch || pcfNodeMatches(child, keyword) ? pcfLeafHtml(child) : '')
    : pcfGroupHtml(child, selfMatch ? '' : keyword))).join('');
  if (!body) return '';
  const openAttr = keyword || pcfDraft.open.has(node.external_id) ? ' open' : '';
  return `<details class="pcf-node"${openAttr} data-pcf="${esc(node.external_id)}">
    <summary><label class="pcf-label" data-pcf-stop>
      <input type="checkbox"${checked} data-act="map.pcfCheck"
        data-external="${esc(node.external_id)}">
      <span class="map-code">${esc(node.code)}</span><span>${esc(node.name)}</span>
      ${node.name_en ? `<span class="tiny">${esc(node.name_en)}</span>` : ''}
    </label></summary>${body}</details>`;
}

function rememberPcfOpen(details) {
  const code = details.getAttribute('data-pcf');
  if (!code) return;
  if (details.open) pcfDraft.open.add(code);
  else pcfDraft.open.delete(code);
}

function renderPcfDraftTree() {
  const box = document.getElementById('pcfTree');
  if (!box) return;
  const keyword = (pcfDraft.keyword || '').trim().toLowerCase();
  const html = pcfDraft.tree
    .filter((node) => pcfNodeMatches(node, keyword) || (node.children || []).some(
      (child) => pcfNodeMatches(child, keyword)
        || (child.children || []).some((leaf) => pcfNodeMatches(leaf, keyword))))
    .map((node) => pcfGroupHtml(node, keyword)).join('');
  box.innerHTML = html || '<div class="empty">没有匹配的分类</div>';
  bindPcfTreeEvents(box);
}

/** toggle 不冒泡，且 label 点击会误触 details；在树容器上挂一次捕获监听。 */
function bindPcfTreeEvents(box) {
  if (!box || box.dataset.pcfBound) return;
  box.dataset.pcfBound = '1';
  box.addEventListener('click', (event) => {
    if (event.target.closest && event.target.closest('[data-pcf-stop]')) {
      event.stopPropagation();
    }
  }, true);
  box.addEventListener('toggle', (event) => {
    if (event.target.matches && event.target.matches('details[data-pcf]')) {
      rememberPcfOpen(event.target);
    }
  }, true);
}

function filterPcfDraftTree(value) {
  pcfDraft.keyword = value;
  renderPcfDraftTree();
}

function findPcfNode(nodes, externalId) {
  for (const node of nodes) {
    if (node.external_id === externalId) return node;
    const hit = findPcfNode(node.children || [], externalId);
    if (hit) return hit;
  }
  return null;
}

function togglePcfNode(externalId, checked) {
  const node = findPcfNode(pcfDraft.tree, externalId);
  if (!node) return;
  const ids = pcfLeafIds(node, []);
  ids.forEach((id) => (checked ? pcfDraft.selected.add(id) : pcfDraft.selected.delete(id)));
  renderPcfDraftTree();
  resetPcfPreview();
}

function resetPcfPreview() {
  const box = document.getElementById('pcfPreview');
  if (box) {
    box.textContent = `已选 ${pcfDraft.selected.size} 个 L3 分类；`
      + '生成时自动补齐上级 L1/L2。';
  }
}

/* -------------------------------------------------- 1+3+10 引导 */

function setPcfDraftMode(mode) {
  pcfDraft.mode = mode === 'guided' ? 'guided' : 'expert';
  document.querySelectorAll('#mBody [data-act="map.pcfMode"]').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.mode === pcfDraft.mode);
  });
  const expert = document.getElementById('pcfExpertPanel');
  const guided = document.getElementById('pcfGuidedPanel');
  if (expert) expert.classList.toggle('hide', pcfDraft.mode !== 'expert');
  if (guided) guided.classList.toggle('hide', pcfDraft.mode !== 'guided');
  if (pcfDraft.mode === 'guided') renderGuidedPanel();
}

function guidedL1Node() {
  return (pcfDraft.tree || []).find(
    (node) => node.level === 1 && node.external_id === pcfDraft.guidedL1) || null;
}

function guidedL2Nodes() {
  const l1 = guidedL1Node();
  return l1 ? (l1.children || []).filter((node) => node.level === 2) : [];
}

function guidedL3Nodes() {
  const out = [];
  guidedL2Nodes().forEach((l2) => {
    if (!pcfDraft.guidedL2.has(l2.external_id)) return;
    (l2.children || []).forEach((l3) => {
      if (l3.level === 3) out.push(l3);
    });
  });
  return out;
}

function renderGuidedPanel() {
  const box = document.getElementById('pcfGuided');
  if (!box) return;
  const l1Nodes = (pcfDraft.tree || []).filter((node) => node.level === 1);
  const l2Nodes = guidedL2Nodes();
  const l3Nodes = guidedL3Nodes();
  const l1Html = l1Nodes.map((node) => `
    <label class="pcf-label">
      <input type="radio" name="pcfGuidedL1"${
        pcfDraft.guidedL1 === node.external_id ? ' checked' : ''}
        data-act="map.guidedL1" data-external="${esc(node.external_id)}">
      <span class="map-code">${esc(node.code)}</span><span>${esc(node.name)}</span>
    </label>`).join('');
  const l2Html = l2Nodes.map((node) => `
    <label class="pcf-label">
      <input type="checkbox"${pcfDraft.guidedL2.has(node.external_id) ? ' checked' : ''}
        data-act="map.guidedL2" data-external="${esc(node.external_id)}">
      <span class="map-code">${esc(node.code)}</span><span>${esc(node.name)}</span>
    </label>`).join('');
  const l3Html = l3Nodes.map((node) => `
    <label class="pcf-label">
      <input type="checkbox"${pcfDraft.selected.has(node.external_id) ? ' checked' : ''}
        data-act="map.guidedL3" data-external="${esc(node.external_id)}">
      <span class="map-code">${esc(node.code)}</span><span>${esc(node.name)}</span>
    </label>`).join('');
  box.innerHTML = `
    <div class="pcf-step">
      <h4>第 1 步：选 1 个 L1
        <span class="pcf-count">${pcfDraft.guidedL1 ? '已选 1/1' : '还没选'}</span></h4>
      <div class="pcf-list">${l1Html || '<div class="tiny muted">没有可用的 L1</div>'}</div>
    </div>
    <div class="pcf-step">
      <h4>第 2 步：选 L2
        <span class="pcf-count">已选 ${pcfDraft.guidedL2.size}/3（推荐）</span>
        ${pcfDraft.guidedL1
          ? '<button class="btn-sm" data-act="map.guidedRecommend">套用推荐</button>' : ''}</h4>
      <div class="pcf-list">${pcfDraft.guidedL1
        ? (l2Html || '<div class="tiny muted">该 L1 下没有 L2</div>')
        : '<div class="tiny muted">先选一个 L1</div>'}</div>
    </div>
    <div class="pcf-step">
      <h4>第 3 步：选 L3
        <span class="pcf-count">已选 ${pcfDraft.selected.size}/10（推荐）</span></h4>
      <div class="pcf-list">${pcfDraft.guidedL2.size
        ? (l3Html || '<div class="tiny muted">所选 L2 下没有 L3</div>')
        : '<div class="tiny muted">先选 L2，再从这里挑 L3</div>'}</div>
    </div>`;
}

function selectGuidedL1(external) {
  pcfDraft.guidedL1 = external;
  pcfDraft.guidedL2 = new Set();
  pcfDraft.selected = new Set();
  resetPcfPreview();
  renderGuidedPanel();
}

function toggleGuidedL2(external, checked) {
  const l2 = guidedL2Nodes().find((node) => node.external_id === external);
  if (!l2) return;
  if (checked) {
    pcfDraft.guidedL2.add(external);
  } else {
    pcfDraft.guidedL2.delete(external);
    (l2.children || []).forEach((l3) => pcfDraft.selected.delete(l3.external_id));
  }
  resetPcfPreview();
  renderGuidedPanel();
}

function toggleGuidedL3(external, checked) {
  if (checked) pcfDraft.selected.add(external);
  else pcfDraft.selected.delete(external);
  resetPcfPreview();
  renderGuidedPanel();
}

function applyGuidedRecommendation() {
  const l1Nodes = (pcfDraft.tree || []).filter((node) => node.level === 1);
  if (!pcfDraft.guidedL1 && l1Nodes.length) {
    pcfDraft.guidedL1 = l1Nodes[0].external_id;
  }
  const l2s = guidedL2Nodes().slice(0, 3);
  pcfDraft.guidedL2 = new Set(l2s.map((node) => node.external_id));
  const l3Ids = [];
  l2s.forEach((l2) => (l2.children || []).forEach((l3) => {
    if (l3.level === 3 && l3.external_id) l3Ids.push(l3.external_id);
  }));
  pcfDraft.selected = new Set(l3Ids.slice(0, 10));
  resetPcfPreview();
  renderGuidedPanel();
}

function pcfRequestPayload() {
  const activities = document.getElementById('pcfActivities');
  return {
    framework_code: pcfDraft.framework,
    external_ids: Array.from(pcfDraft.selected),
    include_activities: !activities || activities.checked,
  };
}

async function previewPcfDraft() {
  if (!pcfDraft.selected.size) return toast('请至少勾选一个 L3 分类', true);
  try {
    const data = await POST('/process-map/pcf/preview', pcfRequestPayload());
    const byLevel = data.by_level || {};
    const text = [1, 2, 3, 4].map((level) => {
      const row = byLevel[String(level)] || { create: 0, reuse: 0 };
      return `L${level} 新建 ${row.create} / 复用 ${row.reuse}`;
    }).join(' · ');
    const box = document.getElementById('pcfPreview');
    if (box) {
      box.innerHTML = `<b>将新建 ${data.create_count} 个、复用 ${data.reuse_count} 个</b>`
        + `<div class="tiny">${text}</div>`
        + `<div class="tiny">${esc(data.framework_name)} ${esc(data.framework_version || '')}</div>`;
    }
  } catch (e) {
    toast(e.message, true);
  }
}

async function generatePcfDraft() {
  if (!pcfDraft.selected.size) return toast('请至少勾选一个 L3 分类', true);
  const ok = await confirmDialog(
    `按当前选择生成 ${pcfDraft.selected.size} 个 L3 分类的流程草稿？`,
    { title: '生成流程草稿', okText: '生成' });
  if (!ok) return;
  try {
    const data = await POST('/process-map/pcf/generate', pcfRequestPayload());
    closeModal();
    invalidateProcessCaches();
    toast(data.create_count
      ? `已生成 ${data.create_count} 个草稿${data.reuse_count ? `，复用 ${data.reuse_count} 个` : ''}`
      : `没有新增节点（${data.reuse_count} 个已存在）`);
    RENDERERS.map();
  } catch (e) {
    toast(e.message, true);
  }
}

async function promoteDrafts(ids) {
  if (!ids || !ids.length) return;
  const ok = await confirmDialog(`确认 ${ids.length} 个流程草稿？确认后按正式流程参与统计。`,
    { title: '确认流程草稿', okText: '确认' });
  if (!ok) return;
  try {
    const data = await POST('/process-map/drafts/promote', { process_ids: ids });
    toast(`已确认 ${data.updated} 个草稿`);
    invalidateProcessCaches();
    RENDERERS.map();
  } catch (e) {
    toast(e.message, true);
  }
}

function promoteAllDrafts() {
  const ids = flattenTree(state.map.tree || [])
    .filter((node) => node.is_draft)
    .map((node) => node.id);
  promoteDrafts(ids);
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
  const description = c.description
    ? `<div class="note">${esc(c.description)}</div>` : '';
  const processTable = c.processes.length ? `
    <table class="tbl">
      <thead><tr><th>编码</th><th>流程</th><th>层级</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>` : '<div class="empty">该分类下没有已映射流程</div>';
  const metricButton = c.external_id && c.metric_count
    ? `<button class="btn btn-g" data-act="map.categoryMetrics" data-index="${index}">查看 PCF 指标（${
      c.metric_count}）</button>` : '';
  openModal(`${c.code} ${c.name}${c.name_en ? ' · ' + c.name_en : ''} · 覆盖流程`,
    description + processTable,
    metricButton + '<button class="btn btn-g" data-act="map.close">关闭</button>');
}

async function openCategoryMetrics(index) {
  const c = state.map.benchmark && state.map.benchmark.by_top_category[index];
  if (!c) return;
  const gen = openModal('加载指标…', '<div class="empty">加载中…</div>');
  try {
    const data = await GET('/benchmark/categories/' + c.category_id + '/metrics');
    if (!modalAlive(gen)) return;
    const rows = data.metrics.map((m) => `
      <tr><td class="tiny">${esc(m.metric_id)}</td>
        <td>${esc(m.name)}</td>
        <td class="tiny">${esc(m.metric_category || '—')}</td>
        <td class="tiny">${esc(m.formula || '—')}</td>
        <td class="tiny">${esc(m.unit || '—')}</td></tr>`).join('')
      || emptyRow(5, '该分类没有配置 PCF 指标');
    openModal(`${data.code} ${data.name} · PCF 指标`, `
      ${data.name_en ? `<div class="note">${esc(data.name_en)}</div>` : ''}
      <table class="tbl">
        <thead><tr><th>指标 ID</th><th>指标</th><th>类别</th><th>公式</th><th>单位</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`,
    '<button class="btn btn-g" data-act="map.close">关闭</button>', true);
  } catch (e) {
    if (modalAlive(gen)) toast(e.message, true);
  }
}

/* -------------------------------------------------- 流程架构的写入口 */

/** 写操作会让地图树、设计器下拉的缓存失效 */
function invalidateProcessCaches() {
  state.map.tree = null;
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

function mapOrgOptions(selected) {
  return (state.map.orgs || []).map((org) =>
    `<option value="${org.id}"${String(selected) === String(org.id) ? ' selected' : ''}>${
      esc(org.code)} · ${esc(org.name)}</option>`).join('');
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
        <select id="pfLevel" data-act="map.refreshParents">
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
      <div class="field"><label>归属组织</label>
        <select class="sel" id="pfOrg"><option value="">未指定</option>${mapOrgOptions(null)}</select></div>
    </div>
    <div class="field"><label>责任部门（展示标签）</label>
      <input id="pfDepartment" placeholder="如：采购部"></div>
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
    `<button class="btn btn-g" data-act="map.close">取消</button>
     <button class="btn btn-p" data-act="map.saveProcessNew">创建</button>`);
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
      <div class="field"><label>归属组织</label>
        <select class="sel" id="pfOrg"><option value="">未指定</option>${
          mapOrgOptions(node.org_unit_id)}</select></div>
    </div>
    <div class="field"><label>责任部门（展示标签）</label>
      <input id="pfDepartment" value="${esc(node.department || '')}"></div>
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
    `<button class="btn btn-g" data-act="map.close">取消</button>
     <button class="btn btn-p" data-act="map.saveProcess" data-id="${processId}">保存</button>`);
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
    org_unit_id: val('pfOrg') ? Number(val('pfOrg')) : null,
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
  const ok = await confirmDialog(
    `确定删除流程 ${code}？其下级流程与流程模型会一并删除，且不可恢复。`,
    { danger: true, okText: '删除' });
  if (!ok) return;
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


export { renderMap };
