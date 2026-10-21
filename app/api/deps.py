"""公共依赖：数据库会话、当前用户、权限门槛。"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import parse_token
from app.models.enums import Role
from app.models.user import User

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Authorization: Bearer <token>")

# 能写业务数据的角色
WRITE_ROLES = {Role.ADMIN.value, Role.MANAGER.value, Role.OWNER.value}
# 能管理全部业务数据的角色（OWNER 受限于自己名下的对象）
MANAGER_ROLES = {Role.ADMIN.value, Role.MANAGER.value}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DbSession,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> User:
    if creds is None or not creds.credentials:
        raise _unauthorized("未登录，请先获取令牌")
    user_id = parse_token(creds.credentials)
    if user_id is None:
        raise _unauthorized("令牌无效或已过期，请重新登录")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("用户不存在或已停用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_write(user: CurrentUser) -> User:
    """写操作的准入门槛：ADMIN / MANAGER / OWNER。"""
    if user.role not in WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="当前角色为只读，无权修改数据"
        )
    return user


def require_manager(user: CurrentUser) -> User:
    """结构性写操作（流程架构、KPI 定义、知识库）只允许 ADMIN / MANAGER。"""
    if user.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该操作需要流程管理科或系统管理员角色",
        )
    return user


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="该操作需要系统管理员角色"
        )
    return user


def ensure_can_edit_owned(user: User, owner_name: Optional[str]) -> None:
    """OWNER 只能改自己名下的对象；ADMIN / MANAGER 不受限。

    Owner 目前是按姓名文本匹配的（数据模型里 owner 是字符串）。
    这是已知的简化，接企业账号体系后应改成 owner_user_id 外键。
    """
    if user.role in MANAGER_ROLES:
        return
    if user.role == Role.OWNER.value and (owner_name or "").strip() == user.display_name:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"只能修改自己名下的对象（当前用户：{user.display_name}，对象 Owner：{owner_name or '未指定'}）",
    )


WriteUser = Annotated[User, Depends(require_write)]
ManagerUser = Annotated[User, Depends(require_manager)]
AdminUser = Annotated[User, Depends(require_admin)]
