/* 视图：map */
import { esc, num, HEAT_COLOR, HEAT_LABEL, emptyRow } from '../core/format.js';
import { toast, openModal, closeModal, viewEl } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';
import { openDesigner } from './designer.js';

/* ============================================================ 2. 企业流程地图 */

const renderMap = () => {
  const paint = () => {
    const tree = state.map.tree || [];
    const path = state.map.path;
    let nodes = tree;
    for (const code of path) {
      const found = nodes.find((n) => n.code === code);
      if (!found) break;
      nodes = found.children || [];
    }
    const kw = state.mapKeyword || '';
    const shown = kw ? nodes.filter((n) => (n.name + n.code + (n.owner || '')).includes(kw)) : nodes;

    const crumbs = ['<a onclick="mapGo(-1)">全部价值链</a>']
      .concat(path.map((code, i) =>
        '<span>/</span><a onclick="mapGo(' + i + ')">' + esc(state.map.names[code] || code) + '</a>'));

    const cards = shown.map((n) => {
      // 热度由后端统一判定（见 app/api/v1/process_map.py 的阈值），前端不再各算一套
      const heat = n.heat_level || 'LOW';
      const color = HEAT_COLOR[heat];
      const hasKids = (n.children || []).length > 0;
      return `
        <div class="step" style="border-left-color:${color};min-height:auto"
             onclick="mapClick('${n.code}', ${hasKids})">
          <div class="between">
            <b>${esc(n.name)}</b>
            <span class="tag" style="background:${color}1a;color:${color}">${HEAT_LABEL[heat]}</span>
          </div>
          <span>${esc(n.code)} · Owner: ${esc(n.owner || '未指定')}</span>
          <div class="tiny" style="margin-top:5px">
            健康度 ${n.health_score === null ? '—' : num(n.health_score, 0)}
            · 痛点 ${num(n.pain_score, 1)}/5
            · 战略价值 ${num(n.strategic_importance, 1)}/5
            ${n.is_improvement_target ? ' · <span style="color:#ef4444">待改善</span>' : ''}
          </div>
          <div class="pipe"><i style="width:${Math.min(100, (n.priority_score / 125) * 100)}%;
            background:${color}"></i></div>
          ${hasKids ? '<div class="tiny" style="margin-top:6px;color:var(--brand)">' +
            (n.children || []).length + ' 个下级流程 · 点击下钻 →</div>' : ''}
        </div>`;
    }).join('') || '<div class="empty">该层级下没有流程（或没有匹配结果）</div>';

    const heat = (state.map.heat || []).slice(0, 10).map((h) => `
      <tr class="clk" onclick="mapJump('${h.code}')">
        <td>${esc(h.code)}</td>
        <td><b>${esc(h.name)}</b><div class="tiny">${esc(h.owner || '未指定 Owner')}</div></td>
        <td><span class="tag" style="background:${HEAT_COLOR[h.heat_level]}1a;color:${HEAT_COLOR[h.heat_level]}">
          ${HEAT_LABEL[h.heat_level]}</span></td>
        <td>${num(h.priority_score, 0)}</td>
        <td>${h.health_score === null ? '—' : num(h.health_score, 0)}</td>
        <td>${h.project_count}</td>
      </tr>`).join('') || emptyRow(6, '暂无待改善项');

    viewEl().innerHTML = `
      <div class="card">
        <div class="between mb">
          <div><h2 style="margin:0">企业流程架构（L1 → L4 分层）</h2>
            <div class="desc" style="margin:0">点击层级节点逐级下钻 · 优先级 = 战略重要性 × 痛点严重度 × 改善空间</div></div>
          ${canManage()
            ? '<button class="btn btn-p" onclick="newProcessModal()">+ 新建流程</button>'
            : '<span class="tiny">当前角色只读</span>'}
        </div>
        <div class="crumb">${crumbs.join(' ')}</div>
        <div class="legend mb">
          <span><i style="background:#ef4444"></i>紧急</span>
          <span><i style="background:#f59e0b"></i>高</span>
          <span><i style="background:#2f5bea"></i>中</span>
          <span><i style="background:#16a34a"></i>低</span>
          <span class="muted">条长代表优先级得分</span>
        </div>
        <div class="g3">${cards}</div>
      </div>

      <div class="card">
        <h2>改善优先级热力图（L3 流程层 Top 10）</h2>
        <div class="desc">点击任意行可直接跳转到该流程所在的层级</div>
        <table class="tbl">
          <thead><tr><th>编码</th><th>流程</th><th>优先级</th><th>综合得分</th>
            <th>健康度</th><th>关联项目</th></tr></thead>
          <tbody>${heat}</tbody>
        </table>
      </div>`;
  };

  const start = async () => {
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
        ? '<button class="btn btn-g" style="margin-right:auto;color:#d14343"'
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


export { renderMap, deleteProcess, editProcessModal, flattenTree, invalidateProcessCaches, mapClick, mapGo, mapJump, newProcessModal, processParentOptions, refreshParentOptions, saveProcess };
