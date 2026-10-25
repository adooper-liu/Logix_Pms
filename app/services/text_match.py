"""中文/英文粗分词。

知识库推荐和「按问题找工具」共用同一套分词，避免两处对同一句话切出不同结果。
这里刻意不引入 jieba 等额外依赖：当前数据量下 2 字滑窗 + 英文按空白切分足够，
而且离线部署零依赖。
"""

from __future__ import annotations

from typing import List


def tokens(text: str) -> List[str]:
    """粗分词：中文取 2 字滑窗，英文/数字按空白与符号切分。"""
    result: List[str] = []
    chinese = "".join(ch for ch in text if "一" <= ch <= "鿿")
    result.extend(chinese[i : i + 2] for i in range(max(0, len(chinese) - 1)))
    for chunk in text.replace("，", " ").replace("、", " ").replace(",", " ").split():
        chunk = chunk.strip()
        if chunk and not all("一" <= ch <= "鿿" for ch in chunk):
            result.append(chunk)
    return result
