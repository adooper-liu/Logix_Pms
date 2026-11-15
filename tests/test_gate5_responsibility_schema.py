"""Gate 5 responsibility schema contracts."""


def test_responsibility_models_are_imported_and_have_required_columns():
    import app.models  # noqa: F401
    from app.core.database import Base
    from app.models.execution import NodeAssignment
    from app.models.responsibility import ProcessResponsibilityAcceptance

    assert "process_responsibility_acceptance" in Base.metadata.tables
    assert {
        "model_version_id",
        "approver_user_id",
        "backup_assignee_user_id",
        "effective_from",
        "effective_to",
    } <= {column.name for column in NodeAssignment.__table__.columns}
    assert {
        "process_id",
        "model_version_id",
        "node_key",
        "scope",
        "subject_user_id",
        "accepted_by_user_id",
        "accepted_at",
        "valid_until",
        "evidence_note",
        "status",
    } <= {column.name for column in ProcessResponsibilityAcceptance.__table__.columns}


def test_acceptance_has_current_uniqueness_constraint():
    from app.models.responsibility import ProcessResponsibilityAcceptance

    indexes = ProcessResponsibilityAcceptance.__table__.indexes
    assert any("current" in index.name and index.unique for index in indexes)
