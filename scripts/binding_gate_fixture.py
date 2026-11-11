"""浏览器专项共用合成绑定；只通过原 API，不向业务库写入。"""

from uuid import uuid4


def api_for(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}

    def api(method, path, data=None):
        response = page.request.fetch(
            base + "/api/v1" + path, method=method, headers=headers, data=data
        )
        assert response.ok, (method, path, response.status, response.text())
        return response.json()

    return api, headers


def add_bindings(page, base, pid, aid, position_id, node_key, *, with_a=True, performance=True):
    api, headers = api_for(page, base)
    suffix = uuid4().hex[:8]
    form = api(
        "POST",
        "/execution/forms",
        {"process_id": pid, "node_key": node_key, "name": "合成活动记录", "fields": []},
    )
    standard = api(
        "POST",
        "/workload/standards",
        {
            "name": "合成工时",
            "activity_id": aid,
            "position_id": position_id,
            "observed_minutes": 5,
            "sample_size": 5,
            "method_description": "仅隔离合成验证，非实际业务标准",
            "monthly_frequency": 10,
        },
    )
    api("POST", f"/workload/standards/{standard['id']}/verify")
    result = {"form": form, "standard": standard}
    if with_a:
        result["raci"] = add_accountability(api, pid, aid, position_id)
    if performance:
        api(
            "POST",
            "/monitor/kpis",
            {
                "code": "GUK-" + suffix,
                "name": "合成活动指标",
                "dimension": "EFFICIENCY",
                "process_id": pid,
                "activity_id": aid,
                "target_value": 5,
                "formula": "合成样本均值",
                "measurement": {
                    "source_kind": "MANUAL",
                    "minimum_samples": 1,
                    "freshness_days": 30,
                    "purpose": "隔离合成结构核对",
                    "response_note": "回原来源核对",
                },
            },
        )
        doc = api(
            "POST",
            "/process-documents",
            {
                "process_id": aid,
                "title": "合成活动标准",
                "category": "SOP",
                "control_points": "办理后核对合成记录",
            },
        )
        response = page.request.post(
            base + f"/api/v1/process-documents/{doc['id']}/versions/upload",
            headers=headers,
            multipart={
                "version_label": "1.0",
                "file": {
                    "name": "synthetic-standard.txt",
                    "mimeType": "text/plain",
                    "buffer": b"Synthetic only, not a business standard.",
                },
            },
        )
        assert response.ok, response.text()
        version = response.json()
        for target in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            api(
                "POST",
                f"/process-documents/{doc['id']}/versions/{version['id']}/transition",
                {"status": target},
            )
    return result


def add_accountability(api, pid, aid, position_id):
    suffix = uuid4().hex[:8]
    role = api("POST", "/governance/roles", {"code": "GUR-" + suffix, "name": "合成负责角色"})
    member = api(
        "POST",
        "/auth/users",
        {
            "username": "gate-" + suffix,
            "display_name": "合成岗位成员",
            "password": "Synthetic-Only-48!",
            "role": "OWNER",
            "position_id": position_id,
        },
    )
    api("POST", f"/governance/roles/{role['id']}/members", {"user_id": member["id"]})
    return api(
        "POST",
        "/governance/raci",
        {
            "process_id": pid,
            "activity_id": aid,
            "role_id": role["id"],
            "matter": "合成活动负责",
            "raci": "A",
        },
    )
