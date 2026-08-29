"""Hardware and load are a unit family, and a model designation is a name.

Run 19 asked the pipeline to design a local AI datacenter. It could describe
the shape of the load and never size anything, because the number grammar knew
time, money and percent only:

  * "24 GB per card" parsed as the bare number 24 and typed as "count" --
    indistinguishable from "24 staff". The client's own stated figure could not
    be matched back to the claim it came from (units never agreed), so the
    document's use of it read as an unlabelled invention; and equally, a
    hardware number the model made up could not be told from a stated one.
  * "RTX 5090" parsed as the quantity 5090, so naming the recommended hardware
    tripped the labelling law -- the document was told it had invented a
    threshold by writing down a product name.

Both are the same doctrine the AI-logic law already follows after requests 16,
17 and 18: a law that reads prose must not read a NAME, and a number means
nothing without the kind of thing it counts.
"""
import pytest

from app.pipeline.registry import (
    _CAPACITY_FAMILY, _infer_unit, _numbers, _unit_compatible,
    canonical_capacity_unit, classify_threshold,
)


def units(text):
    return [(tok, unit) for tok, _v, unit, _s, _e in _numbers(text)]


def values(text):
    return [(v, unit) for _tok, v, unit, _s, _e in _numbers(text)]


# ── the family parses ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("each card carries 24 GB of VRAM", (24.0, "GB")),
    ("the card gives 32GB", (32.0, "GB")),
    ("a 2 TB NVMe scratch disk", (2.0, "TB")),
    ("512 MB of overhead", (512.0, "MB")),
    ("sustained 1,200 tokens/sec at peak", (1200.0, "tokens/sec")),
    ("about 45 req/s across the cluster", (45.0, "requests/sec")),
    ("the rack draws 3.45 kW under load", (3.45, "kW")),
    ("memory bandwidth of 936 GB/s", (936.0, "GB/s")),
    ("a 10 Gbps link", (10.0, "Gbps")),
    ("82 TFLOPS of compute", (82.0, "TFLOPS")),
])
def test_hardware_quantities_carry_their_unit(text, expected):
    assert values(text) == [expected]


@pytest.mark.parametrize("surface", ["GB / s", "gb/s", "GiB/s", "Gb / S"])
def test_one_quantity_canonicalises_to_one_unit(surface):
    """Spacing and case vary in client prose. Two spellings of one quantity
    must not become two units, or a figure stops matching its own claim."""
    assert canonical_capacity_unit(surface) == "GB/s"


@pytest.mark.parametrize("surface,canon", [
    ("tokens / second", "tokens/sec"), ("tok/s", "tokens/sec"), ("TPS", "tokens/sec"),
    ("requests/sec", "requests/sec"), ("QPS", "requests/sec"), ("GiB", "GB"),
])
def test_synonyms_canonicalise(surface, canon):
    assert canonical_capacity_unit(surface) == canon


def test_a_non_capacity_unit_is_not_one():
    for u in ("", "days", "%", "usd", "count", None):
        assert canonical_capacity_unit(u) is None


# ── the units that already worked still work ─────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("25 missed calls a week", [("25", "")]),
    ("a budget of $4,500 a month", [("$4,500", "")]),
    ("raise resolution to 90%", [("90", "%")]),
    ("settlement within 10 days after month-end", [("10", "days")]),
    ("p95 latency under 800 ms", [("800", "ms")]),
    ("we run 2 weeks of baseline", []),
    ("70 staff on shift", [("70", "")]),
])
def test_the_existing_grammar_is_unchanged(text, expected):
    assert units(text) == expected


# ── typing ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("unit,expected", [
    ("GB", "capacity_assumption"), ("TB", "capacity_assumption"),
    ("kW", "capacity_assumption"), ("GB/s", "capacity_assumption"),
    ("TFLOPS", "capacity_assumption"),
    # a rate the system must sustain is a target it can miss
    ("tokens/sec", "performance_target"), ("requests/sec", "performance_target"),
])
def test_hardware_numbers_get_a_real_type_not_the_catch_all(unit, expected):
    assert classify_threshold("1", 1.0, unit, "sustained ", " at peak") == expected


def test_the_new_types_are_ones_that_demand_a_provenance_label():
    """capacity_assumption and performance_target are both in _LABELED_TYPES,
    which is the whole point: an invented "3.45 kW" must now say it is
    proposed, where before it was an untyped number nobody could check."""
    from app.pipeline.registry import _LABELED_TYPES

    assert {"capacity_assumption", "performance_target"} <= _LABELED_TYPES


def test_a_bare_number_in_hardware_context_is_not_a_count():
    assert _infer_unit("24", "", "24 of VRAM per card")[0] == "GB"
    assert _infer_unit("8", "", "8 GPU per rig")[0] == "GPUs"
    assert _infer_unit("100", "", "100 concurrent users")[0] == "concurrent requests"


def test_hardware_hints_do_not_fire_on_ordinary_words():
    """"card" would match inside "scorecard" and "node" inside a journey's
    nodes, so only unambiguous hints are used."""
    assert _infer_unit("12", "", "12 items on the scorecard")[0] == "count"


# ── families never cross-match ───────────────────────────────────────────────

def test_a_memory_size_is_never_a_throughput():
    claim = {"unit": "tokens/sec", "time_basis": "n/a"}
    assert not _unit_compatible("GB", claim)


def test_a_memory_size_matches_a_memory_claim():
    assert _unit_compatible("GB", {"unit": "GB", "time_basis": "n/a"})
    assert _unit_compatible("TB", {"unit": "MB", "time_basis": "n/a"}), "same family"


def test_a_bare_number_is_not_the_clients_gigabytes():
    """24 cards is not the client's 24 GB -- the same rule that already keeps
    '5 minutes' away from '5 support staff'."""
    assert not _unit_compatible("", {"unit": "GB", "time_basis": "n/a"})


def test_a_bare_number_still_matches_an_ordinary_claim():
    assert _unit_compatible("", {"unit": "count", "time_basis": "as stated"})


def test_every_family_member_is_classifiable():
    for unit in _CAPACITY_FAMILY:
        assert classify_threshold("1", 1.0, unit, "", "") in (
            "capacity_assumption", "performance_target")


# ── a designation is a name ──────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "an RTX 5090 card", "two RTX 3090 cards", "a Quadro 6000",
    "Llama 3.1 70B", "Mixtral 8x22B", "Whisper large-v3",
    "on Python 3.11", "a Xeon 6338 socket",
])
def test_a_product_designation_is_not_a_quantity(text):
    assert units(text) == [], f"{text!r} named a product; nothing was measured"


def test_the_hardware_around_a_designation_still_counts():
    """Skipping the designation must not swallow the real figure beside it."""
    assert values("an RTX 5090 with 32 GB") == [(32.0, "GB")]
    assert values("Llama 3.1 70B needs 48 GB at 8-bit") == [(48.0, "GB")]


def test_money_beats_the_parameter_suffix():
    """"70B" is a model size, but "$70M" is money and keeps its meaning."""
    assert values("$70M in revenue") == [(70.0, "")]
    assert values("a 70B model") == []
