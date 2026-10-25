/* 模型治理：结构校验、评审流转、发布、版本历史 / 对比 / 回滚。
 *
 * 后端是版本化覆盖式保存，这一组动作都通过 ctx.reload 重新拉取模型，
 * 避免内存里的模型与已发布版本分叉。
 */

import { esc, dtShort, emptyRow } from '../../core/format.js';
import { toast, openModal, closeModal, confirmDialog, promptDialog } from '../../core/ui.js';
import { state } from '../../core/state.js';
import { GET, POST } from '../../core/api.js';
import { RENDERERS, go } from '../../core/router.js';

function validateModel(model) {
  const errors = [];
  const warnings = [];
  const keys = new Set();
  (model.nodes || []).forEach((n) => {
    if (keys.has(n.node_key)) errors.push(`节点 key 重复：${n.node_key}`);
    keys.add(n.node_key);
  });
  const pairs = new Set();
  (model.edges || []).forEach((e) => {
    if (!keys.has(e.source_key) || !keys.has(e.target_key)) {
      errors.push(`连线 ${e.source_key} → ${e.target_key} 引用了不存在的节点`);
    }
    if (e.source_key === e.target_key) {
      errors.push(`连线 ${e.source_key} → ${e.target_key} 是自环`);
    }
    const pair = e.source_key + '→' + e.target_key;
    if (pairs.has(pair)) errors.push(`重复连线：${pair}`);
    pairs.add(pair);
    if (e.probability < 0 || e.probability > 1) {
      errors.push(`连线 ${pair} 的概率必须在 0–1`);
    }
  });
  const starts = (model.nodes || []).filter((n) => n.node_type === 'START');
  if (starts.length > 1) errors.push(`只能有一个开始节点，当前有 ${starts.length} 个`);
  if (!starts.length) warnings.push('没有开始节点，运行时将按唯一入口推断');
  if (!(model.nodes || []).some((n) => n.node_type === 'END')) {
    warnings.push('没有结束节点，末端任务完成后实例结束');
  }
  const targets = new Set((model.edges || []).map((e) => e.target_key));
  (model.nodes || []).forEach((n) => {
    if (n.node_type !== 'START' && !targets.has(n.node_key)) {
      warnings.push(`节点「${n.name}」没有入边，可能是不可达节点`);
    }
  });
  return { errors, warnings };
}

function validationHtml(model) {
  const v = validateModel(model);
  if (!v.errors.length && !v.warnings.length) return '';
  const items = [
    ...v.errors.map((m) => `<div class="designer-issue error">✕ ${esc(m)}</div>`),
    ...v.warnings.map((m) => `<div class="designer-issue warn">! ${esc(m)}</div>`),
  ].join('');
  return `<div class="designer-validation">${items}</div>`;
}

export function createVersions(ctx) {
  async function submitReview() {
    const note = await promptDialog('评审说明（可选；取消则不提交）', {
      title: '提交评审', okText: '提交', placeholder: '说明本次变更',
    });
    if (note === null) return;
    try {
      await POST('/processes/' + state.designer.processId + '/design/submit-review', {
        note: note.trim() || null,
      });
      toast('已提交评审');
      await ctx.reload();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function rejectReview() {
    const note = await promptDialog('驳回原因（可选）', {
      title: '驳回评审', okText: '驳回', placeholder: '说明需要修改的地方',
    });
    if (note === null) return;
    try {
      await POST('/processes/' + state.designer.processId + '/design/reject', {
        note: note.trim() || null,
      });
      toast('已驳回，草稿可继续修改');
      await ctx.reload();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function publishDesign() {
    const model = state.designer.model || {};
    let changeRequestId = null;
    let gateNote = '';
    try {
      const current = state.designer.model || model;
      const check = await POST('/design/validate', {
        nodes: current.nodes || [],
        edges: current.edges || [],
      });
      if (check.errors && check.errors.length) {
        ctx.runLint();
        ctx.showSidebar('lint');
        toast('发布被阻止：' + check.errors.join('；'), true);
        return;
      }
      // 待评审的草稿不能再保存（后端会拒绝），发布直接用已评审的版本
      if (model.status !== 'IN_REVIEW') {
        const saved = await ctx.saveNow();
        if (!saved) return;
      }
    } catch (e) {
      return toast('发布前校验失败：' + e.message, true);
    }
    if (model.requires_change_request) {
      const change = await ctx.approvedChangeRequest();
      if (!change) {
        toast('该流程启用了变更门禁：请先在「变更」页创建并批准变更申请', true);
        state.designer.tab = 'change';
        RENDERERS.designer();
        return;
      }
      changeRequestId = change.id;
      gateNote = `\n本次发布将引用变更单 ${change.code}。`;
    }
    const ok = await confirmDialog(
      '发布后，新启动的流程实例将使用这个模型；运行中的实例仍用启动时快照。确定发布？'
      + gateNote,
      { title: '发布到运行时', okText: '发布' });
    if (!ok) return;
    try {
      await POST('/processes/' + state.designer.processId + '/design/publish', {
        expected_version: state.designer.model.version,
        change_note: null,
        change_request_id: changeRequestId,
      });
      const pid = state.designer.processId;
      toast('模型已发布，正在打开执行启动页');
      // 发布后的下一步就是启动一个新实例，直接把上下文带进执行页并拉起启动弹窗
      go('execution', {
        params: { process: pid, tab: 'config', start: 1 },
        push: true,
      });
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function openVersionHistory() {
    const pid = state.designer.processId;
    let rows = [];
    try {
      rows = await GET('/processes/' + pid + '/design/versions');
    } catch (e) {
      return toast(e.message, true);
    }
    const current = state.designer.model || {};
    const tone = { DRAFT: 't-gry', IN_REVIEW: 't-yel', PUBLISHED: 't-grn', SUPERSEDED: 't-gry' };
    const body = rows.map((v) => `
      <tr>
        <td><b>v${v.version}</b></td>
        <td><span class="tag ${tone[v.status] || 't-blu'}">${esc(v.status_label)}</span></td>
        <td class="tiny">${esc(v.change_note || '—')}</td>
        <td class="tiny">${esc(v.created_by_name || '—')}<div>${dtShort(v.created_at)}</div></td>
        <td class="tiny">${v.published_at ? dtShort(v.published_at) : '—'}</td>
        <td>
          ${v.id !== current.version_id
            ? `<button class="btn-sm" data-act="designer.diffVersion" data-id="${v.id}">对比当前</button>` : ''}
          ${v.version !== current.version
            ? `<button class="btn-sm" data-act="designer.rollbackVersion" data-id="${v.id}">回滚到此版</button>` : ''}
          ${['PUBLISHED', 'SUPERSEDED'].includes(v.status) && v.id !== current.version_id
            ? `<button class="btn-sm" data-act="designer.publishRollback"
                data-id="${v.id}">回滚并发布</button>` : ''}
        </td>
      </tr>`).join('') || emptyRow(6, '还没有模型版本');
    openModal('模型版本历史', `
      <div class="note">草稿会覆盖；已发布版本保留。回滚会生成新草稿，发布后才影响运行时。</div>
      <table class="tbl">
        <thead><tr><th>版本</th><th>状态</th><th>说明</th><th>创建人</th><th>发布时间</th><th></th></tr></thead>
        <tbody>${body}</tbody>
      </table>`,
      '<button class="btn btn-g" data-act="designer.close">关闭</button>');
  }

  async function publishRollback(versionId) {
    const ok = await confirmDialog(
      '会以历史版本生成一个新的已发布版本；运行中的实例不受影响。确定回滚并发布？',
      { title: '回滚并发布', okText: '回滚并发布' },
    );
    if (!ok) return;
    try {
      await POST(
        `/processes/${state.designer.processId}/design/versions/${versionId}/publish-rollback`,
        { note: null },
      );
      toast('已回滚并发布');
      closeModal();
      await ctx.reload();
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function diffVersion(versionId) {
    const currentId = state.designer.model && state.designer.model.version_id;
    if (!currentId) return toast('当前模型还没有版本记录', true);
    try {
      const d = await GET(
        '/processes/' + state.designer.processId + '/design/diff?from_version_id=' +
        versionId + '&to_version_id=' + currentId,
      );
      const line = (label, items, format) => items.length
        ? `<div class="diff-block"><b>${label}（${items.length}）</b>${
          items.map((item) => `<div class="tiny">${esc(format(item))}</div>`).join('')}</div>`
        : '';
      const content = [
        line('新增节点', d.nodes_added, (x) => x.node_key + ' ' + (x.name || '')),
        line('删除节点', d.nodes_removed, (x) => x.node_key + ' ' + (x.name || '')),
        line('修改节点', d.nodes_changed,
          (x) => x.node_key + '：' + x.fields.join('、')),
        line('新增连线', d.edges_added, (x) => x.source_key + ' → ' + x.target_key),
        line('删除连线', d.edges_removed, (x) => x.source_key + ' → ' + x.target_key),
        line('修改连线', d.edges_changed,
          (x) => x.source_key + ' → ' + x.target_key + '：' + x.fields.join('、')),
      ].join('') || '<div class="empty">两个版本没有差异</div>';
      openModal(`版本差异 · v${d.from_version} → v${d.to_version}`, content,
        '<button class="btn btn-g" data-act="designer.close">关闭</button>');
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function rollbackVersion(versionId) {
    const ok = await confirmDialog(
      '回滚会在当前模型上创建一个新草稿，发布后才影响运行时。继续？',
      { title: '回滚模型版本', okText: '回滚' });
    if (!ok) return;
    try {
      await POST(
        '/processes/' + state.designer.processId + '/design/versions/' +
        versionId + '/rollback', { note: null });
      toast('已从历史版本创建草稿');
      closeModal();
      await ctx.reload();
    } catch (e) {
      toast(e.message, true);
    }
  }

  return {
    validationHtml,
    submitReview,
    rejectReview,
    publishDesign,
    openVersionHistory,
    diffVersion,
    rollbackVersion,
    publishRollback,
  };
}
