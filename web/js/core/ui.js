/* 通用 UI 原语：提示条、模态框、事件委托根、确认/输入对话框。 */

import { esc } from './format.js';

export const viewEl = () => document.getElementById('view');

export function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.toggle('err', !!isError);
  t.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => t.classList.remove('show'), isError ? 4200 : 2000);
}

/**
 * 弹窗代号。异步流程（先显示"加载中"，拿到数据再填内容）必须靠它判断
 * 自己是否还是"当前那个弹窗"——否则用户在请求返回前关掉弹窗，
 * 内容回来后又会把弹窗重新弹出来。openModal / closeModal 都会让代号自增，
 * 从而作废所有在途的异步弹窗。
 */
let modalGen = 0;
/** 关闭钩子：confirmDialog / promptDialog 用它把「用户点了关闭」变成取消结果 */
let modalCloseHandler = null;

function resolveModalClose() {
  const handler = modalCloseHandler;
  modalCloseHandler = null;
  if (handler) handler();
}

export function openModal(title, body, foot, wide) {
  resolveModalClose();
  document.getElementById('mTitle').textContent = title;
  document.getElementById('mBody').innerHTML = body;
  document.getElementById('mFoot').innerHTML = foot ||
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>';
  const m = document.getElementById('modal');
  m.classList.toggle('wide', !!wide);
  m.scrollTop = 0;
  document.getElementById('mask').classList.add('show');
  return ++modalGen;
}

export function closeModal() {
  document.getElementById('mask').classList.remove('show');
  modalGen++;
  resolveModalClose();
}

/** 异步回填前调用；返回 false 说明弹窗已被关闭或被别的弹窗取代，应放弃本次渲染 */
export function modalAlive(gen) {
  return gen === modalGen;
}

/** 模态框内的标签页切换 */
export function tab(btn, id) {
  const body = document.getElementById('mBody');
  body.querySelectorAll(':scope > div[data-pane]').forEach((d) => d.classList.add('hide'));
  const pane = document.getElementById(id);
  if (pane) pane.classList.remove('hide');
  btn.parentElement.querySelectorAll('button').forEach((b) => b.classList.remove('on'));
  btn.classList.add('on');
}

/* -------------------------------------------------- 事件委托根
 *
 * 行为写在 JS 里，模板只写 data-act。注意：
 * - 不能只监听 click：筛选器主要用 change/input，表单回车用 submit；
 * - toggle 事件不冒泡，<details> 的状态变化仍用直接监听；
 * - data-act 只应挂在 button/a 上（静态守卫会检查）；
 * - 键名必须带视图前缀，如 knowledge.open、map.openProject。
 */
const DELEGATES = new Map();
const EVENT_TYPES = ['click', 'change', 'input', 'submit', 'keydown'];
const NATIVE_INTERACTIVE = new Set(['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY']);

export function on(dataAct, handler) {
  if (DELEGATES.has(dataAct)) {
    throw new Error(`data-act 重名：${dataAct}`);
  }
  DELEGATES.set(dataAct, handler);
}

export function delegateCount() {
  return DELEGATES.size;
}

if (typeof document !== 'undefined') {
  for (const type of EVENT_TYPES) {
    document.addEventListener(type, (event) => {
      const target = event.target;
      const el = target && target.closest ? target.closest('[data-act]') : null;
      if (!el) return;
      const handler = DELEGATES.get(el.dataset.act);
      if (!handler) return;
      // <select> / checkbox / radio 会同时触发 input 与 change；只处理 change，
      // 否则同一个动作会执行两次（真实事故：步骤状态被 PATCH 两次）。
      if (type === 'input') {
        const tag = el.tagName;
        if (tag === 'SELECT' || el.type === 'checkbox' || el.type === 'radio') return;
      }
      if (type === 'keydown') {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        // 原生 button/a 由浏览器合成 click，避免重复触发
        if (NATIVE_INTERACTIVE.has(el.tagName)) return;
        event.preventDefault();
      }
      if (type === 'submit') event.preventDefault();
      handler(el.dataset, el, event);
    });
  }
}

/* -------------------------------------------------- 确认 / 输入对话框
 *
 * 替换原生 confirm()/prompt()：视觉、行为、可访问性都与自建模态框一致。
 * 返回 Promise：confirm 为 boolean，prompt 为 string | null。
 */

function dialogFoot(cancelText, okText, danger) {
  return `<button class="btn btn-g" id="uiDialogCancel">${esc(cancelText)}</button>
    <button class="btn ${danger ? 'btn-d' : 'btn-p'}" id="uiDialogOk">${esc(okText)}</button>`;
}

function bindDialog(settle) {
  modalCloseHandler = () => settle(false, null);
  document.getElementById('uiDialogCancel').addEventListener('click', () => settle(false, null));
  document.getElementById('uiDialogOk').addEventListener('click', () => settle(true, null));
}

export function confirmDialog(message, options = {}) {
  const title = options.title || '确认';
  const okText = options.okText || '确定';
  const cancelText = options.cancelText || '取消';
  return new Promise((resolve) => {
    let settled = false;
    const settle = (ok) => {
      if (settled) return;
      settled = true;
      modalCloseHandler = null;
      closeModal();
      resolve(ok);
    };
    openModal(title, `<div class="ui-dialog-msg">${esc(message)}</div>`,
      dialogFoot(cancelText, okText, options.danger));
    bindDialog((ok) => settle(ok));
  });
}

export function promptDialog(message, options = {}) {
  const title = options.title || '输入';
  const okText = options.okText || '确定';
  const cancelText = options.cancelText || '取消';
  const value = options.value || '';
  const placeholder = options.placeholder || '';
  return new Promise((resolve) => {
    let settled = false;
    const settle = (ok, result) => {
      if (settled) return;
      settled = true;
      modalCloseHandler = null;
      const input = document.getElementById('uiDialogInput');
      closeModal();
      resolve(ok && input ? input.value : result);
    };
    openModal(title, `
      <div class="ui-dialog-msg">${esc(message)}</div>
      <div class="field" style="margin-top:12px">
        <input id="uiDialogInput" value="${esc(value)}" placeholder="${esc(placeholder)}">
      </div>`,
    dialogFoot(cancelText, okText, options.danger));
    bindDialog((ok) => settle(ok, null));
    const input = document.getElementById('uiDialogInput');
    if (input) {
      input.focus();
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          settle(true, null);
        }
      });
    }
  });
}
