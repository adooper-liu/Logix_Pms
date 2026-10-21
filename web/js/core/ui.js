/* 通用 UI 原语：提示条、模态框、视图容器。 */

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

export function openModal(title, body, foot, wide) {
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
