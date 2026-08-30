"""C0 contracts: the frozen vocabularies, quantities, envelope, payloads and
entity of app/engine/types.py. Each test names the law it pins; the
mutations the work breakdown requires are noted where they are caught.
"""
from __future__ import annotations

import dataclasses
import json
from decimal import Decimal

import pytest

from app.engine import types as T
from app.engine.types import (
    BOUNDS, FILTERABLE_FIELDS, ID_PREFIX, PAYLOAD_TYPES, TEXT_FIELDS, Actor, Authority, Confidence, Dimensions,
    Entity, FactBasis, InfoType, Kind, Provenance, Quantity, RelationToCentralDecision, Relevance, Status,
    UnitFamily, info_type_of, make_entity, payload_field, validate_payload,
)

from conftest import sample_entity, sample_payload


# ---------------------------------------------------------------------------
# vocabularies
# ---------------------------------------------------------------------------

def test_every_kind_has_a_unique_id_prefix():
    assert set(ID_PREFIX) == set(Kind)
    prefixes = list(ID_PREFIX.values())
    assert len(set(prefixes)) == len(prefixes) == 41
    assert all(len(p) == 3 and p.isupper() for p in prefixes)


def test_every_kind_has_a_typed_payload_and_every_payload_belongs_to_one_kind():
    # Mutation "drop a Kind from PAYLOAD_TYPES" is caught here (and by the
    # import-time assert): validate_payload would KeyError on the orphan kind.
    assert set(PAYLOAD_TYPES) == set(Kind)
    assert len(set(PAYLOAD_TYPES.values())) == 41
    for kind in Kind:
        cls = PAYLOAD_TYPES[kind]
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen
        validate_payload(kind, sample_payload(kind))


def test_filterable_and_text_fields_are_disjoint():
    # A filter that could read prose is how an engagement type creeps in (M2/P1).
    assert not (FILTERABLE_FIELDS & TEXT_FIELDS)
    assert "text" in TEXT_FIELDS and "statement" in TEXT_FIELDS
    assert "basis" in FILTERABLE_FIELDS and "capability_class" in FILTERABLE_FIELDS


def test_precedence_lists_every_document_verified_record_class_and_client_stated():
    for rc in T.RecordClass:
        if rc != T.RecordClass.UNKNOWN:
            assert f"document_verified:{rc.value}" in T.CURRENT_STATE_PRECEDENCE
    assert "client_stated" in T.CURRENT_STATE_PRECEDENCE and "inferred" in T.CURRENT_STATE_PRECEDENCE
    assert T.CURRENT_STATE_PRECEDENCE.index("document_verified:system_of_record") < T.CURRENT_STATE_PRECEDENCE.index("client_stated")


def test_phase_transitions_cover_every_phase_and_only_name_phases():
    assert set(T.PHASE_TRANSITIONS) == set(T.Phase)
    for targets in T.PHASE_TRANSITIONS.values():
        assert targets and all(isinstance(t, T.Phase) for t in targets)


# ---------------------------------------------------------------------------
# quantities
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0.1, 1e3, True, False, None, object()])
def test_quantity_refuses_float_and_non_numbers(bad):
    with pytest.raises(TypeError):
        Quantity(bad, "EUR", UnitFamily.MONEY)


def test_quantity_is_exact_decimal_from_int_str_or_decimal():
    assert Quantity(3, "heads", UnitFamily.COUNT).value == Decimal(3)
    assert Quantity("0.1", "%", UnitFamily.RATE).value == Decimal("0.1")
    assert Quantity(Decimal("2.50"), "EUR", UnitFamily.MONEY).value == Decimal("2.50")
    with pytest.raises(ValueError):
        Quantity("forty", "heads", UnitFamily.COUNT)
    with pytest.raises(ValueError):
        Quantity(1, "", UnitFamily.COUNT)
    with pytest.raises(TypeError):
        Quantity(1, "EUR", "money")


def test_dimensions_none_means_unknown_never_a_default():
    d = Dimensions(currency="EUR")
    assert d.pinned_for(("currency",)) and not d.pinned_for(("currency", "period"))
    assert d.unpinned() == ("period", "period_basis", "scope", "as_of", "definition")
    assert Dimensions().unpinned() == Dimensions.DIMENSION_NAMES


# ---------------------------------------------------------------------------
# envelope
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("v", [-0.01, 1.01, 2, -1])
def test_confidence_outside_unit_interval_is_refused(v):
    with pytest.raises(ValueError):
        Confidence(v)


def test_confidence_none_is_unknown_and_kept_none():
    assert Confidence(None).value is None
    assert Confidence(0.0).value == 0.0 and Confidence(1.0).value == 1.0
    assert 0.0 < T.UNKNOWN_CONFIDENCE_PRIOR < 1.0


@pytest.mark.parametrize("w", [-0.1, 1.5])
def test_relevance_weight_outside_unit_interval_is_refused(w):
    with pytest.raises(ValueError):
        Relevance("DEC-1", w)


def test_relevance_accepts_unattached_decision():
    assert Relevance(None).decision_id is None and Relevance(None).weight == 0.0


# ---------------------------------------------------------------------------
# payload validation and structural reads
# ---------------------------------------------------------------------------

def test_validate_payload_rejects_a_string_in_an_enum_field():
    p = dataclasses.replace(sample_payload(Kind.FACT), basis="client_stated")
    with pytest.raises(TypeError, match="basis must be FactBasis"):
        validate_payload(Kind.FACT, p)
    p2 = dataclasses.replace(sample_payload(Kind.ACTION), capability_class="process")
    with pytest.raises(TypeError, match="capability_class"):
        validate_payload(Kind.ACTION, p2)


def test_validate_payload_rejects_wrong_dataclass_for_kind():
    with pytest.raises(TypeError, match="FactPayload"):
        validate_payload(Kind.FACT, sample_payload(Kind.RISK))


def test_validate_payload_allows_none_in_optional_enum_field():
    validate_payload(Kind.FACT, dataclasses.replace(sample_payload(Kind.FACT), record_class=None))
    validate_payload(Kind.ISSUE, dataclasses.replace(sample_payload(Kind.ISSUE), capability_class=None))


def test_payload_field_reads_enums_as_values_and_derives_structural_flags():
    fact = sample_payload(Kind.FACT)
    assert payload_field(fact, "basis") == "client_stated"
    assert payload_field(fact, "has_quantity") is True
    assert payload_field(fact, "unit_family") == "count"
    assert payload_field(fact, "has_measure") is True and payload_field(fact, "has_formula") is False
    assert payload_field(sample_payload(Kind.MEASURE), "unit_family") == "count"
    assert payload_field(sample_payload(Kind.OWNER), "has_reports_to") is True
    assert payload_field(sample_payload(Kind.GOVERNANCE), "has_raci") is True
    assert payload_field(sample_payload(Kind.DEADLINE), "has_date") is True
    assert payload_field(sample_payload(Kind.WORKSTREAM), "has_legacy_request") is True
    assert payload_field(sample_payload(Kind.MILESTONE), "has_deadline") is True
    assert payload_field(sample_payload(Kind.CONFLICT), "conflict_kind") == "value"
    assert payload_field(sample_payload(Kind.RISK), "has_quantity") is False
    assert payload_field(sample_payload(Kind.RISK), "nonexistent") is None


# ---------------------------------------------------------------------------
# information type: a function of the kind of information, never the producer
# ---------------------------------------------------------------------------

CLIENT_PREFERENCE_KINDS = {Kind.OBJECTIVE, Kind.SUCCESS_CRITERION, Kind.CONSTRAINT, Kind.DECISION_OWNER,
                           Kind.DEADLINE, Kind.STAKEHOLDER, Kind.BUSINESS_CONTEXT, Kind.MEASURE}
CONSULTANT_KINDS = {Kind.DECISION, Kind.HYPOTHESIS, Kind.ANALYSIS, Kind.OPTION, Kind.EVALUATION_CRITERION,
                    Kind.TRADE_OFF, Kind.RECOMMENDATION, Kind.CAPABILITY, Kind.PROCESS_STEP, Kind.WORKSTREAM,
                    Kind.INITIATIVE, Kind.ACTION, Kind.MILESTONE, Kind.DEPENDENCY, Kind.OWNER, Kind.COST,
                    Kind.BENEFIT, Kind.RISK, Kind.CONTROL, Kind.GOVERNANCE, Kind.EXPECTED_OUTCOME,
                    Kind.ASSUMPTION, Kind.ISSUE, Kind.CONFLICT, Kind.DECISION_REQUIRED}
PROCESS_RECORD_KINDS = {Kind.QUESTION, Kind.WORK_PRODUCT, Kind.EVIDENCE_SOURCE, Kind.STATEMENT,
                        Kind.SPECIALIST_ASSIGNMENT, Kind.CHARTER}


def expected_info_type(kind: Kind) -> InfoType:
    if kind in CLIENT_PREFERENCE_KINDS:
        return InfoType.CLIENT_PREFERENCE
    if kind == Kind.FACT:
        return InfoType.CLIENT_RECOLLECTION          # the sample fact is client_stated
    if kind == Kind.REGULATED_MATTER:
        return InfoType.LICENSED_INTERPRETATION
    if kind in CONSULTANT_KINDS:
        return InfoType.CONSULTANT_JUDGEMENT
    return InfoType.PROCESS_RECORD


def test_the_kind_partition_is_complete():
    assert CLIENT_PREFERENCE_KINDS | CONSULTANT_KINDS | PROCESS_RECORD_KINDS | {Kind.FACT, Kind.REGULATED_MATTER} == set(Kind)


@pytest.mark.parametrize("kind", list(Kind), ids=[k.value for k in Kind])
def test_info_type_of_every_kind(kind):
    assert info_type_of(kind, sample_payload(kind)) == expected_info_type(kind)


@pytest.mark.parametrize("basis,expected", [
    (FactBasis.CLIENT_STATED, InfoType.CLIENT_RECOLLECTION),      # MF2.1: the client's recollection is theirs to confirm
    (FactBasis.DOCUMENT_EXTRACTED, InfoType.CURRENT_STATE_FACT),
    (FactBasis.DOCUMENT_VERIFIED, InfoType.CURRENT_STATE_FACT),
    (FactBasis.INFERRED, InfoType.CURRENT_STATE_FACT),
    (FactBasis.EXTERNAL_SOURCED, InfoType.EXTERNAL_FACT),
    (FactBasis.CALCULATED, InfoType.ARITHMETIC),
])
def test_fact_basis_discriminates_information_type(basis, expected):
    # Mutation "info_type_of returns CURRENT_STATE_FACT for client_stated" is
    # caught by the first row: a client recollection would then be owned by
    # VERIFIED_RECORD and the client could never confirm what they said.
    assert info_type_of(Kind.FACT, sample_payload(Kind.FACT, basis=basis)) == expected


def test_licensed_recommendation_and_material_trade_off_change_owner():
    assert info_type_of(Kind.RECOMMENDATION, sample_payload(Kind.RECOMMENDATION, licensed_interpretation=True)) \
        == InfoType.LICENSED_INTERPRETATION
    assert info_type_of(Kind.RECOMMENDATION, sample_payload(Kind.RECOMMENDATION, licensed_interpretation=False)) \
        == InfoType.CONSULTANT_JUDGEMENT
    assert info_type_of(Kind.TRADE_OFF, sample_payload(Kind.TRADE_OFF, material=True)) == InfoType.MATERIAL_TRADE_OFF
    assert info_type_of(Kind.TRADE_OFF, sample_payload(Kind.TRADE_OFF, material=False)) == InfoType.CONSULTANT_JUDGEMENT


def test_info_type_does_not_depend_on_the_producer():
    for actor in Actor:
        e = sample_entity(Kind.RECOMMENDATION, actor=actor)
        assert e.info_type == InfoType.CONSULTANT_JUDGEMENT and e.authority == Authority.CONSULTANT


# ---------------------------------------------------------------------------
# Entity: I7, hashing, round trip
# ---------------------------------------------------------------------------

def _envelope(**kw):
    base = dict(provenance=Provenance(Actor.PARTNER, "partner:1", ("EVI-1",)), confidence=Confidence(None),
                relevance=Relevance("DEC-1", 0.5), relation=RelationToCentralDecision.INFORMS, status=Status.PROPOSED)
    base.update(kw)
    return base


def test_entity_refuses_a_producer_chosen_authority():
    # I7: a client fact is the client's whoever wrote the row.
    with pytest.raises(ValueError, match="I7"):
        Entity(id="FCT-1", kind=Kind.FACT, engagement_id="E-1", payload=sample_payload(Kind.FACT),
               authority=Authority.CONSULTANT, info_type=InfoType.CLIENT_RECOLLECTION, **_envelope())
    with pytest.raises(ValueError, match="I7"):
        Entity(id="FCT-1", kind=Kind.FACT, engagement_id="E-1", payload=sample_payload(Kind.FACT),
               authority=Authority.CLIENT_STATED, info_type=InfoType.CONSULTANT_JUDGEMENT, **_envelope())
    ok = Entity(id="FCT-1", kind=Kind.FACT, engagement_id="E-1", payload=sample_payload(Kind.FACT),
                authority=Authority.CLIENT_STATED, info_type=InfoType.CLIENT_RECOLLECTION, **_envelope())
    assert ok.authority == Authority.CLIENT_STATED


def test_entity_validates_its_payload_at_construction():
    with pytest.raises(TypeError):
        make_entity(kind=Kind.FACT, engagement_id="E-1", payload=sample_payload(Kind.RISK), **_envelope())


def test_make_entity_derives_authority_for_every_kind():
    from app.engine.authority import AUTHORITY_OF
    for kind in Kind:
        e = sample_entity(kind)
        assert e.info_type == expected_info_type(kind)
        assert e.authority == AUTHORITY_OF[e.info_type]


def test_content_hash_ignores_recorded_at():
    # MF3.7: the same content hashes identically whatever the clock said, or
    # a re-load from the store would never match the release record.
    a = sample_entity(Kind.FACT, recorded_at="2026-01-01T00:00:00+00:00")
    b = sample_entity(Kind.FACT, recorded_at="2031-12-31T23:59:59+00:00")
    c = sample_entity(Kind.FACT, recorded_at="")
    assert a.content_hash() == b.content_hash() == c.content_hash()
    assert len(a.content_hash()) == 64


def test_content_hash_changes_with_content():
    a = sample_entity(Kind.FACT)
    b = sample_entity(Kind.FACT, payload=sample_payload(Kind.FACT, statement="we have 41 people"))
    c = dataclasses.replace(a, status=Status.CONFIRMED)
    assert len({a.content_hash(), b.content_hash(), c.content_hash()}) == 3


@pytest.mark.parametrize("kind", list(Kind), ids=[k.value for k in Kind])
def test_to_json_from_json_round_trips_every_kind(kind):
    e = sample_entity(kind, recorded_at="2026-01-01T00:00:00+00:00", status=Status.PROPOSED)
    e = dataclasses.replace(e, version=3, supersedes=2, confirmed_by="client:turn:4", labels=("a", "b"))
    d = e.to_json()
    text = json.dumps(d, sort_keys=True)              # must be plain JSON: enums as values, Decimal tagged
    back = Entity.from_json(json.loads(text))
    assert back == e
    assert back.content_hash() == e.content_hash()
    assert '"$decimal"' in text or kind not in (Kind.FACT, Kind.COST, Kind.BENEFIT, Kind.TRADE_OFF)


def test_round_trip_preserves_decimal_exactness_and_enum_members():
    e = sample_entity(Kind.TRADE_OFF)
    back = Entity.from_json(json.loads(json.dumps(e.to_json())))
    assert back.payload.scores[0].score == Decimal("3.5") and isinstance(back.payload.scores[0].score, Decimal)
    f = Entity.from_json(json.loads(json.dumps(sample_entity(Kind.FACT).to_json())))
    assert f.payload.basis is FactBasis.CLIENT_STATED
    assert isinstance(f.payload.quantity.value, Decimal) and f.payload.quantity.value == Decimal("40")
    assert f.payload.quantity.dimensions.currency == "EUR" and f.payload.quantity.dimensions.scope is None


def test_with_status_keeps_everything_else():
    e = sample_entity(Kind.OBJECTIVE)
    c = e.with_status(Status.CONFIRMED, "client:turn:2")
    assert c.status == Status.CONFIRMED and c.confirmed_by == "client:turn:2"
    assert dataclasses.replace(c, status=e.status, confirmed_by=e.confirmed_by) == e


def test_finding_as_dict_mirrors_the_integrity_layer_shape():
    d = T.Finding("L2.unsupported_recommendation", "REC-1", "no supports", "add a confirmed fact").as_dict()
    assert d["source"] == "engine.integrity" and d["severity"] == "high" and d["blocks_final"] is True


# ---------------------------------------------------------------------------
# bounds: names frozen here, values in Settings
# ---------------------------------------------------------------------------

def test_every_bound_is_a_setting_and_every_engine_setting_is_a_bound():
    from app.config import Settings, settings
    for name, default in BOUNDS.items():
        assert hasattr(Settings, f"ENGINE_{name}"), name
        assert isinstance(getattr(settings, f"ENGINE_{name}"), type(default)), name
    engine_settings = {n[len("ENGINE_"):] for n in vars(Settings) if n.startswith("ENGINE_")}
    assert engine_settings == set(BOUNDS)
    assert settings.engine_bounds() == {n: getattr(settings, f"ENGINE_{n}") for n in BOUNDS}


def test_bounds_come_in_min_max_pairs_with_min_below_max():
    from app.config import settings
    for lo, hi in (("MIN_QUESTIONS_PER_TURN", "MAX_QUESTIONS_PER_TURN"), ("MIN_WORK_PRODUCTS", "MAX_WORK_PRODUCTS")):
        assert 0 < getattr(settings, f"ENGINE_{lo}") < getattr(settings, f"ENGINE_{hi}")


def test_engine_bounds_read_the_environment(monkeypatch):
    import importlib
    monkeypatch.setenv("ENGINE_MAX_FANOUT", "9")
    monkeypatch.setenv("ENGINE_ASK_FLOOR", "0.2")
    import app.config as cfg
    reloaded = importlib.reload(cfg)
    try:
        assert reloaded.settings.ENGINE_MAX_FANOUT == 9 and reloaded.settings.ENGINE_ASK_FLOOR == 0.2
    finally:
        monkeypatch.delenv("ENGINE_MAX_FANOUT")
        monkeypatch.delenv("ENGINE_ASK_FLOOR")
        importlib.reload(cfg)


# ---------------------------------------------------------------------------
# nothing here can express an engagement type
# ---------------------------------------------------------------------------

def test_no_engagement_type_vocabulary_in_the_contracts():
    import inspect
    import app.engine.authority as A
    src = (inspect.getsource(T) + inspect.getsource(A)).lower()
    for word in ("acquisition", "market_entry", "market entry", "cost_reduction", "cost reduction", "turnaround",
                 "restructuring", "product launch", "nordvik", "vitalis"):
        assert word not in src, word
    assert all(ord(ch) < 128 for ch in inspect.getsource(T) + inspect.getsource(A))
