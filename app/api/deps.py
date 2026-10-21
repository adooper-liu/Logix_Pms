"""公共依赖：数据库会话、当前用户、权限门槛。"""

from __future__ import annotations

from typing import Annotated, Optional, Tuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
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


def resolve_owner(
    db: Session, owner_user_id: Optional[int], owner_name: Optional[str]
) -> Tuple[Optional[int], Optional[str]]:
    """确定对象的归属：优先用账号 id，其次按姓名精确绑定。

    返回 (owner_user_id, 展示用 owner 文本)。

    按姓名绑定只发生在**写入时**，且要求 display_name 唯一——同名用户无法判断，
    就保持未绑定（fail closed，只有 ADMIN / MANAGER 能改）。权限判断永远只看
    owner_user_id，不再比较姓名字符串，因此改个 display_name 不会凭空获得权限。
    """
    if owner_user_id is not None:
        user = db.get(User, owner_user_id)
        if user is None:
            raise HTTPException(status_code=400, detail="owner_user_id 指向的用户不存在")
        return user.id, user.display_name

    name = (owner_name or "").strip()
    if not name:
        return None, None

    matches = db.scalars(select(User).where(User.display_name == name)).all()
    if len(matches) == 1:
        return matches[0].id, matches[0].display_name
    return None, name


def apply_owner_update(
    db: Session,
    data: dict,
    current_owner_name: Optional[str],
) -> dict:
    """在局部更新的字段字典里解析 owner 与 owner_user_id，就地返回。

    - 显式给了 owner_user_id：以它为准，展示文本同步成该用户的姓名；
      显式传 null 表示解绑，只保留文本。
    - 只改了 owner 文本：文本没变就沿用原绑定；变了才按新姓名重新尝试绑定。
    """
    if "owner_user_id" in data:
        uid = data["owner_user_id"]
        if uid is None:
            name = data.get("owner", current_owner_name)
            data["owner"] = (name or "").strip() or None
            data["owner_user_id"] = None
        else:
            data["owner_user_id"], data["owner"] = resolve_owner(db, uid, None)
    elif "owner" in data:
        name = (data["owner"] or "").strip()
        if name == (current_owner_name or "").strip():
            data["owner"] = name or None
        else:
            data["owner_user_id"], data["owner"] = resolve_owner(db, None, name)
    return data


def ensure_can_edit_owned(
    user: User, owner_user_id: Optional[int], owner_label: Optional[str] = None
) -> None:
    """OWNER 只能改自己名下的对象；ADMIN / MANAGER 不受限。

    归属判断只认 `owner_user_id` 外键。对象未绑定账号时对 OWNER 一律拒绝——
    宁可让管理员显式绑定，也不靠姓名字符串猜。
    """
    if user.role in MANAGER_ROLES:
        return
    if user.role == Role.OWNER.value and owner_user_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"只能修改自己名下的对象（当前用户：{user.display_name}，"
            f"对象 Owner：{owner_label or '未绑定账号'}）"
        ),
    )


WriteUser = Annotated[User, Depends(require_write)]
ManagerUser = Annotated[User, Depends(require_manager)]
AdminUser = Annotated[User, Depends(require_admin)]
