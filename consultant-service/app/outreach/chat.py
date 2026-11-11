"""The report as a few chat messages, readable right in Instagram without a tap.

Built only from the report already checked by write.problems, so the messages
say exactly what the report page says and nothing more. No link here: the link
travels last, in the follow-up line.
"""
from __future__ import annotations

IG_MAX = 1000  # Instagram cuts a direct message at 1000 characters


def _fit(text: str) -> str:
    return text if len(text) <= IG_MAX else text[: IG_MAX - 1].rstrip() + "…"


def messages(report: dict | None) -> list[str]:
    """What we noticed and saw, their assistant answering a customer, then one message per change."""
    if not isinstance(report, dict) or not str(report.get("today") or "").strip():
        return []
    note = str(report.get("sources_note") or "").strip()
    noticed = str(report.get("noticed") or "").strip()
    opening = f"What we noticed: {noticed}\n\n" if noticed else ""
    out = [_fit(f"Here is the short breakdown. {note}".strip() + f"\n\n{opening}What we saw: {report['today'].strip()}")]
    turns = [t for t in report.get("chat") or [] if isinstance(t, dict) and str(t.get("text") or "").strip()]
    if turns:
        lines = [f"{'Customer' if t.get('from') == 'customer' else 'Your assistant'}: {t['text'].strip()}" for t in turns]
        out.append(_fit("Here is how your own AI assistant could answer a customer:\n\n" + "\n".join(lines)))
    for i, c in enumerate(report.get("changes") or [], start=1):
        if not isinstance(c, dict):
            continue
        out.append(_fit(f"{i}. {c.get('change', '').strip()}\n"
                        f"Who does it: {c.get('ai', '').strip()}\n"
                        f"Each day: {c.get('day_to_day', '').strip()}\n"
                        f"For you: {c.get('difference', '').strip()}"))
    return out
