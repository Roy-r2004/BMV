"""What public pages say about one business, kept only when the search cited it."""
import json

from outreach_helpers import reply

from app.models import Prospect
from app.outreach import learn
from app.outreach.__init__ import new_token

FACTS = json.dumps({"facts": [
    {"fact": "Known for its Moroccan bath", "source": "https://reviews.example/glow"},
    {"fact": "Invented fact", "source": "https://not-cited.example"},
    {"fact": "Open until 10pm", "source": "https://glowsalon.ae"}]})


def _prospect(db):
    p = Prospect(token=new_token(), name="Glow Salon", city="Dubai", kind="salon", key=f"k-{new_token()}",
                 what="Hair and nails", score=50, status="ready",
                 sources_json=json.dumps([{"url": "https://glowsalon.ae", "what": "its website"}]))
    db.add(p)
    db.commit()
    return p


def test_only_cited_facts_are_kept():
    facts = learn.parse_facts(reply(FACTS, ["https://reviews.example/glow", "https://glowsalon.ae"]))
    assert [f["fact"] for f in facts] == ["Known for its Moroccan bath", "Open until 10pm"]


def test_what_is_learned_joins_what_was_read(db, monkeypatch):
    p = _prospect(db)
    calls = []
    monkeypatch.setattr(learn.provider, "chat", lambda *a, **k: calls.append(1) or reply(
        FACTS, ["https://reviews.example/glow", "https://glowsalon.ae"]))
    learn.learn(db, p)
    learn.learn(db, p)
    assert len(calls) == 1 and learn.learned(p)
    assert "- Known for its Moroccan bath" in p.what and "Invented fact" not in p.what
    urls = [s["url"] for s in json.loads(p.sources_json)]
    assert urls.count("https://glowsalon.ae") == 1 and "https://reviews.example/glow" in urls


def test_finding_nothing_still_counts_as_learned(db, monkeypatch):
    p = _prospect(db)
    monkeypatch.setattr(learn.provider, "chat", lambda *a, **k: reply('{"facts": []}', []))
    learn.learn(db, p)
    assert learn.learned(p) and p.what == "Hair and nails"


def test_a_search_that_cannot_be_done_is_tried_again_later(db, monkeypatch):
    p = _prospect(db)

    def down(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(learn.provider, "chat", down)
    learn.learn(db, p)
    assert not learn.learned(p) and p.what == "Hair and nails"
