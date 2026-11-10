"""Finding businesses: only ones a cited page shows, each once."""
import json

from outreach_helpers import reply

from app.outreach import find

SRC = "https://www.example.ae/best-salons-dubai"


def _item(name="Glow Salon", website="https://glowsalon.ae", instagram="glow.dxb", source=SRC):
    return {"name": name, "website": website, "instagram": instagram, "phone": "+971 4 000 0000",
            "source": source, "what": "a hair and nails salon in JLT"}


def test_only_cited_sources_are_kept():
    body = reply(json.dumps({"found": [_item(), _item(name="Ghost", source="https://nowhere.example/")]}), [SRC])
    assert [b["name"] for b in find.parse_found(body)] == ["Glow Salon"]


def test_quoted_facts_from_cited_pages_are_kept_with_what_it_does():
    item = {**_item(), "facts": ["Bio: DM to book", "Open 10am to 10pm", 7, "x" * 400]}
    [found] = find.parse_found(reply(json.dumps({"found": [item]}), [SRC]))
    assert found["what"].startswith("a hair and nails salon in JLT")
    assert "- Bio: DM to book" in found["what"] and "- Open 10am to 10pm" in found["what"]
    assert "x" * 200 not in found["what"]


def test_a_cited_instagram_profile_gives_the_handle():
    [found] = find.parse_found(reply(json.dumps({"found": [{**_item(instagram=None), "source": "https://www.instagram.com/glow.dxb/"}]}),
                                     ["https://www.instagram.com/glow.dxb/"]))
    assert found["instagram"] == "glow.dxb"


def test_an_instagram_url_becomes_a_handle():
    assert find.handle("https://www.instagram.com/glow.dxb/") == "glow.dxb"
    assert find.handle("@glow.dxb") == "glow.dxb"
    assert find.handle("not a handle!") is None
    assert find.handle(None) is None


def test_the_same_business_is_found_once(db, monkeypatch):
    assert find.dedup_key("Glow Salon", "Dubai", "https://www.glowsalon.ae/book", None) == \
        find.dedup_key("Glow Salon LLC", "Dubai", "http://glowsalon.ae", None)
    from app.models import Prospect
    from app.outreach import new_token

    db.add(Prospect(token=new_token(), name="Old One", city="Dubai", kind="salon",
                    key=find.dedup_key("Old One", "Dubai", None, "old.one")))
    db.commit()
    items = [_item(), _item(name="Glow Salon LLC", website="http://glowsalon.ae", instagram=None),
             _item(name="Old One", website=None, instagram="old.one")]
    monkeypatch.setattr(find.provider, "chat", lambda *a, **k: reply(json.dumps({"found": items}), [SRC]))
    new = find.find(db, "Dubai", "salon", 10)
    assert [p.name for p in new] == ["Glow Salon"]
    assert new[0].status == "found" and json.loads(new[0].sources_json)[0]["url"] == SRC


def test_a_failed_search_finds_nothing_and_does_not_raise(db, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("search down")

    monkeypatch.setattr(find.provider, "chat", down)
    assert find.find(db, "Dubai", "salon", 10) == []
