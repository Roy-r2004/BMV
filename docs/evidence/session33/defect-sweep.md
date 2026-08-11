# The per-screen defect sweep — session 33

*15 independent inspectors, one per shipped screen of the golden set. Every
claim was then handed to a separate verifier told to REFUTE it, defaulting to
refuted when uncertain; only survivors are listed. Text-spelling claims were
forbidden unless the inspector had magnified the exact text at 4× or more —
this project has twice had judges invent misspellings that were not there.*

**Clean: 2 of 15** — dental/dashboard, hedgefund/analytics_overview.

**Carrying a verified defect: 13 of 15.** 16 further claims were made and refuted.

I disagree with the two clean verdicts: I read a duplicated
"Book Appointment"/"Reschedule" pair on dental's dashboard and a floating
frame with two cards hanging outside it on hedgefund's analytics overview.
13/15 is therefore the conservative number, not the alarmist one.

## dental/schedule

- **prompt_scaffolding_as_ui** — title of the bottom-right panel, next to Practitioner Availability: Panel titled "Premium Intelligence" above the "Fill 11 AM slot" recommendation — reads like the renderer brief for the AI-insight panel rather than a product label a dental practice would ship (compare "AI Suggestions" / "Recommended Action")

## dental/analytics

- **garbled_axis_or_label** — y-axis of the "Recall Engagement" chart, right-hand card of the middle row: Five evenly-spaced gridlines are labelled 60 / 50 / 40 / 20 / 0 top to bottom — equal pixel spacing (~43px each) but unequal value steps of 10, 10, 20, 20, so the scale is nonsensical. Verified at 10x magnification; the glyphs themselves are crisp. Related: the Jan data point labelled "30" is plotted below the 20 gridline, so the series does not sit on its own axis.
- **prompt_scaffolding_as_ui** — eyebrow label at the top of the bottom-right card, above "Prioritize lapsed patients": The card is titled "OPINION" in all caps — a renderer-section name rather than a product label a dental practice would ship (e.g. "Recommendation" or "Insight"). Same family as the "SOFTWARE-FORMED OPINION" scaffolding heading.

## law/dashboard

- **prompt_scaffolding_as_ui** — eyebrow label at the top-left of the insight card in the upper-right quadrant, directly above "Prioritize high-value leads": The card's kicker reads "HERO INTELLIGENCE" (verified at 4x magnification). "HERO" is renderer/layout vocabulary for the lead slot, not a product label a law firm would ship; it matches the known scaffolding family ("HERO ASSET", "ONLY AI INTELLIGENCE").

## law/pipeline

- **duplicated_panel** — bottom row of the page — the left card (x≈50-695) and the right card (x≈715-1360), spanning the full width below the three main panels: The same recommendation card is drawn twice, side by side: identical eyebrow "SOFTWARE-FORMED OPINION", identical headline "Automate routine follow-ups", identical subtitle "High volume, standardized information required", and the identical three chips "Document Collection · Reminder Set · Client Nurture". Verified at 3x magnification on both cards; the only difference is the 95% reliable ring present on the right copy.
- **prompt_scaffolding_as_ui** — eyebrow label at the top-left of each of the two bottom cards (left card y≈552, right card y≈552): Both cards are titled "SOFTWARE-FORMED OPINION" — a renderer-facing description of what the panel is supposed to contain rather than a product label a law firm would ship (e.g. "Recommended action"). Confirmed legible at 3x on both instances.

## law/analytics

- **duplicated_panel** — top-right column (x~1096-1358, y~230-405) and centre column below the chart (x~712-1076, y~520-710): The "Attorney Performance" card is drawn twice, with the identical title, the identical divider, and the identical four rows and values: S. Hartwell 6, M. Grey 4, E. Chen 5, D. Kim 3. Only difference is that the lower copy adds a coloured dot per row; the data is byte-for-byte the same list.
- **prompt_scaffolding_as_ui** — eyebrow label at the top of the right-hand insight card, above "Boost Estate Planning leads" (x~1114-1255, y~447-460): A small-caps label reading "ONLY AI INTELLIGENCE" — this is renderer instruction language, not a product label for an insight card.
- **other** — "Weekly Consults" chart, centre-top card (x~712-1076, y~230-490): Tick labels carry values that contradict the plotted series: the highlighted marker and its "Thu, 5" tooltip sit at y=335px, which calibrates to 7.3 on the axis (0 at y=452.5, 10 at y=291), not 5; likewise "Mon 3" is plotted at 4.0. Also the header reads "+0% Mon -> Fri" while Mon and Fri labels are 3 and 3. Data/label inconsistency rather than a rendering-structure fault, so flagging it only for the parent to weigh.

## retail/analytics

- **garbled_axis_or_label** — third column of the configurator, "3 CONFIGURE BAG", rows 3 and 4 (~y 292 and y 320): Size options read "WHOLE BEAN SLB" and "GROUND SLB". Magnified at 10x, the first character is unambiguously a letter S (full double curve) — compared side by side with the real digit 5 in "$4,850", which has a flat top bar and straight upper-left stem. "SLB" is not a unit; in a column whose other rows are "12OZ" it is a mangled "5LB".
- **prompt_scaffolding_as_ui** — eyebrow label at the top-left of the forecast card, bottom-left of the app (~x 85, y 558): Small caps label "PREMIUM AI INTELLIGENCE" sitting above "Forecast House Blend reorder". It reads as a renderer instruction / prompt section heading about the panel's content rather than a product label, and is near-identical in form to the known scaffolding leak "ONLY AI INTELLIGENCE".
- **prompt_scaffolding_as_ui** — primary pill button at the far right of the top navigation bar (~x 1274-1344, y 45-73): The header's primary CTA is labelled simply "Action" (confirmed legible at 3x). That is a template slot name, not a product label — no verb or object the roaster would act on.

## retail/dashboard

- **window_chrome** — the whole frame — a margin of backdrop runs around all four sides of the app: The application is drawn as a rounded-corner floating card sitting on a brown gradient backdrop: bare backdrop from x=0..~35 on the left, y=0..~32 above the header, x~1372..1408 on the right, and a gap between the card's bottom edge (~y=737) and the black brand strip (~y=765), with rounded corners and a drop shadow visible at 5x in both top corners. No OS title bar or traffic-light buttons are present, but the app is not edge to edge — this is the 'application floating as a rounded card/window on a backdrop' framing.
- **prompt_scaffolding_as_ui** — eyebrow label at the top-left of the large AI panel, right column above 'Recommend roast for Ethiopia': A small caps label reading 'PREMIUM AI INTELLIGENCE' sits above the headline. Verified at 4x; characters are clean. It is a renderer-facing description turned into a panel title — the same family as the previously logged 'ONLY AI INTELLIGENCE' / 'SOFTWARE-FORMED OPINION' leaks, and the module is specified to have no title with nothing written above the headline (app/pipeline/prompt_builder.py:488-490: 'given real size and premium treatment... the module has no separate title, and nothing whatever is written above that headline').
- **blank_or_unlabelled_control** — the row of four metric cards along the top of the right column: All four stat cards carry a bare number (245, 3, 6, 2) and a delta caption ('-2 change', '-2 change', '-1 change', '+2 change') with no metric name whatsoever — nothing identifies what any of the values measure. Contrast-boosted crops of the space above the numbers and below the captions confirm no faint or clipped label is present; the labels are simply absent (the KPI block sends label + value + delta, so the label was dropped).
- **prompt_scaffolding_as_ui** — the accented pill button at the far right of the top navigation bar: The primary button is labelled 'Action' (verified at 5x, characters clean). No action string is supplied to the model; the nav block only describes 'a single accented action button at the right' (app/pipeline/prompt_builder.py:372), so the prompt's own descriptive word has been rendered as the button's label rather than a product action such as 'New Order'.

## retail/customers

- **prompt_scaffolding_as_ui** — eyebrow label at the top of the right-hand recommendation card, above "Offer loyalty discount to John Smith": The card is titled "INTELLIGENCE MODULE" — a renderer/module descriptor rather than a product section name (a real product would say e.g. "Recommended action" or "AI insight"). Same family as the known scaffolding leaks like "ONLY AI INTELLIGENCE" / "SOFTWARE-FORMED OPINION".
- **prompt_scaffolding_as_ui** — floating over the hero photo: a tag chip straddling the photo's top edge, and a switch at the photo's top-right: Two orphan controls labelled "Price" (tag chip, half on the page background, half on the photo) and "Configuration" (labelled switch) sit on a decorative product photo where neither has anything to act on — they read as generic renderer-supplied control labels rather than product affordances on a customers page. Text itself is clean at 4x.

## salon/dashboard

- **garbled_axis_or_label** — left "3. PICK TIME SLOT" panel, selected chip in the middle of the first row (approx x=205-270, y=585-610): The selected time chip renders as "10:1S AM" — the final character is an S glyph (smooth curved top terminal, no flat top bar), not a digit 5. Verified at 12x and side-by-side at 16x against the correctly formed "10:15 AM" in the Booking Details card, where the 5 clearly has a flat horizontal top stroke and straight left descender.
- **garbled_axis_or_label** — right column, "Recommend Add-on: Deep Conditioning" card, first line of body copy: Reads "High-value clients beoking full color services often upgrade." — the word is drawn b-e-o-k-i-n-g, with a clear crossbarred 'e' as the second character. Verified at 8x and 14x magnification.

## salon/schedule

- **garbled_axis_or_label** — top navigation bar, third item (between "Schedule" and "Services"): The nav label reads "Cilents", not "Clients". Verified at 14x and 20x nearest-neighbour, plus a pixel profile: the first stroke after the C peaks at 160 on y=47, drops to 48 on y=48 (a dot with a gap = 'i'), while confirmed full ascenders elsewhere in the same nav (the 'l' in "Schedule") show a continuous ~185 column with no break.
- **garbled_axis_or_label** — last visible row of the FULL DAY VIEW list (left column), the 1:30 PM group: "Charlotte Moore (Cot)" — the service tag is a closed 'o' where every other row in the same list uses "(Cut)". Verified at 9x stacked directly against "Isabella King (Cut)" two lines above: the 'u' is open-topped with a right stem, the character here is a closed bowl.
- **duplicated_panel** — 12:00 PM row of the FULL DAY VIEW list, left column: The word "Break" is drawn five times tiled as a 3-across + 2-across grid, while every other time group in the same table lists one entry per line in a single column. The tiling also pushes "James Wilson (Cut)" under the STATUS column header, where it wraps onto a second line.
- **other** — over the hero photo in the centre column — one on the left cabinet edge, one on the right end of the reception desk: Two glossy 3D mouse-cursor arrows are baked into the photograph, each with an attached empty badge (a blank pink pill on the left one, a blank dark circle on the right one). They are not part of the room and carry no label or function.
- **blank_or_unlabelled_control** — header stat strip, third and fourth metrics (top right): Two of the four header metrics carry a value and a delta but no metric name anywhere on the screen: a bare "0" with "-1 vs yesterday", and "$1,420" with "+$180 today". The reader cannot tell what the 0 counts.

## salon/analytics

- **garbled_axis_or_label** — Weekly Revenue Trend card, lower-left quadrant — the y-axis and the per-point value labels: The plotted series does not sit on the axis it is labelled against. Measured tick centres: 0 = y654, 2000 = y622, 4000 = y590, 6000 = y557, 8000 = y525 (32.25 px per 2000). The Wk 1 marker centre is at y619, i.e. ~2,170 on that scale, yet it is labelled 5800; Wk 2 sits at ~2,900 labelled 6100; Wk 3 at ~3,950 labelled 6500; Wk 4 at ~5,600 labelled 6800; Wk 5 at ~6,450 labelled 7100. Only Wk 6 (~7,450) matches its 7,500 callout. At 8x the '5800' label is visibly floating above a dot that rests exactly on the 2000 gridline, so the axis is meaningless for five of the six points.
- **garbled_axis_or_label** — Popular Services panel, right column — second table row, service name cell: The service name renders as 'Full Highiights': the 'l' of 'Highlights' is drawn as a dotted i. Verified at 10x and by per-column pixel analysis of the glyph strip — the 5th glyph after 'High' has a dot at y6-7, a gap at y8, then a stem from y9-17, identical to the neighbouring 'i' and unlike the continuous full-height 'l' strokes in 'Full' (y6-17 with no break).
- **window_chrome** — outer frame of the whole image — pink backdrop visible left, top, right and below the app: The application is drawn as a rounded, drop-shadowed floating window inset on a pink desktop backdrop (card spans x29-1347, y26-742 in a 1376x814 image) rather than filling the frame edge to edge. No OS title bar, traffic-light buttons or browser frame are present, so this is only the floating-window presentation, not literal chrome — flagging as unsure for that reason. The dark strip with the round logo at the very bottom is treated as the intended brand mark and is not counted.

## hedgefund/performance_dashboard

- **duplicated_panel** — right sidebar (lower half of the "Top Performers" card, ~x1100-1270 / y375-480) and again as a standalone card below the photo (~x712-948 / y535-690): The "Recent Trades" panel is drawn twice with byte-identical content: heading "Recent Trades" followed by GOOGL / Buy / $500k, JPM / Sell / $300k, KO / Buy / $250k. Verified by cropping and magnifying both regions (4x and 3x) — same three rows, same tickers, same amounts, same Buy/Sell colouring.

## hedgefund/clients_overview

- **garbled_axis_or_label** — top navigation bar, 5th item, between "Clients" and "Reports" (approx. x=735-800, y=20-40): The nav item is drawn as "Portfollo" — cropped and magnified at 10x, the two characters after "Portfo" are both full-height dotless "l" strokes. Compared side by side at the same 10x with the "i" in the adjacent "Clients" tab (visibly shorter with a separate dot), the character that should be an "i" is rendered as a second "l". The glyph itself is malformed, not just a wording choice.
- **window_chrome** — the full frame — left and right edges of the image: The application is not edge to edge: it is drawn as a rounded-corner floating card with a drop shadow sitting on a plain white page. Measured, the dark app surface spans only x=138 to x=1269, leaving ~138px of blank white gutter down the entire left side and the entire right side. There is no OS title bar and no minimize/maximize/close buttons and no browser UI, but the presentation is a window/device mockup framing rather than the app alone. (The full-width dark strip with the round logo at the very bottom is the intended brand mark and is not counted here.)
- **other** — "Client AUM Growth" chart, first data point at Q1 '23 (approx. x=897, y=616): The point-value label and the plotted position disagree. The first marker's centre sits exactly on the "165" y-axis gridline, but it is labelled "160"; the axis floor 160 gridline is a full band below it. Verified at 6x with the y-axis tick and the marker in the same crop. The remaining points are also loosely placed against their labels (the "175" marker sits nearer 172-174), so the series does not read against its own axis.
