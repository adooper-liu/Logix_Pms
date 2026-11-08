/* 视图：OMG BPMN 符号学习。
 *
 * 只讲本系统画布能画、保存时会拒绝的符号。不转载 OMG 规范正文。
 */

import { esc, tipHelp } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { go } from '../core/router.js';
import { pageShell } from '../core/layout.js';
import { state } from '../core/state.js';

const LESSONS = [
  {
    id: 'place',
    title: '这一页管什么',
    body: 'BPMN 是 OMG 发布的流程符号，用来画一条流程从哪一步走到哪一步。'
      + '它不负责把工作归类，归类看 PCF。它也不负责列出从业要会的全部事情，那是 CBOK。',
    points: [
      '一张 BPMN 图回答：先做哪步、在哪分支、谁在这一步上停一下。',
      '公司流程地图上的 L1、L2、L3 是架构节点，不是这张图上的符号。',
    ],
  },
  {
    id: 'flow',
    title: '顺序流',
    body: '箭头把两个符号连起来，表示做完左边再做右边。没有箭头，执行引擎不知道下一步。',
    points: [
      '一条线上可以写匹配条件。任务完成时按条件选路。',
      '条件写在设计器的连线上，执行页只按已发布的那一版走。',
    ],
  },
  {
    id: 'ends',
    title: '开始和结束',
    body: '开始事件是这条流程被启动的入口。结束事件表示这一条走到头了，实例可以收束。',
    points: [
      '一张可运行的图要有开始，也要有走到结束的路。',
      '开始不是公司地图的 L1，结束也不是「范围外」。范围外写在十层核对的范围说明里。',
    ],
  },
  {
    id: 'tasks',
    title: '任务、审批、移交',
    body: '任务是一步要做的事。本系统把用户任务用作审批，把手工任务用作移交。',
    points: [
      '审批节点要能落到人：默认处理人、候选角色，或公共队列。',
      '移交是把工作交给下一步的人，本身不是另一张流程地图。',
    ],
  },
  {
    id: 'wait',
    title: '等待',
    body: '等待用中间捕获事件表示：流程停在这里，直到外面的条件出现再继续。它不是结束。',
    points: [
      '调色板上的等待入口创建的是中间捕获事件。',
      '不要把等待画成结束事件，否则这条实例会被收掉。',
    ],
  },
  {
    id: 'xor',
    title: '互斥分支',
    body: '互斥网关表示几条路里只走一条。走哪条，由连线上的条件决定。',
    points: [
      '两条出边都写了条件时，完成任务后只应命中一条。',
      '本系统的执行引擎按串行来跑，所以这里只教互斥，不教同时走两条。',
    ],
  },
  {
    id: 'refused',
    title: '画布上不提供的符号',
    body: '执行引擎只跑串行流程。并行网关、复杂网关、事件网关、子流程、事务和边界事件不在调色板里。从外面导入带这些符号的文件，保存会被拒绝。',
    points: [
      '要表达「两件事都做完才继续」，先拆成先后两步，或分成两条流程再在地图上挂成上下级。',
      '子流程不是 L3。L3 在流程地图上，子流程是另一张图嵌进这张图，本系统不保存这种嵌套。',
    ],
  },
];

on('bpmn.lesson', ({ id }) => {
  state.bpmn.lesson = id || LESSONS[0].id;
  paint();
});

on('bpmn.jump', ({ view }) => {
  if (view) go(view);
});

function rail(current) {
  const items = [
    ['bpmn', 'BPMN 符号', '一条流程怎么走'],
    ['pcf', '流程架构', 'APQC 分类'],
    ['cbok', 'CBOK 知识域', '从业要覆盖哪些事'],
    ['train', 'BPM 实训', '学完去系统里做'],
  ];
  return `<div class="study-rail">${items.map(([view, title, sub]) => {
    if (view === current) {
      return `<div class="is-on"><b>${title}</b><div class="tiny">${sub}</div></div>`;
    }
    return `<button type="button" data-act="bpmn.jump" data-view="${view}"><b>${esc(title)}</b><div class="tiny">${esc(sub)}</div></button>`;
  }).join('')}</div>`;
}

function paint() {
  const current = LESSONS.find((item) => item.id === state.bpmn.lesson) || LESSONS[0];
  state.bpmn.lesson = current.id;
  const list = LESSONS.map((item) => `
    <button type="button" class="study-lesson${item.id === current.id ? ' on' : ''}"
      data-act="bpmn.lesson" data-id="${item.id}">${esc(item.title)}</button>`).join('');
  const points = current.points.map((line) => `<li>${esc(line)}</li>`).join('');
  const shell = pageShell({
    title: 'BPMN 符号',
    badge: '<span class="module-badge">OMG · 一条流程怎么走</span>',
    subtitle: '按本系统画布实际能画的符号来学；规范全文在 OMG，本页不转载。',
    tip: tipHelp('只讲本系统画布能画、保存时会拒绝的符号。', 'BPMN 说明'),
    sections: [{
      key: 'main',
      html: `${rail('bpmn')}
        <div class="study-layout">
          <div class="card study-list">${list}</div>
          <div class="card">
            <h3>${esc(current.title)}</h3>
            <p>${esc(current.body)}</p>
            <ul class="study-points">${points}</ul>
            <div class="gap mt">
              <button type="button" class="btn btn-p" data-act="bpmn.jump" data-view="designer">去流程设计器画</button>
              <button type="button" class="btn btn-g" data-act="bpmn.jump" data-view="pcf">去看流程架构</button>
            </div>
          </div>
        </div>`,
    }],
    active: 'main',
    mode: 'plain',
  });
  viewEl().innerHTML = shell.html;
}

const renderBpmn = () => paint();

export { renderBpmn };
