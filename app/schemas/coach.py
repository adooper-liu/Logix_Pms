"""实训指导：根据已有记录给出下一步。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class CoachHint(BaseModel):
    title: str
    detail: str
    view: Optional[str] = None
    params: str = ""


class CoachOut(BaseModel):
    area: str
    basis: str = Field(description="建议从哪来")
    hints: List[CoachHint]
