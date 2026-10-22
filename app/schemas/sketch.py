"""架构草图（draw.io 白板）出入参。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class SketchCreate(BaseModel):
    title: str = Field(max_length=128)
    description: Optional[str] = Field(default=None, max_length=2000)
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    mxfile_xml: Optional[str] = Field(default=None, max_length=2_000_000)


class SketchUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=2000)
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    mxfile_xml: Optional[str] = Field(default=None, max_length=2_000_000)


class SketchSummaryOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    project_id: Optional[int] = None
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class SketchOut(SketchSummaryOut):
    mxfile_xml: str = ""


class SketchMeta(BaseModel):
    embed_url: str
