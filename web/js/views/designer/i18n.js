/* bpmn-js 内置文案中文化。
 *
 * 只翻译通用 UI 文案；业务节点名与操作提示仍在各自的 providers/panels 中维护。
 */

const DICT = {
  'Activate hand tool': '抓手工具',
  'Activate lasso tool': '套索选择',
  'Activate space tool': '空间工具',
  'Activate create/remove space tool': '空间工具',
  'Activate global connect tool': '全局连线',
  'Append {type}': '追加 {type}',
  'Create {type}': '创建 {type}',
  'Change element': '更改元素',
  'Delete': '删除',
  'Remove': '移除',
  'Edit': '编辑',
  'Connect using sequence/message flow or association': '用连线接入流程',
  'Search in diagram': '在图中搜索',
  'Undo': '撤销',
  'Redo': '重做',
  'Zoom in': '放大',
  'Zoom out': '缩小',
  'Fit viewport': '适应画布',
  'Toggle fullscreen': '全屏/退出全屏',
  'Add text annotation': '添加文本注释',
  'Open {element}': '打开 {element}',
  'No results': '没有结果',
  'Search': '搜索',
  'Show properties panel': '显示属性面板',
  'Hide properties panel': '收起属性面板',
  'Activate the hand tool': '切换到抓手工具',
  'Activate the lasso tool': '切换到套索选择',
  'Activate the space tool': '切换到空间工具',
  'Activate the global connect tool': '切换到全局连线',
};

export function translate(template, replacements) {
  const text = DICT[template] || template;
  if (!replacements) return text;
  return text.replace(/\{([^}]+)\}/g, (match, key) =>
    Object.prototype.hasOwnProperty.call(replacements, key) ? replacements[key] : match);
}

export function createTranslateModule() {
  return { translate: ['value', translate] };
}
