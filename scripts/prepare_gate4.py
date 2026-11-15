"""Prepare L3-032 Gate 4 configuration; preview by default, never run business cases.

python -m scripts.prepare_gate4          # transaction rollback, no attachment
python -m scripts.prepare_gate4 --apply  # explicit atomic configuration write
python -m scripts.prepare_gate4 --check  # strictly read-only verification
"""

import argparse
import json

from sqlalchemy import text

import app.models  # noqa: F401
from app.core.database import SessionLocal, engine
from app.models.execution import ProcessInstance
from app.models.process import ProcessModelVersion
from app.services import binding_snapshot, gate4_configuration


def _history(db):
    """Guard original model/instance facts, not merely their row counts."""
    from sqlalchemy import select

    pid = gate4_configuration._process(db, "L3-032").id
    models = db.scalars(
        select(ProcessModelVersion).where(ProcessModelVersion.process_id == pid)
    ).all()
    instances = db.scalars(select(ProcessInstance).where(ProcessInstance.process_id == pid)).all()
    return {
        "models": {r.id: binding_snapshot._hash(binding_snapshot._row(r)) for r in models},
        "instances": {r.id: binding_snapshot._hash(binding_snapshot._row(r)) for r in instances},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            if args.check:
                if engine.dialect.name == "postgresql":
                    db.execute(text("SET TRANSACTION READ ONLY"))
                result = gate4_configuration.check(db)
                db.rollback()
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result["configuration_ready"] else 1
            before = _history(db)
            result = gate4_configuration.prepare(db, persist_file=args.apply)
            after = _history(db)
            if before["instances"] != after["instances"] or any(
                after["models"].get(ident) != digest for ident, digest in before["models"].items()
            ):
                raise ValueError("原模型或历史实例发生变化，已拒绝提交")
            result["historical_instances_unchanged"] = len(before["instances"])
            result["historical_models_unchanged"] = len(before["models"])
            if args.apply:
                db.commit()
                result["transaction"] = "COMMITTED_CONFIGURATION_ONLY"
            else:
                db.rollback()
                result["transaction"] = "ROLLED_BACK_PREVIEW"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
