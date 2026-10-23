"""对标框架的出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class BenchmarkFrameworkOut(BaseModel):
    id: int
    code: str
    name: str
    name_en: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    is_primary: bool = False
    base_framework_code: Optional[str] = None
    generated_on: Optional[str] = None
    attribution: Optional[str] = None
    is_active: bool = True
    category_count: int = 0
    mapped_process_count: int = 0


class BenchmarkCategoryOut(BaseModel):
    """标准分类树节点。

    mapped_process_count 只统计直接映射到本节点的流程；
    subtree_mapped_process_count 是整棵子树覆盖的去重流程数。
    """

    id: int
    code: str
    name: str
    name_en: Optional[str] = None
    name_zh: Optional[str] = None
    external_id: Optional[str] = None
    level: int
    parent_id: Optional[int] = None
    description: Optional[str] = None
    metrics_available: bool = False
    metric_count: int = 0
    difference_index: int = 0
    change_details: Optional[str] = None
    mapped_process_count: int = 0
    subtree_mapped_process_count: int = 0
    children: List["BenchmarkCategoryOut"] = []


BenchmarkCategoryOut.model_rebuild()


class ProcessRef(BaseModel):
    id: int
    code: str
    name: str
    level: int


class BenchmarkMappingOut(BaseModel):
    id: int
    process_id: int
    process_code: str
    process_name: str
    category_id: int
    category_code: str
    category_external_id: Optional[str] = None
    category_name: str
    category_level: int
    framework_code: str
    framework_name: str
    note: Optional[str] = None
    created_at: Optional[UtcDateTime] = None


class BenchmarkMappingCreate(BaseModel):
    process_id: int
    category_id: int
    note: Optional[str] = Field(default=None, max_length=200)


class CoverageCategoryOut(BaseModel):
    category_id: int
    code: str
    name: str
    name_en: Optional[str] = None
    name_zh: Optional[str] = None
    external_id: Optional[str] = None
    level: int
    description: Optional[str] = None
    metric_count: int = 0
    mapped_count: int = 0
    processes: List[ProcessRef] = []


class BenchmarkMetricOut(BaseModel):
    id: int
    external_id: str
    metric_id: str
    metric_category: Optional[str] = None
    name: str
    formula: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None


class CategoryMetricsOut(BaseModel):
    """某个分类元素挂载的 PCF 指标；按 PCF ID 跨变体共用。"""

    category_id: int
    code: str
    name: str
    name_en: Optional[str] = None
    external_id: Optional[str] = None
    metrics: List[BenchmarkMetricOut] = []


class FrameworkCoverageOut(BaseModel):
    """某个框架对公司某层流程的覆盖情况，用于页面级切换后的对标视图。"""

    framework_code: str
    framework_name: str
    framework_version: Optional[str] = None
    process_level: int = Field(description="被统计的公司流程层级")
    total_processes: int
    mapped_processes: int
    coverage_rate: float = Field(description="已映射流程占比 0–1")
    by_top_category: List[CoverageCategoryOut] = []
    unmapped_processes: List[ProcessRef] = []


class ProcessBenchmarkOut(BaseModel):
    """单个流程在所有框架下的映射，用于流程详情页展示对标关系。"""

    process: ProcessRef
    mappings: List[BenchmarkMappingOut] = []
