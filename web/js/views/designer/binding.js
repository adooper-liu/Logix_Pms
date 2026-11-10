/* P0 绑定核对：后端唯一口径，前端只读展示与画布定位。 */
import { esc, tipHelp } from '../../core/format.js';
import { foldCard } from '../../core/layout.js';
import { GET } from '../../core/api.js';
import { state } from '../../core/state.js';
import { on, toast } from '../../core/ui.js';
import { canManage } from '../../core/auth.js';

const TONE = { READY: 't-grn', PARTIAL: 't-yel', MISSING: 't-gry', CONFLICT: 't-red' };
const MARKERS = ['pms-bind-red', 'pms-bind-yellow', 'pms-bind-green'];

export function createBinding(ctx) {
  let requestRevision = 0;
  function currentData() {
    const st = state.designer;
    return st.binding?.process_id === st.processId ? st.binding : null;
  }
  function facetsHtml(facets) {
    return (facets || []).map(facet => `<section class="binding-facet" data-binding-facet="${esc(facet.key)}">
      <div class="between"><b>${esc(facet.label)}</b>
        <span class="tag ${TONE[facet.status] || 't-gry'}">${esc(facet.status_label)}</span></div>
      <div class="tiny muted">${esc(facet.source_label)}</div>
      ${(facet.gaps || []).map(gap => `<p class="tiny">${esc(gap)}</p>`).join('')}
      ${facet.refs.length ? foldCard('来源引用', `<ul class="binding-refs">${facet.refs.map(ref =>
        `<li><b>${esc(ref.label)}</b> <span class="tiny muted">${esc(ref.source_label)}${ref.id ? ' · #' + esc(ref.id) : ''}</span>
          ${ref.detail ? `<div class="tiny">${esc(ref.detail)}</div>` : ''}</li>`).join('')}</ul>`, {open: false}) : ''}
    </section>`).join('');
  }
  function paneHtml() {
    const data = currentData();
    if (!data) return `<div class="card" data-binding-summary>绑定暂不可核对：${esc(state.designer.bindingError || '正在读取当前已保存模型…')}。请刷新重试；未展示就绪状态。</div>`;
    const summary = data.summary;
    return `<div class="card" data-binding-summary>
      <div class="between"><h3>绑定核对 · 只读</h3><span class="tag ${TONE[summary.overall]}">${esc(summary.overall_label)}</span></div>
      <p>当前已保存模型 v${esc(data.model_version)} · ${summary.counts.activities} 个活动 · ${summary.counts.unmapped_nodes} 个节点未映射</p>
      <div class="binding-summary-facets">${summary.facets.map(facet => `<span class="tag ${TONE[facet.status]}">${esc(facet.label)} · ${esc(facet.status_label)}</span>`).join('')}</div>
      <p data-binding-consistency class="tiny">${esc(data.consistency_label)}</p>
      ${canManage() ? data.activities.map(activity => `<button class="btn-sm" data-act="designer.bindingEdit" data-activity="${activity.activity_id}">维护 ${esc(activity.activity_code)} 绑定</button>`).join(' ') : ''}
      <p class="tiny">下一步：先核对缺口与原来源；维护仅改原责任与资源引用，不自动确认冻结依据。
        ${tipHelp(data.limitations.join(' '), '核对范围与限制')}</p>
      ${summary.conflicts.length ? `<div class="warnbox">${summary.conflicts.map(esc).join('；')}</div>` : ''}
    </div>
    ${data.activities.map(activity => foldCard(`${activity.activity_code} · ${activity.activity_name}`,
      `<div class="gap mb">${activity.node_keys.map(key => `<button class="btn-sm" data-act="designer.bindingLocate" data-key="${esc(key)}">定位 ${esc(key)}</button>`).join('') || '<span class="tag t-yel">尚未建模</span>'}</div>
       ${activity.blockers.map(item => `<p class="tiny">${esc(item)}</p>`).join('')}
       <div class="binding-facets">${facetsHtml(activity.facets)}</div>`, {open: false})).join('')}
    ${data.nodes.filter(node => node.blockers.length).map(node => foldCard(`${node.node_key} · ${node.node_name}`,
      `<p>${node.blockers.map(esc).join('；')}</p><button class="btn-sm" data-act="designer.bindingLocate" data-key="${esc(node.node_key)}">定位节点</button>`, {open: false})).join('')}`;
  }
  function nodeHtml(key) {
    const data = currentData();
    const node = data?.nodes.find(item => item.node_key === key);
    if (!node) return '<div data-node-binding class="hint">当前节点尚无可核对的绑定结果；保存后重新读取。开始/结束等非活动节点不参与四面核对。</div>';
    return `<div data-node-binding><p class="tiny">只读 · 当前已保存模型 v${esc(data.model_version)}。${tipHelp(data.limitations.join(' '), '绑定核对说明')}</p>
      ${node.blockers.map(item => `<p class="tiny">${esc(item)}</p>`).join('')}
      ${canManage() ? node.activity_ids.map(activity => `<button class="btn-sm" data-act="designer.bindingEdit" data-activity="${activity}" data-node="${esc(key)}">维护活动绑定</button>`).join('') : ''}
      ${facetsHtml(node.facets)}</div>`;
  }
  function clearMarkers(modeler) {
    if (!modeler) return;
    const canvas = modeler.get('canvas');
    modeler.get('elementRegistry').getAll().forEach(element => MARKERS.forEach(marker => canvas.removeMarker(element, marker)));
    modeler.get('overlays').remove({type: 'pms-binding'});
  }
  function applyMarkers() {
    const modeler = ctx.getModeler();
    if (!modeler) return;
    clearMarkers(modeler);
    const data = currentData();
    if (!data) return;
    const canvas = modeler.get('canvas');
    const overlays = modeler.get('overlays');
    data.nodes.forEach(node => {
      const element = modeler.get('elementRegistry').get(node.node_key);
      if (!element) return;
      canvas.addMarker(element, 'pms-bind-' + node.marker);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'binding-marker binding-marker-' + node.marker;
      button.dataset.bindingMarker = node.node_key;
      button.title = '绑定核对 · ' + node.status_label;
      button.setAttribute('aria-label', button.title + ' · ' + node.node_name);
      button.textContent = node.status === 'CONFLICT' ? '!' : '绑';
      button.addEventListener('click', event => { event.stopPropagation(); locate(node.node_key); });
      overlays.add(element, 'pms-binding', {position: {top: -9, right: -9}, html: button});
    });
  }
  async function refresh() {
    const revision = ++requestRevision;
    const pid = state.designer.processId;
    state.designer.binding = null;
    state.designer.bindingError = null;
    applyMarkers();
    try {
      const data = await GET('/processes/' + pid + '/binding-readiness');
      if (revision !== requestRevision || state.view !== 'designer' || state.designer.processId !== pid) return;
      if (data.model_version !== (state.designer.model?.draft_version ?? state.designer.model?.version)) {
        state.designer.bindingError = '模型已变化，请重新加载核对';
        return;
      }
      state.designer.binding = data;
    } catch (error) {
      if (revision !== requestRevision || state.view !== 'designer' || state.designer.processId !== pid) return;
      state.designer.bindingError = error.message;
    }
    applyMarkers();
    const pane = document.getElementById('designerBindingPane');
    if (pane && state.designer.tab === 'binding') pane.innerHTML = paneHtml();
    ctx.renderSelection(state.designer.bpmnSelection || []);
  }
  function locate(key) {
    const element = ctx.getElement(key);
    if (state.designer.tab !== 'model' || !document.getElementById('bpmnCanvas') || !element) {
      state.designer.bindingLocate = key;
      ctx.showModel();
      return;
    }
    state.designer.propSection = 'binding';
    ctx.select(element);
    ctx.showSidebar('props');
    ctx.renderSelection([element]);
    ctx.getModeler().get('canvas').scrollToElement(element);
  }
  function mounted() {
    applyMarkers();
    const key = state.designer.bindingLocate;
    state.designer.bindingLocate = null;
    if (key) locate(key);
  }
  on('designer.bindingLocate', ({key}) => locate(key));
  function load(processId) {
    ++requestRevision;
    return GET('/processes/' + processId + '/binding-readiness')
      .then(data => ({data})).catch(error => ({error: error.message}));
  }
  function accept(result, model = state.designer.model) {
    ++requestRevision;
    const matches = !result.data || result.data.model_version === (model?.draft_version ?? model?.version);
    state.designer.binding = matches ? result.data || null : null;
    state.designer.bindingError = matches ? result.error || null : '模型已变化，请重新加载核对';
  }
  function acceptLocation(params, result, model) {
    if (!params.node) return;
    state.designer.tab = 'model';
    state.designer.bindingLocate = null;
    if (params.basis && String(result.data?.model_version_id) !== params.basis) {
      toast('原责任书模型与当前工作版不同，请先核对版本；未自动定位同名节点。', 'error');
    } else if (model.nodes.some(node => node.node_key === params.node)) {
      state.designer.bindingLocate = params.node;
    } else toast('原活动节点当前不存在，请核对来源版本。', 'error');
  }
  return {paneHtml, nodeHtml, refresh, applyMarkers, mounted, load, accept, acceptLocation};
}
