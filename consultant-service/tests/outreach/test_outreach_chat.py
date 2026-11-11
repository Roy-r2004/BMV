"""The report as a few chat messages, readable right in Instagram without a tap."""
from app.outreach import chat

REPORT = {"today": "Glow takes bookings by DM.",
          "changes": [{"change": "Answer at once", "ai": "A booking assistant on Instagram",
                       "day_to_day": "Replies and books", "difference": "Nobody waits"},
                      {"change": "Remind before visits", "ai": "A reminder assistant",
                       "day_to_day": "Sends a reminder the day before", "difference": "Fewer empty chairs"}],
          "sources_note": "Read from your website."}


def test_one_message_for_what_we_saw_and_one_per_change():
    msgs = chat.messages(REPORT)
    assert len(msgs) == 3
    assert "Glow takes bookings by DM." in msgs[0] and "Read from your website." in msgs[0]
    assert msgs[1].startswith("1. Answer at once") and "A booking assistant on Instagram" in msgs[1]
    assert "Replies and books" in msgs[1] and "Nobody waits" in msgs[1]
    assert msgs[2].startswith("2. Remind before visits") and "Fewer empty chairs" in msgs[2]


def test_the_messages_say_only_what_the_report_says():
    words = " ".join(chat.messages(REPORT))
    assert "http" not in words and "{link}" not in words


def test_every_message_fits_one_instagram_message():
    long = dict(REPORT, today="x" * 900)
    assert all(len(m) <= chat.IG_MAX for m in chat.messages(REPORT))
    assert len(chat.messages(long)[0]) <= chat.IG_MAX


def test_a_broken_report_gives_no_messages():
    assert chat.messages({}) == [] and chat.messages(None) == []
