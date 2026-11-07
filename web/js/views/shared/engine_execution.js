/* Engine command feedback shares the original execution page; never replace an unresolved request. */
import { api } from '../../core/api.js';
import { esc } from '../../core/format.js';
import { on, openModal, toast } from '../../core/ui.js';
import { RENDERERS } from '../../core/router.js';

const pendingKey = 'logix.engine.pending';

export async function executionWrite(path, body, method = 'POST') {
  const saved = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
  if (saved) {
    showPending(saved);
    throw new Error('原请求结果待核对，请先恢复原命令');
  }
  const intent = { path, method, body, key: crypto.randomUUID() };
  sessionStorage.setItem(pendingKey, JSON.stringify(intent));
  let value;
  try {
    value = await api(path, { method, body: body || {}, headers: { 'Idempotency-Key': intent.key } });
  } catch (error) {
    if (error.status && error.status < 500) sessionStorage.removeItem(pendingKey);
    else showPending(intent);
    throw error;
  }
  if (value && value.command_id) {
    intent.command_id = value.command_id;
    sessionStorage.setItem(pendingKey, JSON.stringify(intent));
    if (value.status !== 'SUCCEEDED' || value.error) {
      showPending(intent, value);
      throw new Error(value.error || value.status_label);
    }
  }
  sessionStorage.removeItem(pendingKey);
  return value;
}

function showPending(intent, value = {}) {
  openModal('原请求待核对', `<div class="note">请求已保存，结果待核对；请勿重新发起。</div>
    <p>${esc(value.error || value.status_label || '连接中断，请核对原请求')}</p>
    <p class="tiny">${esc(intent.command_id || intent.key)}</p>
    <button class="btn btn-p" data-act="engine.recover">核对原请求</button>`);
}

on('engine.recover', async () => {
  const intent = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
  if (!intent) return;
  try {
    const result = intent.command_id
      ? await api('/execution/engine/commands/' + intent.command_id + '/recover', { method: 'POST', body: {} })
      : await api(intent.path, { method: intent.method, body: intent.body || {}, headers: { 'Idempotency-Key': intent.key } });
    if (result.command_id && (result.status !== 'SUCCEEDED' || result.error)) {
      intent.command_id = result.command_id;
      sessionStorage.setItem(pendingKey, JSON.stringify(intent));
      return showPending(intent, result);
    }
    sessionStorage.removeItem(pendingKey);
    toast('原请求已核对');
    RENDERERS.execution();
  } catch (error) { toast(error.message, true); }
});

export function engineConfigurationHtml(data, processId) {
  if (!data || data.provider !== 'FLOWABLE') return '';
  return `<section class="note"><h3>${esc(data.provider_label)}</h3>
    <p>仅沙箱合成数据，不代表生产上线。</p><p>${esc(data.state_label)}</p>
    <div class="tiny">模型 ${esc(data.model_version_id || '—')} / 定义 ${esc(data.definition_id || '—')}</div>
    ${(data.missing || []).map(x => `<p>${esc(x)}</p>`).join('')}
    <button class="btn btn-g" data-act="engine.deploy" data-model="${data.model_version_id}" ${data.enabled ? '' : 'disabled'}>部署当前发布版本</button>
    <button class="btn btn-p" data-act="engine.enable" data-process="${processId}" data-deployment="${data.deployment_id || ''}" ${data.deployment_current ? '' : 'disabled'}>确认启用沙箱新启动</button>
    <button class="btn btn-g" data-act="engine.disable" data-process="${processId}" data-deployment="${data.deployment_id || ''}" ${data.deployment_id ? '' : 'disabled'}>停止新启动</button>
    <button class="btn btn-g" data-act="engine.pending">核对未决请求</button></section>`;
}

on('engine.pending', () => {
  const intent = JSON.parse(sessionStorage.getItem(pendingKey) || 'null');
  if (intent) showPending(intent); else toast('本浏览器会话没有未决请求');
});
on('engine.deploy', async ({ model }) => {
  try { await executionWrite('/execution/engine/deploy', { model_version_id: Number(model) }); RENDERERS.execution(); }
  catch (error) { toast(error.message, true); }
});
for (const [action, enabled] of [['enable', true], ['disable', false]]) {
  on('engine.' + action, async ({ process, deployment }) => {
    try { await executionWrite('/execution/engine/enable', { process_id: Number(process), deployment_id: Number(deployment), enabled }); RENDERERS.execution(); }
    catch (error) { toast(error.message, true); }
  });
}
on('engine.reconcile', async ({ id }) => {
  try { await executionWrite('/execution/engine/instances/' + id + '/reconcile', {}); RENDERERS.execution(); }
  catch (error) { toast(error.message, true); }
});
