"""v1 路由汇总。

除登录接口外，所有业务路由都挂在 `protected` 上，统一要求身份认证。
具体每个写接口的角色门槛在各自的 handler 里通过依赖声明。
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    auth,
    baselines,
    benchmark,
    dashboard,
    deliverables,
    designer,
    execution,
    integrations,
    knowledge,
    monitor,
    notifications,
    orgs,
    process_documents,
    process_map,
    projects,
    tool_templates,
    tools,
    workflow,
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
protected.include_router(process_documents.router)
protected.include_router(benchmark.router)
protected.include_router(baselines.router)
protected.include_router(workflow.router)
protected.include_router(projects.router)
protected.include_router(deliverables.standard_router)
protected.include_router(deliverables.project_router)
protected.include_router(deliverables.router)
protected.include_router(execution.router)
protected.include_router(integrations.router)
protected.include_router(tools.router)
protected.include_router(tool_templates.router)
protected.include_router(designer.router)
protected.include_router(monitor.router)
protected.include_router(notifications.router)
protected.include_router(orgs.router)
protected.include_router(knowledge.router)
api_router.include_router(protected)

__all__ = ["api_router"]
