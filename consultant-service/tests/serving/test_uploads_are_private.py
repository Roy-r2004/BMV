"""The public address serves rendered pictures and nothing else.

Finished packages are stored under a sequential id (`exports/1-engagement.zip`)
and client documents under `engagements/`. Neither may be reachable without
the signed-in routes that check who is asking.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.serving import signed
from main import app

#: The folder the server mounted when it started. Read here, at import: the
#: suite's per-test fixture repoints `settings.UPLOADS_DIR`, and a file written
#: there is one the server never sees, so every "not served" would pass falsely.
SERVED_ROOT = settings.UPLOADS_DIR


@pytest.fixture
def client():
    return TestClient(app)


def _put(relative: str, body: bytes = b"secret") -> None:
    path = os.path.join(SERVED_ROOT, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)


@pytest.mark.parametrize(
    "relative",
    [
        "exports/1-engagement.zip",
        "exports/1-blueprint.pdf",
        "exports/1.pptx",
        "exports/1-law-blueprint.json",
        "engagements/abc/original.xlsx",
        "requests/1/notes.txt",
    ],
)
def test_private_files_are_not_served(client, relative):
    _put(relative)
    assert client.get(f"/uploads/{relative}").status_code == 404


def test_a_rendered_screen_is_served_at_the_address_the_server_gave(client):
    _put("images/1/dashboard_0.png", b"\x89PNG")
    response = client.get(signed("/uploads/images/1/dashboard_0.png?v=3"))
    assert response.status_code == 200 and response.content == b"\x89PNG"


def test_a_screen_cannot_be_reached_by_counting(client):
    _put("images/1/dashboard_0.png", b"\x89PNG")
    assert client.get("/uploads/images/1/dashboard_0.png").status_code == 404
    assert client.get("/uploads/images/1/dashboard_0.png?k=guess").status_code == 404


def test_one_engagements_key_does_not_open_another(client):
    _put("images/2/dashboard_0.png", b"\x89PNG")
    key = signed("/uploads/images/1/dashboard_0.png").split("k=")[1]
    assert client.get(f"/uploads/images/2/dashboard_0.png?k={key}").status_code == 404


@pytest.mark.parametrize("name", ["dashboard_0.json", "dashboard_0.html", "notes.txt"])
def test_only_pictures_leave_the_images_folder(client, name):
    _put(f"images/1/{name}")
    assert client.get(signed(f"/uploads/images/1/{name}")).status_code == 404


def test_a_key_from_an_earlier_run_with_the_same_number_does_not_open_this_one(client):
    _put("images/1/dashboard_0.png", b"\x89PNG")
    key = signed("/uploads/images/1/dashboard_0.png?v=100").split("k=")[1]
    assert client.get(f"/uploads/images/1/dashboard_0.png?v=200&k={key}").status_code == 404


@pytest.mark.parametrize("query", ["", "?review_token=wrong"])
def test_the_operator_view_needs_the_reviewer_token(client, monkeypatch, query):
    monkeypatch.setattr(settings, "REVIEW_TOKEN", "reviewer")
    assert client.get(f"/api/requests/1/admin{query}").status_code == 403


def test_the_operator_view_is_closed_when_no_reviewer_token_is_set(client, monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_TOKEN", "")
    assert client.get("/api/requests/1/admin?review_token=").status_code == 403


def test_an_address_outside_the_pictures_is_left_alone():
    assert signed(None) is None
    assert signed("https://example.com/a.png") == "https://example.com/a.png"


@pytest.mark.parametrize("path", ["/uploads/images/../exports/1-engagement.zip", "/uploads/images/%2e%2e/exports/1-engagement.zip"])
def test_the_images_folder_cannot_be_climbed_out_of(client, path):
    _put("exports/1-engagement.zip")
    assert client.get(path).status_code == 404
