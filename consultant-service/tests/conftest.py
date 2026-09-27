import os
import sys
import tempfile

# Make `app` importable when pytest runs from the service root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the DB at a throwaway file BEFORE anything imports app.config,
# which reads DATABASE_URL once at class-definition time and builds the
# engine from it. Without this, the API tests write rows into whatever DB
# the developer's .env names — the real dev database, on a laptop.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(prefix="bmv-consultant-tests-"), "test.db")

import pytest


@pytest.fixture(autouse=True)
def _signed_in(monkeypatch):
    """Every API test runs as a signed-in account unless it overrides this
    — the auth gate's own tests monkeypatch resolve_user back to None."""
    from app import auth_client

    monkeypatch.setattr(
        auth_client, "resolve_user",
        lambda authorization: {"email": "test@example.com", "name": "Test"},
    )
