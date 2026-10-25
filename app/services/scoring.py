"""推荐打分的公共函数。

知识库和工具箱都用同一套证据置信度算法，避免两处对「有效率」给出不同解释。
"""

from __future__ import annotations

import math


def wilson_lower_bound(effective: int, used: int, z: float = 1.96) -> float:
    """二项分布的 Wilson 置信区间下界。

    直接使用 effective / used 会让「1 次使用、1 次有效」得到 100%，
    从而压过「50 次使用、40 次有效」的可靠知识。Wilson 下界会惩罚小样本。
    """
    if used <= 0:
        return 0.0
    p = effective / used
    denominator = 1 + z * z / used
    centre = p + z * z / (2 * used)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * used)) / used)
    return max(0.0, (centre - margin) / denominator)
