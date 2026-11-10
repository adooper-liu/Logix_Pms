"""岗位责任书单一业务模板；不查询、不更改编译依据。"""

from html import escape


def _e(value):
    return escape(str(value if value is not None else "未明确"), quote=True)


def row_html(row) -> str:
    if isinstance(row, str):
        return f"<p>{_e(row)}</p>"
    if "sources" in row:
        return (
            f"<article><h3>{_e(row['process_code'])} · {_e(row['activity_name'])}</h3>"
            f"<p>职责来源：{'；'.join(_e(s['label']) for s in row['sources'])}</p>"
            f"<p>岗位责任：{'；'.join(_e(r['role_name']) + ' · ' + _e(r['raci_label']) for r in row['raci']) or '未绑定活动 RACI'}</p>"
            f"<p>模型版本 #{_e(row['model_version_id'])} · 节点 {_e('、'.join(row['node_keys']) or '未建模')}</p>"
            f'<a href="{_e(row["designer_url"])}">返回设计器核对该活动</a></article>'
        )
    if "raci_label" in row:
        return f"<p>{_e(row['role_name'])}：{_e(row['raci_label'])} · 作用域 {_e(row['scope_key'])}</p>"
    if "totals" in row:
        total = row["totals"]
        rate = total["utilization"]
        parts = [
            f"<p>期间：{_e(row['period'])}；需求 {total['demand_minutes']} 分钟；实际 {total['actual_minutes']} 分钟；可用 {total['available_minutes']} 分钟；负荷率 {_e(f'{rate:.1%}' if rate is not None else '待登记产能')}</p>"
        ]
        for standard in row["standards"]:
            parts.append(
                f"<p>{_e(standard['name'])}：{standard['standard_minutes']} 分钟/次 × {standard['monthly_frequency']} 次/月；{_e(standard['status_label'])}，{'计入' if standard['included'] else '不计入'}需求。</p>"
            )
        return "".join(parts)
    if "facets" in row:
        parts = [f"<h3>{_e(row['activity_name'])}</h3>"]
        for facet in row["facets"]:
            parts.append(f"<h4>{_e(facet['label'])} · {_e(facet['status_label'])}</h4>")
            parts.extend(
                f"<p>{_e(ref['label'])} · {_e(ref['source_label'])}：{_e(ref.get('detail') or '原引用')}</p>"
                for ref in facet["refs"]
            )
            parts.extend(f"<p>{_e(gap)}</p>" for gap in facet["gaps"])
        return "".join(parts)
    return f"<p>岗位：{_e(row.get('name'))} · {_e(row.get('code'))}</p><p>所属组织：{_e(row.get('org_unit_name') or '集团通用')}</p><p>职责边界：{_e(row.get('description') or '未明确')}</p>"


def render(preview_data: dict) -> str:
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>岗位责任书</title><style>body{font:16px/1.7 sans-serif;max-width:960px;",
        "margin:24px auto;padding:0 16px;color:#202830;background:#fff}a{color:#174ca1}",
        "section{margin:24px 0}article{border-left:3px solid #315e88;padding-left:16px}",
        "@media print{a{color:inherit}section{break-inside:avoid}}</style></head><body>",
        f"<h1>{_e(preview_data['position']['name'])} · 岗位责任书</h1>",
        "<p>岗位标准草稿；来源存在不代表有权组织确认或业务效果成立。</p>",
    ]
    for section in preview_data["sections"]:
        parts.append(f"<section><h2>{_e(section['title'])}</h2>")
        parts.extend(row_html(row) for row in section["rows"])
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)
