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


@pytest.fixture(autouse=True)
def _stage_reply_attempts(monkeypatch):
    """Every test sees the default: a stage asks for an unusable reply twice in
    all, whatever the developer's environment sets."""
    from app.config import settings

    monkeypatch.setattr(settings, "STAGE_REPLY_ATTEMPTS", 2)


@pytest.fixture(autouse=True)
def _no_live_provider(monkeypatch):
    """No test reaches OpenRouter. A test that needs a model stubs
    `provider.chat` (or, to exercise `chat` itself, `provider.httpx.post`) and
    that replaces this; one that forgets fails here instead of making a paid
    call. `pytest.fail` is not an `Exception`, so a stage's own
    `except Exception` cannot swallow the missing stub as a failed call.

    The guard sits on the HTTP post, not on `chat`, so the tests that run the
    real `chat` against a fake response keep working. Other URLs pass through."""
    import httpx

    from app.ai import provider

    real_post = httpx.post

    def post(url, *args, **kwargs):
        if str(url) == provider.CHAT_URL:
            pytest.fail("a test called the live provider; stub app.ai.provider.chat")
        return real_post(url, *args, **kwargs)

    monkeypatch.setattr(httpx, "post", post)
