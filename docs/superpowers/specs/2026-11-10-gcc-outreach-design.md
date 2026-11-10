# GCC outreach: find businesses, write them a report, Roy sends the DM

Date: 2026-11-10. Owner: Roy. Status: approved by Roy on 2026-11-11.

## Why

BMV is an AI consultancy. Roy wants clients, as many as he can get. This is a
second way in, separate from the $200 consultation. A business gets a free,
specific report showing what it could change and which AI would do it. If
the business is interested, it gets in touch and Roy runs a call. The
consultation product is not part of this pitch.

## What it does, start to finish

1. **Find.** The pipeline finds businesses in the GCC from public sources and
   keeps the ones that would gain most.
2. **Read.** For each one it reads what is public: what a web search returns
   about it (category, area, rating and review snippets where shown, with the
   pages they came from), its website, and its Instagram handle.
3. **Judge.** It scores how much the business would gain, from signs such as:
   bookings or orders taken only by DM or phone, no booking link, a slow, broken
   or missing website, or reviews complaining about replies or waiting.
4. **Write.** For each business above the bar it writes:
   - a private report page on the BMV site, made for that one business;
   - a short Instagram DM with the link to that page.
5. **Queue.** It puts them on a daily list for Roy, best first.
6. **Roy sends.** He opens the list, copies the message, pastes it into
   Instagram by hand and ticks it as sent. Nothing is ever sent automatically.

## The report page

- A page on the BMV site at an unguessable address, one per business. It
  does not appear in search engines or in any public list.
- In English.
- It covers what the business does today, as seen from outside; two or three
  specific changes; which AI does each change and what it would do day to day;
  and what each change would make different for them.
- It ends with a "book a call" button. The button opens an email to
  consulting@buildmyversion.com with the business name already in the subject.
- It looks like the BMV site: the approved white film look.
- It records when it was opened, so Roy can see who looked.

## The DM

- In English, short: a few lines and the link.
- It names one specific thing about the business, so it is plainly not a mass
  message.
- No claims that BMV has done this for others, no client names, no results.

## Roy's daily list

- Visible only to Roy, behind the existing admin sign-in.
- Each row shows the business, its Instagram handle linked to its profile, why
  it was picked, the message ready to copy, and the report link.
- Roy can mark each row as sent, replied, call booked, not interested, or
  skip. A business marked anything other than "skip" is never offered again.
- Pace: Instagram restricts accounts that send many cold DMs. The list offers
  about 30 a day by default, and Roy can change that number. Messages are never
  sent from the pipeline.

## Where it looks

- Start in Dubai with businesses that take bookings or orders by DM: clinics,
  salons, gyms, restaurants and real-estate agents.
- Then Riyadh, Doha, Abu Dhabi, Kuwait City, Manama and Muscat.
- City and type are settings, so new ones need no code.

## Rules it must keep

- **Facts only.** Every statement about a business comes from something public
  that the pipeline read, and the report says what it was read from. No
  invented numbers, revenue, customer counts or results. No invented BMV
  clients, team members or case studies. The number checks already in the
  consultation (`app/figures/law.py`) are the model to follow.
- **No logging in, no bulk scraping.** The pipeline never signs into Instagram
  and never scrapes it. Instagram is used only for the handle and the profile
  link Roy opens himself. Businesses are found with the web-search model the
  consultation already uses; Google Maps is not used.
- **Safe fetching.** Websites are fetched with the guards already in
  `app/figures/references.py`: public addresses only, a size limit, a time
  limit, and redirects checked.
- **Privacy.** Only business information is kept, never personal details of
  staff or reviewers. Review text is used to judge and is not quoted with names.
  The UAE and Saudi data-protection laws apply.
- **Nothing reaches a business without Roy.** He sends every message himself.

## Goals

- A steady list of well-chosen businesses, ready each morning.
- Reports specific enough that a business owner recognises their own business.
- A clear record of what was sent and what came back.

## Not in this version

- Arabic.
- Sending DMs, emails or WhatsApp automatically.
- Follow-up messages.
- Countries outside the GCC.
- A paid tier or a link to the $200 consultation.

## What would make it a failure even if it works

- A report that says something untrue about a business.
- Roy's Instagram account restricted because the pace was too high.
- A report page that a stranger could find or list.
- Generic messages that read like spam.

## Decided by Roy

- A free report, separate from the $200 consultation; the goal is a call.
- Roy sends every DM by hand on Instagram.
- English only.
- "Book a call" goes to consulting@buildmyversion.com.
- As many as he can send.
- Businesses are found with the web-search model plus their own websites, not
  Google Maps.
- Spending is capped at $100 a month for searches and AI writing. When the cap
  is reached, the pipeline stops finding new businesses until the next month,
  and the list says so.

## My calls (Claude's, open to change)

- About 30 a day by default, adjustable.
- Start with Dubai and the five business types above.
- Instagram is not read at all. This changes what I first told Roy: I had said
  the pipeline would read public Instagram profiles. Instagram now needs a
  login for most profile pages, and reading them without one breaks its terms.
- The report is a web page, not a PDF, because Instagram DMs cannot carry files.

## Settled after the builder check (Claude's calls, open to change)

- **Finding the handle.** From the business's own website first, then from a
  web search for its Instagram account. If neither finds one, the business
  still goes on the list with its map link and phone, marked "find the handle",
  so Roy can look it up himself.
- **"Takes bookings by DM or phone".** Judged from the website and the listing:
  no booking link or form, "DM to book" or "WhatsApp us" wording, or a missing
  website. Nothing else counts as proof.
- **The bar.** Each business is scored, and the ones that clear a fixed score go
  on the list, best first, up to the daily number. Some days there may be fewer.
- **Opens.** Only the time is kept, with no IP address or device. Visits from
  link-preview bots (Instagram's, WhatsApp's) are not counted.
- **The page tells the truth about itself.** It says it was made from public
  information and names the sources. It also offers a "remove this page" link
  that emails consulting@buildmyversion.com, and the page is taken down when
  that email arrives.
- **Retention.** Data about a business marked "not interested" or "skip" is
  deleted after 90 days. Only its name and the fact it was skipped are kept, so
  it is never offered again.
- **Arabic-only businesses** are still scored. Their report is in English.
- **Sign-in.** The list sits behind the main site's existing admin sign-in.

## Left to the builder

- Which service it lives in (the consultation service already has the
  web-search model, the safe fetcher and the number checks). It must sit behind
  the admin sign-in.
- The scoring formula, as long as every point in it comes from something read.
- How the report page is laid out within the BMV look.
- Which model writes the report and the DM.
