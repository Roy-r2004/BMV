# The s34-full re-measure — 4 briefs, 12 screens, control arm briefs-v2

*Label `s34-full`, requests 84–87, ledger-bracketed 554→673 rows,
$22.1552→$24.5638 (**$2.4087**). Hedgefund (request 88) produced nothing:
the shared OpenRouter key hit 402 on its first anchor call, $0 spent —
the control set is 4 of 5 briefs until it re-runs.*

Produced by [`aggregate_fullset.py`](aggregate_fullset.py). "conf" =
structural defects CONFIRMED by the two-stage check on the shipped
candidate; "best-effort" = nothing was approved and the least-bad
candidate shipped (rank: text-true > defect-free > score).

```
brief      screen                   s33   s34  text claims conf shipped-clean best-effort
dental     analytics                8.1   8.1  True      1    1 NO:malformed_data_display   True
dental     dashboard                8.1   8.5  True      1    0           YES       False
dental     schedule                 8.7   8.1  True      3    0           YES       False
law        analytics                7.5   6.5  True      1    0           YES        True
law        dashboard                7.5   8.0  True      2    0           YES       False
law        pipeline                 8.7   8.1  True      1    0           YES       False
retail     analytics                9.2   9.2  True      2    0           YES       False
retail     customers                9.2   9.2  True      1    0           YES       False
retail     dashboard                8.7   9.2  True      2    0           YES       False
salon      analytics                8.4   9.2  True      1    1 NO:malformed_data_display   True
salon      dashboard                7.9   8.7  True      3    0           YES       False
salon      schedule                 9.1   8.0  True      3    1 NO:malformed_data_display   True

request 84 (dental): $0.6328 (5 image calls — 1 regeneration)
request 85 (law):    $0.7365 (6 image calls — 2 regenerations)
request 86 (retail): $0.5262 (4 image calls — nominal)
request 87 (salon):  $0.5132 (4 image calls — nominal)

screens: 12   below 8: 1   shipped-with-confirmed-defect: 3
total: $2.4087   mean/brief: $0.6022
```

## Reading it honestly

**What died.** No collapsed letterform on any screen inspected (salon and
law nav bands at matched zoom: flawless; retail's s33 "SLB" spot renders
"5lb" correctly this run). No floating backdrop shipped — salon's three
floats were the crop's kill in validation, and no new one survived to
ship. No text-truth failure shipped. No invented AI-module title was
looked for here — this is the v2 CONTROL arm, which cannot carry JOB 5's
fix by design; the v3 arm is blocked on credits.

**What remains, precisely.** All three confirmed shipped defects are
`malformed_data_display` — charts whose plotted marks contradict their own
axis. This was JOB 6's diagnosis before there was an instrument; now it
is an in-path measured rate (3 of 12 screens, all on
analytics/schedule-class screens). The 2K salon analytics chart from the
probe run was correct, so resolution helps sometimes and is not the fix.
Composite the charts in code, one archetype first, owner's eye on it —
exactly as the brief already scoped JOB 6.

**The score clause.** 11 of 12 at ≥8. The exception (law analytics 6.5)
is a best-effort ship where every candidate failed some gate — the
enforced floor cannot conjure an 8 out of two bad rolls, only reroll
once; it shipped the least-bad honestly. s33 shipped four sub-8 screens
silently.

**The money, stated plainly.** Mean $0.6022/brief sits ON the DoD line,
and the distribution is bimodal: nominal briefs land ~$0.52, briefs where
the gates buy regenerations land $0.63–0.74. The gates are working —
each regeneration replaced a candidate carrying a confirmed defect or a
sub-8 score. The owner's options if the mean must come down: accept
defects (turn `ENABLE_DEFECT_CHECK` off — the knob exists), or accept
that a quality-gated request costs ~$0.60 ± $0.14. The projection
(`cost_model.py`) prices nominal at $0.537 and the regeneration tail at
$0.905, both pinned.

**Instrument caveat, so this table is not oversold.** s33's "13 of 15
defective" came from an offline sweep with a per-screen inspector far
more thorough than the in-path check (it read screens at 10–20× zoom and
was allowed magnified text claims). The in-path check is calibrated to
countable structure only. "3 of 12" and "13 of 15" are therefore not the
same instrument and not directly comparable; the honest comparison is
per-class: letterforms 6→0 observed, floats 5→0 shipped, duplicated
panels 3→0 confirmed shipped, charts 4→3. A next-session offline sweep at
s33's thoroughness on this run's screens would be the apples-to-apples
number.
