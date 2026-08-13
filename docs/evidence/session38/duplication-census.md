# Duplication census — all 33 shipped screens, requests 100–120

*2026-08-13. Every screen shipped by requests 100–120 (sessions 37–38),
eye-labelled for a module, panel, card, row, caption or annotation drawn
twice, and compared against what the instruments stored in `qa_issues`.
Counted whole, not sampled: this is the artifact, all of it.*

Labelling is complete on the MISS side — all 21 screens where no
duplication was reported were opened and read. On the precision side the
instruments' own claims are quoted and adjudicated from the text plus the
five screens opened directly; two claims are judged weak rather than
wrong, and are marked.

## Reported (12)

| screen | qa | what the instrument said | verdict |
|---|---|---|---|
| 100 Dashboard | 6.8 | KPI section duplicates New Capital / Risk Alerts / Client Inquiries | real — panel |
| 101 Dashboard | 7.0 | "Sarah Hartwell" repeated in CHOOSE ATTORNEY | real — row |
| 101 Pipeline | 8.1 | axis label duplicated in the tooltip, "slightly redundant" | weak — that is a tooltip doing its job |
| 101 Analytics | 6.5 | (matched the census keyword filter; the claim is about a confusing image, not duplication) | not a duplication claim |
| 102 Analytics | 9.0 | axis tick values 70, 80, 80, 90, 100 | real — duplicated tick |
| 103 Dashboard | 9.2 | "Very High" appears twice in the reorder card | real — label |
| 104 Analytics | 8.7 | `duplicated_panel`: "Apply Model" button appears twice, with coordinates | real — control |
| 105 Pipeline | 7.5 | Y-axis label 9000 repeated | real — duplicated tick |
| 106 Schedule | 7.5 | "the duplicate 'Smart Scheduling' module is a critical flaw" | real — module |
| 106 Analytics | 9.2 | duplicate "Blowout" row with different values | real — row |
| 107 Analytics | 6.8 | "two identical 'Top Artworks' tables are duplicated" | real — module |
| 120 Analytics | 6.5 | duplicate "Top Course Inquiries" module AND duplicate "Avg. Response Time" KPI card | real — module + card |

## Not reported (21) — all opened and read

Clean, confirmed by eye (18): 100 Analytics, 100 Customers, 102 Dashboard,
102 Schedule, 103 Analytics, 103 Customers, 104 Customers, 104 Dashboard,
105 Analytics, 105 Dashboard, 106 Dashboard, 107 Dashboard, 107 Schedule,
108 Analytics, 108 Customers, 108 Dashboard, 119 Conversations,
120 Conversations.

**Missed (3):**

| screen | qa | what is drawn twice | what the instruments said instead |
|---|---|---|---|
| 119 Analytics | 9.2 | the hero caption "Growth Trends", once top-right and once bottom-right of the same image | "a slightly thicker border" on one of them |
| 119 Knowledge | 8.4 | the chart annotation "+150% Week 1 → Week 4", twice on one chart | nothing; the one issue raised was uneven Y-axis ticks |
| 120 Knowledge | 8.5 | the whole "AI Suggestion / Review 'Gift Vouchers' entry" module — same title, same headline, same rationale, different confidence | nothing at all; **shipped approved with a clean sheet** |

## What the count says

Split by WHAT was duplicated rather than by screen:

- **Panels, modules, cards, rows and controls: 8 caught, 1 missed.** The
  instruments are good at this, and precise — 104's claim carries pixel
  coordinates, 107's names the table. The single miss is 120 Knowledge,
  and it is the expensive kind: a full module, on a screen that scored
  8.5 and shipped approved.
- **Text drawn on top of an image or a chart: 0 caught, 2 missed.** Both
  misses are here. A hero caption and a chart annotation are painted over
  imagery rather than laid out as panels, and neither instrument counts
  them — the aesthetic judge saw one and described it as a border weight.

That is a sharper finding than "the judge is unreliable about
duplication", and it points somewhere specific: the blind spot is overlay
text, not structure. `image_defect_inspector.j2`'s `duplicated_panel`
category asks for "the same panel, card, button pair, label or block of
information drawn twice" — an overlay caption is none of those nouns.

## What this does NOT say

The three misses are all on requests 119 and 120, the two console pilots.
That is suggestive and it is not evidence: the console is also the only
archetype whose screens are new, and n=6. Whether overlay-text
duplication is more common on the console or simply more visible there
needs screens the corpus does not yet have.
