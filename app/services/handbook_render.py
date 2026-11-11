"""手册原作业模板：转义全部原文，不查询或猜测指令。"""

from html import escape


def e(value):
    return escape(str(value if value is not None else ""), quote=True)


def entry_html(row):
    documents = "".join(
        f"<li>{e(d['title'])} · v{e(d['version_label'])} · {e(d['source_label'])}"
        + (
            f' <a href="{e(d["download_url"])}">打开固定依据版本</a>'
            if d["openable"]
            else " · 原文件不可打开"
        )
        + f"<p>控制点：{e(d['control_points'] or '原依据未明确')}</p><p>例外条款：{e(d['exception_terms'] or '原依据未明确')}</p></li>"
        for d in row["documents"]
    )
    forms = "".join(
        f"<li>{e(f['name'])} · v{e(f['version'])} · {e(f['source_label'])}<p>{e(f['fields'])}</p></li>"
        for f in row["forms"]
    )
    rules = "".join(
        f"<li>{e(r['name'])} · v{e(r['version'])}：{e(r['conditions'])} → 原节点 {e(r['target_node_key'])}</li>"
        for r in row["rules"]
    )
    tools = "".join(
        f"<li>{e(t['name'])} · {e(t['label'])} · {e(t['note'])}</li>" for t in row["tools"]
    )
    return (
        f"<article><h3>{e(row['process_code'])} / {e(row['name'])}</h3><p>{e(row['assignment_label'])}</p>"
        f"<p>模型 #{e(row['model_version_id'])} · 节点 {e(row['node_key'] or '未推定')} · 任务 {e(row['task_id'] or '—')}</p>"
        f"<p>作业说明：{e(row['instruction'] or row['instruction_label'])}</p><ul>{documents}</ul>"
        f"<h4>原表单／记录</h4><ul>{forms or '<li>原依据未明确</li>'}</ul>"
        f"<h4>例外与原规则</h4><p>{e(row['exception_label'])}</p><ul>{rules}</ul>"
        f"<h4>方法工具</h4><ul>{tools or '<li>未绑定</li>'}</ul>"
        f'<p>{e(row["source_note"])}</p><a href="{e(row["designer_url"])}">回原模型步骤核对</a></article>'
    )


def render(subject, entries, collaboration, gaps):
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>员工作业手册</title><style>body{font:16px/1.7 sans-serif;max-width:960px;margin:24px auto;padding:0 16px;background:#fff;color:#202830}"
        "article{border-left:3px solid #315e88;padding:0 16px;margin:24px 0}p,li{overflow-wrap:anywhere}a{color:#174ca1}@media print{article{break-inside:avoid}}</style></head><body>"
        f"<h1>{e(subject['name'])} · 员工作业手册</h1><p>员工能看出哪些步骤归自己、该打开哪一版依据、遇到例外该按哪条原规则处理；系统不知道的，明确说不知道。</p>"
        + "".join(entry_html(row) for row in entries)
        + "<section><h2>协作而非执行步骤</h2>"
        + "".join(
            f"<p>{e(r['role_name'])} · {e(r['raci_label'])} · 原节点 {e(r['node_key'] or '流程事项/活动')}</p>"
            for r in collaboration
        )
        + "</section>"
        + "<section><h2>缺口与限制</h2>"
        + "".join(f"<p>{e(g['message'])}</p>" for g in gaps)
        + "<p>原依据存在不代表组织授权、员工能力或实际业务效果已经验证。不据排序推定业务执行次序。</p></section></body></html>"
    )
