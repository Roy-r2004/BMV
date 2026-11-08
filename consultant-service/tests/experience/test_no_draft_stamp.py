"""Roy's decision: clients see no DRAFT stamp. The checks behind it keep running."""
from types import SimpleNamespace

import pytest

from app.config import settings
from app.pipeline import export_pdf as ep


def _gate(monkeypatch, status):
    monkeypatch.setattr(ep, "release_status", lambda req: {
        "status": status, "status_label": ep.STATUS_LABELS[status], "reasons": ["a finding"] if status == "draft" else []})


@pytest.fixture
def stamp_off(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_DRAFT_STAMP", False)


def test_the_cover_of_a_package_with_findings_says_nothing_about_its_state(monkeypatch, stamp_off):
    _gate(monkeypatch, "draft")
    assert ep._status_lines(SimpleNamespace()) == []


def test_it_does_not_claim_to_be_final_either(monkeypatch, stamp_off):
    _gate(monkeypatch, "draft")
    assert ep.stamped_status(SimpleNamespace()) == "unstamped"
    assert not any("FINAL" in getattr(f, "text", "") for f in ep._status_lines(SimpleNamespace()))


def test_a_clean_package_still_says_final(monkeypatch, stamp_off):
    _gate(monkeypatch, "final")
    assert ep.stamped_status(SimpleNamespace()) == "final"
    assert ep._status_lines(SimpleNamespace())


def test_the_gate_still_knows_it_has_findings(monkeypatch, stamp_off):
    _gate(monkeypatch, "draft")
    assert ep.release_status(SimpleNamespace())["reasons"] == ["a finding"]


def test_the_switch_brings_the_stamp_back(monkeypatch):
    monkeypatch.setattr(settings, "SHOW_DRAFT_STAMP", True)
    _gate(monkeypatch, "draft")
    monkeypatch.setattr(ep, "plain_reasons", lambda req, gate: ["One check did not pass."])
    assert ep.stamped_status(SimpleNamespace()) == "draft"
    assert "DRAFT" in ep._status_lines(SimpleNamespace())[1].text
