"""/api/engagements - the one surface the client and the reviewer touch
(design 16.2).

The endpoints are thin. Everything that decides anything lives in the engine
modules they call, and the only laws stated HERE are the ones that belong to
a request rather than to a registry:

A1  the actor class comes from the CREDENTIAL, never from the body. A caller
    is Actor.CLIENT because they signed in as the owner; DECISION_OWNER only
    when they name a recorded DECISION_OWNER row to act for (the id lands in
    `Provenance.actor_ref`, so delegation is a recorded fact - design 5.3);
    QUALIFIED_PROFESSIONAL only with the reviewer token AND an adviser
    identity. Then `may_advance` decides, and a class the table refuses is a
    403 - not a 500 out of the registry, and never a silent downgrade.
A2  one turn at a time per engagement. `is_working` is claimed before a turn
    and released after it, and a second turn arriving mid-flight is a 409:
    two Partner turns over one registry would each load the rows the other
    was about to write, and the loser's would vanish with nothing saying so.
    The same flag, counted across engagements, is the 429 burst cap that
    keeps an unauthenticated rush from draining the credit balance.
A3  a deliverable is withheld while the review gate holds it (403 through
    r30's own `_pending_for`), and is stamped DRAFT until a release record
    says FINAL. The stamp is a fact about the artifact, so it is baked into
    the file and it is part of the file's cache key.
A4  an export is rebuilt when, and only when, the registry moved. The
    artifact row carries the registry hash it was rendered FROM, so
    staleness is a comparison and never a guess (design 11.4/16.1).

The view rules are r30's, imported rather than re-implemented
(`requests._is_reviewer` / `_pending_for`, app/routers/requests.py:72/:80):
one definition of "may this caller see this", for both products.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from dataclasses import replace
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import auth_client, mailer
from app.config import settings
from app.database import get_db
from app.engine.api import schemas
from app.engine.authority import may_advance
from app.engine.calc.arith import DecimalCalculator
from app.engine.gates import release as release_mod
from app.engine.gates.laws import ArtifactRef, run_laws
from app.engine.llm import OpenRouterProvider
from app.engine.partner.charter import VERDICTS
from app.engine.partner.loop import Partner
from app.engine.partner.state import EngagementState
from app.engine.persistence import store as store_mod
from app.engine.persistence.models import (
    Engagement, EngagementArtifact, EngagementDocument, EngagementRelease, EngagementTurn,
)
from app.engine.persistence.store import RegistryStore, emit_engine
from app.engine.synthesis.resolve import ResolutionRefused
from app.engine.synthesis.resolve import resolve as resolve_conflict
from app.engine.types import (
    Actor, Kind, Phase, Provenance, RegistryError, SetStatus, Status, Supersede,
    TERMINAL_STATUSES, make_entity,
)
from app.engine.work_products import render_csv, render_deck, render_md, render_pdf
from app.engine.work_products.decl import WORK_PRODUCTS
from app.engine.work_products.integrity_record import ArtifactReport, build_integrity_record
from app.engine.work_products.plan import plan_work_products
from app.routers import requests as r30_requests

# Registration by import: METHODS is populated by importing the builtin
# package, and the API is the process's entry point into the engine. Without
# this the selector would find an empty library and every engagement would
# truthfully report that no method applies.
import app.engine.methods.builtin  # noqa: F401,E402  -- method registration

logger = logging.getLogger("consultant.engine.api")

router = APIRouter(prefix="/api/engagements", tags=["engagements"])

# The formats a work product can be asked for. csv is a table dump, so a
# product with no tabular section has no csv artifact and says so (404)
# rather than serving an empty file.
FORMATS: Mapping[str, str] = {"pdf": "pdf", "md": "md", "pptx": "pptx", "csv": "csv"}

# One page of the registry read. A cursor, not a per-engagement count: the
# number of entities an engagement holds is never fixed (BOUNDS govern what
# the engine PRODUCES), and this only bounds one HTTP response.
PAGE_DEFAULT = 200
PAGE_MAX = 1000


# ---------------------------------------------------------------------------
# Seams: everything a test replaces, in one place
# ---------------------------------------------------------------------------

def _provider():
    """The one path to a paid model (design 15). Replaced by a FakeProvider in
    tests; nothing else in this module constructs a provider."""
    return OpenRouterProvider(record_call=store_mod.record_model_call)


def _partner() -> Partner:
    return Partner(_provider())


def _store() -> RegistryStore:
    return RegistryStore()


# ---------------------------------------------------------------------------
# Loading, viewing, locking
# ---------------------------------------------------------------------------

def _load(ref: str, db: Session) -> Engagement:
    row = db.query(Engagement).filter(Engagement.public_id == ref).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return row


def _require_view(row: Engagement, review_token: str | None, authorization: str | None) -> None:
    """r30's rule, on an engagement: the reviewer sees everything, an
    unowned row is public, and otherwise the signed-in owner and nobody
    else. Fail-closed - an unreachable auth backend is 'not signed in'."""
    if r30_requests._is_reviewer(review_token):
        return
    if not row.owner_email:
        return
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to view your engagement")
    if user["email"].lower() != row.owner_email.lower():
        raise HTTPException(status_code=403, detail="This engagement belongs to another account")


def _require_owner(authorization: str | None) -> dict:
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to start an engagement")
    return user


def _claim(db: Session, row: Engagement, *, stage: str, label: str, pct: int) -> None:
    """A2. Take the engagement's working lock or refuse the request.

    409, not a queue: the caller is told their previous turn is still being
    thought about, which is true and actionable. A silent second turn would
    load the same registry rows the running one is about to write.
    """
    if row.is_working:
        raise HTTPException(
            status_code=409,
            detail="This engagement is already working on the previous message.",
        )
    row.is_working = True
    row.is_failed = False
    row.status = "working"
    row.stage = stage
    row.stage_label = label
    row.progress_pct = pct
    row.updated_at = datetime.utcnow()
    db.commit()


def _release_lock(db: Session, row: Engagement, *, status: str = "idle",
                  stage: str = "idle", label: str = "Waiting for you", pct: int = 100,
                  failed: bool = False, detail: str | None = None) -> None:
    row.is_working = False
    row.is_failed = failed
    row.status = status
    row.stage = stage
    row.stage_label = label[:200]
    row.progress_pct = pct
    row.progress_detail = detail
    row.updated_at = datetime.utcnow()
    db.commit()


def _client_turns(db: Session, engagement_id: str) -> int:
    return (db.query(EngagementTurn)
            .filter(EngagementTurn.engagement_id == engagement_id,
                    EngagementTurn.role == "client")
            .count())


def _state(db: Session, row: Engagement, store: RegistryStore) -> EngagementState:
    """The whole state, rebuilt from rows on every request (design 6.1). The
    phase pointer is stored because it is a pointer; everything it points at
    is a row."""
    registry = store.load(row.public_id, db)
    return EngagementState(registry=registry, phase=Phase(row.phase or Phase.OPENING.value),
                           turn_n=_client_turns(db, row.public_id))


def _bindings(db: Session, row: Engagement) -> dict:
    """This request's per-call bindings for the methods that may run: the r30
    commissioning callable bound to THIS session, and the two strings that are
    not claims about the business (design 13.2). A method never opens a
    session of its own, so the thread that owns one hands it over here."""
    from app.engine.legacy.r30_adapter import run_technology_blueprint
    from app.engine.methods.builtin.legacy_r30_technology_blueprint import (
        BUSINESS_NAME_KEY, COMMISSION_KEY, OWNER_EMAIL_KEY,
    )

    def commission(inputs):
        outputs = run_technology_blueprint(db, inputs)
        _record_legacy_request(db, row, outputs.request_id)
        return outputs

    return {
        COMMISSION_KEY: commission,
        BUSINESS_NAME_KEY: row.client_name or row.title or "",
        OWNER_EMAIL_KEY: row.owner_email or "",
    }


def _record_legacy_request(db: Session, row: Engagement, request_id: int) -> None:
    """The r30 Request ids this engagement commissioned, as a JSON list. The
    frozen `requests` table gains no column and no foreign key (design 16.1);
    the pointer lives on this side."""
    try:
        ids = json.loads(row.legacy_request_ids_json) if row.legacy_request_ids_json else []
    except (TypeError, ValueError):
        ids = []
    if request_id not in ids:
        ids.append(request_id)
        row.legacy_request_ids_json = json.dumps(ids)
        db.commit()


# ---------------------------------------------------------------------------
# A1: who the caller is allowed to be
# ---------------------------------------------------------------------------

def _caller_actor(claim: schemas.ActorClaim, *, row: Engagement, review_token: str | None,
                  authorization: str | None, turn_n: int) -> tuple[Actor, str, str | None]:
    """(actor, actor_ref, on_behalf_of). A1.

    The body ASKS; the credential DECIDES. A caller who has only signed in is
    the client, whatever the body says, and a claim the credential does not
    support is refused rather than quietly downgraded - a downgrade would
    write a resolution under the wrong authority and look deliberate.
    """
    if claim.acting_as == "qualified_professional":
        # I4: a licensed interpretation is never confirmed by the engine. The
        # adviser is a person, and their identity is what the record carries.
        if not r30_requests._is_reviewer(review_token):
            raise HTTPException(status_code=403,
                                detail="A qualified professional acts with the reviewer credential")
        adviser = (claim.adviser or "").strip()
        if not adviser:
            raise HTTPException(status_code=403,
                                detail="A qualified professional's identity is recorded with their decision")
        return Actor.QUALIFIED_PROFESSIONAL, f"adviser:{adviser}"[:200], None

    user = auth_client.resolve_user(authorization)
    if user is None and not r30_requests._is_reviewer(review_token):
        raise HTTPException(status_code=401, detail="Sign in to act on your engagement")

    if claim.acting_as == "decision_owner":
        # Delegation is recorded, never assumed (design 5.3): the body names
        # the DECISION_OWNER row it acts for, and resolve() checks that the
        # row exists before it writes anything.
        if not claim.on_behalf_of:
            raise HTTPException(status_code=403,
                                detail="A decision owner acts on behalf of a recorded DECISION_OWNER")
        return Actor.DECISION_OWNER, f"client:turn:{turn_n} as {claim.on_behalf_of}", claim.on_behalf_of

    return Actor.CLIENT, f"client:turn:{turn_n}", None


def _require_authorised(entity, status: Status, actor: Actor) -> None:
    """A1's teeth. `may_advance` is the authority table (design 5.3); this is
    the only place the API asks it, and it asks BEFORE anything is written so
    the answer is a 403 rather than an I1 error surfacing as a 500."""
    if not may_advance(entity, status, actor):
        raise HTTPException(
            status_code=403,
            detail=(f"{actor.value} may not set {entity.kind.value} {entity.id} "
                    f"to {status.value}"),
        )


# ---------------------------------------------------------------------------
# Intake and turns
# ---------------------------------------------------------------------------

async def _attachments(files: Sequence[UploadFile] | None) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for f in files or []:
        if not f or not f.filename:
            continue
        out.append((f.filename, await f.read()))
    return out


def _persist_turn(db: Session, engagement_id: str, *, n: int, role: str, text: str,
                  source_entity_id: str | None = None,
                  attachments: Sequence[str] = ()) -> None:
    db.add(EngagementTurn(engagement_id=engagement_id, n=n, role=role, text=text,
                          source_entity_id=source_entity_id,
                          attachments_json=json.dumps(list(attachments)) if attachments else None))
    db.commit()


def _persist_documents(db: Session, store: RegistryStore, engagement_id: str,
                       registry, attachments: Sequence[tuple[str, bytes]]) -> None:
    """Store each attachment's bytes and extracted text against the
    EVIDENCE_SOURCE the ingest minted for it. The text is what a
    document-verified locator is checked against on every later load (I2), so
    an unstored text would quietly turn verified facts into unverifiable ones
    the next time the registry is rebuilt."""
    import hashlib

    by_sha: dict[str, str] = {}
    for src in registry.query(Kind.EVIDENCE_SOURCE):
        sha = getattr(src.payload, "sha256", None)
        if sha:
            by_sha.setdefault(sha, src.id)
    for name, data in attachments:
        sha = hashlib.sha256(data).hexdigest()
        source_id = by_sha.get(sha)
        existing = (db.query(EngagementDocument)
                    .filter(EngagementDocument.engagement_id == engagement_id,
                            EngagementDocument.sha256 == sha).first())
        if existing is not None:
            continue
        store.store_document(engagement_id, name, data,
                             extracted_text=registry.source_text(source_id) if source_id else None,
                             source_entity_id=source_id, db=db)


def _run_turn(db: Session, row: Engagement, message: str,
              attachments: Sequence[tuple[str, bytes]]) -> dict:
    """One Partner turn, under the working lock, persisted as one batch."""
    store = _store()
    _claim(db, row, stage="thinking", label="Reading what you sent", pct=10)
    try:
        state = _state(db, row, store)
        reply = _partner().turn(state, message, tuple(attachments),
                                context_settings=_bindings(db, row))
        store.save(state.registry, db)
        _persist_turn(db, row.public_id, n=reply.turn_n, role="client", text=message,
                      source_entity_id=reply.turn_id,
                      attachments=[n for n, _ in attachments])
        _persist_documents(db, store, row.public_id, state.registry, attachments)
        row.phase = state.phase.value
        central = state.registry.central_decision()
        row.central_decision_id = central.id if central is not None else None
        if reply.charter is not None:
            row.charter_id = reply.charter.charter.id
        body = schemas.reply_out(reply)
        _persist_turn(db, row.public_id, n=reply.turn_n, role="partner",
                      text=json.dumps(body, default=str))
        return body
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("engagement %s turn failed", row.public_id)
        _release_lock(db, row, status="failed", stage="failed",
                      label=f"The turn failed: {exc}", failed=True)
        raise HTTPException(status_code=500, detail="The engagement could not process that message")
    finally:
        if row.is_working:
            _release_lock(db, row, stage="waiting", label="Waiting for you")


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_engagement(
    opening_statement: str = Form(...),
    client_name: str | None = Form(None),
    title: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The opening statement becomes the first turn; the reply carries the
    engine's questions. 401 anonymous, 429 over the burst cap."""
    user = _require_owner(authorization)
    in_flight = db.query(Engagement).filter(Engagement.is_working.is_(True)).count()
    if in_flight >= settings.MAX_CONCURRENT_GENERATIONS:
        raise HTTPException(
            status_code=429,
            detail="A lot of engagements are running right now - please try again in a few minutes.",
        )
    statement = (opening_statement or "").strip()
    if not statement:
        raise HTTPException(status_code=422, detail="An engagement opens with what the client said")

    row = Engagement(
        public_id="E-" + secrets.token_urlsafe(9),
        owner_email=user["email"],
        client_name=(client_name or "").strip()[:200] or None,
        title=(title or "").strip()[:300] or None,
        phase=Phase.OPENING.value,
        status="idle",
        is_working=False,
        stage="queued",
        stage_label="Queued",
        progress_pct=0,
        # The consultant signs before the client is handed the package; the
        # gate only bites when REVIEW_MODE is "gate" (r30's `_pending_for`).
        review_status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    reply = _run_turn(db, row, statement, await _attachments(files))
    return {"id": row.public_id, "public_id": row.public_id, "reply": reply}


@router.get("/mine")
def my_engagements(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    user = auth_client.resolve_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to see your engagements")
    rows = (db.query(Engagement)
            .filter(Engagement.owner_email == user["email"])
            .order_by(Engagement.id.desc()).limit(50).all())
    return {"engagements": [schemas.card_out(r) for r in rows]}


@router.get("/review-queue")
def review_queue(review_token: str | None = None, db: Session = Depends(get_db)):
    if not r30_requests._is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    rows = (db.query(Engagement)
            .filter(Engagement.review_status == "pending")
            .order_by(Engagement.id.desc()).all())
    return {"pending": [schemas.card_out(r) for r in rows]}


@router.post("/{ref}/turns")
async def post_turn(
    ref: str,
    message: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    review_token: str | None = None,
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    attachments = await _attachments(files)
    if not (message or "").strip() and not attachments:
        raise HTTPException(status_code=422, detail="A turn carries a message or a document")
    return {"reply": _run_turn(db, row, message, attachments)}


@router.post("/{ref}/answers")
def post_answers(ref: str, body: schemas.AnswersRequest,
                 review_token: str | None = None,
                 authorization: str | None = Header(None),
                 db: Session = Depends(get_db)):
    """The client's answers to open questions. Each answer is a turn (so the
    facts it carries cite the turn they were said in, I2) and each answered
    question is closed by the CLIENT - including "I do not know", which is an
    answer and stops the question being asked again (design 6.5)."""
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    if not body.answers:
        raise HTTPException(status_code=422, detail="An answer batch carries at least one answer")

    message = "\n".join(a.text.strip() for a in body.answers if a.text.strip())
    reply = _run_turn(db, row, message or "I do not know.", ())

    store = _store()
    registry = store.load(row.public_id, db)
    closed: list[str] = []
    for answer in body.answers:
        q = registry.get(answer.question_id)
        if q is None or q.kind is not Kind.QUESTION:
            continue
        if q.status in TERMINAL_STATUSES or q.status is Status.RESOLVED:
            # Already answered. Closing it twice would write a second
            # resolution over the same question and make the history say the
            # client answered it twice.
            continue
        _require_authorised(q, Status.RESOLVED, Actor.CLIENT)
        by = Provenance(actor=Actor.CLIENT, actor_ref=f"client:turn:{reply['turn_n']}",
                        derived_from=(reply["turn_id"],) if reply["turn_id"] else ())
        try:
            if answer.unknown and q.payload.unknown is not True:
                # The flag goes ON the question, because that is where the gap
                # scorer reads it (`questions._unknown_gap_ids`, checked with
                # `is True`). A label would record the answer somewhere the
                # engine does not look, and the question would be asked again.
                registry.apply(Supersede(q.id, make_entity(
                    kind=q.kind, engagement_id=q.engagement_id,
                    payload=replace(q.payload, unknown=True), provenance=by,
                    confidence=q.confidence, relevance=q.relevance, relation=q.relation,
                    status=q.status, entity_id=q.id, labels=q.labels)))
            registry.apply(SetStatus(q.id, Status.RESOLVED, by))
            closed.append(q.id)
        except RegistryError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    store.save(registry, db)
    return {"reply": reply, "closed_questions": closed}


# ---------------------------------------------------------------------------
# Charter and analysis
# ---------------------------------------------------------------------------

def run_analysis_job(engagement_id: str, *, session_factory: Callable[[], Any] | None = None) -> dict | None:
    """The background analysis pass, on its OWN session.

    The thread that runs this outlives the request that started it, so it
    cannot borrow the request's session; it opens one, owns it, and closes it.
    The working lock it inherits from the confirm endpoint is released here,
    whatever happened - a crashed analysis leaves a retryable failure, never
    an engagement stuck at working forever (the same shape the startup sweep
    exists to repair after a restart kills this thread).
    """
    if session_factory is None:
        from app.database import SessionLocal

        session_factory = SessionLocal
    db = session_factory()
    row = None
    try:
        row = db.query(Engagement).filter(Engagement.public_id == engagement_id).first()
        if row is None:
            return None
        store = _store()
        state = _state(db, row, store)
        emit_engine(db, engagement_id, "analysis", "Analysing the engagement", 20)
        run = _partner().run_analysis(state, context_settings=_bindings(db, row))
        store.save(state.registry, db)
        row.phase = state.phase.value
        central = state.registry.central_decision()
        row.central_decision_id = central.id if central is not None else None
        db.commit()
        emit_engine(db, engagement_id, "analysis_done", "Analysis complete", 80,
                    detail=f"{run.rounds} round(s)")
        return schemas.analysis_out(run)
    except Exception as exc:
        logger.exception("engagement %s analysis failed", engagement_id)
        if row is not None:
            _release_lock(db, row, status="failed", stage="failed",
                          label=f"Analysis failed: {exc}", failed=True)
        return None
    finally:
        if row is not None and row.is_working:
            _release_lock(db, row, stage="analysis_done", label="Analysis complete")
        db.close()


def _start_analysis(engagement_id: str) -> None:
    """A daemon thread, exactly as r30 starts a generation
    (`requests.create_request` -> `orchestrator.run`). The seam a test
    replaces to run the same job synchronously."""
    threading.Thread(target=run_analysis_job, args=(engagement_id,), daemon=True).start()


@router.post("/{ref}/charter/confirm")
def confirm_charter(ref: str, body: schemas.CharterConfirmRequest,
                    review_token: str | None = None,
                    authorization: str | None = Header(None),
                    db: Session = Depends(get_db)):
    """The client's per-item verdicts on the charter. An approved charter is
    the mandate, and only an approved charter starts the analysis."""
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    verdicts: dict[str, str] = {}
    corrections: dict[str, Any] = {}
    for item in body.items:
        if item.verdict not in VERDICTS:                    # pragma: no cover - the literal already refuses
            raise HTTPException(status_code=422, detail=f"{item.verdict!r} is not a verdict")
        verdicts[item.entity_id] = item.verdict
        if item.verdict == "correct":
            if not (item.text or "").strip():
                raise HTTPException(status_code=422,
                                    detail=f"{item.entity_id}: a correction carries the client's own words")
            corrections[item.entity_id] = item.text

    store = _store()
    _claim(db, row, stage="charter", label="Confirming the charter", pct=15)
    started = False
    try:
        state = _state(db, row, store)
        turn = db.query(EngagementTurn).filter(
            EngagementTurn.engagement_id == row.public_id,
            EngagementTurn.role == "client").order_by(EngagementTurn.id.desc()).first()
        outcome = _partner().confirm_charter(
            state, body.charter_id, verdicts=verdicts, corrections=corrections,
            turn_id=turn.source_entity_id if turn is not None else None)
        store.save(state.registry, db)
        row.phase = state.phase.value
        if outcome.charter is not None:
            row.charter_id = outcome.charter.id
        db.commit()
        result = {
            "charter_id": body.charter_id,
            "approved": outcome.approved,
            "confirmed": list(outcome.confirmed),
            "corrected": list(outcome.corrected),
            "rejected": list(outcome.rejected),
            "central_decision": outcome.central_decision,
            "refused": list(outcome.refused),
            "phase": state.phase.value,
            "analysis_started": False,
        }
        if outcome.approved:
            # The lock stays held and passes to the analysis thread, which
            # releases it: from the client's side the engagement is one
            # continuous piece of work, not a gap between two locks.
            started = True
            result["analysis_started"] = True
            _start_analysis(row.public_id)
        return result
    finally:
        if not started and row.is_working:
            _release_lock(db, row, stage="waiting", label="Waiting for you")


# ---------------------------------------------------------------------------
# Resolution: conflicts, decisions required, assumptions
# ---------------------------------------------------------------------------

@router.post("/{ref}/conflicts/{conflict_id}/resolve")
def resolve_conflict_endpoint(ref: str, conflict_id: str, body: schemas.ResolveRequest,
                              review_token: str | None = None,
                              authorization: str | None = Header(None),
                              db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    store = _store()
    registry = store.load(row.public_id, db)
    conflict = registry.get(conflict_id)
    if conflict is None or conflict.kind is not Kind.CONFLICT:
        raise HTTPException(status_code=404, detail="Conflict not found")

    turn_n = _client_turns(db, row.public_id)
    actor, actor_ref, on_behalf_of = _caller_actor(
        body, row=row, review_token=review_token, authorization=authorization, turn_n=turn_n)
    # A1: the authority table decides who may settle THIS conflict, before a
    # single row is written.
    _require_authorised(conflict, Status.RESOLVED, actor)
    try:
        resolved = resolve_conflict(registry, conflict_id, chosen_entity_id=body.chosen_entity_id,
                                    actor=actor, actor_ref=actor_ref, rationale=body.rationale,
                                    on_behalf_of=on_behalf_of)
    except ResolutionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    store.save(registry, db)
    return {"conflict": schemas.entity_out(resolved), "acting_as": body.acting_as,
            "on_behalf_of": on_behalf_of, "actor_ref": actor_ref}


@router.post("/{ref}/decisions/{decision_id}/resolve")
def resolve_decision_required(ref: str, decision_id: str, body: schemas.ResolveRequest,
                              review_token: str | None = None,
                              authorization: str | None = Header(None),
                              db: Session = Depends(get_db)):
    """Close an open DECISION_REQUIRED. The choice is recorded on the row
    (payload.chosen) and the rationale as a label, so the reason travels with
    the decision in lineage instead of living in a request log."""
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    store = _store()
    registry = store.load(row.public_id, db)
    entity = registry.get(decision_id)
    if entity is None or entity.kind is not Kind.DECISION_REQUIRED:
        raise HTTPException(status_code=404, detail="Decision not found")

    turn_n = _client_turns(db, row.public_id)
    actor, actor_ref, on_behalf_of = _caller_actor(
        body, row=row, review_token=review_token, authorization=authorization, turn_n=turn_n)
    _require_authorised(entity, Status.RESOLVED, actor)
    if actor is Actor.DECISION_OWNER:
        owner = registry.get(on_behalf_of) if on_behalf_of else None
        if owner is None or owner.kind is not Kind.DECISION_OWNER or owner.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=403,
                                detail="A decision owner acts on behalf of a recorded DECISION_OWNER")
    labels = (f"rationale:{body.rationale.strip()[:180]}",) if body.rationale.strip() else ()
    try:
        if body.chosen_entity_id and body.chosen_entity_id != entity.payload.chosen:
            registry.apply(Supersede(entity.id, make_entity(
                kind=entity.kind, engagement_id=entity.engagement_id,
                payload=replace(entity.payload, chosen=body.chosen_entity_id),
                provenance=Provenance(actor=actor, actor_ref=actor_ref,
                                      derived_from=entity.provenance.derived_from),
                confidence=entity.confidence, relevance=entity.relevance, relation=entity.relation,
                status=entity.status, entity_id=entity.id, labels=entity.labels)))
        resolved = registry.apply(SetStatus(
            entity.id, Status.RESOLVED,
            Provenance(actor=actor, actor_ref=actor_ref), labels=labels))
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    store.save(registry, db)
    return {"decision": schemas.entity_out(resolved), "acting_as": body.acting_as,
            "on_behalf_of": on_behalf_of, "actor_ref": actor_ref}


def _decide_assumption(ref: str, assumption_id: str, body: schemas.ApprovalRequest,
                       *, status: Status, review_token: str | None,
                       authorization: str | None, db: Session) -> dict:
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    store = _store()
    registry = store.load(row.public_id, db)
    entity = registry.get(assumption_id)
    if entity is None or entity.kind is not Kind.ASSUMPTION:
        raise HTTPException(status_code=404, detail="Assumption not found")

    turn_n = _client_turns(db, row.public_id)
    actor, actor_ref, on_behalf_of = _caller_actor(
        body, row=row, review_token=review_token, authorization=authorization, turn_n=turn_n)
    _require_authorised(entity, status, actor)
    labels = (f"rationale:{body.rationale.strip()[:180]}",) if body.rationale.strip() else ()
    try:
        decided = registry.apply(SetStatus(entity.id, status,
                                           Provenance(actor=actor, actor_ref=actor_ref),
                                           labels=labels))
    except RegistryError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    store.save(registry, db)
    return {"assumption": schemas.entity_out(decided), "acting_as": body.acting_as,
            "on_behalf_of": on_behalf_of, "actor_ref": actor_ref}


@router.post("/{ref}/assumptions/{assumption_id}/approve")
def approve_assumption(ref: str, assumption_id: str, body: schemas.ApprovalRequest,
                       review_token: str | None = None,
                       authorization: str | None = Header(None),
                       db: Session = Depends(get_db)):
    return _decide_assumption(ref, assumption_id, body, status=Status.APPROVED,
                              review_token=review_token, authorization=authorization, db=db)


@router.post("/{ref}/assumptions/{assumption_id}/reject")
def reject_assumption(ref: str, assumption_id: str, body: schemas.ApprovalRequest,
                      review_token: str | None = None,
                      authorization: str | None = Header(None),
                      db: Session = Depends(get_db)):
    return _decide_assumption(ref, assumption_id, body, status=Status.REJECTED,
                              review_token=review_token, authorization=authorization, db=db)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@router.get("/{ref}/progress")
def get_progress(ref: str, review_token: str | None = None,
                 authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    elapsed = int((datetime.utcnow() - row.created_at).total_seconds()) if row.created_at else 0
    return schemas.progress_out(row, elapsed_s=max(0, elapsed))


@router.get("/{ref}/turns")
def get_turns(ref: str, review_token: str | None = None,
              authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    rows = (db.query(EngagementTurn)
            .filter(EngagementTurn.engagement_id == row.public_id)
            .order_by(EngagementTurn.id).all())
    return {"turns": [{"n": t.n, "role": t.role, "text": t.text,
                       "source_entity_id": t.source_entity_id,
                       "attachments": json.loads(t.attachments_json) if t.attachments_json else [],
                       "created_at": t.created_at.isoformat() if t.created_at else None}
                      for t in rows]}


@router.get("/{ref}/registry")
def get_registry(ref: str, kind: str | None = None, status: str | None = None,
                 after: str | None = None, limit: int = PAGE_DEFAULT,
                 review_token: str | None = None,
                 authorization: str | None = Header(None), db: Session = Depends(get_db)):
    """The live rows, filtered by the closed vocabularies only. `kind` and
    `status` are enum names: an unknown one is a 422, never an empty result
    that looks like an answer."""
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    try:
        want_kind = Kind(kind) if kind else None
        want_status = Status(status) if status else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    registry = _store().load(row.public_id, db)
    rows = registry.query(want_kind, status=want_status) if want_status else registry.live(want_kind)
    if after:
        ids = [e.id for e in rows]
        rows = rows[ids.index(after) + 1:] if after in ids else []
    page = rows[:max(1, min(int(limit), PAGE_MAX))]
    return {"entities": schemas.entities_out(page),
            "next_after": page[-1].id if page and len(page) < len(rows) else None,
            "total": len(rows)}


@router.get("/{ref}/entities/{entity_id}/lineage")
def get_lineage(ref: str, entity_id: str, review_token: str | None = None,
                authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    registry = _store().load(row.public_id, db)
    versions = registry.lineage(entity_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"entity_id": entity_id, "versions": schemas.entities_out(versions)}


def _work_product_rows(registry) -> list:
    return [e for e in registry.live(Kind.WORK_PRODUCT)]


@router.get("/{ref}/work-products")
def get_work_products(ref: str, review_token: str | None = None,
                      authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    registry = _store().load(row.public_id, db)
    artifacts = (db.query(EngagementArtifact)
                 .filter(EngagementArtifact.engagement_id == row.public_id).all())
    by_product: dict[str, list[dict]] = {}
    for a in artifacts:
        by_product.setdefault(a.product_id or "", []).append(
            {"fmt": a.fmt, "sha256": a.sha256, "registry_hash": a.registry_hash,
             "stale": a.registry_hash != registry.content_hash()})
    return {
        "registry_hash": registry.content_hash(),
        "withheld": r30_requests._pending_for(row, review_token),
        "work_products": [
            {"entity_id": e.id, "product_id": e.payload.product_id, "title": e.payload.title,
             "planned_because": e.payload.planned_because,
             "section_ids": list(e.payload.section_ids),
             "artifacts": by_product.get(e.payload.product_id, [])}
            for e in _work_product_rows(registry)
        ],
    }


@router.get("/{ref}")
def get_engagement(ref: str, review_token: str | None = None,
                   authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    registry = _store().load(row.public_id, db)
    central = registry.central_decision()
    stated = [e for e in registry.live(Kind.DECISION) if e.field("role") == "stated_request"]
    charter = registry.get(row.charter_id) if row.charter_id else None
    findings = run_laws(registry, ())
    return {
        "id": row.public_id,
        "public_id": row.public_id,
        "phase": row.phase,
        "status": row.status,
        "is_working": bool(row.is_working),
        "review_status": row.review_status,
        "client_name": row.client_name,
        "title": row.title,
        "registry_hash": registry.content_hash(),
        "central_decision": schemas.entity_out(central) if central is not None else None,
        "stated_request": schemas.entity_out(stated[0]) if stated else None,
        "charter": schemas.entity_out(charter) if charter is not None else None,
        "live_summary": registry.live_summary(),
        "work_products": [{"product_id": e.payload.product_id, "title": e.payload.title}
                          for e in _work_product_rows(registry)],
        "release_status": release_mod.release_status(
            findings, approval=release_mod.client_approval(registry)),
    }


@router.get("/{ref}/integrity-record")
def get_integrity_record(ref: str, review_token: str | None = None,
                         authorization: str | None = Header(None), db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    registry = _store().load(row.public_id, db)
    plan = plan_work_products(registry, preliminary=True, bounds=settings.engine_bounds())
    reports, refs = _artifact_reports(db, row.public_id)
    return build_integrity_record(registry, artifacts=reports, unplanned=plan.unplanned,
                                  findings=run_laws(registry, refs),
                                  calc=DecimalCalculator(registry))


# ---------------------------------------------------------------------------
# A3/A4: exports
# ---------------------------------------------------------------------------

def _artifacts_dir(engagement_id: str) -> str:
    return os.path.join(store_mod.documents_dir(engagement_id), "artifacts")


def _released(db: Session, engagement_id: str) -> bool:
    """A3. DRAFT until a release record says otherwise - and it is the RECORD
    that says so, not a status column somebody could set by hand."""
    row = (db.query(EngagementRelease)
           .filter(EngagementRelease.engagement_id == engagement_id)
           .order_by(EngagementRelease.revision.desc()).first())
    return row is not None and row.status in (release_mod.STATUS_FINAL,
                                              release_mod.STATUS_CLIENT_APPROVED)


def _expected_path(engagement_id: str, product_id: str, fmt: str, draft: bool) -> str | None:
    """Where this format lands. The DRAFT stamp changes the bytes, so it is
    part of the name: a released package can never be served from the file
    that was rendered while the gate still held it (A3). csv has no stamp and
    its file names are the renderer's business, so it has no expected path."""
    if fmt == "csv":
        return None
    ext = {"pdf": "pdf", "md": "md", "pptx": "pptx"}[fmt]
    stamp = "draft" if draft else "final"
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in product_id)
    return os.path.join(_artifacts_dir(engagement_id), f"{safe}-{stamp}.{ext}")


def _render_product(registry, decl, section_ids: Sequence[str] | None):
    """Render, and settle the STATEMENT rows the pass mints.

    The first pass writes the statements a repeated claim renders from; those
    rows change the registry hash, so the artifact is rendered again from the
    settled registry. Without the second pass every export would be born
    stale against the registry it just created (A4).
    """
    bounds = settings.engine_bounds()
    rendered = render_md.render_product(decl, registry, provider=_provider(),
                                        calc=DecimalCalculator(registry),
                                        section_ids=section_ids, bounds=bounds)
    if rendered.statement_deltas:
        registry.apply_all(rendered.statement_deltas)
        rendered = render_md.render_product(decl, registry, provider=_provider(),
                                            calc=DecimalCalculator(registry),
                                            section_ids=section_ids, bounds=bounds)
    return rendered


def _build_artifact(db: Session, engagement_id: str, registry, product, fmt: str,
                    draft: bool, subtitle: str) -> ArtifactRef:
    product_id = product.payload.product_id
    try:
        decl = WORK_PRODUCTS.get(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"{product_id} is not a registered work product")
    section_ids = list(product.payload.section_ids) or None
    rendered = _render_product(registry, decl, section_ids)
    _store().save(registry, db)
    registry_hash = registry.content_hash()
    out_dir = _artifacts_dir(engagement_id)
    os.makedirs(out_dir, exist_ok=True)
    path = _expected_path(engagement_id, product_id, fmt, draft)

    if fmt == "pdf":
        ref = render_pdf.render_pdf(rendered, out_path=path, draft=draft, subtitle=subtitle,
                                    registry_hash=registry_hash)
    elif fmt == "md":
        ref = render_pdf.render_markdown_artifact(rendered, out_path=path,
                                                  registry_hash=registry_hash)
    elif fmt == "pptx":
        ref = render_deck.render_deck(rendered, out_path=path, draft=draft, subtitle=subtitle,
                                      registry_hash=registry_hash)
    else:
        refs = render_csv.render_csv(rendered, out_dir=out_dir, registry_hash=registry_hash)
        if not refs:
            raise HTTPException(status_code=404,
                                detail=f"{product_id} has no tabular section to export as csv")
        ref = refs[0]

    db.add(EngagementArtifact(engagement_id=engagement_id, work_product_id=product.id,
                              product_id=product_id, fmt=fmt, path=ref.path, sha256=ref.sha256,
                              registry_hash=ref.registry_hash))
    db.commit()
    return ref


def _artifact_reports(db: Session, engagement_id: str) -> tuple[list[ArtifactReport], list[ArtifactRef]]:
    """The artifacts on record for this engagement, newest per (product, fmt).
    Read from rows, so the Integrity Record and the release describe the files
    that actually exist."""
    latest: dict[tuple[str, str], EngagementArtifact] = {}
    for a in (db.query(EngagementArtifact)
              .filter(EngagementArtifact.engagement_id == engagement_id)
              .order_by(EngagementArtifact.id)):
        latest[(a.product_id or "", a.fmt or "")] = a
    reports: list[ArtifactReport] = []
    refs: list[ArtifactRef] = []
    for a in latest.values():
        if not a.path or not os.path.exists(a.path):
            continue
        text = ""
        if a.fmt == "pdf":
            text = render_pdf.strip_engine_chrome(render_pdf.extract_text(a.path))
        elif a.fmt == "md":
            with open(a.path, encoding="utf-8") as fh:
                text = fh.read()
        ref = ArtifactRef(product_id=a.product_id or "", fmt=a.fmt or "", path=a.path,
                          sha256=a.sha256, registry_hash=a.registry_hash or "",
                          extracted_text=text)
        refs.append(ref)
        reports.append(ArtifactReport(ref=ref))
    return reports, refs


@router.get("/{ref}/work-products/{product_id}/export/{fmt}")
def export_work_product(ref: str, product_id: str, fmt: str,
                        review_token: str | None = None,
                        authorization: str | None = Header(None),
                        db: Session = Depends(get_db)):
    row = _load(ref, db)
    _require_view(row, review_token, authorization)
    # A3: the review gate withholds the deliverable itself, not the progress.
    if r30_requests._pending_for(row, review_token):
        raise HTTPException(status_code=403,
                            detail="This engagement is with the consultant for review")
    if fmt not in FORMATS:
        raise HTTPException(status_code=404, detail=f"{fmt} is not an export format")

    registry = _store().load(row.public_id, db)
    product = next((e for e in _work_product_rows(registry)
                    if e.payload.product_id == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Work product not planned for this engagement")

    draft = not _released(db, row.public_id)
    expected = _expected_path(row.public_id, product_id, fmt, draft)
    current = registry.content_hash()
    cached = (db.query(EngagementArtifact)
              .filter(EngagementArtifact.engagement_id == row.public_id,
                      EngagementArtifact.product_id == product_id,
                      EngagementArtifact.fmt == fmt)
              .order_by(EngagementArtifact.id.desc()).first())
    # A4: rebuilt when the registry moved (or the stamp did), served from the
    # file when neither did. export_pdf.py:1756's rule, on engine artifacts.
    fresh = (cached is not None and cached.registry_hash == current and cached.path
             and os.path.exists(cached.path)
             and (expected is None or cached.path == expected))
    if fresh:
        path, sha = cached.path, cached.sha256
    else:
        built = _build_artifact(db, row.public_id, registry, product, fmt, draft,
                                row.client_name or row.title or "")
        path, sha = built.path, built.sha256

    return FileResponse(
        path, filename=os.path.basename(path),
        headers={"X-Engine-Cache": "hit" if fresh else "miss",
                 "X-Engine-Draft": "true" if draft else "false",
                 "X-Engine-Sha256": sha},
    )


# ---------------------------------------------------------------------------
# Release and review
# ---------------------------------------------------------------------------

def _deliverables(registry) -> list[str]:
    """The deliverable list a notification names, derived from the products
    the engagement actually planned - never a fixed list of volumes."""
    return [e.payload.title for e in _work_product_rows(registry)]


@router.post("/{ref}/release")
def post_release(ref: str, review_token: str | None = None, db: Session = Depends(get_db)):
    """Reviewer-gated. Every law runs over the artifacts on record, the
    record is built in tools/release_audit's own shape, and a record that
    does not validate is a 409 carrying the validator's errors - never a
    frozen revision (release R1)."""
    if not r30_requests._is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    row = _load(ref, db)
    registry = _store().load(row.public_id, db)
    reports, refs = _artifact_reports(db, row.public_id)
    if not refs:
        raise HTTPException(status_code=409,
                            detail="Nothing to release: no artifact has been exported yet")
    plan = plan_work_products(registry, preliminary=True, bounds=settings.engine_bounds())
    integrity = build_integrity_record(registry, artifacts=reports, unplanned=plan.unplanned,
                                       findings=run_laws(registry, refs),
                                       calc=DecimalCalculator(registry))
    titles = {e.payload.product_id: e.payload.title for e in _work_product_rows(registry)}
    result = release_mod.release(registry, refs, engagement_id=row.public_id,
                                 integrity=integrity, titles=titles, freeze_it=False)
    errors = list(result.record.get("validation_errors") or [])
    if errors:
        raise HTTPException(status_code=409, detail={"validation_errors": errors})

    revision = int(str(result.revision).rsplit("-r", 1)[-1])
    directory = release_mod.freeze(result.record, refs, engagement_id=row.public_id,
                                   revision=revision)
    verification = release_mod.verify(directory)
    release_mod.persist_release(result.record, engagement_id=row.public_id, revision=revision,
                                parent=revision - 1 if revision > 1 else None, db=db)
    if result.record["status"] != release_mod.STATUS_DRAFT:
        row.status = "released"
        db.commit()
    return {"revision": result.record["revision"], "status": result.record["status"],
            "reasons": result.record["reasons"], "verification": verification,
            "directory": directory,
            "findings": [f.as_dict() for f in result.findings]}


@router.post("/{ref}/review/approve")
def review_approve(ref: str, review_token: str | None = None, db: Session = Depends(get_db)):
    """The consultant signs. The client is told, and told what they are
    getting: the deliverable list is derived from the products this
    engagement planned, so the mail cannot promise a volume nobody built."""
    if not r30_requests._is_reviewer(review_token):
        raise HTTPException(status_code=403, detail="Reviewer token required")
    row = _load(ref, db)
    row.review_status = "approved"
    row.reviewed_at = datetime.utcnow()
    db.commit()
    registry = _store().load(row.public_id, db)
    deliverables = _deliverables(registry)
    name = row.client_name or row.title or "your engagement"
    mailer.send_async(
        row.owner_email,
        f"Your engagement is ready - {name}",
        "Your engagement has been reviewed and released.\n\n"
        + ("What it includes:\n" + "\n".join(f"- {d}" for d in deliverables)
           if deliverables else "The deliverables are listed in your engagement.")
        + f"\n\nOpen it: https://buildmyversion.com/engagements/{row.public_id}\n",
    )
    return {"id": row.public_id, "review_status": row.review_status,
            "deliverables": deliverables}


__all__ = ["router", "run_analysis_job"]
