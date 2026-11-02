/* 视图：BPM 实训。
 *
 * 正文是九讲逐字稿。本系统的页面只出现在每讲末尾的实证，用来对照，不代替讲义。
 * 实证里的下一步来自 /train/coach，只读已有记录，不接外部语言模型。
 */

import { esc } from '../core/format.js';
import { viewEl, on, toast } from '../core/ui.js';
import { go, renderAsync, urlParams } from '../core/router.js';
import { state } from '../core/state.js';
import { GET } from '../core/api.js';
import { LECTURE } from './train/lecture.js';

const DONE_KEY = 'psm_train_done';

const EVIDENCE = {
  bpm: {
    lead: '十层核对用来写清一条流程从哪开始、到哪结束。公司地图谁能改，在开始使用。',
    view: 'pilot',
    button: '打开十层核对',
    gap: '讲义把生命周期写成八段。本系统在监控和变革之后还有治理：谁能改图、谁审批。地图层级是 L1 到 L4，活动在 L4。',
    check: {
      q: '只把本部门的步骤做快，算流程改好了吗？',
      a: '不算。要看从触发到客户拿到结果的整段。局部变快、前后仍在等，客户感觉不到。',
    },
  },
  model: {
    lead: '符号页对照 BPMN。能执行的图在设计器里，发布之后执行才读。',
    view: 'bpmn',
    button: '打开 BPMN 符号',
    extra: { view: 'designer', button: '打开设计器' },
    gap: 'EPC、UML 活动图和表格泳道图不另存一套。未发布的草稿不能启动实例。',
    check: {
      q: '泳道上应该写部门还是写系统名？',
      a: '写角色或部门。系统名属于集成和架构，不写进泳道。',
    },
  },
  analysis: {
    lead: '流程分析一页里有现状、瓶颈、根因、价值流、规则和绩效基线。先在标题右侧选一条流程。',
    view: 'monitor',
    params: 'tab=analysis',
    button: '打开流程分析',
    gap: '没有鱼骨图页面，根因是文字记录。增值时间来自设计器里填的分钟，不是现场秒表。挖掘不连接外部业务系统。',
    check: {
      q: '增值占比很低，是不是就能当成现场已经测过？',
      a: '不能。这一项来自设计器节点上的时间，是估计。现场工时在工作量页，来自任务记录。',
    },
  },
  design: {
    lead: '未来态画在设计器里。发布之后，新实例用新版本。正在跑的实例仍用启动时的版本。',
    view: 'designer',
    button: '打开设计器',
    gap: '没有耗时分布、到达率和随机抽样的仿真器。上线前能做的是设计器校验和十层核对。',
    check: {
      q: '草稿改完，正在跑的实例会跟着变吗？',
      a: '不会。实例启动时已经钉住当时的已发布版本。',
    },
  },
  performance: {
    lead: '指标在运营驾驶舱的 KPI。红黄来自定义和数据点。没有数据点的指标是灰的。',
    view: 'monitor',
    params: 'tab=kpi',
    button: '打开 KPI',
    gap: '四个视角没有单独一页，指标按效率、质量、成本、灵活性汇总。标准工时不用于个人排名、扣罚或奖金。',
    check: {
      q: '把流程指标直接拿去给个人打分、发奖金，本系统支持吗？',
      a: '不支持。标准工时只做能力基线，页面写明不用于个人排名、扣罚或奖金。',
    },
  },
  change: {
    lead: '改进项目在流程项目组合。红黄指标和未关闭异常可以生成草稿，不自动改已发布模型。',
    view: 'projects',
    button: '打开流程项目组合',
    gap: '六西格玛的实验设计和精益看板没有对应页面。变革记在项目和十层变更上。',
    check: {
      q: '指标变红，会自动出现在异常台账里吗？',
      a: '不会。异常要人登记。变红只能在 KPI 上看到，需要人决定是否转成项目。',
    },
  },
  tech: {
    lead: '已发布的流程在流程执行里启动。挖掘读本系统记下的日志和已完成实例。机器人只登记用途和运行结果。',
    view: 'execution',
    button: '打开流程执行',
    extra: { view: 'monitor', params: 'tab=mining', button: '打开过程挖掘' },
    gap: '没有能执行任意模型的套件，没有从邮件里识别意图，没有机器人运行时。分派靠运行配置，没有智能路由。',
    check: {
      q: '想知道采购实际有没有绕过审批，能不能直接挖外部系统日志？',
      a: '不能。只挖这里记下的事件和跑完的实例。外部日志要先记成这些记录。',
    },
  },
  org: {
    lead: '治理角色在组织与人员。谁能改公司地图，在开始使用。单条流程谁审批，在授权矩阵。',
    view: 'orgs',
    button: '打开组织与人员',
    extra: { view: 'authorization', button: '打开授权矩阵' },
    gap: '流程委员会和方法团队的三种建制没有独立机构页面。用治理角色和项目成员表达。授权规则目前被流程卡计数，办理看运行配置里的处理人。',
    check: {
      q: '授权规则生效后，任务会不会自动拒绝越权办理？',
      a: '不会自动按委员会建制来拦。办理看运行配置里的处理人。金额或事项命中已生效规则时，才要求审批角色或已批准的例外。',
    },
  },
  enterprise: {
    lead: '公司自己的树在企业流程地图。流程架构页是分类，不是执行顺序。先改哪一条，看地图上的优先级。',
    view: 'map',
    button: '打开企业流程地图',
    extra: { view: 'pcf', button: '打开流程架构' },
    gap: '讲义的第五层具体动作，在本系统落在 L4。战略页上的链接不进入地图优先级。成熟度没有一张等级打分表。',
    check: {
      q: '流程架构树上的先后，是不是公司流程的执行顺序？',
      a: '不是。那是分类。执行顺序在设计器的连线上。',
    },
  },
};

function readDone() {
  try {
    return JSON.parse(localStorage.getItem(DONE_KEY) || '{}');
  } catch (e) {
    return {};
  }
}

function jump(view, params) {
  if (!view) return;
  const parsed = {};
  new URLSearchParams(params || '').forEach((value, key) => {
    parsed[key] = value;
  });
  go(view, Object.keys(parsed).length ? { params: parsed, push: true } : undefined);
}

on('train.module', ({ id }) => {
  state.train.module = id || 'bpm';
  go('train', { params: { module: state.train.module }, push: true });
});

on('train.jump', ({ view, params }) => jump(view, params));

on('train.part', ({ id }) => {
  const node = id ? document.getElementById(id) : null;
  if (node) node.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

on('train.reveal', () => {
  state.train.reveal = true;
  paint(state.train.coach || null);
});

on('train.done', ({ id }) => {
  const done = readDone();
  done[id] = true;
  localStorage.setItem(DONE_KEY, JSON.stringify(done));
  toast('这一讲已记下');
  paint(state.train.coach || null);
});

function lessonButtons(done) {
  return LECTURE.map((item) => `
    <button type="button" class="study-lesson${item.id === state.train.module ? ' on' : ''}"
      data-act="train.module" data-id="${item.id}">
      ${done[item.id] ? '<span class="tag t-grn">已记</span> ' : ''}${item.n}. ${esc(item.title.split('（')[0])}
    </button>`).join('');
}

function tableHtml(table) {
  if (!table) return '';
  const head = table.cols.map((col) => `<th>${esc(col)}</th>`).join('');
  const body = table.rows.map((row) => `
    <tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join('')}</tr>`).join('');
  return `<table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function conceptHtml(concept) {
  const paras = (concept.paras || []).map((line) => `<p>${esc(line)}</p>`).join('');
  const after = (concept.paras2 || []).map((line) => `<p>${esc(line)}</p>`).join('');
  const bullets = (concept.bullets || []).length
    ? `<ul class="study-points">${concept.bullets.map((line) => `<li>${esc(line)}</li>`).join('')}</ul>`
    : '';
  const analogy = concept.analogy ? `<div class="note">${esc(concept.analogy)}</div>` : '';
  const flow = concept.flow ? `<pre class="lecture-flow">${esc(concept.flow)}</pre>` : '';
  const note = concept.note ? `<p class="desc">讲师备注：${esc(concept.note)}</p>` : '';
  return `
    <div class="lecture-concept">
      <h4>${esc(concept.title)}</h4>
      ${paras}${bullets}${tableHtml(concept.table)}${flow}${after}${analogy}${note}
    </div>`;
}

function coachHtml(coach) {
  if (!coach) {
    return '<div class="note">暂时读不到当前记录。讲义和上面的页面入口仍然可用。</div>';
  }
  const hints = (coach.hints || []).map((hint) => `
    <div class="mb">
      <b>${esc(hint.title)}</b>
      <div class="desc">${esc(hint.detail)}</div>
      ${hint.view ? `<button type="button" class="btn btn-g" data-act="train.jump"
        data-view="${esc(hint.view)}" data-params="${esc(hint.params || '')}">打开对应页面</button>` : ''}
    </div>`).join('');
  return `
    <h4>根据当前记录</h4>
    <p class="tiny">${esc(coach.basis || '')}</p>
    ${hints || '<div class="desc">这条记录上没有更多建议。</div>'}`;
}

function evidenceHtml(item, coach) {
  const evidence = EVIDENCE[item.id];
  if (!evidence) return '';
  const revealed = state.train.reveal && state.train.revealedFor === item.id;
  return `
    <div class="lecture-evidence" id="train-evidence">
      <h3>本系统实证</h3>
      <p class="desc">下面只说明这套系统里哪一页能对上这一讲。对不上的写在后面，不把讲义里的工具说成已经具备。</p>
      <p>${esc(evidence.lead)}</p>
      <div class="gap mb">
        <button type="button" class="btn btn-p" data-act="train.jump" data-view="${esc(evidence.view)}"
          data-params="${esc(evidence.params || '')}">${esc(evidence.button)}</button>
        ${evidence.extra ? `<button type="button" class="btn btn-g" data-act="train.jump"
          data-view="${esc(evidence.extra.view)}" data-params="${esc(evidence.extra.params || '')}">${
            esc(evidence.extra.button)}</button>` : ''}
        <button type="button" class="btn btn-g" data-act="train.done" data-id="${item.id}">记下这一讲</button>
      </div>
      <h4>这里还没有</h4>
      <div class="warnbox">${esc(evidence.gap)}</div>
      <h4>对照自测</h4>
      <p>${esc(evidence.check.q)}</p>
      ${revealed
        ? `<div class="note">${esc(evidence.check.a)}</div>`
        : '<button type="button" class="btn btn-g" data-act="train.reveal">看答案</button>'}
      ${coachHtml(coach)}
    </div>`;
}

function paint(coach) {
  const current = LECTURE.find((item) => item.id === state.train.module) || LECTURE[0];
  state.train.module = current.id;
  const done = readDone();
  const practice = current.practice || { steps: [] };
  viewEl().innerHTML = `
    <div class="card page-head">
      <h2>BPM 实训<span class="module-badge">九讲讲义</span></h2>
      <div class="desc">《BPM 业务流程管理专业实战教程》。参考 ABPMP BPM CBOK 4.0。正文按讲义展开，本系统的页面只在每讲末尾作实证。</div>
    </div>
    <div class="study-layout">
      <div class="card study-list">${lessonButtons(done)}</div>
      <div class="card lecture-body">
        <h3>${current.n}. ${esc(current.title)}</h3>
        <p class="desc">${esc(current.subtitle)}</p>
        <div class="lecture-toc">
          <button type="button" class="btn btn-g" data-act="train.part" data-id="train-open">开场</button>
          <button type="button" class="btn btn-g" data-act="train.part" data-id="train-concepts">概念</button>
          <button type="button" class="btn btn-g" data-act="train.part" data-id="train-practice">演练</button>
          <button type="button" class="btn btn-g" data-act="train.part" data-id="train-summary">小结</button>
          <button type="button" class="btn btn-g" data-act="train.part" data-id="train-evidence">实证</button>
        </div>
        <div class="lecture-part" id="train-open">
          <h3>开场导入</h3>
          <p>${esc(current.open)}</p>
        </div>
        <div class="lecture-part" id="train-concepts">
          <h3>核心概念</h3>
          ${(current.concepts || []).map(conceptHtml).join('')}
        </div>
        <div class="lecture-part" id="train-practice">
          <h3>实操演练</h3>
          <h4>${esc(practice.title || '')}</h4>
          ${(practice.paras || []).map((line) => `<p>${esc(line)}</p>`).join('')}
          <ol class="study-points">${(practice.steps || []).map((line) => `<li>${esc(line)}</li>`).join('')}</ol>
          ${practice.note ? `<p class="desc">讲师备注：${esc(practice.note)}</p>` : ''}
        </div>
        <div class="lecture-part" id="train-summary">
          <h3>模块小结</h3>
          <table class="tbl">
            <thead><tr><th>要点</th><th>记住一句话</th></tr></thead>
            <tbody>${(current.summary || []).map((row) => `
              <tr><td>${esc(row[0])}</td><td>${esc(row[1])}</td></tr>`).join('')}</tbody>
          </table>
          ${current.close ? `<div class="note lecture-close">${esc(current.close)}</div>` : ''}
        </div>
        ${evidenceHtml(current, coach)}
      </div>
    </div>`;
}

const renderTrain = () => {
  const params = urlParams();
  if (params.module && LECTURE.some((item) => item.id === params.module)) {
    state.train.module = params.module;
  }
  if (!state.train.module) state.train.module = 'bpm';
  if (state.train.revealedFor !== state.train.module) state.train.reveal = false;
  state.train.revealedFor = state.train.module;
  const area = state.train.module;
  return renderAsync('train',
    () => GET('/train/coach?area=' + encodeURIComponent(area)).catch(() => null),
    (coach) => {
      state.train.coach = coach;
      paint(coach);
    });
};

export { renderTrain };
