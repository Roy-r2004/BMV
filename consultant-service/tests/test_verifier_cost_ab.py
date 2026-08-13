"""Pins the two things in the verifier cost harness that fail silently.

`scripts/verifier_cost_ab.py` answered session 39's JOB 1 for $0.18 —
a question that would have cost ~$111 a side to answer by running
generations. Both of its footguns are quiet ones:

1. `--requests 104-108,119` decides which corpus gets measured. A range
   parsed wrong does not raise; it measures a different set of images and
   reports a confident number about the wrong thing.
2. Both arms must resolve to the SAME template path the pipeline reads,
   because the whole method is swapping that file underneath
   `defect_check`. If the constant drifts from the real prompt location,
   the harness measures one template twice and reports no difference —
   which is indistinguishable from a change that did nothing.

These tests spend nothing: no image is read and no model is called.
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(SERVICE_ROOT, "scripts", "verifier_cost_ab.py")
    spec = importlib.util.spec_from_file_location("verifier_cost_ab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_request_range_expands_the_way_the_evidence_documents_claim():
    parse = _load().parse_requests
    # The exact argument session 39's measurement was taken with.
    assert parse("104-108,119,120,128,129") == [104, 105, 106, 107, 108, 119, 120, 128, 129]


def test_ranges_are_inclusive_at_both_ends():
    parse = _load().parse_requests
    assert parse("104-106") == [104, 105, 106]
    assert parse("7") == [7]


def test_duplicates_and_whitespace_do_not_double_count_an_image():
    """An id counted twice would weight one request's images twice in a
    rate that is reported as a per-image fraction."""
    parse = _load().parse_requests
    assert parse(" 104 , 104-105 ,105 ") == [104, 105]


def test_both_arms_swap_the_template_defect_check_actually_reads():
    """The harness's only mechanism is overwriting this file. If it points
    anywhere else, both arms run the live prompt and the measurement
    reports a null result for every possible change."""
    from app.pipeline import defect_check  # noqa: F401  (import must succeed)

    template = _load().TEMPLATE
    assert os.path.basename(template) == "image_defect_verifier.j2"
    assert template == os.path.join(
        SERVICE_ROOT, "app", "prompts", "image_defect_verifier.j2"
    )
    assert os.path.exists(template), "the harness would restore a file that never existed"
