from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.routers.requests import create_request, retry_generation
from app.application.services.customer_access import customer_access_token_digest
from app.infrastructure.db.base import Base
from app.domain.models.request import Request


class _Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.result


class _Db:
    def __init__(self, req: Request | None = None):
        self.req = req
        self.commits = 0
        self.rollbacks = 0

    def add(self, req: Request) -> None:
        self.req = req

    def commit(self) -> None:
        self.commits += 1
        if self.req is not None and getattr(self.req, "id", None) is None:
            self.req.id = 101

    def refresh(self, _req: Request) -> None:
        return None

    def query(self, entity):
        if entity is Request:
            return _Query(self.req)
        raise AssertionError(entity)

    def execute(self, statement):
        params = statement.compile().params
        if self.req is None:
            rowcount = 0
        elif int(params.get("id_1") or 0) != int(self.req.id):
            rowcount = 0
        elif str(self.req.status or "") != str(params.get("status_1") or ""):
            rowcount = 0
        else:
            self.req.status = params.get("status")
            rowcount = 1

        class _Result:
            def __init__(self, rowcount: int):
                self.rowcount = rowcount

        return _Result(rowcount)

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


async def _create(db: _Db):
    return await create_request(
        business_name="Retry Safe Booking",
        business_description="Booking app",
        email="owner@example.com",
        industry="Services",
        target_customers="Customers",
        main_problem="Manual booking",
        desired_outcome="Online scheduling",
        project_type="new",
        needs_ai="no",
        reference_url=None,
        what_you_like=None,
        existing_product_url=None,
        budget_range=None,
        timeline=None,
        whatsapp=None,
        reference_file=None,
        db=db,
    )


def test_create_request_returns_raw_customer_token_once_but_stores_digest(
    monkeypatch,
) -> None:
    started = {"count": 0}

    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started["count"] += 1

    monkeypatch.setattr("app.api.v1.routers.requests.threading.Thread", _Thread)
    db = _Db()

    response = asyncio.run(_create(db))

    assert response.customer_access_token
    assert db.req is not None
    assert db.req.customer_access_token != response.customer_access_token
    assert db.req.customer_access_token == customer_access_token_digest(
        response.customer_access_token
    )
    assert started["count"] == 1


def test_retry_generation_rejects_missing_customer_access_token() -> None:
    req = Request(
        id=41,
        business_name="Retry Safe Booking",
        business_description="Booking app",
        email="owner@example.com",
        status="failed",
        customer_access_token=customer_access_token_digest("tok-41"),
    )

    with pytest.raises(HTTPException) as exc:
        retry_generation(req.id, db=_Db(req), x_request_access_token=None)

    assert exc.value.status_code == 401


def test_retry_generation_rejects_invalid_customer_access_token() -> None:
    req = Request(
        id=42,
        business_name="Retry Safe Booking",
        business_description="Booking app",
        email="owner@example.com",
        status="failed",
        customer_access_token=customer_access_token_digest("tok-42"),
    )

    with pytest.raises(HTTPException) as exc:
        retry_generation(req.id, db=_Db(req), x_request_access_token="bad-token")

    assert exc.value.status_code == 403


def test_retry_generation_rejects_non_failed_request_even_with_valid_token() -> None:
    req = Request(
        id=43,
        business_name="Retry Safe Booking",
        business_description="Booking app",
        email="owner@example.com",
        status="ready",
        customer_access_token=customer_access_token_digest("tok-43"),
    )

    with pytest.raises(HTTPException) as exc:
        retry_generation(req.id, db=_Db(req), x_request_access_token="tok-43")

    assert exc.value.status_code == 409


def test_retry_generation_migrates_legacy_token_and_starts_once(
    monkeypatch,
) -> None:
    req = Request(
        id=44,
        business_name="Retry Safe Booking",
        business_description="Booking app",
        email="owner@example.com",
        status="failed",
        customer_access_token="tok-44",
    )
    db = _Db(req)
    started = {"count": 0}

    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started["count"] += 1

    monkeypatch.setattr("app.api.v1.routers.requests.threading.Thread", _Thread)
    monkeypatch.setattr("app.api.v1.routers.requests._emit", lambda *a, **k: None)

    with pytest.raises(HTTPException) as exc:
        retry_generation(req.id, db=db, x_request_access_token=None)
    assert exc.value.status_code == 401
    assert started["count"] == 0

    payload = retry_generation(req.id, db=db, x_request_access_token="tok-44")

    assert payload["ok"] is True
    assert payload["id"] == req.id
    assert payload["mode"] == "full"
    assert started["count"] == 1
    assert req.customer_access_token == customer_access_token_digest("tok-44")


def test_retry_generation_allows_only_one_atomic_claim_across_sessions(
    tmp_path,
    monkeypatch,
) -> None:
    started = {"count": 0}

    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started["count"] += 1

    monkeypatch.setattr("app.api.v1.routers.requests.threading.Thread", _Thread)
    monkeypatch.setattr("app.api.v1.routers.requests._emit", lambda *a, **k: None)

    db_path = tmp_path / "retry-claim.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    try:
        req = Request(
            business_name="Atomic Retry",
            business_description="Booking app",
            email="owner@example.com",
            status="failed",
            customer_access_token=customer_access_token_digest("tok-55"),
        )
        seed.add(req)
        seed.commit()
        request_id = req.id
    finally:
        seed.close()

    first = Session()
    second = Session()
    try:
        payload = retry_generation(
            request_id,
            db=first,
            x_request_access_token="tok-55",
        )
        assert payload["ok"] is True

        with pytest.raises(HTTPException) as exc:
            retry_generation(
                request_id,
                db=second,
                x_request_access_token="tok-55",
            )
        assert exc.value.status_code == 409
        assert started["count"] == 1
    finally:
        first.close()
        second.close()


def test_retry_generation_preview_worker_can_acquire_lock_after_claim(
    monkeypatch,
) -> None:
    req = Request(
        id=56,
        business_name="Retry Preview",
        business_description="Booking app",
        email="owner@example.com",
        status="failed",
        mvp_blueprint="has blueprint",
        customer_access_token=customer_access_token_digest("tok-56"),
    )
    db = _Db(req)
    worker = {"acquired": False, "count": 0}

    def _worker(request_id: int) -> None:
        from app.api.v1.routers.requests import _preview_gen_lock

        worker["count"] += 1
        lock = _preview_gen_lock(request_id)
        worker["acquired"] = lock.acquire(blocking=False)
        if worker["acquired"]:
            lock.release()

    class _Thread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            assert self.target is not None
            self.target(*self.args)

    monkeypatch.setattr("app.api.v1.routers.requests.threading.Thread", _Thread)
    monkeypatch.setattr("app.api.v1.routers.requests._emit", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.api.v1.routers.requests._run_preview_app_in_background",
        _worker,
    )

    payload = retry_generation(req.id, db=db, x_request_access_token="tok-56")

    assert payload["mode"] == "preview_app"
    assert worker["count"] == 1
    assert worker["acquired"] is True


def test_preview_worker_persists_failed_terminal_status(monkeypatch) -> None:
    req = Request(
        id=57,
        business_name="Retry Preview",
        business_description="Booking app",
        email="owner@example.com",
        status="retrying_preview_app",
        mvp_blueprint="has blueprint",
    )

    class _BgDb(_Db):
        def query(self, entity):
            if entity is Request:
                return _Query(req)
            raise AssertionError(entity)

    bg_db = _BgDb(req)
    monkeypatch.setattr("app.api.v1.routers.requests.SessionLocal", lambda: bg_db)
    monkeypatch.setattr(
        "app.api.v1.routers.requests.generate_preview_app",
        lambda *_args, **_kwargs: {
            "preview_contract": {"status": "candidate_contract_failed"}
        },
    )

    from app.api.v1.routers.requests import _run_preview_app_in_background

    _run_preview_app_in_background(req.id)

    assert req.status == "failed"


def test_preview_worker_persists_ready_status_on_visual_acceptance(monkeypatch) -> None:
    req = Request(
        id=58,
        business_name="Retry Preview",
        business_description="Booking app",
        email="owner@example.com",
        status="retrying_preview_app",
        mvp_blueprint="has blueprint",
    )

    class _BgDb(_Db):
        def query(self, entity):
            if entity is Request:
                return _Query(req)
            raise AssertionError(entity)

    bg_db = _BgDb(req)
    monkeypatch.setattr("app.api.v1.routers.requests.SessionLocal", lambda: bg_db)
    monkeypatch.setattr(
        "app.api.v1.routers.requests.generate_preview_app",
        lambda *_args, **_kwargs: {
            "preview_contract": {"status": "candidate_visual_accepted"}
        },
    )

    from app.api.v1.routers.requests import _run_preview_app_in_background

    _run_preview_app_in_background(req.id)

    assert req.status == "ready"
