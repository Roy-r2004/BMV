"""The report as one image a business sees right in the chat."""
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
