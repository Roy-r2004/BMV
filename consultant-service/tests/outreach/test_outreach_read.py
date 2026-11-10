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


def test_a_site_that_cannot_be_read_is_never_called_missing(db, monkeypatch):
    def blocked(url):
        raise references.Unreadable("403")

    monkeypatch.setattr(read.references, "_fetch_html", blocked)
    p = read.read(db, _prospect(db))
    assert json.loads(p.reasons_json) == ["Its website could not be read automatically"]
    assert p.score == 20 and p.status == "skip"
    assert json.loads(p.signals_json)["site"] == "unreadable"


def test_no_website_at_all_is_said_plainly(db):
    p = read.read(db, _prospect(db, website=None))
    assert p.score == 40 and json.loads(p.reasons_json) == ["No website was found"]
    assert json.loads(p.signals_json)["site"] == "none"


def test_what_the_search_quoted_counts_when_there_is_no_site(db):
    p = _prospect(db, website=None)
    p.what = "a ladies salon\n- Bio: DM to book or WhatsApp 050 000 0000"
    p = read.read(db, p)
    assert p.score == 80 and "Bookings are taken by message or phone" in json.loads(p.reasons_json)


def test_a_business_that_already_books_online_is_skipped(db, monkeypatch):
    assert read.score({"has_site": True, "books_online": True, "books_by_message": False, "shows_whatsapp": False}) == (0, [])
    monkeypatch.setattr(read.references, "_fetch_html", lambda url: "book online today at fresha.com/a/glow")
    assert read.read(db, _prospect(db)).status == "skip"


def test_the_handle_comes_from_the_site(db, monkeypatch):
    monkeypatch.setattr(read.references, "_fetch_html",
                        lambda url: "follow us instagram.com/glow.dxb whatsapp us on wa.me/97150 to book")
    p = read.read(db, _prospect(db))
    assert p.instagram == "glow.dxb" and p.score == 70 and p.site_text


def test_a_handle_the_search_found_is_not_replaced(db, monkeypatch):
    monkeypatch.setattr(read.references, "_fetch_html", lambda url: "instagram.com/someone.else")
    assert read.read(db, _prospect(db, instagram="glow.dxb")).instagram == "glow.dxb"


PAGE = """<html><body><h1>Glow</h1><a href="https://www.fresha.com/a/glow-dubai">Book appointment</a>
<a href="https://wa.me/971500000000">Chat</a><a href="https://instagram.com/glow.dxb">Follow</a></body></html>"""


def test_a_booking_link_is_seen_on_a_real_page(db, monkeypatch):
    monkeypatch.setattr(read.references, "_fetch_html", lambda url: PAGE)
    p = read.read(db, _prospect(db))
    sig = json.loads(p.signals_json)
    assert sig["books_online"] is True and p.status == "skip"
    assert p.instagram == "glow.dxb" and sig["shows_whatsapp"] is True


def test_a_bad_address_from_the_search_does_not_end_the_run(db):
    p = read.read(db, _prospect(db, website="http://[x"))
    assert json.loads(p.signals_json)["site"] == "unreadable"
