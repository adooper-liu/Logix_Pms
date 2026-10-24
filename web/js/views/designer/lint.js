/* bpmnlint：规则执行、结果中文化与问题定位。
 *
 * 规则名和英文消息对业务用户不友好，这里逐条翻译成「问题 + 建议」；
 * 未收录的规则保留原始消息，但仍以中文标题呈现，避免界面突然冒出英文。
 */

import { esc } from '../../core/format.js';
import { toast } from '../../core/ui.js';
import { state } from '../../core/state.js';

const BPMN_LINT_HELP = {
  'start-event-required': {
    title: '缺少开始节点',
    detail: '整个流程没有开始事件。运行时只能按「唯一入口」推断起点，流程一复杂就可能推错。',
    action: '从调色板添加开始事件，并把第一条活动连到它。',
  },
  'end-event-required': {
    title: '缺少结束节点',
    detail: '整个流程没有结束事件。注意：等待事件（中间捕获/抛出事件）不算结束事件。',
    action: '从调色板添加粗圆圈的结束事件，并把最终活动连到它。',
  },
  'no-implicit-start': {
    title: '节点被当作隐式起点',
    detail: '这个节点没有上游连线，运行时会被当成流程入口。',
    action: '如果它确实是起点，建议改成开始事件；否则补上上游连线。',
  },
  'no-implicit-end': {
    title: '节点被当作隐式终点',
    detail: '这个节点没有下游连线，执行到这里实例会直接结束。若是等待事件，它不会起到结束事件的作用。',
    action: '如果流程还要继续，补下游连线；如果到此结束，接一个结束事件。',
  },
  'fake-join': {
    title: '多路汇入没有网关',
    detail: '有多条上游连线直接汇入这个节点，中间没有汇合网关，执行语义不明确。',
    action: '在汇入处加一个排他网关，让分支先汇合再进入该节点。',
  },
  'no-implicit-split': {
    title: '节点被当作隐式分支',
    detail: '这个节点有多条下游连线，但没有用网关明确分支。',
    action: '改用判断（排他）网关分支，执行引擎才能按条件路由。',
  },
  'superfluous-label': {
    title: '连线标签不会生效',
    detail: '这条连线填了标签，但起点不是判断或审批节点，标签不会参与运行时路由。',
    action: '删除标签；如果要按条件走不同分支，请把起点改为判断节点并配置条件。',
  },
  'conditional-flows': {
    title: '分支缺少条件',
    detail: '从判断节点分出的连线没有配置条件表达式。',
    action: '为每条分支补上条件，并设置一条默认分支兜底。',
  },
  'no-disconnected': {
    title: '元素没有接入流程',
    detail: '这个元素与主流程没有连线，运行时永远不会执行。',
    action: '用连线把它接入流程，或删除它。',
  },
  'label-required': {
    title: '元素缺少名称',
    detail: '这个元素还没有名称，任务列表和运行记录里无法辨认。',
    action: '双击元素补上名称。',
  },
  'no-duplicate-sequence-flows': {
    title: '存在重复连线',
    detail: '同一对节点之间有多条完全相同的连线。',
    action: '删除重复的连线，只保留一条。',
  },
  'superfluous-gateway': {
    title: '网关是多余的',
    detail: '这个网关只有一个入边和一个出边，没有起到分支或汇合作用。',
    action: '删除网关，直接把前后两个节点连起来。',
  },
  'no-gateway-join-fork': {
    title: '网关同时分流和汇合',
    detail: '同一个网关既做分支又做汇合，执行语义容易混淆。',
    action: '拆成两个网关：前面负责分流，后面负责汇合。',
  },
  'single-blank-start-event': {
    title: '开始事件不唯一',
    detail: '流程里有多个无类型开始事件，运行时无法确定从哪个开始。',
    action: '只保留一个无类型开始事件；其余改成带触发类型的开始事件或删除。',
  },
  'single-event-definition': {
    title: '事件定义重复',
    detail: '同一个事件配置了多个事件定义（例如同时是消息和定时），运行时无法判断用哪个。',
    action: '只保留一个事件定义。',
  },
  'sub-process-blank-start-event': {
    title: '子流程开始事件不规范',
    detail: '子流程里有不带事件定义的开始事件。',
    action: '为子流程的开始事件补上事件定义，或改用普通开始事件。',
  },
  'event-sub-process-typed-start-event': {
    title: '事件子流程缺少事件定义',
    detail: '事件子流程的开始事件需要消息、定时或信号等事件定义。',
    action: '给开始事件补上对应的事件定义。',
  },
  'event-based-gateway': {
    title: '不支持事件网关',
    detail: '执行引擎只做串行流程，事件网关不在支持范围内。',
    action: '改用排他网关，或把等待改成中间捕获事件。',
  },
  'no-complex-gateway': {
    title: '不支持复杂网关',
    detail: '执行引擎只做串行流程，复杂网关不在支持范围内。',
    action: '改用排他网关。',
  },
  'no-inclusive-gateway': {
    title: '不推荐包容网关',
    detail: '包容网关的多路执行语义与当前单令牌执行引擎不一致。',
    action: '改用排他网关。',
  },
  'ad-hoc-sub-process': {
    title: '不支持 Ad-hoc 子流程',
    detail: '执行引擎不支持 Ad-hoc 子流程。',
    action: '删掉子流程，把内部活动展开到主流程。',
  },
  'link-event': {
    title: '链接事件缺少名称',
    detail: '链接事件没有填写链接名称，无法与配对的另一个链接事件对应。',
    action: '在属性里补上链接名称。',
  },
  'no-overlapping-elements': {
    title: '元素在画布上重叠',
    detail: '两个元素的位置重叠，容易看错连线关系。',
    action: '拖动分开，或使用「自动布局」重新排列。',
  },
  'superfluous-termination': {
    title: '终止事件是多余的',
    detail: '终止事件后面没有其他元素，终止语义没有实际作用。',
    action: '改成普通结束事件。',
  },
  'no-bpmndi': {
    title: '缺少图形信息',
    detail: '元素没有对应的 BPMN DI 坐标，画布上无法定位。',
    action: '在 bpmn-js 里重新保存一次，让图形信息补齐。',
  },
  'rule-error': {
    title: '校验规则执行失败',
    detail: '这条规则本身报错，通常是模型结构异常。',
    action: '保存后重试；仍然失败请反馈给流程管理科。',
  },
  global: {
    title: '使用了全局任务',
    detail: '全局任务不是可执行的流程节点。',
    action: '改成普通任务或删除。',
  },
};

export function createLint(ctx) {
  function hydrateConnections(container) {
    const elements = (container && container.flowElements) || [];
    elements.forEach((element) => {
      if (element.$type !== 'bpmn:SequenceFlow') return;
      const source = element.sourceRef;
      const target = element.targetRef;
      if (source) {
        source.outgoing = source.outgoing || [];
        if (!source.outgoing.includes(element)) source.outgoing.push(element);
      }
      if (target) {
        target.incoming = target.incoming || [];
        if (!target.incoming.includes(element)) target.incoming.push(element);
      }
    });
    elements.forEach((element) => {
      if (element.flowElements) hydrateConnections(element);
    });
  }

  function render() {
    const box = document.getElementById('bpmnLint');
    if (!box) return;
    const issues = state.designer.bpmnLint || [];
    const errors = issues.filter((i) => i.category === 'error').length;
    const warns = issues.filter((i) => i.category !== 'error').length;
    const toggle = document.getElementById('bpmnLintToggle');
    if (toggle) {
      toggle.textContent = issues.length ? `校验问题 ${issues.length}` : '校验问题 无';
      toggle.classList.toggle('has-error', errors > 0);
      toggle.classList.toggle('has-warn', errors === 0 && warns > 0);
    }
    const summary = `<div class="between mb"><b>建模校验</b>
      <span class="tiny">${errors} 错误 · ${warns} 警告</span></div>`;
    if (!issues.length) {
      box.innerHTML = `${summary}<div class="tiny muted">bpmnlint 未发现问题</div>`;
      return;
    }
    box.innerHTML = `
      ${summary}
      ${issues.map((issue, index) => {
        const element = issue.meta && issue.meta.element;
        const bo = element && element.businessObject;
        const isProcess = bo && (bo.$type === 'bpmn:Process' || bo.$type === 'bpmn:Collaboration');
        const label = element && !isProcess ? ((bo && (bo.name || bo.id)) || element.id) : '整个流程';
        const category = issue.category === 'error' ? 'error' : 'warn';
        const help = BPMN_LINT_HELP[issue.rule];
        const title = help ? help.title : '建模规范提示';
        const detail = help ? help.detail : (issue.message || '');
        const raw = issue.rule + (issue.message ? '：' + issue.message : '');
        return `<button class="bpmn-lint-item ${category}" type="button"
            data-act="designer.lintIssue" data-index="${index}" title="${esc(raw)}">
          <div class="bpmn-lint-head">
            <span class="tag ${category === 'error' ? 't-red' : 't-yel'}">${
              category === 'error' ? '错误' : '警告'}</span>
            <b>${esc(title)}</b>
            <span class="tiny muted">${esc(label)}</span>
          </div>
          <div class="bpmn-lint-detail">${esc(detail)}</div>
          ${help && help.action
            ? `<div class="bpmn-lint-action muted">建议：${esc(help.action)}</div>` : ''}
        </button>`;
      }).join('')}`;
  }

  async function run() {
    const st = state.designer;
    const modeler = ctx.getModeler();
    if (!modeler) return;
    try {
      await ctx.loadLint();
      const definitions = modeler.getDefinitions();
      (definitions.rootElements || []).forEach((root) => {
        if (root.$type === 'bpmn:Process') hydrateConnections(root);
      });
      const grouped = await window.BpmnLint.lint(definitions);
      const registry = modeler.get('elementRegistry');
      const issues = [];
      Object.entries(grouped || {}).forEach(([rule, list]) => {
        (list || []).forEach((issue) => {
          const element = issue.id ? registry.get(issue.id) : null;
          issues.push({
            ...issue,
            rule,
            meta: { ...(issue.meta || {}), element },
          });
        });
      });
      // 错误优先，方便先处理会阻塞发布的问题；同级别保持规则原始顺序
      issues.sort((a, b) => (a.category === 'error' ? 0 : 1) - (b.category === 'error' ? 0 : 1));
      st.bpmnLint = issues;
      render();
    } catch (e) {
      toast(e.message, true);
    }
  }

  function selectIssue(index) {
    const issue = (state.designer.bpmnLint || [])[index];
    const element = issue && issue.meta && issue.meta.element;
    if (!element) return;
    const modeler = ctx.getModeler();
    if (!modeler) return;
    ctx.select(element);
    modeler.get('canvas').scrollToElement(element);
    // 跳到属性页签，方便直接修改刚定位到的节点
    ctx.showSidebar('props');
  }

  return { run, selectIssue };
}
