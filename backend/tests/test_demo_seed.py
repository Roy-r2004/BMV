"""PlateSync seed must never delete customer builds."""
from __future__ import annotations

from pathlib import Path

from app.application.services import demo_seed
from app.domain.models.request import Request


def test_seed_skips_insert_when_requests_exist(monkeypatch, tmp_path: Path) -> None:
    seed_file = tmp_path / "seed_platesync.json"
    seed_file.write_text('{"business_name":"PlateSync ERP"}', encoding="utf-8")

    class _Query:
        def count(self):
            return 2

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            other = Request(
                business_name="LedgerFlow",
                concept_name="Accounting",
                visual_demo_json="{}",
            )
            other.id = 9
            return [other]

    class _Session:
        def __init__(self):
            self.added = []

        def query(self, *_args, **_kwargs):
            return _Query()

        def add(self, row):
            self.added.append(row)

        def delete(self, row):
            raise AssertionError(f"must not delete customer row {row}")

        def commit(self):
            return None

        def flush(self):
            return None

        def close(self):
            return None

    session = _Session()
    monkeypatch.setattr(demo_seed, "SessionLocal", lambda: session)
    monkeypatch.setattr(demo_seed, "_first_existing", lambda paths, is_dir=False: seed_file)
    monkeypatch.setattr(demo_seed, "_install_preview_dist", lambda *_a, **_k: False)

    demo_seed.seed_demo_if_empty()
    assert session.added == []


def test_seed_demo_env_default_is_false() -> None:
    import os

    assert os.getenv("SEED_DEMO", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }
