"""Scoring a business only on what its own site shows."""
import json

from app.figures import references
from app.outreach import read


def _prospect(db, website="https://glowsalon.ae", instagram=None):
    from app.models import Prospect
    from app.outreach import new_token

    p = Prospect(token=new_token(), name="Glow", city="Dubai", kind="salon", key=f"k-{new_token()}",
                 website=website, instagram=instagram, sources_json="[]")
    db.add(p)
    db.commit()
    return p


def test_a_booking_platform_link_counts_as_online_booking():
    assert read.signals("<a href='https://www.fresha.com/a/glow'>Book</a>")["books_online"] is True


def test_dm_to_book_is_booking_by_message():
    sig = read.signals("Welcome! DM us to book your slot")
    assert sig["books_by_message"] is True and sig["books_online"] is False


def test_a_site_that_cannot_be_read_scores_as_no_website(db, monkeypatch):
    def blocked(url):
        raise references.Unreadable("403")

    monkeypatch.setattr(read.references, "_fetch", blocked)
    p = read.read(db, _prospect(db))
    assert p.score == 40 and p.status == "ready"
    assert json.loads(p.reasons_json) == ["No working website was found"]


def test_a_business_that_already_books_online_is_skipped(db, monkeypatch):
    assert read.score({"has_site": True, "books_online": True, "books_by_message": False, "shows_whatsapp": False}) == (0, [])
    monkeypatch.setattr(read.references, "_fetch", lambda url: "book online today at fresha.com/a/glow")
    assert read.read(db, _prospect(db)).status == "skip"


def test_the_handle_comes_from_the_site(db, monkeypatch):
    monkeypatch.setattr(read.references, "_fetch",
                        lambda url: "follow us instagram.com/glow.dxb whatsapp us on wa.me/97150 to book")
    p = read.read(db, _prospect(db))
    assert p.instagram == "glow.dxb" and p.score == 70 and p.site_text


def test_a_handle_the_search_found_is_not_replaced(db, monkeypatch):
    monkeypatch.setattr(read.references, "_fetch", lambda url: "instagram.com/someone.else")
    assert read.read(db, _prospect(db, instagram="glow.dxb")).instagram == "glow.dxb"
