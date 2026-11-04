/* 视图：ABPMP CBOK 4.0 的读法。
 *
 * 生命周期放在「把公司流程体系立起来」。
 * 知识域 1–7 对「把一条流程建好」，8–9 留在公司体系。
 * 流程架构对 APQC。不转载手册正文，也不写未核对的考试题量。
 */

import { esc } from '../core/format.js';
import { viewEl, on } from '../core/ui.js';
import { renderAsync, go, urlParams } from '../core/router.js';
import { GET } from '../core/api.js';
import { loadLifecycle, lifecycleHtml } from '../core/lifecycle.js';
import { state } from '../core/state.js';

const AREAS = [
  {
    id: 'bpm',
    n: 1,
    lane: 'process',
    title: '业务流程管理',
    body: '先说清这条流程是什么、从哪到哪、属于核心、支持还是管理。生命周期是公司体系的顺序，这一项把顺序用在一条流程上。',
    here: '十层核对写这一条的起止和范围。公司地图和谁能改图，在开始使用。',
    view: 'pilot',
    button: '打开十层核对',
  },
  {
    id: 'model',
    n: 2,
    lane: 'process',
    title: '流程建模',
    body: '把一条流程画成能沟通、能度量、能执行的图。本系统的符号是 BPMN。分类名去流程架构，不要画进箭头里。',
    here: '流程设计器画图。BPMN 学习页列出能保存和不能保存的符号。',
    view: 'designer',
    button: '打开流程设计器',
  },
  {
    id: 'analysis',
    n: 3,
    lane: 'process',
    title: '流程分析',
    body: '现状拆解、瓶颈识别、根因分析、价值流分析、规则与上下文、绩效基线。六项都落在已有记录上。',
    here: '过程挖掘读已记下的路径。测算给出瓶颈和增值占比。异常和项目上写根因。KPI 上记基线值。',
    view: 'monitor',
    params: 'tab=analysis',
    button: '打开流程分析',
  },
  {
    id: 'design',
    n: 4,
    lane: 'process',
    title: '流程设计',
    body: '按要达成的结果画出以后的走法：步骤、规则、控制点和谁来处理。',
    here: '在设计器改完要发布。没发布的草稿不会换成已经在跑的实例。',
    view: 'designer',
    button: '打开流程设计器',
  },
  {
    id: 'performance',
    n: 5,
    lane: 'process',
    title: '流程绩效',
    body: '同时看花了多少时间与成本，和结果有没有用。只看快不快，不够。',
    here: 'KPI 页签记公式、阈值、责任人、数据点和达成率。',
    view: 'monitor',
    params: 'tab=kpi',
    button: '打开 KPI',
  },
  {
    id: 'change',
    n: 6,
    lane: 'process',
    title: '流程变革',
    body: '改进、重画或重做，都要有范围、有人负责。改完再落到已发布的走法。',
    here: '流程项目组合记改善项目。十层核对记已经应用的变更。',
    view: 'projects',
    button: '打开流程项目组合',
  },
  {
    id: 'tech',
    n: 7,
    lane: 'process',
    title: '流程技术',
    body: '表单、规则、机器人、挖掘、人工智能是帮手。流程还乱的时候，不要先自动化。业务系统管数据和事务，这里管跨步骤的走法。',
    here: '流程执行放表单和运行。十层核对记录机器人运行、挖掘路径和技术用途。没有一条会自己连上外部系统。',
    view: 'execution',
    button: '打开流程执行',
  },
  {
    id: 'org',
    n: 8,
    lane: 'company',
    title: '流程组织',
    body: '流程负责人对端到端结果负责，不等于部门经理管手下所有人。组织还要有谁能改图、谁审批。',
    here: '组织与人员维护岗位和治理角色。授权矩阵写审批人、例外和证据。',
    view: 'orgs',
    button: '打开组织与人员',
  },
  {
    id: 'enterprise',
    n: 9,
    lane: 'company',
    title: '企业流程管理',
    body: '把单条流程放回全公司：上下级怎么挂，对外用哪套分类对齐。流程架构对的是 APQC，不是先后顺序。',
    here: '流程架构页是 APQC 分类。企业流程地图是公司自己的树。',
    view: 'map',
    button: '打开企业流程地图',
  },
];

const LANE = { process: '一条流程', company: '公司体系' };

on('cbok.area', ({ id }) => {
  state.cbok.area = id || 'read';
  renderCbok();
});

on('cbok.jump', ({ view, params }) => {
  if (!view) return;
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  go(view, Object.keys(parsed).length ? { params: parsed, push: true } : undefined);
});

function rail(current) {
  const items = [
    ['bpmn', 'BPMN 符号', '一条流程怎么走'],
    ['pcf', '流程架构', 'APQC 分类'],
    ['cbok', 'CBOK 知识域', '九项落在哪一页'],
    ['train', 'BPM 实训', '学完去系统里做'],
  ];
  return `<div class="study-rail">${items.map(([view, title, sub]) => {
    if (view === current) {
      return `<div class="is-on"><b>${title}</b><div class="tiny">${sub}</div></div>`;
    }
    return `<button type="button" data-act="cbok.jump" data-view="${view}"><b>${esc(title)}</b><div class="tiny">${esc(sub)}</div></button>`;
  }).join('')}</div>`;
}

function readPane() {
  return `
    <h3>怎么读</h3>
    <p>流程承接战略，不是把部门制度订成一册。先看现状，再定以后怎么走。技术是帮手，流程还乱就不要先自动化。</p>
    <ul class="study-points">
      <li>流程负责人对端到端结果负责，不等于部门经理。</li>
      <li>模型用来沟通、度量、治理和执行，不是存档。</li>
      <li>绩效同时看时间成本，和结果有没有用。</li>
      <li>治理是管流程的流程：版本、谁能改、指标、审计、下一轮。</li>
      <li>业务系统管数据和事务。这条产品管跨步骤的走法和规则。</li>
    </ul>
    <h3>学习顺序</h3>
    <ol class="study-points">
      <li>先看上面的生命周期，再看左边九项各自打开哪一页。</li>
      <li>建模打开 BPMN 符号，再去设计器画。</li>
      <li>分析打开六项记录。绩效打开 KPI。</li>
      <li>组织和治理在公司体系：组织与人员、授权矩阵。</li>
      <li>技术只看到边界。机器人、挖掘和用途是记下的结果，不代替外部系统。</li>
    </ol>
    <div class="note">认证名称是 CBPA（先掌握九项在说什么）和 CBPP（再做分析和设计）。题量和分数线以协会当期考试说明为准，这里不写死。</div>`;
}

function areaPane(area) {
  return `
    <h3>${area.n}. ${esc(area.title)}</h3>
    <div class="tiny muted mb">${esc(LANE[area.lane])}</div>
    <p>${esc(area.body)}</p>
    <div class="note">${esc(area.here)}</div>
    <div class="gap mt">
      <button type="button" class="btn btn-p" data-act="cbok.jump" data-view="${esc(area.view)}"${
        area.params ? ` data-params="${esc(area.params)}"` : ''}>${esc(area.button)}</button>
      ${area.id === 'model' ? '<button type="button" class="btn btn-g" data-act="cbok.jump" data-view="bpmn">去看 BPMN 符号</button>' : ''}
      ${area.id === 'enterprise' ? '<button type="button" class="btn btn-g" data-act="cbok.jump" data-view="pcf">去看流程架构</button>' : ''}
      <button type="button" class="btn btn-g" data-act="cbok.jump" data-view="train" data-params="module=${esc(area.id)}">去实训这一讲</button>
    </div>`;
}

function paint(data, processes) {
  const currentId = state.cbok.area || 'read';
  const area = AREAS.find((item) => item.id === currentId);
  state.cbok.area = area ? area.id : 'read';
  const lessons = [{ id: 'read', label: '怎么读' }].concat(AREAS.map((item) => ({
    id: item.id,
    label: `${item.n}. ${item.title}`,
    lane: item.lane,
  })));
  const list = lessons.map((item) => `
    <button type="button" class="study-lesson${item.id === state.cbok.area ? ' on' : ''}"
      data-act="cbok.area" data-id="${item.id}">${esc(item.label)}${
        item.lane ? `<span class="tiny"> ${esc(LANE[item.lane])}</span>` : ''}</button>`).join('');
  viewEl().innerHTML = `
    <div class="card page-head">
      <h2>CBOK 知识域<span class="module-badge">ABPMP 4.0 · 九项落在哪一页</span></h2>
      <p class="desc">生命周期是长期流程的管理导航，不是阶段推进器。知识域 1 到 7 在「把一条流程建好」，8 和 9 留在公司体系。流程架构对 APQC。手册正文不转载。</p>
      ${lifecycleHtml(data, processes)}
      ${rail('cbok')}
    </div>
    <div class="study-layout">
      <div class="card study-list">${list}</div>
      <div class="card">${area ? areaPane(area) : readPane()}</div>
    </div>`;
}

const renderCbok = () => renderAsync('cbok', () => Promise.all([loadLifecycle(urlParams()), GET('/process-map/flat')]), ([data, processes]) => paint(data, processes));

export { renderCbok };
