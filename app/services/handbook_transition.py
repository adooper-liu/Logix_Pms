def validate_for_transition(db, document, version, target, user):
    from fastapi import HTTPException

    if target not in {"IN_REVIEW", "APPROVED", "EFFECTIVE"}:
        return
    manifest = version.compile_manifest or {}
    if manifest.get("kind") != "HANDBOOK":
        raise HTTPException(409, "员工手册缺少原编译依据")
    if not manifest.get("input_hash"):
        raise HTTPException(409, "员工手册缺少固定编译指纹")
    from app.services.handbook import preview

    data = preview(
        db,
        manifest["subject"]["scope"],
        manifest["subject"]["id"],
        user,
        application_url=manifest.get("application_url"),
    )
    if data.input_hash != manifest.get("input_hash") or not data.can_compile:
        raise HTTPException(409, "原手册依据已变化，请重新预览并生成草稿")
    if not data.can_submit_review:
        raise HTTPException(
            409, {"message": "员工手册作业依据未齐，不能正式流转", "gaps": data.gaps}
        )
