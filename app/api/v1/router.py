"""v1 路由汇总。

除登录接口外，所有业务路由都挂在 `protected` 上，统一要求身份认证。
具体每个写接口的角色门槛在各自的 handler 里通过依赖声明。
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    alignment,
    asset_graph,
    auth,
    authorization,
    baselines,
    benchmark,
    changes,
    coach,
    collaboration,
    compensation,
    dashboard,
    data_governance,
    decisions,
    deliverables,
    designer,
    execution,
    governance_evidence,
    improvement_round,
    integrations,
    job_description,
    knowledge,
    lifecycle,
    maturity,
    monitor,
    notifications,
    orgs,
    pilot,
    positions,
    process_card,
    process_documents,
    process_map,
    process_tasks,
    projects,
    raci,
    replication,
    sketches,
    startup,
    strategy,
    tool_templates,
    tools,
    workbench,
    workflow,
    workforce,
    workload,
)

api_router = APIRouter()

# 公开：/auth/login；入站 Webhook 用 HMAC 签名而不是登录态
api_router.include_router(auth.router)
api_router.include_router(auth.audit_router)
api_router.include_router(integrations.inbound_router)

# 受保护：所有业务接口都需要登录
protected = APIRouter(dependencies=[Depends(get_current_user)])
protected.include_router(dashboard.router)
protected.include_router(process_map.router)
protected.include_router(process_card.router)
protected.include_router(asset_graph.router)
protected.include_router(asset_graph.package_router)
protected.include_router(asset_graph.trace_router)
protected.include_router(governance_evidence.router)
protected.include_router(process_documents.router)
protected.include_router(process_tasks.router)
protected.include_router(benchmark.router)
protected.include_router(baselines.router)
protected.include_router(workflow.router)
protected.include_router(projects.router)
protected.include_router(sketches.router)
protected.include_router(deliverables.standard_router)
protected.include_router(deliverables.project_router)
protected.include_router(deliverables.router)
protected.include_router(execution.router)
protected.include_router(integrations.router)
protected.include_router(tools.router)
protected.include_router(tool_templates.router)
protected.include_router(designer.router)
protected.include_router(collaboration.router)
protected.include_router(compensation.router)
protected.include_router(changes.router)
protected.include_router(coach.router)
protected.include_router(monitor.router)
protected.include_router(notifications.router)
protected.include_router(orgs.router)
protected.include_router(positions.router)
protected.include_router(job_description.router)
protected.include_router(workload.router)
protected.include_router(workforce.router)
protected.include_router(strategy.router)
protected.include_router(alignment.router)
protected.include_router(raci.router)
protected.include_router(replication.router)
protected.include_router(authorization.router)
protected.include_router(data_governance.router)
protected.include_router(decisions.router)
protected.include_router(lifecycle.router)
protected.include_router(workbench.router)
protected.include_router(improvement_round.router)
protected.include_router(startup.router)
protected.include_router(pilot.router)
protected.include_router(knowledge.router)
protected.include_router(maturity.router)
api_router.include_router(protected)

__all__ = ["api_router"]
