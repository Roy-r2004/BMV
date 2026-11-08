"""The public address serves rendered pictures and nothing else.

Finished packages are stored under a sequential id (`exports/1-engagement.zip`)
and client documents under `engagements/`. Neither may be reachable without
the signed-in routes that check who is asking.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
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


def test_a_rendered_screen_is_served(client):
    _put("images/1/dashboard_0.png", b"\x89PNG")
    response = client.get("/uploads/images/1/dashboard_0.png")
    assert response.status_code == 200 and response.content == b"\x89PNG"


@pytest.mark.parametrize("name", ["dashboard_0.json", "dashboard_0.html", "notes.txt"])
def test_only_pictures_leave_the_images_folder(client, name):
    _put(f"images/1/{name}")
    assert client.get(f"/uploads/images/1/{name}").status_code == 404


@pytest.mark.parametrize("path", ["/uploads/images/../exports/1-engagement.zip", "/uploads/images/%2e%2e/exports/1-engagement.zip"])
def test_the_images_folder_cannot_be_climbed_out_of(client, path):
    _put("exports/1-engagement.zip")
    assert client.get(path).status_code == 404
