"""A customer is told "ready" only when there is something to look at.

Request 67 answered `GET /api/requests/67/progress` with
`status: "ready"`, `stage_label: "Your preview is ready"`, `pct: 100`,
`is_failed: false`, `visual_demo_status: "available"` — and `preview_url: null`.

The withholding itself was right: the quality gate had failed and there was
nothing worth serving. The label on top of it was the defect. Every internal
signal `_base_customer_status` consulted says "the pipeline finished"; only the
URL says "the pipeline produced something". Treating any of the former as
sufficient turns a correct withhold into a contradiction the user reads as a
broken product.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.services.customer_preview import (  # noqa: E402
    _base_customer_status,
)


def _status(*, preview_url, request_status="ready", stage="ready", contract_status=""):
    return _base_customer_status(
        SimpleNamespace(status=request_status),
        {"status": contract_status},
        {"stage": stage},
        preview_url=preview_url,
    )


def test_finished_with_a_preview_is_ready() -> None:
    assert _status(preview_url="/api/preview-apps/67/") == "ready"


def test_finished_with_no_preview_is_never_ready() -> None:
    """The exact shape request 67 served."""
    assert _status(preview_url=None) != "ready"


def test_every_finished_signal_needs_the_url_too() -> None:
    """Each of the three was independently sufficient before."""
    for kwargs in (
        {"request_status": "ready", "stage": "", "contract_status": ""},
        {"request_status": "done", "stage": "", "contract_status": ""},
        {"request_status": "delivered", "stage": "", "contract_status": ""},
        {"request_status": "approved", "stage": "", "contract_status": ""},
        {"request_status": "", "stage": "ready", "contract_status": ""},
        {"request_status": "", "stage": "done", "contract_status": ""},
        {"request_status": "", "stage": "refine_done", "contract_status": ""},
        {"request_status": "", "stage": "", "contract_status": "candidate_visual_accepted"},
    ):
        assert _status(preview_url=None, **kwargs) != "ready", kwargs
        assert _status(preview_url="/api/preview-apps/1/", **kwargs) == "ready", kwargs


def test_a_failed_run_still_reads_as_failed() -> None:
    """Withholding is not failure, but failure must not be softened into it."""
    failed = _base_customer_status(
        SimpleNamespace(status="failed"),
        {"status": "failed"},
        {"stage": "failed"},
        preview_url=None,
    )
    assert failed == "failed"
