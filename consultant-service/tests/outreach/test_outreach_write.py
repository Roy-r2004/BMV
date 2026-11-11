"""A report that says only what was read."""
import json

from outreach_helpers import reply

from app.outreach import write

READ = "Glow Salon, JLT. Rated 4.8. DM us to book. Open 10am to 10pm."
CHANGE = {"change": "Answer booking messages at once", "ai": "A booking assistant on Instagram",
          "day_to_day": "It replies to every DM, offers the free slots and books them",
          "difference": "No one waits for a reply to book"}
CHAT = [{"from": "customer", "text": "Do you do balayage?"},
        {"from": "assistant", "text": "Yes, Glow Salon does balayage. Shall I book it for you?"},
        {"from": "customer", "text": "Yes please, this weekend."},
        {"from": "assistant", "text": "I'll pass it to the team to confirm a time with you."}]
GOOD = {"noticed": "Every booking at Glow Salon goes through Instagram DMs.",
        "today": "Glow Salon takes bookings by DM and is rated 4.8.", "chat": CHAT, "changes": [CHANGE, CHANGE],
        "sources_note": "Read from the salon's website."}
GOOD_DM = "Hi Glow team, I saw that bookings at Glow Salon go through DMs. I made you a short breakdown of how AI could answer them. Want me to send it?"
GOOD_FOLLOW = "Here it is. The same thing as a page, if that is easier to read: {link}"


def test_a_clean_draft_passes():
    assert write.problems(GOOD, GOOD_DM, READ, GOOD_FOLLOW) == []


def test_a_report_with_an_unread_number_is_refused():
    bad = {**GOOD, "today": "You lose 40 bookings a week to slow replies."}
    assert write.problems(bad, GOOD_DM, READ, GOOD_FOLLOW)


def test_a_number_in_words_with_a_unit_is_checked_too():
    assert write.problems({**GOOD, "today": "Replies take three hours."}, GOOD_DM, READ, GOOD_FOLLOW)


def test_a_percentage_that_was_not_read_is_refused():
    assert write.problems({**GOOD, "today": "This could lift bookings 30%."}, GOOD_DM, READ, GOOD_FOLLOW)


def test_a_guess_is_refused():
    assert write.problems({**GOOD, "today": "Customers likely reach you by phone."}, GOOD_DM, READ, GOOD_FOLLOW)
    assert write.problems({**GOOD, "today": "Perhaps you take walk-ins."}, GOOD_DM, READ, GOOD_FOLLOW)


def test_a_claim_about_past_clients_is_refused():
    assert write.problems(GOOD, "We helped salons in Dubai do this. Want to see?", READ, GOOD_FOLLOW)


def test_a_dm_without_the_link_or_too_long_is_refused():
    assert write.problems(GOOD, GOOD_DM, READ, "Here it is.")
    assert write.problems(GOOD, "x" * 401 + "?", READ, GOOD_FOLLOW)


def test_a_report_with_too_few_changes_is_refused():
    assert write.problems({**GOOD, "changes": [CHANGE]}, GOOD_DM, READ, GOOD_FOLLOW)


def _prospect(db):
    from app.models import Prospect
    from app.outreach import new_token

    p = Prospect(token=new_token(), name="Glow Salon", city="Dubai", kind="salon", key=f"k-{new_token()}",
                 phone="+971 4 555 1234", what="a salon in JLT", site_text=READ, sources_json="[]",
                 reasons_json=json.dumps(["Bookings are taken by message or phone"]), status="ready", score=60)
    db.add(p)
    db.commit()
    return p


def test_a_draft_still_wrong_after_the_second_try_skips_the_business(db, monkeypatch):
    bad = json.dumps({"report": {**GOOD, "today": "You lose 40 bookings a week."}, "dm": GOOD_DM, "followup": GOOD_FOLLOW})
    calls = []
    monkeypatch.setattr(write.provider, "chat", lambda *a, **k: calls.append(1) or reply(bad))
    p = write.write(db, _prospect(db))
    assert p.status == "skip" and len(calls) == 2 and p.dm_text is None
    assert "The draft could not be written from what was read" in json.loads(p.reasons_json)


def test_a_good_draft_is_kept_with_its_link_placeholder(db, monkeypatch):
    monkeypatch.setattr(write.provider, "chat", lambda *a, **k: reply(json.dumps({"report": GOOD, "dm": GOOD_DM, "followup": GOOD_FOLLOW})))
    p = write.write(db, _prospect(db))
    assert p.status == "ready" and "{link}" not in p.dm_text and "{link}" in p.followup_text and json.loads(p.report_json)["today"] == GOOD["today"]


def test_the_model_sees_no_more_than_was_read(db, monkeypatch):
    seen = []

    def chat(model, messages, **k):
        seen.append(messages[0]["content"])
        return reply(json.dumps({"report": GOOD, "dm": GOOD_DM, "followup": GOOD_FOLLOW}))

    monkeypatch.setattr(write.provider, "chat", chat)
    write.write(db, _prospect(db))
    assert "DM us to book" in seen[0] and "555 1234" not in seen[0]


def test_curly_quotes_do_not_hide_a_claim():
    assert write.problems(GOOD, "We\u2019ve helped many salons. Want it?", READ, GOOD_FOLLOW)
    assert write.problems(GOOD, "We\u2019ve worked with clinics like yours. Want it?", READ, GOOD_FOLLOW)


def test_more_number_words_and_numbers_touching_letters_are_checked():
    for bad in ("Save twenty hours a week.", "Halve your no-shows.", "It costs AED250.", "Double your bookings."):
        assert write.problems({**GOOD, "today": bad}, GOOD_DM, READ, GOOD_FOLLOW), bad


def test_a_claim_that_they_are_losing_out_is_refused():
    assert write.problems({**GOOD, "today": "You may be missing bookings at night."}, GOOD_DM, READ, GOOD_FOLLOW)


def test_a_model_outage_leaves_the_business_to_try_again(db, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(write.provider, "chat", down)
    p = write.write(db, _prospect(db))
    assert p.status == "ready" and p.dm_text is None
    assert write.COULD_NOT not in json.loads(p.reasons_json)


def test_the_first_message_carries_no_link():
    assert write.problems(GOOD, "Hi Glow team, here is a page: {link} Want it?", READ, GOOD_FOLLOW)
    assert write.problems(GOOD, "Hi Glow team, see https://buildmyversion.com. Want it?", READ, GOOD_FOLLOW)


def test_the_first_message_asks_before_sending_anything():
    assert write.problems(GOOD, "Hi Glow team, I made you a short breakdown.", READ, GOOD_FOLLOW)


def test_the_report_opens_with_what_we_noticed_about_them():
    assert write.problems({**GOOD, "noticed": ""}, GOOD_DM, READ, GOOD_FOLLOW)


def test_the_sample_chat_starts_with_the_customer_and_has_four_to_six_turns():
    assert write.problems({**GOOD, "chat": CHAT[:2]}, GOOD_DM, READ, GOOD_FOLLOW)
    assert write.problems({**GOOD, "chat": CHAT[1:] + CHAT[:1]}, GOOD_DM, READ, GOOD_FOLLOW)
    assert write.problems({**GOOD, "chat": [{"from": "bot", "text": "hi"}] + CHAT[1:]}, GOOD_DM, READ, GOOD_FOLLOW)


def test_the_sample_chat_never_invents_a_price_or_a_time():
    bad = CHAT[:3] + [{"from": "assistant", "text": "We have 3pm free, it costs 450 AED."}]
    found = write.problems({**GOOD, "chat": bad}, GOOD_DM, READ, GOOD_FOLLOW)
    assert any("450" in f for f in found) and any("3" in f for f in found)
