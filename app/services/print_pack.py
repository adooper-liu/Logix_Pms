"""项目交付物打印包：服务端生成可打印 HTML，必要时用 LibreOffice 转 PDF。

打印包不是新的数据口径：项目、步骤、交付物、阶段门都直接读现有表，
标签复用后端枚举映射，避免前端/打印件出现第二套中文。
"""

from __future__ import annotations

from html import escape
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessArch
from app.models.project import Project, ProjectGateCondition, ProjectStep, WorkflowTemplate
from app.services import deliverable as deliverable_service
from app.services import improvement as improvement_service
from app.services import project_workflow as workbench_service
from app.services import workflow as workflow_service


def _e(value) -> str:
    return escape(str(value)) if value is not None else ""


def _stage_names(db: Session) -> Dict[int, str]:
    names = dict(workflow_service.STAGE_NAMES)
    rows = db.execute(
        select(WorkflowTemplate.stage_no, WorkflowTemplate.stage_name)
        .distinct()
        .order_by(WorkflowTemplate.stage_no)
    ).all()
    for stage_no, name in rows:
        names.setdefault(stage_no, name)
    return names


def build_print_pack(db: Session, project: Project) -> str:
    steps: List[ProjectStep] = list(
        db.scalars(
            select(ProjectStep)
            .where(ProjectStep.project_id == project.id)
            .order_by(ProjectStep.stage_no, ProjectStep.step_no)
        ).all()
    )
    instances = deliverable_service.project_instances(db, project.id)
    views = [deliverable_service.instance_out(instance) for instance in instances]
    by_step: Dict[str, List] = {}
    for view in views:
        by_step.setdefault(view.step_no, []).append(view)
    gates: Dict[int, List[ProjectGateCondition]] = {}
    for gate in db.scalars(
        select(ProjectGateCondition)
        .where(ProjectGateCondition.project_id == project.id)
        .order_by(ProjectGateCondition.stage_no, ProjectGateCondition.sort_order)
    ).all():
        gates.setdefault(gate.stage_no, []).append(gate)

    process: Optional[ProcessArch] = (
        db.get(ProcessArch, project.process_id) if project.process_id else None
    )
    summary = deliverable_service.project_summary(db, project.id)
    names = _stage_names(db)
    generated = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    status_label = improvement_service.PROJECT_STATUS_LABELS.get(project.status, project.status)

    stage_nos = sorted({step.stage_no for step in steps})
    sections = []
    for stage_no in stage_nos:
        stage_steps = [step for step in steps if step.stage_no == stage_no]
        step_rows = []
        for step in stage_steps:
            step_view = by_step.get(step.step_no, [])
            dlv_rows = (
                "".join(
                    f"<tr>"
                    f"<td>{_e(item.definition_name)}<div class='sub'>{_e(item.definition_code)}"
                    f"{' · 必需' if item.required else ' · 可选'}</div></td>"
                    f"<td>{_e(item.type_label)}</td>"
                    f"<td>{_e(item.status_label)}</td>"
                    f"<td>{_e(item.current_version.version_label) if item.current_version else '—'}"
                    f"{('<div class=sub>' + _e(item.current_version.status_label) + '</div>') if item.current_version else ''}</td>"
                    f"<td>{_e(item.current_version.source_model_label) if item.current_version and item.current_version.source_model_label else _e(item.current_version.file_name if item.current_version else '—')}</td>"
                    f"<td>{_e(item.owner or '—')}</td>"
                    f"</tr>"
                    for item in step_view
                )
                or "<tr><td colspan='6' class='sub'>未生成交付物实例</td></tr>"
            )
            step_rows.append(
                f"<tr class='step'>"
                f"<td><b>{_e(step.step_no)}</b> {_e(step.name)}"
                f"<div class='sub'>{_e(workbench_service.STEP_STATUS_LABELS.get(step.status, step.status))}"
                f" · {_e(step.owner or '未指定')}</div></td>"
                f"<td colspan='5'></td></tr>"
                f"{dlv_rows}"
            )
        gate_rows = (
            "".join(
                f"<li>{_e(gate.text)} <span class='sub'>"
                f"{'✓ 已满足' if gate.is_met else '未满足'}"
                f"{' · 证据：' + _e(gate.evidence) if gate.evidence else ''}"
                f"{' · 责任人：' + _e(gate.owner) if gate.owner else ''}"
                f"{' · 截止：' + _e(gate.due_date) if gate.due_date else ''}"
                f"</span></li>"
                for gate in gates.get(stage_no, [])
            )
            or "<li class='sub'>本阶段没有配置门槛</li>"
        )
        sections.append(
            f"<section class='stage'>"
            f"<h2>阶段{stage_no} {_e(names.get(stage_no, ''))}</h2>"
            f"<table><thead><tr><th>步骤 / 交付物</th><th>类型</th><th>状态</th>"
            f"<th>当前版本</th><th>文件 / 模型来源</th><th>负责人</th></tr></thead>"
            f"<tbody>{''.join(step_rows)}</tbody></table>"
            f"<h3>阶段退出门槛</h3><ul class='gates'>{gate_rows}</ul>"
            f"</section>"
        )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>项目交付物打印包 · {_e(project.code)}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 12px/1.55 "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
         color: #111; margin: 0; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 18px 0 8px; border-bottom: 1px solid #999;
        padding-bottom: 4px; }}
  h3 {{ font-size: 12.5px; margin: 12px 0 6px; }}
  .meta {{ color: #444; font-size: 11.5px; margin-bottom: 10px; }}
  .summary {{ display: flex; gap: 18px; margin: 8px 0 14px; }}
  .summary b {{ font-size: 16px; }}
  .sub {{ color: #666; font-size: 10.5px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 8px; }}
  th, td {{ border: 1px solid #aaa; padding: 4px 6px; text-align: left;
            vertical-align: top; }}
  th {{ background: #eee; font-size: 11px; }}
  tr.step td {{ background: #f6f6f6; }}
  .gates {{ margin: 0; padding-left: 18px; }}
  .gates li {{ margin-bottom: 3px; }}
  .no-print {{ margin-bottom: 12px; }}
  @media print {{ .no-print {{ display: none; }} h2 {{ page-break-after: avoid; }}
                  table {{ page-break-inside: auto; }} tr {{ page-break-inside: avoid; }} }}
</style></head>
<body>
  <div class="no-print">
    <button onclick="window.print()">打印 / 保存为 PDF</button>
  </div>
  <h1>项目交付物打印包</h1>
  <div class="meta">
    {_e(project.code)} · {_e(project.name)} · Owner {_e(project.owner)}
    · 状态 {_e(status_label)} · 当前阶段 {project.current_stage}
    · 关联流程 {_e(process.code + " " + process.name if process else "未关联")}
    <br>生成时间 {generated}
  </div>
  <div class="summary">
    <span>交付物 <b>{summary.total}</b></span>
    <span>已生效 <b>{summary.effective}</b></span>
    <span>必需项未产出 <b>{summary.required_missing}</b></span>
    <span>完成度 <b>{summary.completeness_pct}%</b></span>
  </div>
  {"".join(sections)}
  <div class="meta">状态与版本以系统当前数据为准；受控文件请以审批生效版本为准。</div>
</body></html>"""
