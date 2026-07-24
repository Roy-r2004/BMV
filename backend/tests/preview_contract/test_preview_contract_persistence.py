from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from app.application.appspec.source import capture_request_source_v2
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.repository import PreviewContractRepository
from app.domain.models import (  # noqa: F401
    AppSpecRevision,
    CustomerSourceArtifact,
    ProductStrategyRevision,
    Request,
)
from app.infrastructure.db.base import Base


def _request(request_id: int = 601) -> Request:
    return Request(
        id=request_id,
        business_name="Northstar",
        industry="Analytics",
        business_description="A data-heavy workflow for trading teams.",
        target_customers="Trading analysts",
        main_problem="Signals and reviews are split across tools.",
        desired_outcome="Review signals and record decisions in one workspace.",
        project_type="new",
        email="owner@example.com",
        mvp_blueprint="A derived trading workspace.",
        preview_features='["Signal review", "Decision log"]',
        created_at=datetime(2026, 7, 24, 10, 0, 0),
    )


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


def test_additive_schema_migration_preserves_an_existing_request() -> None:
    engine = create_engine("sqlite:///:memory:")
    Request.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(_request(602))
        db.commit()

        Base.metadata.create_all(bind=engine)

        tables = set(inspect(engine).get_table_names())
        assert "customer_source_artifacts" in tables
        assert "product_strategy_revisions" in tables
        assert db.query(Request).filter(Request.id == 602).one().business_name == "Northstar"
    finally:
        db.close()


def test_post_migration_artifact_write_rolls_back_with_outer_transaction() -> None:
    _engine, db = _db()
    try:
        req = _request()
        db.add(req)
        db.commit()
        source = capture_request_source_v2(req)
        strategy = project_product_strategy(req, source)

        PreviewContractRepository(db).stage_inputs(
            source=source,
            strategy=strategy,
        )
        assert db.query(CustomerSourceArtifact).count() == 1
        assert db.query(ProductStrategyRevision).count() == 1

        db.rollback()
        assert db.query(CustomerSourceArtifact).count() == 0
        assert db.query(ProductStrategyRevision).count() == 0
    finally:
        db.close()


def test_strategy_insert_failure_rolls_back_new_source_savepoint() -> None:
    _engine, db = _db()
    req = _request(603)
    db.add(req)
    db.commit()
    source = capture_request_source_v2(req)
    strategy = project_product_strategy(req, source)

    def fail_strategy_insert(*_args, **_kwargs) -> None:
        raise RuntimeError("injected strategy persistence failure")

    event.listen(ProductStrategyRevision, "before_insert", fail_strategy_insert)
    try:
        with pytest.raises(RuntimeError, match="injected strategy"):
            PreviewContractRepository(db).stage_inputs(
                source=source,
                strategy=strategy,
            )
        assert db.query(CustomerSourceArtifact).count() == 0
        assert db.query(ProductStrategyRevision).count() == 0
    finally:
        event.remove(ProductStrategyRevision, "before_insert", fail_strategy_insert)
        db.rollback()
        db.close()
