/* 视图：map */
import { esc, num, bar, tipHelp, HEAT_CLASS, HEAT_LABEL, emptyRow } from '../core/format.js';
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
on('map.goSketches', () => go('sketches'));
on('map.benchmarkFramework', (_data, el) => setBenchmarkFramework(el.value));
on('map.pcfWizard', () => openPcfDraftWizard());
on('map.promoteAll', () => promoteAllDrafts());
on('map.promoteOne', ({ id }) => promoteDrafts([Number(id)]));
on('map.newProcess', () => newProcessModal());
on('map.newChild', ({ parent }) => newChildModal(parent ? Number(parent) : null));
on('map.activityFramework', (_data, el) => loadActivityBenchmarkCategories(el.value));
on('map.activityBenchPick', ({ id }, el) => applyActivityBenchmarkPick(id || el.value));
on('map.benchTreeToggle', ({ id }) => toggleBenchTreeGroup(id));
on('map.benchFilter', (_data, el) => {
  activityCreate.benchFilter = el.value || '';
  paintActivityBenchmarkOptions();
});
on('map.benchClear', () => applyActivityBenchmarkPick(''));
on('map.scoreChanged', () => syncScorePreview());
on('map.inheritParentScores', (_data, el) => applyInheritParentScores(!!el.checked));
on('map.orgChanged', (_data, el) => onProcessOrgChanged(el.value));
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
    const ownerList = !!state.map.ownerList && path.length === 0;
    let shown = ownerList
      ? flattenTree(tree).filter((n) => n.level === 3 && n.owner_user_id)
      : nodes;
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
    const title = ownerList ? 'L3 已绑定负责人' : (current ? current.name : '全部价值链');
    const desc = ownerList
      ? `只计 L3，并且负责人已经绑到账号。这里是这 ${shown.length} 条`
      : current
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
            <button class="map-go-btn" type="button" data-act="map.row"
              data-code="${esc(n.code)}" data-kids="${hasKids ? '1' : '0'}">${
              hasKids ? '进入 ›' : '详情 ›'}</button>
          </td>
        </tr>`;
    }).join('') || emptyRow(7, ownerList
      ? '还没有绑定负责人账号的 L3'
      : improvementOnly
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
            <a class="link-btn" data-act="map.goSketches">架构草图</a>
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
                + '<button class="btn-sm" data-act="map.newProcess" title="跨层新建，需自选层级与上级">跨层新建</button>'
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
              <div class="gap">
                ${!ownerList && canManage() && (!current || current.level < 4)
                  ? `<button class="btn btn-p" data-act="map.newChild"
                      data-parent="${current ? current.id : ''}">+ ${
                      esc(LEVEL_LABELS[(current ? current.level : 0) + 1])}</button>`
                  : ''}
                <button class="btn-sm${improvementOnly ? ' on' : ''}"
                  data-act="map.toggleImprovement">
                  ${improvementOnly ? '显示全部' : '只看待改善'}</button>
              </div>
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
    state.map.ownerList = params.owners === 'l3';
    if (state.map.ownerList) state.map.path = [];
    if (params.benchmark && params.benchmark !== '0') {
      const frameworks = state.map.frameworks || [];
      const wanted = params.benchmark === '1'
        ? (frameworks.find(
          (f) => f.code === 'APQC_PCF' || f.base_framework_code === 'APQC_PCF') || {}).code
        : (frameworks.some((f) => f.code === params.benchmark) ? params.benchmark : '');
      if (wanted && state.map.benchmarkFramework !== wanted) {
        state.map.benchmarkFramework = wanted;
        state.map.benchmark = null;
      }
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
    if (!state.map.users) {
      state.map.users = await GET('/execution/assignees');
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
  if (state.map.ownerList) {
    const path = findPathTo(code, state.map.tree || [], []);
    if (!path) return;
    dropOwnerList();
    if (hasKids) {
      state.map.path = path;
      RENDERERS.map();
      return;
    }
    state.map.path = path.slice(0, -1);
  }
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
    const orgRow = (state.map.orgs || []).find(
      (org) => String(org.id) === String(node.org_unit_id),
    );
    const orgName = node.org_unit_name
      || (orgRow ? `${orgRow.code} · ${orgRow.name}` : '')
      || '未指定';
    openModal(node.name + ' · ' + node.code, `
      <div class="form-compact">
        <section class="form-block">
          <h4 class="form-block-hd">1. 基本信息</h4>
          <div class="row3">
            <div class="field"><label>流程编码</label>
              <input value="${esc(node.code)}" readonly></div>
            <div class="field"><label>流程层级</label>
              <input value="L${node.level}" readonly></div>
            <div class="field"><label>待改善项 ${
              tipHelp(IMPROVEMENT_TARGET_TIP, '待改善项说明')}</label>
              <input value="${node.is_improvement_target ? '是' : '否'}" readonly></div>
          </div>
        </section>
        <section class="form-block">
          <h4 class="form-block-hd">2. 组织与责任</h4>
          <div class="row3">
            <div class="field"><label>归属组织</label>
              <input value="${esc(orgName)}" readonly></div>
            <div class="field"><label>流程 Owner</label>
              <input value="${esc(node.owner || '未指定')}" readonly></div>
            <div class="field"><label>责任部门</label>
              <input value="${esc(node.department || '—')}" readonly></div>
          </div>
        </section>
        <section class="form-block">
          <h4 class="form-block-hd">3. 说明与评估</h4>
          <div class="field"><label>流程说明</label>
            <textarea readonly>${esc(node.description || '')}</textarea></div>
          <div class="row2">
            <div class="field"><label>${metricHelp('priority_score', '综合优先级得分')}</label>
              <input value="${num(node.priority_score, 1)}" readonly>
              <div class="hint">重要性 × 痛点 × 改善空间</div></div>
            <div class="field"><label>${metricHelp('health_score', '流程健康度')}</label>
              <input value="${node.health_score === null
                ? '未评估' : num(node.health_score, 0) + ' 分'}" readonly></div>
          </div>
          <div class="row3">
            <div class="field"><label>战略重要性</label>
              <input value="${num(node.strategic_importance, 1)} / 5" readonly></div>
            <div class="field"><label>痛点严重度</label>
              <input value="${num(node.pain_score, 1)} / 5" readonly></div>
            <div class="field"><label>改善空间</label>
              <input value="${num(node.improvement_space, 1)} / 5" readonly></div>
          </div>
        </section>
        <section class="form-block">
          <h4 class="form-block-hd">4. 对标映射</h4>
          <div id="mapBenchMaps"><div class="tiny">加载对标映射…</div></div>
        </section>
        <section class="form-block">
          <div id="mapDocs"></div>
          <div class="note" style="margin-top:10px;margin-bottom:0">在「流程设计器」里可以对这条流程做泳道建模与周期效率测算。</div>
        </section>
      </div>`,
      `${canManage()
        ? '<button class="btn btn-g" style="margin-right:auto;color:var(--bad-strong)"'
          + ` data-act="map.deleteProcess" data-id="${node.id}" data-code="${esc(node.code)}">删除</button>`
        : ''}
       <button class="btn btn-g" data-act="map.close">关闭</button>
       ${canManage() ? `<button class="btn btn-g" data-act="map.editProcess" data-id="${node.id}">编辑</button>` : ''}
       ${canWrite() ? `<button class="btn btn-g" data-act="map.startProject" data-id="${node.id}"
         data-name="${esc(node.name)}">以此流程立项</button>` : ''}
       <button class="btn btn-p" data-act="map.openDesigner" data-process="${node.id}">去设计器分析</button>`,
      'sheet');
    loadProcessBenchmarkMaps(node.id);
    loadProcessDocs(node.id);
  }
}

/** 详情弹窗里的对标映射（只读）；新建时可写，创建后在这里回看。 */
async function loadProcessBenchmarkMaps(processId) {
  const box = document.getElementById('mapBenchMaps');
  if (!box) return;
  try {
    const data = await GET('/benchmark/processes/' + processId + '/mappings');
    if (!box.isConnected) return;
    const rows = data.mappings || [];
    if (!rows.length) {
      box.innerHTML = '<div class="note" style="margin:0">尚未关联对标分类；可在编辑或重建下级时选择标准分类。</div>';
      return;
    }
    box.innerHTML = `<div class="bench-pick" style="max-height:140px">${rows.map((row) =>
      `<div class="bench-pick-leaf" style="cursor:default">
        <span class="bench-code">${esc(row.framework_code || '')}</span>
        <span class="bench-name">${esc(row.category_code || '')} · ${
          esc(row.category_name || '')}</span>
      </div>`).join('')}</div>`;
  } catch (e) {
    if (!box.isConnected) return;
    box.innerHTML = `<div class="note">${esc(e.message || '对标映射加载失败')}</div>`;
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
  dropOwnerList();
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
  dropOwnerList();
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
  const current = urlParams();
  const next = {};
  if (current.process) next.process = current.process;
  if (current.owners === 'l3') next.owners = 'l3';
  if (code) next.benchmark = code;
  setUrlState('map', next, { push: false });
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

function dropOwnerList() {
  if (!state.map.ownerList && urlParams().owners !== 'l3') return;
  state.map.ownerList = false;
  const current = urlParams();
  const next = {};
  if (current.process) next.process = current.process;
  if (current.benchmark) next.benchmark = current.benchmark;
  setUrlState('map', next, { push: false });
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

/** 选中组织及其上级、下级（集团→分公司→部门继承范围）。 */
function orgLineageIds(orgId) {
  if (!orgId) return null;
  const orgs = state.map.orgs || [];
  const selected = orgs.find((org) => String(org.id) === String(orgId));
  if (!selected) return new Set([Number(orgId)]);
  const ids = new Set([selected.id]);
  const selPath = selected.path || '';
  orgs.forEach((org) => {
    const path = org.path || '';
    if (!selPath || selPath === '/') return;
    if (path.startsWith(selPath)) ids.add(org.id);
    if (path !== '/' && selPath.startsWith(path)) ids.add(org.id);
  });
  return ids;
}

function mapOwnerOptions(selected, orgId) {
  const scope = orgLineageIds(orgId);
  return (state.map.users || []).filter((user) => {
    if (user.is_active === false) return false;
    if (!scope) return true;
    if (user.org_unit_id == null) return false;
    return scope.has(user.org_unit_id);
  }).map((user) =>
    `<option value="${user.id}"${String(selected) === String(user.id) ? ' selected' : ''}>${
      esc(user.display_name)} · ${esc(user.role_label || user.role)}${
      user.org_unit_name ? ' · ' + esc(user.org_unit_name) : ''}</option>`).join('');
}

function paintProcessOwnerSelect(selected, orgId) {
  const sel = document.getElementById('pfOwnerUser');
  if (!sel) return;
  const keep = selected != null ? selected : sel.value;
  const options = mapOwnerOptions(null, orgId);
  sel.innerHTML = '<option value="">未指定</option>' + options;
  if (keep && [...sel.options].some((opt) => opt.value === String(keep))) {
    sel.value = String(keep);
  } else {
    sel.value = '';
  }
  setFieldTip(
    'pfOwnerTip',
    orgId
      ? '仅列出该组织及其上下级中的账号（集团→分公司→部门）'
      : '先选归属组织，再选 Owner；未选组织时列出全部可指派账号',
  );
}

function onProcessOrgChanged(orgId) {
  const org = (state.map.orgs || []).find((row) => String(row.id) === String(orgId));
  const dept = document.getElementById('pfDepartment');
  if (dept && org && !dept.value.trim()) dept.value = org.name;
  paintProcessOwnerSelect(null, orgId || null);
}

async function ensureMapUsers() {
  if (state.map.users) return;
  state.map.users = await GET('/execution/assignees');
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

/* -------------------------------------------------- 当前层下新建下级（L3/L4 可对标） */

const activityCreate = {
  categories: [],
  parentId: null,
  parentName: '',
  parentLevel: null,
  childLevel: 4,
  parentMappings: [],
  nameSuggestions: [],
  scopeMode: 'none', // none | mapping | name
  benchFilter: '',
  benchExpanded: new Set(),
  benchExpandedReady: false,
};

function resetBenchPickerState() {
  activityCreate.benchFilter = '';
  activityCreate.benchExpanded = new Set();
  activityCreate.benchExpandedReady = false;
  activityCreate.nameSuggestions = [];
  activityCreate.scopeMode = 'none';
}

function suggestNextCode(siblings, level) {
  const re = new RegExp('^L' + level + '-(\\d+)$', 'i');
  let max = 0;
  (siblings || []).forEach((child) => {
    const match = String(child.code || '').match(re);
    if (match) max = Math.max(max, Number(match[1]));
  });
  const width = level >= 4 ? 3 : 3;
  return 'L' + level + '-' + String(max + 1).padStart(width, '0');
}

function flattenBenchmarkCategories(nodes, prefix, out) {
  const acc = out || [];
  const trail = prefix || [];
  (nodes || []).forEach((node) => {
    const label = (node.name_zh || node.name || node.code || '').trim();
    const path = trail.concat([`${node.code} ${label}`]);
    acc.push({
      id: node.id,
      parent_id: node.parent_id == null ? null : node.parent_id,
      code: node.code,
      name: label,
      level: node.level,
      label: path.join(' / '),
    });
    flattenBenchmarkCategories(node.children, path, acc);
  });
  return acc;
}

function activityFrameworkOptions(selected) {
  return (state.map.frameworks || []).map((fw) =>
    `<option value="${esc(fw.code)}"${fw.code === selected ? ' selected' : ''}>${
      esc(fw.name)}${fw.is_primary ? ' · 主框架' : ''}${
      fw.version ? ' ' + esc(fw.version) : ''}</option>`).join('');
}

/** 新建下级默认对标框架：固定优先 APQC 跨行业；上级仅在已有 APQC 族映射时跟随。 */
function preferredActivityFramework() {
  const frameworks = state.map.frameworks || [];
  const byCode = new Map(frameworks.map((fw) => [fw.code, fw]));
  const isApqcFamily = (code) => {
    const fw = byCode.get(code);
    return !!(fw && (fw.code === 'APQC_PCF' || fw.base_framework_code === 'APQC_PCF'));
  };
  const parentApqc = (activityCreate.parentMappings || [])
    .map((row) => row.framework_code)
    .find((code) => code === 'APQC_PCF' || isApqcFamily(code));
  if (parentApqc) return parentApqc;
  if (byCode.has('APQC_PCF')) return 'APQC_PCF';
  const fallback = frameworks.find((fw) => fw.base_framework_code === 'APQC_PCF')
    || frameworks.find((fw) => fw.is_primary);
  return (fallback && fallback.code) || 'APQC_PCF';
}

/** 沿流程上级查找已有对标；用于把下级选项收窄到上级标准分类之下。 */
async function resolveParentBenchmarkMappings(parent) {
  if (!parent) return [];
  const flat = flattenTree(state.map.tree || []);
  let current = parent;
  while (current) {
    try {
      const data = await GET('/benchmark/processes/' + current.id + '/mappings');
      if ((data.mappings || []).length) return data.mappings;
    } catch (_err) {
      /* 继续向上找 */
    }
    current = current.parent_id
      ? flat.find((node) => node.id === current.parent_id)
      : null;
  }
  return [];
}

function normalizeBenchQuery(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[（）()\[\]【】·・•\s\-_/\\．，。、:：]/g, '')
    .replace(/流程|管理|类别|分类|价值链|活动|与|和|的|及/g, '');
}

/** 上级名称 ↔ 标准分类名：子串命中 + 汉字重合；只作建议，不代替正式映射。 */
function scoreBenchmarkName(query, row) {
  const q = normalizeBenchQuery(query);
  if (!q || q.length < 2) return 0;
  const hay = normalizeBenchQuery(row.name || '');
  if (!hay) return 0;
  if (hay === q) return 100;
  if (hay.includes(q) || q.includes(hay)) return 92;
  const qChars = Array.from(q);
  const haySet = new Set(Array.from(hay));
  let hit = 0;
  qChars.forEach((ch) => {
    if (haySet.has(ch)) hit += 1;
  });
  const overlap = hit / qChars.length;
  if (overlap < 0.45) return 0;
  // 短查询（如「战略」）要求更高重合，减少误伤
  if (q.length <= 2 && overlap < 0.9) return 0;
  return Math.round(45 + overlap * 45);
}

/** 用上级流程名在「上级同级」标准分类里找候选锚点。 */
function suggestScopeByParentName(parentLevel) {
  const name = activityCreate.parentName;
  if (!name || parentLevel == null) return [];
  const scored = activityCreate.categories
    .filter((row) => row.level === parentLevel)
    .map((row) => ({
      id: row.id,
      code: row.code,
      name: row.name,
      score: scoreBenchmarkName(name, row),
    }))
    .filter((row) => row.score >= 55)
    .sort((a, b) => b.score - a.score || String(a.code).localeCompare(String(b.code)));
  if (!scored.length) return [];
  const best = scored[0].score;
  return scored.filter((row) => row.score >= best - 12).slice(0, 3);
}

function resolveBenchmarkScopeIds(frameworkCode) {
  activityCreate.nameSuggestions = [];
  activityCreate.scopeMode = 'none';
  const hard = new Set(
    (activityCreate.parentMappings || [])
      .filter((row) => !frameworkCode || row.framework_code === frameworkCode)
      .map((row) => row.category_id),
  );
  if (hard.size) {
    activityCreate.scopeMode = 'mapping';
    return hard;
  }
  if (!activityCreate.parentId) return hard;
  const suggested = suggestScopeByParentName(activityCreate.parentLevel);
  activityCreate.nameSuggestions = suggested;
  if (suggested.length) {
    activityCreate.scopeMode = 'name';
    suggested.forEach((row) => hard.add(row.id));
  }
  return hard;
}

function scopedBenchmarkCategories(level, frameworkCode) {
  const byId = new Map(activityCreate.categories.map((row) => [row.id, row]));
  const scopeIds = resolveBenchmarkScopeIds(frameworkCode);
  const underScope = (row) => {
    if (!scopeIds.size) return false;
    let current = row;
    const seen = new Set();
    while (current) {
      if (scopeIds.has(current.id)) return true;
      if (seen.has(current.id)) break;
      seen.add(current.id);
      current = current.parent_id != null ? byId.get(current.parent_id) : null;
    }
    return false;
  };
  return activityCreate.categories.filter((row) => {
    if (row.level !== level) return false;
    // 无上级、无正式映射且名称也匹配不上：同级全量，避免下拉被掏空
    if (!activityCreate.parentId || !scopeIds.size) return true;
    return underScope(row);
  }).slice(0, 400);
}

function toggleBenchTreeGroup(groupId) {
  const key = String(groupId);
  if (!activityCreate.benchExpanded) activityCreate.benchExpanded = new Set();
  if (activityCreate.benchExpanded.has(key)) activityCreate.benchExpanded.delete(key);
  else activityCreate.benchExpanded.add(key);
  paintActivityBenchmarkOptions();
}

function benchLeafButton(row, selectedId) {
  const on = selectedId && String(row.id) === String(selectedId);
  return `<button type="button" class="bench-pick-leaf${on ? ' on' : ''}"
      data-act="map.activityBenchPick" data-id="${row.id}">
      <span class="bench-code">${esc(row.code)}</span>
      <span class="bench-name">${esc(row.name)}</span>
    </button>`;
}

/** 同级选项按直接上级分组，树状展开，便于在全量列表里定位。 */
function renderBenchmarkPickTree(sameLevel, filterText, selectedId) {
  const byId = new Map(activityCreate.categories.map((row) => [row.id, row]));
  const raw = String(filterText || '').trim();
  const q = raw.toLowerCase();
  let filtered = sameLevel;
  if (q) {
    filtered = sameLevel
      .map((row) => {
        const codeHit = String(row.code || '').toLowerCase().includes(q);
        const nameHit = String(row.name || '').toLowerCase().includes(q);
        const fuzzy = scoreBenchmarkName(raw, row);
        return { row, score: codeHit ? 100 : (nameHit ? 90 : fuzzy) };
      })
      .filter((item) => item.score >= 55)
      .sort((a, b) => b.score - a.score
        || String(a.row.code).localeCompare(String(b.row.code), undefined, { numeric: true }))
      .map((item) => item.row);
  }
  if (!filtered.length) {
    return '<div class="bench-pick-empty">无匹配分类</div>';
  }

  const clearLabel = '不关联，名称手填'
    + ((activityCreate.childLevel || 0) >= 4 ? '（可继承上级对标）' : '');
  const clearBtn = `<button type="button" class="bench-pick-clear${
    selectedId ? '' : ' on'}" data-act="map.benchClear">${esc(clearLabel)}</button>`;

  const canGroup = filtered.some(
    (row) => row.parent_id != null && byId.has(row.parent_id),
  );
  if (!canGroup) {
    return clearBtn + filtered.map((row) => benchLeafButton(row, selectedId)).join('');
  }

  const groups = new Map();
  filtered.forEach((row) => {
    const pid = row.parent_id;
    if (!groups.has(pid)) groups.set(pid, []);
    groups.get(pid).push(row);
  });
  const keys = [...groups.keys()].sort((a, b) => {
    const ca = String((byId.get(a) || {}).code || '');
    const cb = String((byId.get(b) || {}).code || '');
    return ca.localeCompare(cb, undefined, { numeric: true });
  });

  if (!activityCreate.benchExpanded) activityCreate.benchExpanded = new Set();
  // 分组默认全部折叠；仅在用户输入筛选词时自动展开匹配组
  if (!activityCreate.benchExpandedReady) {
    activityCreate.benchExpandedReady = true;
  }
  if (q) keys.forEach((pid) => activityCreate.benchExpanded.add(String(pid)));

  const body = keys.map((pid) => {
    const parent = byId.get(pid);
    const kids = groups.get(pid) || [];
    const open = activityCreate.benchExpanded.has(String(pid));
    const gLabel = parent
      ? `${esc(parent.code)} · ${esc(parent.name)}`
      : '其他';
    return `<div class="bench-pick-group">
      <button type="button" class="bench-pick-hd" data-act="map.benchTreeToggle"
        data-id="${pid}">
        <span class="bench-caret">${open ? '▼' : '▶'}</span>
        <span class="bench-hd-label">${gLabel}</span>
        <i>${kids.length}</i>
      </button>
      ${open ? kids.map((row) => benchLeafButton(row, selectedId)).join('') : ''}
    </div>`;
  }).join('');
  return clearBtn + body;
}

function syncBenchPickedLabel(categoryId) {
  const picked = document.getElementById('pfBenchPicked');
  if (!picked) return;
  if (!categoryId) {
    picked.textContent = '未关联 · 可手填名称';
    return;
  }
  const row = activityCreate.categories.find(
    (item) => String(item.id) === String(categoryId),
  );
  picked.textContent = row
    ? `已选 ${row.code} · ${row.name}`
    : '已选择';
}

function paintActivityBenchmarkOptions() {
  const treeEl = document.getElementById('pfBenchTree');
  const hidden = document.getElementById('pfBenchCat');
  if (!treeEl || !hidden) return;
  const level = activityCreate.childLevel || 3;
  const frameworkCode = (document.getElementById('pfBenchFw') || {}).value || '';
  const sameLevel = scopedBenchmarkCategories(level, frameworkCode);
  const filterEl = document.getElementById('pfBenchFilter');
  if (filterEl && activityCreate.benchFilter != null
    && filterEl.value !== activityCreate.benchFilter) {
    filterEl.value = activityCreate.benchFilter;
  }
  const previous = hidden.value;
  const keep = previous && sameLevel.some((row) => String(row.id) === String(previous))
    ? previous
    : '';
  if (!keep) hidden.value = '';
  // 分类树始终展示；组节点默认折叠（点 ▶ 再展开子项）
  treeEl.innerHTML = renderBenchmarkPickTree(
    sameLevel,
    activityCreate.benchFilter || (filterEl && filterEl.value) || '',
    hidden.value,
  );
  syncBenchPickedLabel(hidden.value);

  let tip = '';
  if (!activityCreate.parentId) {
    tip = sameLevel.length
      ? `${sameLevel.length} 条 L${level}，按上级分类分组；点选后带出名称`
      : '暂无同级分类';
  } else if (!frameworkCode) {
    tip = '请选择对标框架后再匹配标准分类';
  } else if (activityCreate.scopeMode === 'mapping') {
    tip = sameLevel.length
      ? `已按上级对标收窄为 ${sameLevel.length} 条；可不选，选中后带出名称`
      : '上级对标下没有同级子分类，请手填名称或调整上级映射';
  } else if (activityCreate.scopeMode === 'name') {
    const top = (activityCreate.nameSuggestions || [])[0];
    const label = top ? `${top.code} ${top.name}` : '相近分类';
    tip = sameLevel.length
      ? `上级未正式对标；按「${activityCreate.parentName}」匹配到 ${label}，收窄为 ${
        sameLevel.length} 条（建议稍后给上级建正式映射）`
      : `按「${activityCreate.parentName}」匹配到 ${label}，但其下暂无 L${level}；可手填或改上级映射`;
  } else {
    tip = sameLevel.length
      ? `上级尚未对标且名称未匹配，显示全部 ${sameLevel.length} 条同级（按上级分类树分组）`
      : '暂无同级分类，请手填名称';
  }
  setFieldTip('pfBenchTip', tip);
}

function setFieldTip(id, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.setAttribute('data-tip', text || '');
  el.setAttribute('aria-label', text || '');
}

async function loadActivityBenchmarkCategories(frameworkCode) {
  const treeEl = document.getElementById('pfBenchTree');
  const hidden = document.getElementById('pfBenchCat');
  const level = activityCreate.childLevel || 3;
  resetBenchPickerState();
  if (!frameworkCode) {
    activityCreate.categories = [];
    if (hidden) hidden.value = '';
    if (treeEl) treeEl.innerHTML = '';
    syncBenchPickedLabel('');
    setFieldTip(
      'pfBenchTip',
      activityCreate.parentId
        ? '请选择与上级一致的对标框架'
        : '先选对标框架，再选同级标准分类。',
    );
    return;
  }
  setFieldTip('pfBenchTip', '加载标准分类中…');
  try {
    const tree = await GET(
      '/benchmark/frameworks/' + encodeURIComponent(frameworkCode)
      + '/tree?max_level=' + Math.max(4, level));
    activityCreate.categories = flattenBenchmarkCategories(tree);
    paintActivityBenchmarkOptions();
  } catch (e) {
    activityCreate.categories = [];
    if (hidden) hidden.value = '';
    if (treeEl) {
      treeEl.innerHTML = `<div class="bench-pick-empty">${esc(e.message || '加载失败')}</div>`;
    }
    setFieldTip('pfBenchTip', e.message || '加载标准分类失败');
  }
}

function applyActivityBenchmarkPick(categoryId) {
  const hidden = document.getElementById('pfBenchCat');
  if (hidden) hidden.value = categoryId ? String(categoryId) : '';
  if (categoryId) {
    const row = activityCreate.categories.find(
      (item) => String(item.id) === String(categoryId),
    );
    const nameEl = document.getElementById('pfName');
    if (row && nameEl) nameEl.value = row.name;
  }
  document.querySelectorAll('#pfBenchTree .bench-pick-leaf').forEach((btn) => {
    btn.classList.toggle('on', !!categoryId && btn.dataset.id === String(categoryId));
  });
  const clearBtn = document.querySelector('#pfBenchTree .bench-pick-clear');
  if (clearBtn) clearBtn.classList.toggle('on', !categoryId);
  syncBenchPickedLabel(categoryId);
}

/* 与后端 process_map._heat_level 同口径，仅供弹窗预览 */
const SCORE_HEAT_CRITICAL = 80;
const SCORE_HEAT_HIGH = 55;
const SCORE_HEAT_MEDIUM = 30;
const SCORE_HEALTH_CRITICAL = 50;
const SCORE_HEALTH_POOR = 65;

function readScoreInput(id, fallback) {
  const node = document.getElementById(id);
  if (!node || node.value === '') return fallback;
  const n = Number(node.value);
  return Number.isFinite(n) ? n : fallback;
}

function predictHeatLevel(priority, health) {
  if (priority >= SCORE_HEAT_CRITICAL
    || (health != null && health < SCORE_HEALTH_CRITICAL)) return 'CRITICAL';
  if (priority >= SCORE_HEAT_HIGH
    || (health != null && health < SCORE_HEALTH_POOR)) return 'HIGH';
  if (priority >= SCORE_HEAT_MEDIUM) return 'MEDIUM';
  return 'LOW';
}

function syncScorePreview() {
  const priorityEl = document.getElementById('pfPriority');
  if (!priorityEl) return;
  const si = readScoreInput('pfSi', 0);
  const pain = readScoreInput('pfPain', 0);
  const space = readScoreInput('pfSpace', 0);
  const priority = Math.round(si * pain * space * 10) / 10;
  priorityEl.value = String(priority);

  const healthRaw = document.getElementById('pfHealth');
  const health = healthRaw && healthRaw.value !== ''
    ? readScoreInput('pfHealth', null)
    : null;
  const heat = predictHeatLevel(priority, health);
  const badge = document.getElementById('pfHeatPreview');
  if (badge) {
    badge.className = 'tag ' + (HEAT_CLASS[heat] || 't-gry');
    badge.textContent = HEAT_LABEL[heat] || heat;
  }
  const parts = [`综合分 ${priority}`];
  if (priority >= SCORE_HEAT_CRITICAL) parts.push('≥80 → 紧急');
  else if (priority >= SCORE_HEAT_HIGH) parts.push('≥55 → 高');
  else if (priority >= SCORE_HEAT_MEDIUM) parts.push('≥30 → 中');
  else parts.push('<30 → 低');
  if (health != null && health < SCORE_HEALTH_CRITICAL) {
    parts.push(`健康度 ${health}<50 也可判紧急`);
  } else if (health != null && health < SCORE_HEALTH_POOR) {
    parts.push(`健康度 ${health}<65 至少为高`);
  }
  setFieldTip('pfHeatTip', parts.join(' · ') + '（与地图热度同口径预览）');
}

function applyInheritParentScores(checked) {
  const src = activityCreate.parentScores;
  const ids = ['pfSi', 'pfPain', 'pfSpace'];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !!checked && !!src;
  });
  if (checked && src) {
    const si = document.getElementById('pfSi');
    const pain = document.getElementById('pfPain');
    const space = document.getElementById('pfSpace');
    if (si) si.value = String(src.si);
    if (pain) pain.value = String(src.pain);
    if (space) space.value = String(src.space);
  }
  syncScorePreview();
}

function scoreGuideHtml() {
  return `<details class="score-guide">
    <summary>价值-痛点打分说明 · 知其然与所以然</summary>
    <div class="score-guide-body">
      <p><b>三项在算什么</b>：战略重要性看「做错对战略冲击多大」；痛点严重度看「现状多痛」
        （投诉/延误/成本/风险）；改善空间看「还能挖多少、改不改得动」。
        综合分 = 三者相乘（0–125）。乘法是故意的：任一维接近 0，整体就掉下去，
        避免「重要但改不动」被排到最前。</p>
      <table class="score-anchor-tbl">
        <thead><tr><th>分</th><th>战略重要性</th><th>痛点严重度</th><th>改善空间</th></tr></thead>
        <tbody>
          <tr><td>1</td><td>边缘支撑</td><td>偶发、可兜底</td><td>几乎无杠杆 / 改不动</td></tr>
          <tr><td>3</td><td>常规运营必要</td><td>有稳定损耗，尚可维持</td><td>有空间，需一定投入</td></tr>
          <tr><td>5</td><td>直接绑年度战略/合规生死线</td>
            <td>持续爆雷或大额损失</td><td>方法清晰、ROI 可见、阻力可控</td></tr>
        </tbody>
      </table>
      <p class="tiny">2 / 4 作过渡。默认 3 只表示「尚未认真评」，不要假装已评估。
        APQC 不提供这三项官方分表，档位是企业评估纪律。</p>
      <p><b>热度档位</b>：综合分 ≥80（或健康度&lt;50）紧急；≥55（或健康度&lt;65）高；
        ≥30 中；其余低。由地图后端统一判定，此处为同口径预览。</p>
      <p><b>评在哪一层</b>：主评 L3（热力图/立项优先级以 L3 为主）。
        L4 默认可继承上级；仅当该活动本身是改善切入点时再单独打，
        避免同流程下几十条 L4 各打各的、热力失真。</p>
    </div>
  </details>`;
}

/** 待改善项：人工进池标记，与三维评分/热度独立。 */
const IMPROVEMENT_TARGET_TIP = '人工「改善组合」标记：决定本轮是否进改善池'
  + '（三维评分答值不值得改，本项答要不要改）。'
  + '勾「是」→ 地图「待改善」标签与「只看待改善」过滤、驾驶舱「待改善流程」计数。'
  + '不改优先级/热度/健康度，也不自动立项。';

function scoreAssessmentHtml(opts) {
  const si = opts.si == null ? 3 : opts.si;
  const pain = opts.pain == null ? 3 : opts.pain;
  const space = opts.space == null ? 3 : opts.space;
  const health = opts.health == null ? '' : opts.health;
  const targetOn = !!opts.target;
  const inherit = !!opts.inheritAvailable;
  const inheritOn = !!opts.inheritDefault;
  return `${scoreGuideHtml()}
    ${inherit ? `<label class="score-inherit">
      <input type="checkbox" id="pfInheritParent" data-act="map.inheritParentScores"${
        inheritOn ? ' checked' : ''}>
      L4 继承上级「${esc(opts.parentName || '上级')}」的三项评分（可随时取消后改）
    </label>` : ''}
    <div class="row3">
      <div class="field"><label>战略重要性 ${
        tipHelp('1 边缘支撑 · 3 常规运营必要 · 5 直接绑年度战略/合规生死线', '战略重要性说明')}</label>
        <input id="pfSi" type="number" min="0" max="5" step="0.1" value="${si}"
          data-act="map.scoreChanged"></div>
      <div class="field"><label>痛点严重度 ${
        tipHelp('1 偶发可兜底 · 3 稳定损耗尚可维持 · 5 持续爆雷或大额损失', '痛点严重度说明')}</label>
        <input id="pfPain" type="number" min="0" max="5" step="0.1" value="${pain}"
          data-act="map.scoreChanged"></div>
      <div class="field"><label>改善空间 ${
        tipHelp('1 几乎无杠杆/改不动 · 3 有空间需投入 · 5 方法清晰、ROI 可见', '改善空间说明')}</label>
        <input id="pfSpace" type="number" min="0" max="5" step="0.1" value="${space}"
          data-act="map.scoreChanged"></div>
    </div>
    <div class="row3">
      <div class="field"><label>${metricHelp('priority_score', '综合优先级得分')}</label>
        <input id="pfPriority" value="" readonly></div>
      <div class="field"><label>${metricHelp('heat_level', '热度预览')}
        <span id="pfHeatTip" class="metric-help has-tip tip-inline" data-tip="随三项与健康度即时预览"
          tabindex="0" aria-label="热度预览说明"><i class="q">?</i></span></label>
        <div class="score-heat-line">
          <span id="pfHeatPreview" class="tag t-gry">—</span>
        </div></div>
      <div class="field"><label>流程健康度 ${
        tipHelp('0–100 分；未评估请留空。健康度过低也会拉高热度档。', '流程健康度说明')}</label>
        <input id="pfHealth" type="number" min="0" max="100" step="1"
          value="${health === '' || health == null ? '' : health}"
          placeholder="可选" data-act="map.scoreChanged"></div>
    </div>
    <div class="field" style="max-width:280px"><label>待改善项 ${
      tipHelp(IMPROVEMENT_TARGET_TIP, '待改善项说明')}</label>
      <select id="pfTarget">
        <option value="false"${targetOn ? '' : ' selected'}>否</option>
        <option value="true"${targetOn ? ' selected' : ''}>是</option>
      </select>
      <div class="hint">进本轮改善池；不影响热度分，不自动建项目</div></div>`;
}

function childPlaceholders(level) {
  if (level === 1) {
    return { code: '如 L1-010', name: '如：采购供应', desc: '这条价值链覆盖哪些主业务' };
  }
  if (level === 2) {
    return { code: '如 L2-031', name: '如：寻源与采购', desc: '这一类流程的边界' };
  }
  if (level === 3) {
    return { code: '如 L3-090', name: '如：供应商对账', desc: '这条流程从哪开始、到哪结束' };
  }
  return { code: '如 L4-207', name: '如：需求发起与归集', desc: '这一步做什么、边界到哪' };
}

async function newChildModal(parentId) {
  const parent = parentId
    ? flattenTree(state.map.tree || []).find((node) => node.id === parentId)
    : null;
  if (parentId && !parent) return toast('未找到当前节点，请刷新后重试', true);
  if (parent && parent.level >= 4) return toast('L4 活动下不再新建下级', true);

  const childLevel = parent ? parent.level + 1 : 1;
  const levelLabel = LEVEL_LABELS[childLevel] || ('L' + childLevel);
  const noun = childLevel >= 4 ? '活动' : '流程';
  const siblings = parent ? (parent.children || []) : (state.map.tree || []);
  const suggested = suggestNextCode(siblings, childLevel);
  const ph = childPlaceholders(childLevel);

  activityCreate.parentId = parentId;
  activityCreate.parentName = parent ? (parent.name || '') : '';
  activityCreate.parentLevel = parent ? parent.level : null;
  activityCreate.parentScores = parent ? {
    si: parent.strategic_importance,
    pain: parent.pain_score,
    space: parent.improvement_space,
    health: parent.health_score,
  } : null;
  activityCreate.childLevel = childLevel;
  activityCreate.categories = [];
  activityCreate.parentMappings = [];
  resetBenchPickerState();
  const inheritL4 = childLevel >= 4 && !!parent;

  try {
    if (!state.map.frameworks) {
      state.map.frameworks = await GET('/benchmark/frameworks');
    }
    await ensureMapUsers();
    if (parent) {
      activityCreate.parentMappings = await resolveParentBenchmarkMappings(parent);
    }
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const framework = preferredActivityFramework();

  const modalTitle = parent
    ? `新建${noun} · ${levelLabel} · 挂在 L${parent.level}「${parent.name}」下`
    : `新建${noun} · ${levelLabel}`;
  const nameTip = parent
    ? (activityCreate.parentMappings.length
      ? '名称可手填，或从下方标准分类带出后改。标准分类已按上级正式对标收窄。'
      : '上级未对标时，会按上级名称模糊匹配标准分类并建议收窄。名称可手填，或从对标带出后改。')
    : '名称可手填，或从下方标准分类带出后改。';

  openModal(modalTitle, `
    <div class="form-compact">
      <section class="form-block">
        <h4 class="form-block-hd">1. 基本信息</h4>
        <div class="row2">
          <div class="field"><label>${noun}编码 * ${
            tipHelp('全局唯一，同级顺延建议编码', `${noun}编码说明`)}</label>
            <input id="pfCode" value="${esc(suggested)}" placeholder="${esc(ph.code)}"></div>
          <div class="field"><label>${noun}名称 * ${tipHelp(nameTip, `${noun}名称说明`)}</label>
            <input id="pfName" placeholder="${esc(ph.name)}"></div>
        </div>
      </section>
      <section class="form-block">
        <h4 class="form-block-hd">2. 对标映射（可选）</h4>
        <div class="bench-map">
          <div class="bench-pick-toolbar">
            <label for="pfBenchFw">对标框架 ${
              tipHelp('默认 APQC 跨行业主框架；可改选 SCOR 或其他变体', '对标框架说明')}</label>
            <label for="pfBenchFilter">筛选分类 ${
              tipHelp('按编码或名称模糊筛选下方分类树', '筛选分类说明')}</label>
            <select class="sel" id="pfBenchFw" data-act="map.activityFramework">
              <option value="">不对标</option>${activityFrameworkOptions(framework)}
            </select>
            <input id="pfBenchFilter" class="sel" placeholder="编码或名称"
              data-act="map.benchFilter">
          </div>
          <div class="field">
            <label>标准 L${childLevel} 分类
              <span id="pfBenchTip" class="metric-help has-tip tip-inline" data-tip="加载中…"
                tabindex="0" aria-label="标准分类说明"><i class="q">?</i></span>
              <span class="tiny" id="pfBenchPicked">未关联</span></label>
            <input type="hidden" id="pfBenchCat" value="">
            <div id="pfBenchTree" class="bench-pick" role="listbox"></div>
          </div>
        </div>
      </section>
      <input type="hidden" id="pfLevel" value="${childLevel}">
      <input type="hidden" id="pfParent" value="${parent ? parent.id : ''}">
      <section class="form-block">
        <h4 class="form-block-hd">3. 组织与责任</h4>
        <div class="row3">
          <div class="field"><label>归属组织 ${
            tipHelp('集团 → 分公司 → 部门；Owner 会随组织过滤', '归属组织说明')}</label>
            <select class="sel" id="pfOrg" data-act="map.orgChanged">
              <option value="">未指定</option>${
                mapOrgOptions(parent ? parent.org_unit_id : null)}</select></div>
          <div class="field"><label>${noun} Owner
            <span id="pfOwnerTip" class="metric-help has-tip tip-inline"
              data-tip="随归属组织过滤账号；未指定可稍后补"
              tabindex="0" aria-label="${noun} Owner 说明"><i class="q">?</i></span></label>
            <select class="sel" id="pfOwnerUser">
              <option value="">未指定</option>${
                mapOwnerOptions(null, parent ? parent.org_unit_id : null)}</select></div>
          <div class="field"><label>责任部门 ${
            tipHelp('展示用标签，可与归属组织名称不同', '责任部门说明')}</label>
            <input id="pfDepartment"
              value="${esc(parent && parent.department ? parent.department : '')}"
              placeholder="如：采购部"></div>
        </div>
      </section>
      <section class="form-block">
        <h4 class="form-block-hd">4. 说明与评估</h4>
        <div class="field"><label>${noun}说明 ${
          tipHelp(ph.desc, `${noun}说明`)}</label>
          <textarea id="pfDesc" rows="2" placeholder="${esc(ph.desc)}"></textarea></div>
        ${scoreAssessmentHtml({
          si: inheritL4 ? parent.strategic_importance : 3,
          pain: inheritL4 ? parent.pain_score : 3,
          space: inheritL4 ? parent.improvement_space : 3,
          health: '',
          target: false,
          inheritAvailable: inheritL4,
          inheritDefault: inheritL4,
          parentName: parent ? parent.name : '',
        })}
      </section>
    </div>`,
    `<button class="btn btn-g" data-act="map.close">取消</button>
     <button class="btn btn-p" data-act="map.saveProcessNew">创建</button>`,
    'sheet');
  await loadActivityBenchmarkCategories(framework);
  if (inheritL4) applyInheritParentScores(true);
  else syncScorePreview();
}

async function newProcessModal() {
  try {
    await ensureMapUsers();
  } catch (e) {
    toast(e.message, true);
    return;
  }
  openModal('跨层新建', `
    <div class="form-compact">
      <div class="note">日常请用当前层「+ 下级」。这里仅用于自选层级与上级。</div>
      <div class="form-sec">1. 基本信息</div>
      <div class="row2">
        <div class="field"><label>流程编码 *</label>
          <input id="pfCode" placeholder="如 L3-090">
          <div class="hint">全局唯一</div></div>
        <div class="field"><label>流程名称 *</label>
          <input id="pfName" placeholder="如：供应商对账"></div>
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
      <div class="form-sec">2. 组织与责任</div>
      <div class="row3">
        <div class="field"><label>归属组织</label>
          <select class="sel" id="pfOrg" data-act="map.orgChanged">
            <option value="">未指定</option>${mapOrgOptions(null)}</select></div>
        <div class="field"><label>流程 Owner</label>
          <select class="sel" id="pfOwnerUser">
            <option value="">未指定</option>${mapOwnerOptions(null, null)}</select>
          <div class="hint" id="pfOwnerHint">随组织过滤</div></div>
        <div class="field"><label>责任部门</label>
          <input id="pfDepartment" placeholder="如：采购部"></div>
      </div>
      <div class="form-sec">3. 说明与评估</div>
      <div class="field"><label>流程说明</label>
        <textarea id="pfDesc" rows="2" placeholder="这条流程从哪开始、到哪结束"></textarea></div>
      ${scoreAssessmentHtml({
        si: 3, pain: 3, space: 3, health: '', target: false,
        inheritAvailable: false, inheritDefault: false, parentName: '',
      })}
    </div>`,
    `<button class="btn btn-g" data-act="map.close">取消</button>
     <button class="btn btn-p" data-act="map.saveProcessNew">创建</button>`,
    'sheet');
  syncScorePreview();
}

async function editProcessModal(processId) {
  const node = flattenTree(state.map.tree || []).find((n) => n.id === processId);
  if (!node) return toast('未找到该流程，请刷新后重试', true);
  try {
    await ensureMapUsers();
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const parent = node.parent_id
    ? flattenTree(state.map.tree || []).find((row) => row.id === node.parent_id)
    : null;
  activityCreate.parentScores = parent ? {
    si: parent.strategic_importance,
    pain: parent.pain_score,
    space: parent.improvement_space,
    health: parent.health_score,
  } : null;
  activityCreate.parentName = parent ? (parent.name || '') : '';
  const inheritL4 = node.level >= 4 && !!parent;
  openModal('编辑流程 · ' + node.code, `
    <div class="form-compact">
      <div class="form-sec">1. 基本信息</div>
      <div class="row3">
        <div class="field"><label>流程编码</label>
          <input value="${esc(node.code)}" readonly></div>
        <div class="field"><label>层级</label>
          <input value="L${node.level}" readonly></div>
        <div class="field"><label>流程名称</label>
          <input id="pfName" value="${esc(node.name)}"></div>
      </div>
      <div class="form-sec">2. 组织与责任</div>
      <div class="row3">
        <div class="field"><label>归属组织</label>
          <select class="sel" id="pfOrg" data-act="map.orgChanged">
            <option value="">未指定</option>${mapOrgOptions(node.org_unit_id)}</select>
          <div class="hint">集团 → 分公司 → 部门</div></div>
        <div class="field"><label>流程 Owner</label>
          <select class="sel" id="pfOwnerUser">
            <option value="">未指定</option>${
              mapOwnerOptions(node.owner_user_id, node.org_unit_id)}</select>
          <div class="hint" id="pfOwnerHint">随组织过滤账号</div></div>
        <div class="field"><label>责任部门</label>
          <input id="pfDepartment" value="${esc(node.department || '')}"></div>
      </div>
      <div class="form-sec">3. 说明与评估</div>
      <div class="field"><label>流程说明</label>
        <textarea id="pfDesc" rows="2">${esc(node.description || '')}</textarea></div>
      ${scoreAssessmentHtml({
        si: node.strategic_importance,
        pain: node.pain_score,
        space: node.improvement_space,
        health: node.health_score,
        target: node.is_improvement_target,
        inheritAvailable: inheritL4,
        inheritDefault: false,
        parentName: parent ? parent.name : '',
      })}
    </div>`,
    `<button class="btn btn-g" data-act="map.close">取消</button>
     <button class="btn btn-p" data-act="map.saveProcess" data-id="${processId}">保存</button>`,
    'sheet');
  syncScorePreview();
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

  const ownerUser = val('pfOwnerUser');
  const payload = {
    name: val('pfName').trim(),
    owner_user_id: ownerUser ? Number(ownerUser) : null,
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
  }
  if (document.getElementById('pfHealth')) {
    payload.health_score = numOrNull('pfHealth');
  }

  if (!payload.name) return toast('请填写流程名称', true);
  if (processId === null && !payload.code) return toast('请填写流程编码', true);

  const categoryId = val('pfBenchCat');
  try {
    if (processId === null) {
      const created = await POST('/process-map', payload);
      let mapError = '';
      if (categoryId) {
        try {
          await POST('/benchmark/mappings', {
            process_id: created.id,
            category_id: Number(categoryId),
          });
        } catch (mapErr) {
          mapError = mapErr.message || '对标映射失败';
        }
      }
      // 新建的是顶层流程就回到根层级，否则留在当前层级（用户刚在父节点下创建）
      if (!payload.parent_id) {
        state.map.path = [];
        state.mapKeyword = '';
        const search = document.getElementById('searchInput');
        if (search) search.value = '';
      }
      closeModal();
      invalidateProcessCaches();
      const noun = payload.level === 4 ? '活动' : '流程';
      if (mapError) {
        toast(`已创建 ${created.code}，但对标未写入：${mapError}`, true);
      } else if (categoryId) {
        toast(`${noun}已创建并完成对标：${created.code}`);
      } else {
        toast(`${noun}已创建：${created.code}`);
      }
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
