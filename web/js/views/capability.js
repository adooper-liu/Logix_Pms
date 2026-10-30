/* 视图：capability —— 能力地图
 *
 * 把「四层能力 × 五大收益 × 三个痛点」映射到系统里可演示的入口。
 * 纯静态页面，不读后端；链接统一走 capability.open。
 */
import { viewEl, on } from '../core/ui.js';
import { go } from '../core/router.js';

on('capability.open', ({ view }) => go(view, { push: true }));

function action(view, label, cls = 'btn-sm') {
  return `<button class="${cls}" data-act="capability.open" data-view="${view}">${label}</button>`;
}

function painCard(title, answer, view, label) {
  return `
    <div class="card">
      <div class="wb-eyebrow">痛点</div>
      <h3>${title}</h3>
      <p class="desc">${answer}</p>
      <div class="mt">${action(view, label)}</div>
    </div>`;
}

function abilityCard(title, claim, tools, view, label) {
  return `
    <div class="card">
      <div class="between">
        <h3>${title}</h3>
        <span class="tag t-blu">${claim}</span>
      </div>
      <p class="desc">${tools}</p>
      <div class="mt">${action(view, label)}</div>
    </div>`;
}

function benefitCard(no, title, desc, view, label) {
  return `
    <div class="card">
      <div class="wb-eyebrow">收益 ${no}</div>
      <h3>${title}</h3>
      <p class="desc">${desc}</p>
      <div class="mt">${action(view, label)}</div>
    </div>`;
}

const renderCapability = () => {
  viewEl().innerHTML = `
    <div class="card page-head">
      <div class="between">
        <div>
          <h2>能力地图 <span class="module-badge">四层能力 · 五大收益</span></h2>
          <div class="desc">把能力主张映射到系统入口：面试或汇报时，按这张图走一遍即可。</div>
        </div>
        <div class="gap">
          ${action('start', '回到 0→1 主线', 'btn btn-p')}
          ${action('pilot', '看十层单页', 'btn btn-g')}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="wb-eyebrow">三个痛点 → 三个系统答案</div>
      <div class="grid g3">
        ${painCard(
    '“鸡同鸭讲”，语言不统一',
    'APQC PCF 统一分类树，企业流程架构 L1–L4 与 L5 任务共用一套编码和名称。',
    'map',
    '打开企业流程地图',
  )}
        ${painCard(
    '流程梳理“永远在画”',
    '五阶段项目把梳理变成可推进的项目：阶段条件、步骤证据、退出门和签收都在系统里。',
    'workflow',
    '打开五阶段工作台',
  )}
        ${painCard(
    '工具方法“用不对”',
    '方法论工具箱按问题、场景、阶段和步骤匹配工具，并记录使用证据与复核结论。',
    'toolbox',
    '打开方法论工具箱',
  )}
      </div>
    </div>

    <div class="card">
      <div class="wb-eyebrow">四层能力</div>
      <div class="grid g2">
        ${abilityCard(
    '懂财务',
    '算得清账',
    '战略目标、KPI 定义卡（基线/目标/阈值/公式）、项目预算与实际成本、收益与 ROI、PCE 与可释放人天。',
    'strategy',
    '看目标与 KPI',
  )}
        ${abilityCard(
    '懂业务',
    '摸得清底',
    '流程地图到现场执行、标准工时与产能、过程挖掘；生产与供应链流程可以建模和度量。',
    'execution',
    '看流程执行',
  )}
        ${abilityCard(
    '懂流程',
    '砍得掉浪费',
    '五阶段改善、PCE/等待/返工/移交测算、瓶颈节点、十层单页、阶段门与成熟度。',
    'projects',
    '看流程项目',
  )}
        ${abilityCard(
    '懂 IT',
    '落得了地',
    '自研 FastAPI + 原生前端；BPMN 设计器、执行引擎、数据治理、BI 看板与开放接口。',
    'designer',
    '看流程设计器',
  )}
      </div>
    </div>

    <div class="card">
      <div class="wb-eyebrow">五大收益</div>
      <div class="grid g2">
        ${benefitCard(
    1,
    '流程建系统驱动',
    '从 APQC 骨架到五阶段项目，再到执行与变更，流程不是文档，而是可运行、可放行的系统对象。',
    'map',
    '从流程地图开始',
  )}
        ${benefitCard(
    2,
    '混乱可量化治理',
    '价值/痛点/改善空间评分、KPI 雷达与异常、治理发现、成熟度评估和 L4 覆盖度。',
    'dashboard',
    '打开运营驾驶舱',
  )}
        ${benefitCard(
    3,
    '知识和方法主动找到使用现场',
    '工具箱按问题、场景、阶段和步骤推荐工具；案例/模板、使用证据和求真审核统一管理。',
    'toolbox',
    '打开方法论工具箱',
  )}
        ${benefitCard(
    4,
    '改善日常化',
    '红黄 KPI 和未闭环异常一键转改善项目；五阶段闭环、十层试点、复制资产包持续复用。',
    'projects',
    '看改善项目',
  )}
        ${benefitCard(
    5,
    '跨部门协作 RACI 可查',
    '治理角色、RACI 分配、授权矩阵与例外台账；流程节点可直接看谁负责、谁执行、谁知会。',
    'authorization',
    '打开授权矩阵',
  )}
      </div>
    </div>

    <div class="card">
      <div class="wb-eyebrow">系统边界</div>
      <div class="note mb">
        这是流程治理与改善系统，不是 ERP / MES / WMS / APS / 财务核算系统。
        业务交易在专业系统里；这里回答“流程怎么设计、谁负责、凭什么放行、改善有没有证据”。
      </div>
      <div class="grid g2">
        <div>
          <h3>系统内</h3>
          <div class="tiny muted">APQC 与企业流程架构 · 五阶段项目与退出门 · BPMN 与版本变更 · 执行任务与 SLA ·
            RACI 与授权 · KPI 与异常 · 标准工时与产能 · 知识/工具/案例模板 · 交付物与标准文件 · 数据治理 · 成熟度与复制</div>
        </div>
        <div>
          <h3>系统外</h3>
          <div class="tiny muted">供应商/采购/库存/仓储/物流运费/预提 · APS 有限产能排程 · WMS/条码/Andon ·
            总账与成本核算（杜邦/本量利/标准成本差异/边际贡献）</div>
        </div>
      </div>
      <div class="tiny muted mt">这些边界不是缺陷，而是定位：流程治理层与业务交易层分工明确，避免重复建设。</div>
    </div>`;
};

export { renderCapability };
