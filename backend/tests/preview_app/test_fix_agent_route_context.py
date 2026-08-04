"""The fix agent's route block: allow-list once per run, and degrade by dropping.

`_catalogue_routes_context` serialized one **full** `compact_skeleton_contract`
per catalogue route into a 10,000-character budget. The component definitions
and prop shapes are the bulk of a contract and they repeat verbatim for every
route sharing a skeleton, so measured offline: 1 route = 5,004 chars, 2 routes =
each component list clipped to 12 entries, **3 routes = the whole block replaced
by `{"truncated": true, "preview": "<a prefix of a JSON string>"}`**. Confirmed
live on request 93's real 9-route list, where the fix agent then ran twice for
147.8 s of AI against a route block it could not read.

It goes to the **fix agent** and `chat_rebuild`, not to the architect — four
write-ups said "the architect" and all four were wrong. The repair path is the
consumer that most needs each page's contract.

Two changes, and the second is the one the measurement forced:

1. **The allow-list is stated once.** 45k+ chars of repeated definitions for
   request 93's nine routes become a 6,019-char library plus 2,206 chars of prop
   shapes, said once, with each route naming the components it may use.
2. **The block degrades by dropping, never by collapsing.** The hoist alone is a
   2.4x reduction and *still* 18,869 against 10,000, so it was not enough on its
   own — every archived run with more than two catalogue routes would still have
   received the `truncated` preview. Four rungs now, `detail_level` naming which
   one was sent.

Fixtures are the real archived route lists (`docs/evidence/architect-routes.json`,
10-19 routes) precisely because a three-route fixture cannot reach the budget
this exists to survive.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.application.preview_app.codegen.architect import (
    _DETAIL_FULL,
    _DETAIL_LEVELS,
    _ROUTES_CONTEXT_BUDGET,
    _catalogue_routes_context,
)

_EVIDENCE = (
    Path(__file__).resolve().parents[3] / "docs" / "evidence" / "architect-routes.json"
)


def _corpus() -> dict[str, list[dict]]:
    """Archived runs that actually declare catalogue routes.

    Early runs (request 1 among them) predate `skeleton_id` entirely and their
    block has always been `[]`. Leaving them in makes every assertion below
    pass for the wrong reason.
    """

    raw = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    return {
        rid: routes
        for rid, routes in raw.items()
        if any(r.get("skeleton_id") for r in routes)
    }


#: Written out, not imported. Asserting against the module's own constant means
#: raising the constant silently passes — the budget is the fix agent prompt's,
#: not this block's to choose, and a mutation that widened it survived a sweep.
_FIX_AGENT_PROMPT_BUDGET = 10000


def _block(routes: list[dict]) -> dict:
    rendered = _catalogue_routes_context({"routes": routes})
    assert len(rendered) <= _FIX_AGENT_PROMPT_BUDGET
    return json.loads(rendered)


def _shared_skeleton_pair() -> list[dict]:
    """Two archived routes that share one skeleton.

    The case the allow-list bound exists for: before the hoist, both restated
    that skeleton's entire component list. Request 93's `/` and
    `/concierge-landing` are both `public-home`, and the corpus has the same
    shape in several runs.
    """

    for routes in _corpus().values():
        by_skeleton: dict[str, list[dict]] = {}
        for route in routes:
            if route.get("skeleton_id"):
                by_skeleton.setdefault(route["skeleton_id"], []).append(route)
        for pair in by_skeleton.values():
            if len(pair) >= 2:
                return pair[:2]
    raise AssertionError("no archived run has two routes on one skeleton")


def _big_run() -> list[dict]:
    """The largest archived route list — 19 routes on request 91."""

    corpus = _corpus()
    return max(corpus.values(), key=len)


def test_the_corpus_is_the_size_the_budget_actually_meets() -> None:
    """Guards the fixture, not the code.

    Every route list here is well past two routes, which is where the old
    serialization started collapsing. If this file is ever pointed at a small
    corpus the rest of these tests stop proving anything.
    """

    sizes = sorted(len(routes) for routes in _corpus().values())
    assert sizes[-1] >= 15
    assert sum(1 for n in sizes if n >= 8) >= 5


@pytest.mark.parametrize("request_id", sorted(_corpus(), key=int))
def test_no_archived_run_receives_a_truncated_preview(request_id: str) -> None:
    """The defect, run against every route list the corpus has.

    `{"truncated": true, "preview": …}` is a *string* holding a prefix of a JSON
    document, cut mid-structure. Requests 86, 87, 88, 91 and 93 all got one.
    """

    block = _block(_corpus()[request_id])

    assert "truncated" not in block
    assert block.get("routes"), "a run with catalogue routes must describe some"


def test_every_route_keeps_its_identity_however_degraded() -> None:
    """The one thing no rung may drop.

    A repair agent that knows which page file serves which path, on which
    skeleton, can act. The component library is guidance; this is the map.
    """

    routes = _big_run()
    with_skeletons = [r for r in routes if r.get("skeleton_id")]
    block = _block(routes)

    served = {(r["path"], r["component_file"], r["skeleton_id"]) for r in block["routes"]}
    expected = {
        (r.get("path"), r.get("component_file"), r.get("skeleton_id"))
        for r in with_skeletons
    }
    assert served == expected


def test_a_component_definition_is_stated_once_not_once_per_route() -> None:
    """The allow-list bound itself.

    Request 93 has six distinct skeletons across nine routes and 43 distinct
    components between them; the old block restated each definition on every
    route that allowed it.
    """

    routes = _shared_skeleton_pair()
    block = _block(routes)

    # Fixed at two routes, deliberately: a test that trims until the full level
    # fits will trim down to *one* route when a mutation bloats the library, and
    # a one-route app cannot show a duplicate. That version survived a sweep.
    assert block["detail_level"] == _DETAIL_FULL
    assert len(block["routes"]) == 2

    names = [component["name"] for component in block["component_library"]]
    assert names == sorted(set(names)), "a definition appears more than once"
    # Both routes are on one skeleton, so the library is exactly that skeleton's
    # component set — not two copies of it.
    assert set(names) == set(block["routes"][0]["contract"]["allowed_components"])

    # …and the routes reference it by name rather than restating it.
    for route in block["routes"]:
        allowed = route["contract"]["allowed_components"]
        assert allowed, "a route with a skeleton allows some components"
        assert set(allowed) <= set(names)
        assert "components" not in route["contract"]
        # Prop shapes are hoisted too — 2,206 chars on request 93, and they
        # repeat across every route on the same skeleton just as definitions do.
        assert "prop_shapes" not in route["contract"]
    assert block["prop_shapes"], "the hoisted shapes have to land somewhere"


def test_the_block_says_which_rung_it_came_down_to() -> None:
    """Silent degradation is the defect this repo keeps rediscovering.

    `visual_review_status`, `render_pages_skipped`, `degraded: []` and
    `withheld_reason` are all the same lesson: a measurement that quietly
    reports less than it took is indistinguishable from a clean one.
    """

    for routes in _corpus().values():
        block = _block(routes)
        assert block["detail_level"] in _DETAIL_LEVELS


def test_a_small_app_still_gets_the_whole_contract() -> None:
    """The rungs must not cost the runs that never needed them."""

    routes = [r for r in _big_run() if r.get("skeleton_id")][:1]
    block = _block(routes)

    assert block["detail_level"] == _DETAIL_FULL
    assert block["component_library"]
    assert block["prop_shapes"]


def test_a_run_with_no_catalogue_routes_is_unchanged() -> None:
    """`[]` is what every such run has always sent, and a fix agent prompt
    that suddenly grew a `detail_level` for an empty app would be a change
    nothing asked for."""

    assert _catalogue_routes_context({"routes": []}) == "[]"
    assert _catalogue_routes_context({}) == "[]"
    assert _catalogue_routes_context({"routes": [{"path": "/", "skeleton_id": None}]}) == "[]"
