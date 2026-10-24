/* 跨视图动作注册表（叶子模块）。
 *
 * 设计约束：
 * - 本文件**不得 import 任何 views/**，否则会和视图形成环；
 * - 视图只把自己真正需要跨视图调用的动作导出为 `actions` map，
 *   由 main.js（组合根）收集后调用 registerActions() 注册；
 * - 动作键必须带视图前缀，如 `map.openProject`，注册时查重。
 *
 * DOM 事件委托的处理器登记在 core/ui.js 的 on(dataAct, handler)，
 * 与这里的「可编程动作」分开：前者面向模板，后者面向 JS 调用。
 */

export const actions = Object.create(null);

const owners = Object.create(null);
const NAME_RE = /^[a-z][a-z0-9]*\.[A-Za-z][A-Za-z0-9_]*$/;

export function registerActions(map, source) {
  for (const [name, fn] of Object.entries(map || {})) {
    if (!NAME_RE.test(name)) {
      throw new Error(`action 名必须以视图前缀命名（如 map.openProject）：${name}`);
    }
    if (typeof fn !== 'function') {
      throw new Error(`action ${name} 不是函数`);
    }
    if (actions[name]) {
      throw new Error(`action 重名：${name}（已由 ${owners[name] || '未知来源'} 注册）`);
    }
    actions[name] = fn;
    owners[name] = source || 'unknown';
  }
}

export function actionKeys() {
  return Object.keys(actions).sort();
}

export function getAction(name) {
  return actions[name];
}
