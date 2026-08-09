"""Bind each catalogue photograph to the item it is captioned with.

**The defect this closes is structural, not a bad draw.** `item_pool_query`
composes its search text from the *industry string alone* — it never sees an
item, because the pool is fetched during planning and the items do not exist
until the seed writes them. So request 73's twelve works, titled *Whispers of the
Forest*, *Coastal Serenity*, *City Nocturne*, *River's Edge*, *Autumn Hues*,
*Mountain Ascension* — representational landscapes to a one — were captioned with
**eight non-representational abstracts**, several of them macro crops of paint
texture. Right artifact type, wrong artifact, and invisible to every gate we
have.

Correspondence was **impossible by construction**, and no amount of query tuning
reaches it. It needs the items first.

The insertion point is `sync_mock_images`, which already rewrites the whole
`export const images` block from the pipeline slot map after the seed has run.
By then `mock.ts` holds the real item titles, so this module reads them, asks the
photo index once for pictures of *those things*, scores each candidate against
each title using the index's own `alt` text, and hands back a reordered item slot
map. The existing rewrite carries it; the existing codemod
(`imageSrc: it.image ?? images[item…]`) binds card *i* to slot *i*. No new
surgery, and one extra HTTP request — not one per item.

Every step degrades to today's behaviour rather than failing: no titles, no API
key, a search that raises, or fewer candidates than items all leave the slot map
exactly as it arrived.
"""
from __future__ import annotations

import re

#: Words that carry no subject. Trimmed deliberately: this is a *matching* aid,
#: not a language model, and an over-long list starts deleting the nouns that
#: distinguish one item from another ("still life", "house blend").
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or",
        "our", "the", "to", "with", "series", "no", "vol", "edition",
    }
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")

#: `"title": "…"` or `"name": "…"` inside the seed's catalogue arrays. The seed
#: writes JSON-shaped object literals, so this reads the value it means rather
#: than trying to parse TypeScript. `title` wins where both are present because
#: that is the field the cards render.
_TITLE_RE = re.compile(r'"(title|name)"\s*:\s*"([^"\\]{2,120})"')
_TS_TITLE_RE = re.compile(r'\b(title|name)\s*:\s*"([^"\\]{2,120})"')

#: Arrays whose objects are catalogue items. `services` is included because a
#: service listing is a catalogue with a different noun, and its cards read the
#: same image slots.
_CATALOGUE_KEYS = ("items", "products", "catalogue", "catalog", "menu", "services", "works")


def bind_catalogue_photos(workspace, industry: str | None) -> dict[str, str]:
    """Item slots pointed at photographs of the items, or `{}` to change nothing.

    The one entry point the pipeline calls, and the only place the network is
    touched. **Every failure path returns `{}`** — no catalogue, no titles, no
    API key, a search that raises, or a binding that would repeat a photograph.
    An empty result leaves the pool exactly as the plan phase fetched it, which
    is today's behaviour and a correct app.

    Call it **once per generation**, after the seed. See the note at the call
    site for why the guard sweep is the wrong home for it.
    """
    from app.application.preview_app.workspace import read_file
    from app.application.services.industry_images import (
        item_photos_by_title,
        item_photos_for_titles,
        item_slot_names,
    )

    try:
        titles = catalogue_item_titles(read_file(workspace, "src/data/mock.ts"))
        if not titles:
            return {}
        # Ask the index with each item's own words first. Request 165: the
        # pooled search is composed for the *business*, so a bakery's pool is
        # bread and every cake title matched bread — per-item queries are the
        # only search that can return a photograph *of the item*.
        per_title = item_photos_by_title(titles, industry or "")
        if any(per_title):
            bound = bind_per_title_photos(titles, per_title, item_slot_names())
        else:
            candidates = item_photos_for_titles(titles, industry or "")
            if not candidates:
                return {}
            bound = bind_photos_to_titles(titles, candidates, item_slot_names())
        # A binding that repeats a photograph is worse than the rotation it
        # replaces, which is distinct by construction. Take it or leave it whole.
        if len(set(bound.values())) != len(bound):
            return {}
        return bound
    except Exception:  # noqa: BLE001 — correspondence is an enhancement
        return {}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "")} - _STOPWORDS


def catalogue_item_titles(mock_source: str, *, limit: int = 64) -> list[str]:
    """The catalogue's item titles, in the order the cards render them.

    Reads only the first catalogue-shaped array it finds, because that is the one
    the item slots are bound to; a page with both `products` and `testimonials`
    must not caption a photograph with a customer's name.
    """
    if not mock_source:
        return []

    best: list[str] = []
    for key in _CATALOGUE_KEYS:
        match = re.search(rf"\b{key}\s*:\s*\[", mock_source)
        if not match:
            continue
        chunk = _balanced_array(mock_source, match.end() - 1)
        if not chunk:
            continue
        # JSON-quoted keys first — that is what the seed writes. The bare-key
        # form is the fallback for a hand-edited or scaffolded module.
        titles = [m.group(2).strip() for m in _TITLE_RE.finditer(chunk)] or [
            m.group(2).strip() for m in _TS_TITLE_RE.finditer(chunk)
        ]
        # Objects carrying both `title` and `name` yield two hits for one item;
        # consecutive duplicates are that, not two items with the same name.
        deduped: list[str] = []
        for title in titles:
            if not deduped or deduped[-1] != title:
                deduped.append(title)
        if len(deduped) > len(best):
            best = deduped
    return best[:limit]


def _balanced_array(source: str, open_index: int) -> str:
    """The `[...]` starting at `open_index`, or `""` if it never closes.

    Bracket counting rather than a lazy regex: an item whose description contains
    "]" truncated the array and the census read half a catalogue.
    """
    depth = 0
    in_string = False
    escape = False
    for i in range(open_index, len(source)):
        ch = source[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return source[open_index : i + 1]
    return ""


def score_photo_for_title(title: str, alt: str) -> int:
    """How well one photograph's own description matches one item's title.

    Two points a shared word, one more when the whole title appears in the
    description. Integers on purpose: the assignment below is a deterministic
    sort, and floats invite ties that resolve differently on different machines.
    """
    title_tokens = _tokens(title)
    if not title_tokens:
        return 0
    alt_tokens = _tokens(alt)
    score = 2 * len(title_tokens & alt_tokens)
    if score and title.strip().lower() in (alt or "").lower():
        score += 1
    return score


def bind_per_title_photos(
    titles: list[str],
    per_title: list[list[tuple[str, str]]],
    slots: tuple[str, ...],
) -> dict[str, str]:
    """Assign each slot a photograph searched for *that item*, best-first.

    A photograph from the item's own query outranks any cross-match, and the
    index's own relevance order breaks ties inside a query. Cross-matches (a
    photo fetched for one title answering another) exist only as fallback for
    items whose search returned nothing, scored by `score_photo_for_title` the
    same way the pooled binding scores. Uniqueness by URL: shared queries hand
    the same candidates to several titles, and no two cards may share a photo.
    """
    if not titles:
        return {}
    # One global candidate list deduped by URL, remembering the best (title,
    # rank) that fetched each photo.
    urls: list[str] = []
    alts: dict[str, str] = {}
    own_rank: dict[tuple[int, str], int] = {}
    for t_index, results in enumerate(per_title[: len(slots)]):
        for rank, (url, alt) in enumerate(results):
            if not url:
                continue
            if url not in alts:
                urls.append(url)
                alts[url] = alt
            own_rank[(t_index, url)] = min(
                rank, own_rank.get((t_index, url), rank)
            )
    if not urls:
        return {}

    pairs: list[tuple[int, int, int]] = []
    for t_index in range(min(len(titles), len(slots))):
        for u_index, url in enumerate(urls):
            rank = own_rank.get((t_index, url))
            if rank is not None:
                score = 2000 - rank + score_photo_for_title(titles[t_index], alts[url])
            else:
                score = score_photo_for_title(titles[t_index], alts[url])
                if not score:
                    continue
            pairs.append((-score, u_index, t_index))
    pairs.sort()

    taken_titles: set[int] = set()
    taken_urls: set[int] = set()
    bound: dict[str, str] = {}
    for _neg, u_index, t_index in pairs:
        if t_index in taken_titles or u_index in taken_urls:
            continue
        taken_titles.add(t_index)
        taken_urls.add(u_index)
        bound[slots[t_index]] = urls[u_index]

    # An item nothing answered for still needs a distinct picture.
    spare = (url for i, url in enumerate(urls) if i not in taken_urls)
    for t_index in range(min(len(titles), len(slots))):
        if t_index in taken_titles:
            continue
        url = next(spare, "")
        if not url:
            break
        bound[slots[t_index]] = url
    return bound


def bind_photos_to_titles(
    titles: list[str],
    candidates: list[tuple[str, str]],
    slots: tuple[str, ...],
) -> dict[str, str]:
    """Assign each item slot the best unused photograph for that item's title.

    Greedy over the best remaining (title, photo) pair rather than in title
    order: taking items left to right lets item 1 consume the only photograph
    that item 6 could have matched at all. Ties break on the candidate's search
    rank, which is the index's own relevance ordering, so the result is stable.

    Returns only the slots it can bind. An empty result means "change nothing",
    which is what every failure path here produces.
    """
    usable = [(url, alt) for url, alt in candidates if url]
    if not titles or not usable:
        return {}

    pairs: list[tuple[int, int, int, int]] = []
    for t_index, title in enumerate(titles[: len(slots)]):
        for c_index, (_url, alt) in enumerate(usable):
            score = score_photo_for_title(title, alt)
            if score:
                # Negative score sorts best-first; the two indices are the
                # tie-break, and they are what makes this deterministic.
                pairs.append((-score, c_index, t_index, c_index))
    pairs.sort()

    taken_titles: set[int] = set()
    taken_photos: set[int] = set()
    bound: dict[str, str] = {}
    for _neg, _rank, t_index, c_index in pairs:
        if t_index in taken_titles or c_index in taken_photos:
            continue
        taken_titles.add(t_index)
        taken_photos.add(c_index)
        bound[slots[t_index]] = usable[c_index][0]

    # An item no photograph matched still needs a distinct picture — a hole is a
    # broken card, and a repeat is worse than a merely unmatched photo.
    spare = (url for i, (url, _alt) in enumerate(usable) if i not in taken_photos)
    for t_index in range(min(len(titles), len(slots))):
        if t_index in taken_titles:
            continue
        url = next(spare, "")
        if not url:
            break
        bound[slots[t_index]] = url
    return bound
