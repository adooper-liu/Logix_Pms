"""认证、用户管理与审计日志。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import AdminUser, CurrentUser, DbSession, ManagerUser
from app.core.security import create_token, hash_password, using_dev_secret, verify_password
from app.core.timeutil import utcnow
from app.models.enums import Role
from app.models.user import AuditLog, User
from app.schemas.user import (
    AuditOut,
    AuditPage,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import audit as audit_service
from app.services import ownership as ownership_service

router = APIRouter(prefix="/auth", tags=["认证与权限"])
audit_router = APIRouter(prefix="/audit", tags=["审计"])


@router.post("/login", response_model=LoginResponse, summary="登录，换取访问令牌")
def login(payload: LoginRequest, db: DbSession):
    user = db.scalar(select(User).where(User.username == payload.username.strip()))
    if user is None or not verify_password(payload.password, user.password_hash):
        # 不区分「用户不存在」与「口令错误」，避免枚举账号
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或口令不正确")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")

    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)

    token, expires_at = create_token(user.id)
    return LoginResponse(token=token, expires_at=expires_at, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="当前登录用户")
def me(user: CurrentUser):
    return UserOut.model_validate(user)


@router.post("/change-password", summary="修改自己的口令")
def change_password(payload: ChangePasswordRequest, user: CurrentUser, db: DbSession):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="原口令不正确")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"detail": "口令已更新，请用新口令重新登录"}


@router.get("/users", response_model=List[UserOut], summary="用户列表（管理员）")
def list_users(user: AdminUser, db: DbSession):
    rows = db.scalars(select(User).order_by(User.id)).all()
    return [UserOut.model_validate(u) for u in rows]


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建用户（管理员）",
)
def create_user(payload: UserCreate, admin: AdminUser, db: DbSession):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail=f"用户名 {payload.username} 已存在")
    obj = User(
        username=payload.username.strip(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        department=payload.department,
    )
    db.add(obj)
    db.flush()
    audit_service.record(
        db, admin, "CREATE", "user", obj.id, f"新建用户 {obj.username}（{obj.role}）"
    )
    db.commit()
    db.refresh(obj)
    return UserOut.model_validate(obj)


@router.patch("/users/{user_id}", response_model=UserOut, summary="修改用户（管理员）")
def update_user(user_id: int, payload: UserUpdate, admin: AdminUser, db: DbSession):
    obj = db.get(User, user_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if "role" in data and data["role"] is not None:
        data["role"] = data["role"].value
    old_display_name = obj.display_name
    for field, value in data.items():
        setattr(obj, field, value)
    if obj.display_name != old_display_name:
        # owner 文本是展示标签，跟着账号改名走；权限仍只看 owner_user_id
        ownership_service.sync_owner_display_name(db, obj)
    if password:
        obj.password_hash = hash_password(password)
    audit_service.record(db, admin, "UPDATE", "user", obj.id, f"修改用户 {obj.username}")
    db.commit()
    db.refresh(obj)
    return UserOut.model_validate(obj)


@audit_router.get("", response_model=AuditPage, summary="审计日志（流程管理科及以上）")
def list_audit(
    user: ManagerUser,
    db: DbSession,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    username: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if username:
        like = f"%{username}%"
        stmt = stmt.where(or_(AuditLog.username.like(like), AuditLog.display_name.like(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    ).all()
    return AuditPage(total=total, items=[AuditOut.model_validate(r) for r in rows])


@router.get("/security-check", summary="安全配置自检")
def security_check(user: CurrentUser):
    """开发便利：提示是否仍在使用默认签名密钥。"""
    return {
        "using_dev_secret": using_dev_secret(),
        "hint": "请通过环境变量 SECRET_KEY 设置随机密钥后再上线"
        if using_dev_secret()
        else "已配置自定义密钥",
        "roles": [r.value for r in Role],
    }
