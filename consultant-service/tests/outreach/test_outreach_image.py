"""The report as portrait slides a business sees right in the chat."""
from app.outreach import image

REPORT = {"today": "Glow takes bookings by DM <script>alert(1)</script>.",
          "changes": [{"change": "Answer at once", "ai": "A booking assistant", "day_to_day": "Replies and books",
                       "difference": "Nobody waits"}] * 2, "sources_note": "Read from its website."}


def test_the_image_says_only_what_the_report_says_and_escapes_it():
    html = image.html("Glow Salon", "Dubai", REPORT)
    assert "What AI could change for Glow Salon" in html and "Answer at once" in html and "Nobody waits" in html
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_the_image_names_the_firm_and_how_to_reply():
    html = image.html("Glow Salon", "Dubai", REPORT)
    assert "Build My Version" in html and "Reply to this message" in html


def test_a_cover_one_slide_per_change_and_a_close():
    html = image.html("Glow Salon", "Dubai", REPORT)
    assert image.count(REPORT) == 4 and html.count('class="slide"') == 4
    assert "1 / 4" in html and "4 / 4" in html and "Change 2 of 2" in html


def test_slides_are_drawn_once_and_forgotten_on_request(monkeypatch):
    drawn = []
    monkeypatch.setattr(image, "draw", lambda html: drawn.append(1) or [b"a", b"b", b"c", b"d"])
    assert image.slides_for("tok1", "Glow Salon", "Dubai", REPORT) == [b"a", b"b", b"c", b"d"]
    assert image.slides_for("tok1", "Glow Salon", "Dubai", REPORT) == [b"a", b"b", b"c", b"d"]
    assert len(drawn) == 1
    image.forget("tok1")
    image.slides_for("tok1", "Glow Salon", "Dubai", REPORT)
    assert len(drawn) == 2
