/* 员工作业手册：岗位/治理角色主体、可追溯作业与固定版本。 */
import { GET, POST, download } from '../core/api.js';
import { canManage } from '../core/auth.js';
import { esc, tipHelp } from '../core/format.js';
import { pageShell, foldCard, sideCard } from '../core/layout.js';
import { go, renderAsync, urlParams } from '../core/router.js';
import { viewEl } from '../core/ui.js';

let current = null;
let revision = 0;
let busy = false;
const TABS = { overview: '结论', entries: '作业条目', history: '固定版本' };
const p = () => ({ ...urlParams() });
const context = () => `${p().scope || ''}|${p().subject || ''}`;
const alive = key => key === context() && stateView() === 'handbook';
const stateView = () => window.state?.view;

function subjectQuery(params) {
  const q = new URLSearchParams({ scope: params.scope || 'POSITION', subject_id: params.subject || '' });
  return q.toString();
}

function navigate(params) { revision += 1; current = null; busy = false; go('handbook', { params, push: true }); }

export function renderHandbook() {
  const ticket = ++revision;
  const params = p();
  return renderAsync('handbook', async () => {
    const [positions, roles] = await Promise.all([GET('/positions?active_only=true'), GET('/governance/roles?active_only=true')]);
    const subjects = { positions, roles };
    if (!params.subject) return { subjects, preview: null, history: [] };
    const [preview, history] = await Promise.all([
      POST('/handbooks/preview', { scope: params.scope || 'POSITION', subject_id: Number(params.subject) }),
      GET('/handbooks?' + subjectQuery(params)),
    ]);
    return { subjects, preview, history };
  }, data => {
    if (ticket !== revision) return;
    current = data;
    paint(data);
  });
}

function paint(data) {
  const params = p();
  const active = TABS[params.tab] ? params.tab : 'overview';
  const preview = data.preview;
  const subjects = params.scope === 'ROLE' ? data.subjects.roles : data.subjects.positions;
  const controls = `<label>主体类型 <select class="sel" data-handbook-scope><option value="POSITION"${params.scope !== 'ROLE' ? ' selected' : ''}>岗位</option><option value="ROLE"${params.scope === 'ROLE' ? ' selected' : ''}>治理角色</option></select></label><label>手册主体 <select class="sel" data-handbook-subject><option value="">请选择</option>${subjects.map(s => `<option value="${s.id}"${String(s.id) === String(params.subject || '') ? ' selected' : ''}>${esc(s.name)} · ${esc(s.code)}</option>`).join('')}</select></label>`;
  let body = '<div class="card"><h3>先选择岗位</h3><p>只从已发布流程和原来源编译；不会自动推断个人职责。</p></div>';
  if (preview && active === 'overview') {
    body = `<div class="card" data-handbook-overview><h3>${esc(preview.subject.name)} · 员工作业手册</h3><p>作业条目 ${preview.entries.length} 条 · 协作项 ${preview.collaboration.length} 条</p><p>${preview.can_submit_review ? '可提交正式评审。' : '当前只能预览草稿，缺口需回原设计器或原文件补齐。'}</p><div data-handbook-gates>${(preview.binding_gates || []).map(g => `<p class="tiny">${esc(g.profile_label)} · ${esc(g.consistency_label)}</p>`).join('')}</div>${preview.gaps.map(g => `<p class="warnbox">${esc(g.message)}</p>`).join('')}<p class="tiny muted">${preview.limitations.map(esc).join(' ')}</p></div>`;
  } else if (preview && active === 'entries') {
    body = `<div data-handbook-entries>${preview.entries.map(entry => foldCard(`${entry.process_code} / ${entry.name}`, `<p><b>${esc(entry.assignment_label)}</b> · 节点 ${esc(entry.node_key || '未推定')} · 模型 #${esc(entry.model_version_id)}</p><p>作业说明：${esc(entry.instruction || entry.instruction_label)}</p><p>例外：${esc(entry.exception_label)}</p>${entry.documents.map(d => `<p>${esc(d.title)} · v${esc(d.version_label)} · ${esc(d.source_label)} · ${d.openable ? `<a href="${esc(d.download_url)}">打开固定版本</a>` : '原文件不可打开'}</p>`).join('')}<button class="btn-sm btn-g" data-handbook-node data-process="${entry.process_id}" data-node="${esc(entry.node_key || '')}" data-activity="${entry.activity_ids[0] || ''}" data-model="${entry.model_version_id}">回原模型核对</button>`, { open: true })).join('') || '<div class="card">系统不知道明确作业步骤。</div>'}${foldCard('协作而非执行步骤', preview.collaboration.map(r => `<p>${esc(r.role_name)} · ${esc(r.raci_label)} · ${esc(r.node_key || '流程事项/活动')}</p>`).join('') || '<p>无</p>', { open: false })}</div>`;
  } else if (preview && active === 'history') {
    body = `<div data-handbook-history>${data.history.map(v => foldCard(`v${esc(v.version_label)} · ${esc(v.status_label)}`, `<p>固定内容 hash：${esc(v.content_hash || '—')}</p><button class="btn-sm" data-handbook-download data-url="${esc(v.download_url)}">下载固定版本</button>`, { open: true })).join('') || '<div class="card">尚未生成固定手册。</div>'}</div>`;
  }
  const shell = pageShell({ title: '员工作业手册', subtitle: '员工能看出哪些步骤归自己、该打开哪一版依据、遇到例外该按哪条原规则处理；系统不知道的，明确说不知道。', tip: tipHelp('本页只呈现原依据，不自动补写指令；职级、能力与人数配置留在工作量表。', '边界说明'), actions: controls, sections: Object.entries(TABS).map(([key, label]) => ({ key, label, html: key === active ? body : '' })), active, tabAct: 'handbook.tab', mode: 'nav', aside: preview ? sideCard('当前主体', `<p>${esc(preview.subject.name)}</p><p>缺口回原来源补齐；本页不另录职责。</p>`) : '' });
  viewEl().innerHTML = shell.html;
}

document.addEventListener('change', event => { if (event.target.matches('[data-handbook-scope]')) navigate({ scope: event.target.value, subject: '', tab: 'overview' }); else if (event.target.matches('[data-handbook-subject]')) navigate({ ...p(), subject: event.target.value, tab: 'overview' }); });
document.addEventListener('click', async event => {
  const tab = event.target.closest('[data-act="handbook.tab"]');
  if (tab) navigate({ ...p(), tab: tab.dataset.tab });
  const node = event.target.closest('[data-handbook-node]');
  if (node) go('designer', { params: { process: node.dataset.process, node: node.dataset.node, activity: node.dataset.activity, basis: node.dataset.model, tab: 'model' }, push: true });
  const downloadButton = event.target.closest('[data-handbook-download]');
  if (downloadButton) { try { await download(downloadButton.dataset.url.replace(/^\/api\/v1/, ''), '员工手册.html'); } catch (error) { /* api toast由调用层保留；当前按钮只读 */ } }
});
