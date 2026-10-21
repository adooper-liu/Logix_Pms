"""归属标签同步。

`owner_user_id` 是权限依据，`owner` 只是展示标签。账号改名后必须把引用了
这个账号的对象标签一起改掉，否则界面上会出现「归属还是旧名字」的漂移。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.monitor import ExceptionEvent
from app.models.process import ProcessArch
from app.models.project import Project
from app.models.user import User

# 所有带 owner_user_id + owner 展示标签的模型
OWNER_LABELLED_MODELS = (Project, ProcessArch, ExceptionEvent)


def sync_owner_display_name(db: Session, user: User) -> int:
    """把该用户名下对象的展示标签同步成新的 display_name，返回受影响行数。"""
    updated = 0
    for model in OWNER_LABELLED_MODELS:
        updated += (
            db.query(model)
            .filter(model.owner_user_id == user.id)
            .update({model.owner: user.display_name}, synchronize_session=False)
        )
    return updated
