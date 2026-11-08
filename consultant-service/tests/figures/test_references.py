"""A published figure counts only after code has found it on the page."""
import json
from decimal import Decimal

import pytest

from app.figures import references
from app.figures.known import known_for

URL = "https://www.example.org/prices"
PAGE = "Home cleaning in Dubai. Book your service for as low as AED 30 per hour with vetted cleaners. Market worth AED 1,250 million."
GOOD = {"number": "30", "unit": "AED", "period": "hour", "what": "lowest hourly price, Dubai", "url": URL,
        "quote": "book your service for as low as AED 30 per hour", "publication": "Example", "year": 2026}


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(references, "_fetch", lambda url: PAGE)


def test_a_number_found_on_the_cited_page_becomes_a_reference(page):
    [f] = references.confirm([GOOD], {URL})
    assert f.id == "REF-1" and f.kind == "reference" and f.value == Decimal("30") and f.source.url == URL


def test_the_published_figure_says_when_it_was_read(page):
    [f] = references.confirm([{**GOOD, "year": 0}], {URL})
    assert "read" in f.source.publication and f.source.year >= 2026


def test_a_number_that_is_not_on_the_page_is_dropped(page):
    assert references.confirm([{**GOOD, "number": "45"}], {URL}) == []


def test_a_right_number_beside_the_wrong_words_is_dropped(page):
    assert references.confirm([{**GOOD, "quote": "the average monthly salary of a nurse in Riyadh"}], {URL}) == []


def test_a_number_inside_a_larger_one_does_not_count():
    assert not references.on_the_page("25", "market worth million dirhams cleaning", "cleaning market worth 1250 million dirhams")


def test_thousands_separators_match():
    assert references.on_the_page("1250", "market worth million cleaning", "cleaning market worth AED 1,250 million")


def test_a_quote_too_short_to_check_is_dropped():
    assert not references.on_the_page("30", "AED 30", PAGE)


def test_an_address_the_search_did_not_cite_is_never_opened(monkeypatch):
    def boom(url):
        raise AssertionError("fetched an address the search never cited")

    monkeypatch.setattr(references, "_fetch", boom)
    assert references.confirm([GOOD], {"https://other.example.org/"}) == []


def test_a_page_that_cannot_be_read_is_dropped(monkeypatch):
    def blocked(url):
        raise references.Unreadable("403")

    monkeypatch.setattr(references, "_fetch", blocked)
    assert references.confirm([GOOD], {URL}) == []


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://localhost:8002/", "http://169.254.169.254/latest/meta-data/",
                                 "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "ftp://example.org/x"])
def test_a_model_supplied_address_cannot_reach_inside(url):
    with pytest.raises(references.Unreadable):
        references._fetch(url)


def test_a_redirect_into_the_private_network_is_refused(monkeypatch):
    class Hop:
        is_redirect = True
        headers = {"location": "http://127.0.0.1/secret"}
        extensions = {"network_stream": _Stream("93.184.216.34")}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(references, "_public", lambda host: host != "127.0.0.1")
    monkeypatch.setattr(references.httpx, "stream", lambda *a, **k: Hop())
    with pytest.raises(references.Unreadable):
        references._fetch("https://www.example.org/")


class _Stream:
    def __init__(self, peer):
        self.peer = peer

    def get_extra_info(self, name):
        return (self.peer, 443) if name == "server_addr" else None


def _serve(monkeypatch, peer, chunks):
    class Page:
        is_redirect = False
        status_code = 200
        encoding = "utf-8"
        headers = {"content-type": "text/html"}
        extensions = {"network_stream": _Stream(peer)}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_bytes(self):
            return chunks

    monkeypatch.setattr(references, "_public", lambda host: True)
    monkeypatch.setattr(references.httpx, "stream", lambda *a, **k: Page())


def test_a_page_at_a_public_address_is_read(monkeypatch):
    _serve(monkeypatch, "93.184.216.34", [b"<p>AED 30</p>"])
    assert references._fetch("https://www.example.org/") == "aed 30"


def test_a_name_that_turns_private_after_the_check_is_refused(monkeypatch):
    _serve(monkeypatch, "127.0.0.1", [b"<p>the inside of the network</p>"])
    with pytest.raises(references.Unreadable):
        references._fetch("https://www.example.org/")


def test_a_connection_that_cannot_say_where_it_went_is_refused(monkeypatch):
    _serve(monkeypatch, "", [b"<p>somewhere</p>"])
    with pytest.raises(references.Unreadable):
        references._fetch("https://www.example.org/")


def test_a_page_that_drips_is_given_up_on(monkeypatch):
    clock = [0.0]

    def drip():
        for _ in range(1000):
            clock[0] += 1.0
            yield b"x"

    monkeypatch.setattr(references.time, "monotonic", lambda: clock[0])
    _serve(monkeypatch, "93.184.216.34", drip())
    with pytest.raises(references.Unreadable):
        references._fetch("https://www.example.org/")


def test_the_search_for_pages_has_one_clock(monkeypatch):
    clock = [0.0]
    opened = []

    def slow(url):
        opened.append(url)
        clock[0] += 40.0
        raise references.Unreadable("slow")

    monkeypatch.setattr(references.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(references, "_fetch", slow)
    urls = [f"https://www.example.org/{n}" for n in range(6)]
    assert references.confirm([{**GOOD, "url": u} for u in urls], set(urls)) == []
    assert len(opened) == 2


def test_the_text_of_a_page_leaves_out_the_code():
    html = "<HTML><Script type=x>var a = 99;</SCRIPT><style>p{top:1}</style><p>Book at <b>AED 30</b></p></html>"
    assert references._text(html) == "book at aed 30"


def test_a_stray_angle_bracket_keeps_the_words_after_it():
    assert references._text("price a < b and more") == "price a < b and more"


def test_markup_built_to_stall_the_reader_does_not():
    import time as clock

    started = clock.perf_counter()
    for html in ("<script>" * 250_000, "<" * 2_000_000, "<a " * 650_000, "</script" * 250_000):
        references._text(html)
    assert clock.perf_counter() - started < 3.0


def test_the_number_of_references_is_bounded(page):
    from app.config import settings
    assert len(references.confirm([GOOD] * 40, {URL})) == settings.REFERENCES_MAX


def _row(**kw):
    from app.models import Request
    return Request(**{**dict(business_name="X", business_description="d", email="e@x.co", main_problem="Is there a business?"), **kw})


def test_confirmed_figures_join_what_the_request_knows_and_can_be_cited(page):
    from app.figures.model import as_json
    [f] = references.confirm([GOOD], {URL})
    row = _row(references_json=json.dumps([as_json(f)]))
    assert known_for(row).get("REF-1") == f
    [claim] = references.as_claims(row)
    assert claim["id"] == "REF-1" and "published" in claim["source"]


def test_a_failed_search_means_no_references_not_a_stopped_run(monkeypatch):
    from app.database import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    row = _row()
    db.add(row)
    db.commit()

    def down(*a, **k):
        raise RuntimeError("search down")

    monkeypatch.setattr(references.provider, "chat", down)
    references.write(db, row.id)
    db.refresh(row)
    assert row.references_json is None
    db.delete(row)
    db.commit()
    db.close()
