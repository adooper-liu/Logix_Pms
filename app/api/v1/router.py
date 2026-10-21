"""v1 路由汇总。

除登录接口外，所有业务路由都挂在 `protected` 上，统一要求身份认证。
具体每个写接口的角色门槛在各自的 handler 里通过依赖声明。
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1 import (
    auth,
    benchmark,
    dashboard,
    designer,
    execution,
    integrations,
    knowledge,
    monitor,
    notifications,
    process_map,
    projects,
    tools,
    workflow,
)

api_router = APIRouter()

# 公开：/auth/login；其余端点（/auth/me 等）在 handler 内部声明鉴权
api_router.include_router(auth.router)
api_router.include_router(auth.audit_router)

# 受保护：所有业务接口都需要登录
protected = APIRouter(dependencies=[Depends(get_current_user)])
protected.include_router(dashboard.router)
protected.include_router(process_map.router)
protected.include_router(benchmark.router)
protected.include_router(workflow.router)
protected.include_router(projects.router)
protected.include_router(execution.router)
protected.include_router(integrations.router)
protected.include_router(tools.router)
protected.include_router(designer.router)
protected.include_router(monitor.router)
protected.include_router(notifications.router)
protected.include_router(knowledge.router)
api_router.include_router(protected)

__all__ = ["api_router"]
