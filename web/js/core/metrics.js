/* 指标口径注册表。
 *
 * 页面上的指标统一用 metricHelp(key, label) 渲染：
 * 鼠标悬停/键盘聚焦时显示计算公式与口径说明。
 * 新增指标时在这里登记，不要在各个视图里散落解释文本。
 */

import { esc } from './format.js';

export const METRICS = {
  /* ---- 驾驶舱 ---- */
  active_projects: {
    name: '在办流程项目',
    formula: '状态为“进行中（ACTIVE）”的项目数量',
    note: '不含待启动、暂停、已结项',
  },
  improvement_targets: {
    name: '待改善流程',
    formula: '流程架构中 is_improvement_target = true 的节点数',
    note: '由流程地图的“待改善项”标记决定',
  },
  open_exceptions: {
    name: '未闭环异常',
    formula: '状态为“待处理”或“处理中”的异常事件数',
    note: '不含已解决、已闭环',
  },
  avg_improvement: {
    name: '平均目标改善',
    formula: '在办项目 improvement_pct 的算术平均',
    note: 'improvement_pct = |基线 − 目标| / |基线| × 100%',
  },
  closed_this_year: {
    name: '今年结项',
    formula: '状态为“已完成”且 end_date 在当年的项目数',
  },
  process_total: {
    name: '流程资产',
    formula: '流程架构 L1–L4 的节点总数',
  },
  stage_progress: {
    name: '阶段平均进度',
    formula: '该阶段在办项目 progress 的算术平均',
    note: '没有在办项目时显示“—”，不按 0% 计',
  },
  methodology_share: {
    name: '方法论占比',
    formula: '该方法项目数 ÷ 全部项目数',
    note: '按项目当前 methodology 统计，包含所有状态',
  },
  health_score: {
    name: '流程健康度',
    formula: '0–100 分，来自流程架构评估',
    note: '低于 70 分进入预警；低于 60 分判为高风险',
  },
  health_alert: {
    name: '健康度预警',
    formula: 'health_score < 70 或 pain_score ≥ 4',
    note: '满足任一条件即进入风险提醒',
  },
  level_counts: {
    name: '层级节点数',
    formula: '该层级（L1/L2/L3/L4）的流程节点数量',
  },

  /* ---- 流程地图 / 对标 ---- */
  priority_score: {
    name: '综合优先级得分',
    formula: '战略重要性 × 痛点严重度 × 改善空间',
    note: '三项各 0–5 分，结果范围 0–125',
  },
  heat_level: {
    name: '热度等级',
    formula: '≥80 或健康度<50 为紧急；≥55 或<65 为高；≥30 为中；其余为低',
    note: '由后端统一判定，前端不另算一套',
  },
  pain_space: {
    name: '痛点 / 改善空间',
    formula: '痛点为 1–5 分；改善空间为 1–5 分',
    note: '两者都来自流程架构评估，不参与权限判断',
  },
  child_count: {
    name: '下级数量',
    formula: '当前流程节点直接子节点的数量',
  },
  map_avg_health: {
    name: '平均健康度',
    formula: '全部流程 health_score 非空值的算术平均',
  },
  benchmark_coverage: {
    name: '对标覆盖率',
    formula: '被框架覆盖的目标层流程数 ÷ 目标层流程总数',
    note: '流程自身或任一后代有映射即算覆盖',
  },
  category_mapped: {
    name: '分类覆盖数',
    formula: '映射到该分类（含下级分类）的去重流程数',
  },

  /* ---- 项目组合 ---- */
  project_total: {
    name: '项目总数',
    formula: '当前筛选条件下的项目数量',
  },
  active_count: {
    name: '进行中',
    formula: 'status = ACTIVE 的项目数量',
  },
  closed_count: {
    name: '已结项',
    formula: 'status = CLOSED 的项目数量',
  },
  avg_progress: {
    name: '平均进度',
    formula: '当前筛选结果 progress 的算术平均',
  },
  overdue_project: {
    name: '超期项目',
    formula: 'end_date < 今天且 progress < 100% 的项目数',
  },
  project_progress: {
    name: '整体进度',
    formula: '已完成步骤数 ÷ 全部步骤数 × 100%',
    note: '步骤更新后自动回算；当前阶段全部完成时自动推进',
  },
  improvement_pct: {
    name: '目标改善幅度',
    formula: '|基线值 − 目标值| ÷ |基线值| × 100%',
    note: '基线为 0 时无法计算，保持为空',
  },
  budget_usage: {
    name: '已用 / 预算',
    formula: 'actual_cost / budget，单位万元',
    note: '预算为 0 时只显示实际成本',
  },

  /* ---- 运营监控 ---- */
  achievement_rate: {
    name: '达成率',
    formula: '越小越好：目标 ÷ 实际 × 100%；越大越好：实际 ÷ 目标 × 100%',
    note: '越小越好且实际为 0 时按 100% 计',
  },
  dimension_achievement: {
    name: '维度达成率',
    formula: '该维度有目标值的 KPI 达成率算术平均',
  },
  overall_achievement: {
    name: '综合达成率',
    formula: '四个维度达成率的算术平均',
    note: '没有数据的维度不参与',
  },
  overall_trend: {
    name: '整体达成率趋势',
    formula: '每个月先按维度求平均，再对维度求平均',
    note: '与雷达图同口径，避免指标多的维度权重过大',
  },
  latest_value: {
    name: '当前值',
    formula: '按 period 排序后的最后一个数据点',
  },
  target_value: {
    name: '目标值',
    formula: 'KPI 定义中的 target_value',
  },
  kpi_trend: {
    name: '环比',
    formula: '最新值 − 上一期值',
    note: '箭头颜色结合指标方向判断好坏',
  },
  kpi_series: {
    name: '6 个月走势',
    formula: '按 period 排序的最近 6 个数据点',
  },
  exception_overdue: {
    name: '超期异常',
    formula: 'due_at < 当前时间且状态为待处理/处理中',
  },
  closed_exceptions: {
    name: '已闭环异常',
    formula: '状态为已解决或已闭环的异常数',
  },

  /* ---- 流程设计器 ---- */
  pce: {
    name: '流程周期效率 PCE',
    formula: '增值作业时间 ÷ 期望端到端周期',
    note: '增值时间只算一次通过，返工不计入',
  },
  wait_ratio: {
    name: '等待占比',
    formula: '期望等待时间 ÷ 期望端到端周期',
  },
  work_share: {
    name: '作业时间占比',
    formula: '期望作业时间 ÷ 期望端到端周期',
  },
  lead_time: {
    name: '期望端到端周期',
    formula: 'Σ(作业 + 等待) × 返工倍率 × 期望进入次数',
    note: '按流转概率求期望值，计入分支与回路',
  },
  rework_loss: {
    name: '返工损失',
    formula: '含返工的期望周期 − 不含返工的期望周期',
  },
  handoff_count: {
    name: '跨泳道移交',
    formula: '跨泳道连线数；没有连线时按相邻节点的泳道变化计数',
  },
  approval_levels: {
    name: '累计审批层级',
    formula: 'Σ 每个节点的有效审批层级',
    note: '审批节点未填层级时按 1 层计',
  },
  unit_cost: {
    name: '期望执行成本',
    formula: 'Σ 单次成本 × 返工倍率 × 期望进入次数',
  },
  fte_saved: {
    name: '可释放人天/月',
    formula: '返工额外作业时间 × 月均单量 1000 ÷ 每人天 480 分钟',
    note: '仅为返工作业时间口径，不含等待',
  },
  bottleneck: {
    name: '瓶颈判定',
    formula: '节点期望时长 ≥ 均值 1.5 倍，或审批层级 ≥3，或返工率 ≥10%',
  },
  suggestion_rules: {
    name: '改善建议规则',
    formula: 'PCE、等待、审批、返工、移交、并行、非增值、负责人、成本 9 类规则',
  },
  methodology_pick: {
    name: '方法论推荐',
    formula: 'PCE<15% 且移交≥3 → BPR；返工≥15% 或等待>60% → 精益；PCE<35% → BPI',
  },

  /* ---- 工具箱 / 知识库 ---- */
  match_score: {
    name: '匹配得分',
    formula: '同义词命中每个 +3；工具文本命中每个 +1；阶段一致 +0.5',
    note: '按得分降序取前 8 个工具',
  },
  download_count: {
    name: '查阅次数',
    formula: '每次打开或下载知识条目 +1',
  },
};

/**
 * 渲染带口径说明的指标标签。
 * label 不传时使用注册表里的名称；只设置 data-tip 供自定义提示使用，
 * 不再同时设置 title——否则浏览器原生提示会和自定义提示重复弹出。
 */
export function metricHelp(key, label) {
  const m = METRICS[key];
  if (!m) return esc(label === undefined ? key : label);
  const tip = m.formula + (m.note ? '。' + m.note : '');
  return '<span class="metric-help has-tip" tabindex="0" aria-label="' + esc(m.name + '：' + tip) +
    '" data-tip="' + esc(tip) + '">' + esc(label === undefined ? m.name : label) +
    '<i class="q">?</i></span>';
}
