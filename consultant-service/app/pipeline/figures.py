"""What is left of the consultation's first number checker.

Every number a client reads is now read and checked by `app.figures`: the
reader (`read`), the binder (`bind`) and the one set of figures a request knows
(`known`). There is no leniency there: a small number is a number, and so is a
number word. What stays here is not a checker:

  * `CONSTANTS`, the calendar constants arithmetic may use without anyone
    having said them (the move's terms, `answer._term`);
  * `quoted`, whether a fragment we put in their mouth is really in what they
    wrote (the week's quote, the interview's facts and case file).
"""

import re

#: Constants arithmetic may use without anyone having said them.
CONSTANTS = {52: "weeks a year", 12: "months a year", 7: "days a week", 365: "days a year",
             4: "weeks a month", 4.33: "weeks a month", 30: "days a month", 24: "hours a day",
             60: "minutes an hour"}


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("’", "'").replace("“", '"').replace("”", '"')).strip().casefold()


def quoted(fragment: str, texts) -> bool:
    """Whether `fragment` is really in what they wrote — a quote we put in
    their mouth must be one they said."""
    frag = normalise(fragment).strip(" .\"'")
    if len(frag) < 3:
        return False
    return any(frag in normalise(t) for t in texts or [] if t)
