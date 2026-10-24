/* bpmn-js 扩展点：调色板、上下文菜单、「更改元素」菜单。
 *
 * 执行引擎只支持串行流程，这里把不支持的构造从界面上隐藏，
 * 避免用户画完才在保存时被后端拒绝。
 */

import { state } from '../../core/state.js';

const UNSUPPORTED_REPLACE_FRAGMENTS = [
  'parallel-gateway', 'complex-gateway', 'event-based-gateway',
  'transaction', 'subprocess', 'boundary',
];

function isUnsupportedReplaceEntry(key) {
  return key.startsWith('replace-with-')
    && UNSUPPORTED_REPLACE_FRAGMENTS.some((fragment) => key.includes(fragment));
}

function PmsPaletteProvider(palette, create, elementFactory) {
  this._create = create;
  this._elementFactory = elementFactory;
  palette.registerProvider(500, this);
}
PmsPaletteProvider.$inject = ['palette', 'create', 'elementFactory'];
PmsPaletteProvider.prototype.getPaletteEntries = function () {
  const create = this._create;
  const elementFactory = this._elementFactory;
  const startWait = (event) => {
    create.start(event, elementFactory.createShape({ type: 'bpmn:IntermediateCatchEvent' }));
  };
  const startCreate = (type) => (event) => {
    create.start(event, elementFactory.createShape({ type }));
  };
  // 返回函数而不是对象：在默认调色板（优先级 1000）之后执行，才能删掉既有条目
  return function (entries) {
    delete entries['create.subprocess-expanded'];
    // 默认条目会创建抛出事件；拖到活动上还会变成执行引擎不支持的边界事件
    delete entries['create.intermediate-event'];
    entries['create.pms-wait-event'] = {
      group: 'event',
      className: 'bpmn-icon-intermediate-event-none pms-wait-entry',
      title: '创建等待事件（中间捕获事件，不是结束事件）',
      action: { dragstart: startWait, click: startWait },
    };
    // 简洁画布删除后，审批/移交仍需要直接入口
    entries['create.pms-approval'] = {
      group: 'activity',
      className: 'bpmn-icon-user',
      title: '创建审批节点',
      action: {
        dragstart: startCreate('bpmn:UserTask'),
        click: startCreate('bpmn:UserTask'),
      },
    };
    entries['create.pms-handoff'] = {
      group: 'activity',
      className: 'bpmn-icon-manual',
      title: '创建移交节点',
      action: {
        dragstart: startCreate('bpmn:ManualTask'),
        click: startCreate('bpmn:ManualTask'),
      },
    };
    // 评审/只读时保留调色板可见，但禁止创建元素；导航工具仍可用
    if (!state.designer.editable) {
      Object.keys(entries).forEach((key) => {
        if (key.startsWith('create.') && entries[key]) {
          entries[key] = { ...entries[key], action: {} };
        }
      });
    }
    return entries;
  };
};

function PmsContextPadProvider(contextPad) {
  contextPad.registerProvider(500, this);
}
PmsContextPadProvider.$inject = ['contextPad'];
PmsContextPadProvider.prototype.getContextPadEntries = function () {
  return function (entries) {
    delete entries['append.intermediate-event'];
    return entries;
  };
};

function PmsReplaceMenuProvider(popupMenu) {
  popupMenu.registerProvider('bpmn-replace', 500, this);
}
PmsReplaceMenuProvider.$inject = ['popupMenu'];
PmsReplaceMenuProvider.prototype.getPopupMenuEntries = function () {
  return function (entries) {
    Object.keys(entries).forEach((key) => {
      if (isUnsupportedReplaceEntry(key)) delete entries[key];
    });
    return entries;
  };
};

export const PMS_BPMN_GUARDS = {
  __init__: ['pmsPaletteProvider', 'pmsContextPadProvider', 'pmsReplaceMenuProvider'],
  pmsPaletteProvider: ['type', PmsPaletteProvider],
  pmsContextPadProvider: ['type', PmsContextPadProvider],
  pmsReplaceMenuProvider: ['type', PmsReplaceMenuProvider],
};
