"""C22 api: app/engine/api/{schemas,router,startup}.py and main.py's wiring.

What is pinned here is the request, not the engine: who the caller is allowed
to be, what happens when two of them arrive at once, what a client may see
while the consultant still holds the package, and the order the process boots
in. Everything the endpoints decide with, they ask the engine.

Pinned mutations (work breakdown C22):
- drop the actor-class check on conflict resolve
      -> test_a_conflict_is_settled_only_by_the_authority_that_owns_it
- drop the stranded sweep
      -> test_the_startup_sweep_fails_an_engagement_a_restart_stranded
- register the sweep on the router instead of after init_db
      -> test_a_fresh_database_boots_with_every_engine_table
- drop the is_working lock
      -> test_a_second_turn_arriving_mid_turn_is_refused

Every model call in this file goes through FakeProvider: no test here knows
what any engagement is about, and none of them spends a cent.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.engine import types as T
from app.engine.types import Actor, Add, Authority, Kind, Provenance, Status, make_entity

EMAIL = "test@example.com"
OPENING = ("We run a clinic with 40 staff and our order cycle takes 12 days, "
           "which is why our fulfilment costs keep climbing.")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_uploads):
    """The whole service, with the one paid seam replaced.

    `main` is imported here rather than at module scope so the ancestor
    conftest's DATABASE_URL guard is already in force when app.config is read.
    """
    import main
    from app.config import settings
    from app.database import init_db
    from app.engine.api import router as R
    from app.engine.llm import FakeProvider

    init_db()
    monkeypatch.setattr(R, "_provider", lambda: FakeProvider())
    # The burst cap is its own test; every other test would otherwise trip it
    # as engagements accumulate in the shared test database.
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", 10_000)
    monkeypatch.setattr(settings, "REVIEW_MODE", "on")
    monkeypatch.setattr(settings, "REVIEW_TOKEN", "review-token-for-tests")
    return TestClient(main.app)


@pytest.fixture
def session():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def open_engagement(client, statement: str = OPENING) -> dict:
    r = client.post("/api/engagements", data={"opening_statement": statement,
                                              "client_name": "The client"})
    assert r.status_code == 201, r.text
    return r.json()


def engagement_row(db, engagement_id):
    from app.engine.persistence.models import Engagement

    return db.query(Engagement).filter(Engagement.public_id == engagement_id).first()


def load_registry(db, engagement_id):
    from app.engine.persistence.store import RegistryStore

    return RegistryStore().load(engagement_id, db)


def save_registry(db, registry):
    from app.engine.persistence.store import RegistryStore

    RegistryStore().save(registry, db)


def add(registry, kind, payload, *, actor=Actor.PARTNER, status=Status.PROPOSED,
        relation=T.RelationToCentralDecision.INFORMS):
    return registry.apply(Add(make_entity(
        kind=kind, engagement_id=registry.engagement_id, payload=payload,
        provenance=Provenance(actor=actor, actor_ref=f"{actor.value}:test"),
        confidence=T.Confidence(None), relevance=T.Relevance(None),
        relation=relation, status=status)))


def plan_products(db, engagement_id):
    """Write the work products the registry's own declarations plan. The
    planner decides which and how many; nothing here fixes a count."""
    from app.config import settings
    from app.engine.work_products.plan import plan_work_products

    registry = load_registry(db, engagement_id)
    plan = plan_work_products(registry, preliminary=False, bounds=settings.engine_bounds())
    registry.apply_all(plan.deltas)
    save_registry(db, registry)
    return [d.entity.payload.product_id for d in plan.deltas]


# ===========================================================================
# 1. Who may knock
# ===========================================================================

def test_an_anonymous_caller_cannot_open_an_engagement(api, monkeypatch):
    from app import auth_client

    monkeypatch.setattr(auth_client, "resolve_user", lambda authorization: None)
    r = api.post("/api/engagements", data={"opening_statement": OPENING})
    assert r.status_code == 401


def test_an_unknown_engagement_is_not_found(api):
    assert api.get("/api/engagements/E-nothing-here").status_code == 404


def test_another_account_may_not_read_the_engagement(api, monkeypatch):
    from app import auth_client

    body = open_engagement(api)
    monkeypatch.setattr(auth_client, "resolve_user",
                        lambda authorization: {"email": "someone@else.com", "name": "Else"})
    r = api.get(f"/api/engagements/{body['id']}")
    assert r.status_code == 403


def test_a_burst_over_the_cap_is_refused(api, monkeypatch, session):
    """The 429 counts engagements that are WORKING, so a rush of intakes
    cannot drain the credit balance before anyone notices (requests.py:190)."""
    from app.config import settings
    from app.engine.persistence.models import Engagement

    body = open_engagement(api)
    row = engagement_row(session, body["id"])
    row.is_working = True
    session.commit()
    in_flight = session.query(Engagement).filter(Engagement.is_working.is_(True)).count()
    monkeypatch.setattr(settings, "MAX_CONCURRENT_GENERATIONS", in_flight)
    try:
        r = api.post("/api/engagements", data={"opening_statement": OPENING})
        assert r.status_code == 429
    finally:
        row.is_working = False
        session.commit()


# ===========================================================================
# 2. The conversation
# ===========================================================================

def test_the_opening_statement_comes_back_as_a_reply_with_questions(api):
    body = open_engagement(api)
    reply = body["reply"]
    assert body["id"].startswith("E-")
    assert reply["phase"] == "discovery"
    assert reply["turn_n"] == 1
    assert reply["questions"], "an opening turn that asks nothing has learned nothing"
    assert all(q["kind"] == "question" for q in reply["questions"])
    assert "live_summary" in reply and "missing" in reply["live_summary"]


def test_the_second_turn_asks_different_questions(api):
    """The turn adapts: what was asked once and answered is not asked again,
    so two consecutive question sets over one engagement cannot be equal."""
    body = open_engagement(api)
    first = [q["payload"]["text"] for q in body["reply"]["questions"]]
    r = api.post(f"/api/engagements/{body['id']}/turns", data={
        "message": "The decision is whether to insource fulfilment, and we must "
                   "decide by 2026-06-30. Dr Carter is the owner.",
    })
    assert r.status_code == 200, r.text
    second = [q["payload"]["text"] for q in r.json()["reply"]["questions"]]
    assert r.json()["reply"]["turn_n"] == 2
    assert first != second


def test_a_second_turn_arriving_mid_turn_is_refused(api, session):
    """MUTATION: drop the is_working lock.

    Two Partner turns over one registry would each load the rows the other is
    about to write, and the loser's work would disappear with nothing saying
    so. The second caller is told, in the only currency that is true: your
    previous message is still being worked on.
    """
    body = open_engagement(api)
    row = engagement_row(session, body["id"])
    row.is_working = True
    session.commit()
    try:
        r = api.post(f"/api/engagements/{body['id']}/turns", data={"message": "and another thing"})
        assert r.status_code == 409
        assert "already working" in r.json()["detail"]
    finally:
        row.is_working = False
        session.commit()


def test_a_turn_is_released_from_the_lock_when_it_finishes(api, session):
    body = open_engagement(api)
    row = engagement_row(session, body["id"])
    session.refresh(row)
    assert row.is_working is False
    assert row.status == "idle"


# ===========================================================================
# 3. The charter starts the analysis
# ===========================================================================

def test_confirming_the_charter_starts_the_analysis(api, session, monkeypatch):
    from app.engine.api import router as R
    from app.engine.partner import charter as C

    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    proposal = C.propose(registry, turn_number=1)
    save_registry(session, registry)
    row = engagement_row(session, eid)
    row.charter_id = proposal.charter.id
    row.phase = "charter_proposed"
    session.commit()

    started: list[str] = []
    monkeypatch.setattr(R, "_start_analysis", lambda e: started.append(e))
    r = api.post(f"/api/engagements/{eid}/charter/confirm",
                 json={"charter_id": proposal.charter.id, "items": []})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["approved"] is True
    assert out["analysis_started"] is True
    assert out["phase"] == "charter_confirmed"
    assert started == [eid]

    # The lock passed to the analysis thread rather than being dropped: the
    # engagement is one continuous piece of work from the client's side.
    session.refresh(row)
    assert row.is_working is True
    row.is_working = False
    session.commit()


def test_a_correction_without_the_clients_words_is_refused(api, session):
    from app.engine.partner import charter as C

    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    proposal = C.propose(registry, turn_number=1)
    save_registry(session, registry)
    listed = proposal.items[0].entity_id if proposal.items else "OBJ-1"
    r = api.post(f"/api/engagements/{eid}/charter/confirm", json={
        "charter_id": proposal.charter.id,
        "items": [{"entity_id": listed, "verdict": "correct"}],
    })
    assert r.status_code == 422


# ===========================================================================
# 4. Resolution: the credential decides, the body only asks   [MUTATION]
# ===========================================================================

def _conflict_owned_by(registry, authority: Authority):
    """One CONFLICT whose payload names the authority that must settle it.
    The conclusions are ids nobody wrote: resolve() skips a loser it cannot
    find, so this pins the AUTHORITY rule without inventing evidence."""
    return add(registry, Kind.CONFLICT, T.ConflictPayload(
        kind=T.ConflictKind.VALUE, subject_id="MEA-1",
        conclusions=(T.ConflictConclusion("FCT-90", "40"), T.ConflictConclusion("FCT-91", "45")),
        relation_to_central_decision=T.RelationToCentralDecision.DEFINES,
        authority_required=authority, material=True,
        recommended_resolution="FCT-91",
        recommendation_basis="CURRENT_STATE_PRECEDENCE"), status=Status.OPEN)


def test_a_conflict_is_settled_only_by_the_authority_that_owns_it(api, session):
    """MUTATION: drop the actor-class check on conflict resolve.

    The engagement's decision owner owns a material trade-off; the client,
    signed in, does not. Without the check the registry would still refuse the
    write, but the caller would be told 409 ("that did not apply") instead of
    403 ("that is not yours to settle") - and a client would read a
    consultant's mistake as a system fault.
    """
    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    owner = add(registry, Kind.DECISION_OWNER,
                T.DecisionOwnerPayload(name="Dr Carter", role="managing director"))
    conflict = _conflict_owned_by(registry, Authority.DECISION_OWNER)
    save_registry(session, registry)

    signed_in = api.post(f"/api/engagements/{eid}/conflicts/{conflict.id}/resolve",
                         json={"chosen_entity_id": "FCT-91", "rationale": "the record wins"})
    assert signed_in.status_code == 403

    delegated = api.post(f"/api/engagements/{eid}/conflicts/{conflict.id}/resolve", json={
        "chosen_entity_id": "FCT-91", "rationale": "the record wins",
        "acting_as": "decision_owner", "on_behalf_of": owner.id,
    })
    assert delegated.status_code == 200, delegated.text
    out = delegated.json()
    assert out["on_behalf_of"] == owner.id
    # Delegation is a recorded fact, not an assumption (design 5.3): the
    # DECISION_OWNER id is in the provenance the registry stored.
    assert owner.id in out["conflict"]["provenance"]["actor_ref"]
    assert out["conflict"]["status"] == "resolved"

    stored = load_registry(session, eid).get(conflict.id)
    assert stored.status is Status.RESOLVED
    assert owner.id in stored.provenance.actor_ref


def test_a_claimed_delegation_names_the_row_it_acts_for(api, session):
    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    conflict = _conflict_owned_by(registry, Authority.DECISION_OWNER)
    save_registry(session, registry)
    r = api.post(f"/api/engagements/{eid}/conflicts/{conflict.id}/resolve", json={
        "chosen_entity_id": "FCT-91", "rationale": "because", "acting_as": "decision_owner",
    })
    assert r.status_code == 403


def test_a_qualified_professional_claim_needs_the_reviewer_credential(api, session):
    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    conflict = _conflict_owned_by(registry, Authority.CLIENT)
    save_registry(session, registry)
    r = api.post(f"/api/engagements/{eid}/conflicts/{conflict.id}/resolve", json={
        "chosen_entity_id": "FCT-91", "rationale": "because",
        "acting_as": "qualified_professional", "adviser": "A. Adviser",
    })
    assert r.status_code == 403


def test_an_assumption_is_approved_by_the_client_and_by_nobody_else(api, session):
    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    assumption = add(registry, Kind.ASSUMPTION,
                     T.AssumptionPayload(statement="volumes hold flat", rationale="stated"))
    save_registry(session, registry)

    reviewer = api.post(
        f"/api/engagements/{eid}/assumptions/{assumption.id}/approve",
        params={"review_token": "review-token-for-tests"},
        json={"acting_as": "qualified_professional", "adviser": "A. Adviser"})
    assert reviewer.status_code == 403

    client = api.post(f"/api/engagements/{eid}/assumptions/{assumption.id}/approve",
                      json={"rationale": "we accept it"})
    assert client.status_code == 200, client.text
    assert client.json()["assumption"]["status"] == "approved"
    assert any(lbl.startswith("rationale:")
               for lbl in client.json()["assumption"]["labels"])


# ===========================================================================
# 5. Exports: withheld, stamped, cached
# ===========================================================================

def test_an_export_is_withheld_while_the_review_gate_holds_it(api, session, monkeypatch):
    from app.config import settings

    body = open_engagement(api)
    eid = body["id"]
    products = plan_products(session, eid)
    assert products, "the mandatory declarations always plan something"

    monkeypatch.setattr(settings, "REVIEW_MODE", "gate")
    held = api.get(f"/api/engagements/{eid}/work-products/{products[0]}/export/pdf")
    assert held.status_code == 403

    # The reviewer's own credential lifts it, for the reviewer only.
    seen = api.get(f"/api/engagements/{eid}/work-products/{products[0]}/export/pdf",
                   params={"review_token": "review-token-for-tests"})
    assert seen.status_code == 200


def test_an_export_is_draft_stamped_until_a_release_says_final(api, session):
    from app.engine.persistence.models import EngagementArtifact, EngagementRelease
    from app.engine.work_products.render_pdf import DRAFT_STAMP, extract_text

    body = open_engagement(api)
    eid = body["id"]
    product = plan_products(session, eid)[0]

    first = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pdf")
    assert first.status_code == 200
    assert first.headers["x-engine-draft"] == "true"
    drafted = (session.query(EngagementArtifact)
               .filter(EngagementArtifact.engagement_id == eid).order_by(
                   EngagementArtifact.id.desc()).first())
    assert DRAFT_STAMP in extract_text(drafted.path)

    session.add(EngagementRelease(engagement_id=eid, revision=1, record_json="{}", status="final"))
    session.commit()

    released = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pdf")
    assert released.status_code == 200
    assert released.headers["x-engine-draft"] == "false"
    final = (session.query(EngagementArtifact)
             .filter(EngagementArtifact.engagement_id == eid).order_by(
                 EngagementArtifact.id.desc()).first())
    assert final.path != drafted.path
    assert DRAFT_STAMP not in extract_text(final.path)


def test_an_export_is_rebuilt_only_when_the_registry_moved(api, session):
    body = open_engagement(api)
    eid = body["id"]
    product = plan_products(session, eid)[0]

    first = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pdf")
    assert first.headers["x-engine-cache"] == "miss"
    again = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pdf")
    assert again.headers["x-engine-cache"] == "hit"
    assert again.headers["x-engine-sha256"] == first.headers["x-engine-sha256"]

    # One more row, and the artifact no longer describes the registry.
    registry = load_registry(session, eid)
    add(registry, Kind.RISK, T.RiskPayload(text="a new risk", likelihood="medium",
                                           impact="high"))
    save_registry(session, registry)
    moved = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pdf")
    assert moved.headers["x-engine-cache"] == "miss"


def test_an_unplanned_product_and_an_unknown_format_are_not_found(api, session):
    body = open_engagement(api)
    eid = body["id"]
    product = plan_products(session, eid)[0]
    assert api.get(f"/api/engagements/{eid}/work-products/no_such/export/pdf").status_code == 404
    assert api.get(f"/api/engagements/{eid}/work-products/{product}/export/xlsx").status_code == 404


# ===========================================================================
# 6. Reads
# ===========================================================================

def test_the_progress_shape(api):
    body = open_engagement(api)
    r = api.get(f"/api/engagements/{body['id']}/progress")
    assert r.status_code == 200
    out = r.json()
    assert set(out) == {"review_status", "client_name", "title", "phase", "stage", "label",
                        "pct", "detail", "is_working", "is_failed", "status", "updated_at",
                        "elapsed_s"}
    assert out["is_working"] is False
    assert out["elapsed_s"] >= 0


def test_the_registry_read_only_speaks_the_closed_vocabulary(api):
    body = open_engagement(api)
    eid = body["id"]
    ok = api.get(f"/api/engagements/{eid}/registry", params={"kind": "question"})
    assert ok.status_code == 200
    assert ok.json()["total"] >= 1
    assert all(e["kind"] == "question" for e in ok.json()["entities"])
    # An unknown word is a refusal, never an empty list that reads as "none".
    assert api.get(f"/api/engagements/{eid}/registry",
                   params={"kind": "vibes"}).status_code == 422


def test_lineage_returns_every_version_of_one_row(api, session):
    body = open_engagement(api)
    eid = body["id"]
    registry = load_registry(session, eid)
    assumption = add(registry, Kind.ASSUMPTION, T.AssumptionPayload(statement="a", rationale="r"))
    save_registry(session, registry)
    api.post(f"/api/engagements/{eid}/assumptions/{assumption.id}/approve", json={})
    r = api.get(f"/api/engagements/{eid}/entities/{assumption.id}/lineage")
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[-1]["status"] == "approved"
    assert api.get(f"/api/engagements/{eid}/entities/NOPE-9/lineage").status_code == 404


def test_turns_and_mine_read_back_what_was_written(api):
    body = open_engagement(api)
    turns = api.get(f"/api/engagements/{body['id']}/turns").json()["turns"]
    assert [t["role"] for t in turns] == ["client", "partner"]
    assert turns[0]["text"] == OPENING
    assert json.loads(turns[1]["text"])["turn_n"] == 1

    mine = api.get("/api/engagements/mine")
    assert mine.status_code == 200
    assert body["id"] in [e["public_id"] for e in mine.json()["engagements"]]


# ===========================================================================
# 7. The reviewer
# ===========================================================================

def test_the_review_queue_and_approval_need_the_reviewer_credential(api, session, monkeypatch):
    from app import mailer

    body = open_engagement(api)
    eid = body["id"]
    products = plan_products(session, eid)
    assert api.get("/api/engagements/review-queue").status_code == 403
    assert api.post(f"/api/engagements/{eid}/review/approve").status_code == 403

    queue = api.get("/api/engagements/review-queue",
                    params={"review_token": "review-token-for-tests"})
    assert queue.status_code == 200
    assert eid in [e["public_id"] for e in queue.json()["pending"]]

    sent: list[tuple] = []
    monkeypatch.setattr(mailer, "send_async", lambda to, subject, bodytext: sent.append((to, subject, bodytext)))
    approved = api.post(f"/api/engagements/{eid}/review/approve",
                        params={"review_token": "review-token-for-tests"})
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"
    # The mail names the products this engagement planned, never a fixed list
    # of volumes: a different engagement gets a different letter.
    deliverables = approved.json()["deliverables"]
    assert deliverables and len(deliverables) == len(products)
    assert sent and sent[0][0] == EMAIL
    assert all(d in sent[0][2] for d in deliverables)


def test_a_release_with_nothing_exported_is_refused(api, session):
    body = open_engagement(api)
    plan_products(session, body["id"])
    r = api.post(f"/api/engagements/{body['id']}/release",
                 params={"review_token": "review-token-for-tests"})
    assert r.status_code == 409
    assert "no artifact" in r.json()["detail"]


# ===========================================================================
# 8. Startup: the sweep, and the order it runs in   [MUTATION x2]
# ===========================================================================

def test_the_startup_sweep_fails_an_engagement_a_restart_stranded(api, session):
    """MUTATION: drop the stranded sweep.

    Analysis runs on a daemon thread; a restart kills it silently. Without the
    sweep the engagement says "working" forever and the client watches a
    spinner that will never stop.
    """
    from app.engine.api.startup import STRANDED_LABEL, engine_startup

    body = open_engagement(api)
    row = engagement_row(session, body["id"])
    row.is_working = True
    row.status = "working"
    session.commit()

    engine_startup()

    session.expire_all()
    row = engagement_row(session, body["id"])
    assert row.is_working is False
    assert row.status == "failed"
    assert row.is_failed is True
    assert row.stage_label == STRANDED_LABEL


def test_a_fresh_database_boots_with_every_engine_table(tmp_path, monkeypatch):
    """MUTATION: register the sweep on the router / call it before init_db.

    A router startup handler runs BEFORE the handler main.py registers after
    it, so the sweep would query `engagements` on a database create_all has
    not reached yet - a crash on the very first boot and only on the first
    boot (MF3.2). Nothing is faked here: this is main's own on_startup, run
    against a database that has never existed.
    """
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    import app.database as database
    import main
    from app.engine.persistence.models import ENGINE_TABLES

    fresh = create_engine("sqlite:///" + str(tmp_path / "fresh.db"),
                          connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", fresh)
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(autocommit=False, autoflush=False, bind=fresh))

    main.on_startup()

    names = set(inspect(fresh).get_table_names())
    assert set(ENGINE_TABLES) <= names, f"missing {set(ENGINE_TABLES) - names}"
    assert "requests" in names, "the r30 tables are created by the same init_db"


def test_the_r30_surface_still_answers_with_the_engine_mounted(api):
    """The engine is additive: r30's own routes are untouched and still
    served from the same application (design 13.4)."""
    assert api.get("/health").json() == {"ok": True}
    assert api.get("/api/requests/mine").status_code == 200
    paths = {r.path for r in __import__("main").app.routes if hasattr(r, "path")}
    assert "/api/requests/{request_ref}/progress" in paths
    assert "/api/engagements/{ref}/progress" in paths


# ===========================================================================
# 9. Answers, and the documents a turn carries
# ===========================================================================

def test_an_answer_closes_its_question_once(api, session):
    body = open_engagement(api)
    eid, question_id = body["id"], body["reply"]["questions"][0]["id"]
    first = api.post(f"/api/engagements/{eid}/answers", json={
        "answers": [{"question_id": question_id,
                     "text": "The decision is whether to insource fulfilment."}]})
    assert first.status_code == 200, first.text
    assert first.json()["closed_questions"] == [question_id]
    assert load_registry(session, eid).get(question_id).status is Status.RESOLVED

    # A second answer to a closed question writes no second resolution: the
    # history must not say the client answered it twice.
    again = api.post(f"/api/engagements/{eid}/answers", json={
        "answers": [{"question_id": question_id, "text": "same again"}]})
    assert again.json()["closed_questions"] == []


def test_i_do_not_know_is_recorded_on_the_question(api, session):
    """Design 6.5: "don't know" is an answer. It has to land on the QUESTION
    payload, because that is where the gap scorer reads it - a note anywhere
    else and the client is asked the same thing again next turn."""
    body = open_engagement(api)
    eid, question_id = body["id"], body["reply"]["questions"][0]["id"]
    r = api.post(f"/api/engagements/{eid}/answers", json={
        "answers": [{"question_id": question_id, "unknown": True}]})
    assert r.status_code == 200, r.text
    stored = load_registry(session, eid).get(question_id)
    assert stored.payload.unknown is True
    assert stored.status is Status.RESOLVED


def test_an_uploaded_document_keeps_its_text_against_its_evidence_source(api, session):
    """I2 re-checks a document-verified locator against the hashed text on
    every load. A document whose text was not stored would quietly turn its
    verified facts into unverifiable ones the next time the registry is
    rebuilt from rows."""
    from app.engine.persistence.models import EngagementDocument

    body = open_engagement(api)
    eid = body["id"]
    r = api.post(f"/api/engagements/{eid}/turns",
                 data={"message": "here is the cost ledger"},
                 files={"files": ("ledger.csv", b"item,cost\nfuel,1200\n", "text/csv")})
    assert r.status_code == 200, r.text
    doc = (session.query(EngagementDocument)
           .filter(EngagementDocument.engagement_id == eid).one())
    assert doc.filename == "ledger.csv"
    assert doc.source_entity_id
    assert "fuel,1200" in (doc.extracted_text or "")
    assert load_registry(session, eid).source_text(doc.source_entity_id) == doc.extracted_text


def test_every_declared_format_is_served_or_honestly_refused(api, session):
    body = open_engagement(api)
    eid = body["id"]
    product = plan_products(session, eid)[0]
    md = api.get(f"/api/engagements/{eid}/work-products/{product}/export/md")
    assert md.status_code == 200 and md.content.startswith(b"# ")
    deck = api.get(f"/api/engagements/{eid}/work-products/{product}/export/pptx")
    assert deck.status_code == 200 and deck.content[:2] == b"PK"
    # csv is a table dump: a product with no tabular section has no csv, and
    # says so rather than serving an empty file.
    csv = api.get(f"/api/engagements/{eid}/work-products/{product}/export/csv")
    assert csv.status_code in (200, 404)
    if csv.status_code == 404:
        assert "tabular" in csv.json()["detail"]
