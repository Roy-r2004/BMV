#!/usr/bin/env python3
"""Phase 0's 0.4, measured: are the visual critic's revision instructions
expressible as content-key edits?

0.4 gates Phase 2's 2.6 together with 0.3. 0.3 classified what the AI repair's
ops *did* (content, overwhelmingly). This is the other half: what the critic
*asks for* — because 2.6's proposed replacement is a spec-level actor mapping
each visual finding to a content-key edit, and that actor is only buildable if
the asks are content-shaped.

    python3 backend/scripts/measure/revision_instruction_census.py \
        --reports DIR [--json OUT] [--check ARCHIVED.json]

**The corpus, stated honestly.** The critic's raw `revision_instructions` field
is never persisted — it is consumed transiently by the refine pass
(`visual_critic.py` builds `notes` from it and drops it). What survives is
`_bmv_visual_critique.json`, whose `visual_defect` / `visual_defect_severe`
findings carry the same asks item-by-item: `"{file} scored {n}: {'; '.join(
issues[:6])}"`. Two caps follow and are not recoverable: at most 6 issues per
page are stored, and issues are re-split here on `; ` anchored to sentence
punctuation (a plain `'; '` split over-cuts 19 of 791 — both counts printed).
Reports exist for 41 requests (37-122, extracted from the api volume and
archived in `docs/evidence/visual-critique-reports.tar.gz`); no run after 122
has one — the critic never ran on 129-145, which is the tail-starvation fact
the R5 row already carries.

**The load-bearing judgment calls**, in precedence order (first match wins):

- A page that is wholesale the wrong page (`page_identity`) is a spec-level
  regeneration, not a content edit.
- A planned slot/section/control that is absent or the wrong component
  (`missing_section`) cannot be created by editing a content value. Under
  Phase 2's pages-as-data model it arguably becomes a spec edit, so the
  summary prints the expressibility number both with and without this bucket.
- A blank/unrendered region (`rendering`) is a defect no content edit fixes.
- Visual treatment — spacing, styling, hierarchy, sizing (`styling_layout`) —
  is not content.
- Wrong or generic image *subject* (`imagery_content`) IS content: the image
  binding is a key.
- Navigation set/labels (`nav_links`), list completeness and field values
  (`content_data`), and copy/label/text asks (`content_copy`) are content-key
  edits by construction.
- Anything matching no rule lands in `unclassified` and is printed, never
  forced — 0.3's first-pass lesson: a rubric that always wins reports its own
  priors.

Ties therefore break AGAINST expressibility (structural rules match first), so
the content-share is a floor, not a fitted number. Boundary errors *within*
either group cannot move the headline split; the between-group boundary is the
one the stratified hand-audit in the evidence JSON scores.

Read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_TARBALL = REPO / "docs" / "evidence" / "visual-critique-reports.tar.gz"

DEFECT_CODES = {"visual_defect", "visual_defect_severe"}

#: '; ' anchored to sentence-ending punctuation — the joiner in
#: `_absorb_review` sits between complete sentences; a bare '; ' also lives
#: inside single issues ("availability, dimensions, pricing; please…").
_ATOM_SPLIT = re.compile(r"(?<=[.!?\"'\)]);\s+")

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("meta_note", re.compile(
        r"^Critic score is below|cannot be verified from a static screenshot", re.I)),
    ("page_identity", re.compile(
        r"\bnot (?:the|a|an) [^.]{0,60}\b(?:page|interface|dashboard|homepage)\b"
        r"|appears to be a generic|presents a generic|looks like a (?:marketing|generic)"
        r"|is not the [^.]{0,40}\b(?:described|specified)"
        r"|intended to be [^.]{0,60}\bbut\b"
        r"|assigned skeleton is\b|\bwrong page\b", re.I)),
    ("missing_section", re.compile(
        r"\b(?:slot|section|component|panel|block|strip|footer|header|carousel|form|"
        r"filters?|dropdowns?|search bar|controls?)\b[^.]{0,120}"
        r"\b(?:missing|absent|entirely missing|not (?:present|implemented|visible|assigned|included))\b"
        r"|\b(?:missing|no)\b[^.]{0,40}\b(?:slot|section|component|panel|block|strip|form)\b"
        r"|\brequired slot\b|\brequires? the [^.]{0,30}slot\b"
        r"|\bunderdeveloped\b|\bbrief specified\b[^.]{0,80}\b(?:dropdowns?|sliders?|"
        r"checkboxes|search bar)\b|\bmissing the required [^.]{0,40}slots?\b", re.I)),
    ("slot_contract", re.compile(
        r"\b(?:slot_components|skeleton contract|catalogue contract|compact catalogue)\b"
        r"|\bcontract (?:explicitly )?(?:specifies|requires)\b"
        r"|\bnot (?:listed|an assigned) (?:as )?(?:an? )?assigned slot\b"
        r"|\bnot explicitly assigned\b|\bwas not [^.]{0,30}assigned for this page\b"
        r"|\bimplemented as [^.]{0,60}\bbut\b[^.]{0,80}\b(?:requires?|contract)\b"
        r"|\buses? an? \S+ component\b[^.]{0,60}\b(?:but|when|instead)\b"
        r"|\bsupports only\b|\bprefer \S+ over\b"
        r"|\bpresent on the page but are not listed\b"
        r"|\bdoes not use the \S+ (?:component|shell)\b|\bas required by the \S+ skeleton\b"
        r"|\buse the `?\w+`?\b[^.]{0,40}\bdesigned for\b", re.I)),
    ("rendering", re.compile(
        r"\bblank\b|\bunrendered\b|\bfailed to (?:load|render)\b|\bnot render"
        r"|\bfailure to render\b", re.I)),
    ("interaction", re.compile(
        r"\binteractive\b|\bon hover\b|\bactive state\b|\bclickable\b"
        r"|\bno (?:visible )?(?:interaction|interactivity)\b", re.I)),
    ("styling_layout", re.compile(
        r"\bunstyled\b|\bstyling\b|\bstyled\b|\bspacing\b|\balign(?:ed|ment)?\b|\boverlap"
        r"|\btoo close\b|\bwhitespace\b|\bsparse\b|\blayout\b|\bhierarchy\b|\bcontrast\b"
        r"|\bfont\b|\bfont-display\b|\brounded corners?\b|\bradius\b|\bicon\b"
        r"|\bcard background\b|\bprominent\b|\bunderstated\b|\btruncated\b|\bcut off\b"
        r"|\bcutting off\b|\bclunky\b|\bawkwardly\b|\bvisual separation\b|\bcramped\b"
        r"|\bresponsive\b|\btoo (?:small|large|big)\b|\bsized?\b[^.]{0,20}\b(?:wall|screen)"
        r"|\bpoorly integrated\b|\bvisually separated\b|\bvisually distinct\b"
        r"|\blong and dense\b|\bmisplaced\b", re.I)),
    ("imagery_content", re.compile(
        r"\b(?:image|images|photo|photograph|painting|picture|thumbnail|imagery|"
        r"headshot)\b[^.]{0,120}\b(?:generic|not|wrong|unrelated|inappropriate|"
        r"placeholder|stock|mismatch|calculator|irrelevant|missing)\b"
        r"|\b(?:generic|wrong|unrelated|inappropriate)\b[^.]{0,60}"
        r"\b(?:image|photo|painting|picture|imagery)\b"
        r"|\bhero photograph\b|\bphotography of\b"
        r"|\bimages?\b[^.]{0,140}\b(?:clearly )?(?:shows?|depicts?|displays?)\b"
        r"|\bphotographs? of\b[^.]{0,60}\binstead of\b|\bhero image\b|\bdetail shot\b", re.I)),
    ("nav_links", re.compile(
        r"\bnavigation\b|\bnav\b|\bmenu items?\b|\blinks?\b[^.]{0,60}"
        r"\b(?:inappropriate|dead|wrong|broken|unexpected|missing)\b"
        r"|\bheader navigation\b|\bfooter [^.]{0,30}links\b"
        r"|\bCTA\b|\bcall to action\b"
        r"|\bbutton\b[^.]{0,80}\b(?:links?|routes?|href|whatsapp|should (?:be|not)|"
        r"goes to|not a direct)\b", re.I)),
    ("content_data", re.compile(
        r"\bonly\b[^.]{0,25}\b(?:one|two|three|\d+)\b"
        r"|\bmissing (?:one|its|their|a third|the third)\b"
        r"|\bmissing its [^.]{0,30}\b(?:price|description|text|detail)"
        r"|\b(?:price|prices|operating hours|address|phone)\b[^.]{0,40}\bmissing\b"
        r"|\bmissing\b[^.]{0,40}\b(?:price|hours|address|phone|contact information)\b"
        r"|\bplaceholder(?:s| text)?\b|\bnot populated\b|\bgeneric descriptions?\b"
        r"|\binstead of concrete\b|\bempty (?:content|and unhelpful|cards?|credential|state)\b"
        r"|\bcontent cards?\b[^.]{0,30}\bempty\b|\bno actual\b|\bpopulated with generic\b", re.I)),
    ("content_copy", re.compile(
        r"\bheadline\b|\btitle\b|\bsub-?head(?:er|line)\b|\bsubcopy\b|\bcopy\b|\btext\b"
        r"|\bwording\b|\blabel(?:s|ed|led)?\b|\bre-?labell?ed\b"
        r"|\bshould (?:read|say|simply be|likely be)\b"
        r"|\bredundant\b|\bduplicate\b|\bcopyright\b|\bdescription\b|\bparagraph\b"
        r"|\bdoes not match the (?:sample data|brief)\b|\bagency pitch\b|\btone\b"
        r"|\bnamed?\b|\bcalled\b|\blanguage\b|\bmessage\b|\bmisaligned with\b"
        r"|\binappropriate for\b|\boff-brief\b|\bcontent (?:states|refers|is generic)\b"
        r"|\bstates\b[^.]{0,30}\b(?:date|\d{4})\b|\bmarketing-heavy\b"
        r"|\bfeels (?:like a template|generic)\b|\bunexpected for\b"
        r"|\bsubtext\b|\bmislabell?ed\b|\bout of context\b|\bits content is\b"
        r"|\bdoes not reiterate\b", re.I)),
]

CONTENT_KEY = {"imagery_content", "nav_links", "content_data", "content_copy"}
STRUCTURAL = {"page_identity", "missing_section", "slot_contract", "rendering",
              "interaction", "styling_layout"}
#: Not an ask at all — excluded from both groups and from the share denominators.
EXCLUDED = {"meta_note"}


def classify(atom: str) -> str:
    body = re.sub(r"^SEVERE:\s*", "", atom.strip())
    for name, rx in _RULES:
        if rx.search(body):
            return name
    return "unclassified"


def load_reports(root: Path) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    for path in sorted(root.glob("*/_bmv_visual_critique.json")):
        reports[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    if not reports:
        raise SystemExit(f"no */_bmv_visual_critique.json under {root}")
    return reports


def atoms_of(report: dict) -> list[tuple[str, str, str]]:
    """(severity, page, atom) per stored ask."""
    out = []
    for fd in report.get("findings", []):
        if fd.get("code") not in DEFECT_CODES:
            continue
        msg = fd.get("message", "")
        body = msg.split(": ", 1)[1] if ": " in msg else msg
        for atom in _ATOM_SPLIT.split(body):
            atom = atom.strip()
            if atom:
                out.append((fd.get("severity", ""), fd.get("path", ""), atom))
    return out


def run_census(root: Path) -> dict:
    reports = load_reports(root)
    statuses = Counter(str(r.get("review_status")) for r in reports.values())
    rows = []
    for req, report in sorted(reports.items(), key=lambda kv: int(kv[0])):
        for severity, page, atom in atoms_of(report):
            rows.append({
                "request": int(req), "page": page, "severity": severity,
                "category": classify(atom), "atom": atom,
            })

    def split(sel):
        cat = Counter(r["category"] for r in rows if sel(r))
        content = sum(cat[c] for c in CONTENT_KEY)
        structural = sum(cat[c] for c in STRUCTURAL)
        excluded = sum(cat[c] for c in EXCLUDED)
        total = sum(cat.values()) - excluded
        sections_as_data = cat["missing_section"] + cat["slot_contract"]
        return {
            "total_atoms": total,
            "excluded_meta_notes": excluded,
            "categories": dict(cat.most_common()),
            "content_key": content,
            "structural": structural,
            "unclassified": cat["unclassified"],
            "content_share_pct": round(100 * content / total, 1) if total else None,
            "content_share_if_sections_are_data_pct": round(
                100 * (content + sections_as_data) / total, 1) if total else None,
        }

    naive = sum(
        len(fd["message"].split(": ", 1)[-1].split("; "))
        for r in reports.values() for fd in r.get("findings", [])
        if fd.get("code") in DEFECT_CODES
    )
    # Deterministic stratified sample for the hand-audit: md5 order, first 60.
    sample = sorted(rows, key=lambda r: hashlib.md5(r["atom"].encode()).hexdigest())[:60]
    return {
        "method": "see module docstring; rules applied in precedence order, first match wins",
        "corpus": {
            "reports": len(reports),
            "requests": [int(k) for k in sorted(reports, key=int)],
            "review_status": dict(statuses),
            "defect_findings": sum(
                1 for r in reports.values() for fd in r.get("findings", [])
                if fd.get("code") in DEFECT_CODES),
            "atoms_punctuation_split": len(rows),
            "atoms_naive_split": naive,
            "issues_cap_per_page": 6,
        },
        "all": split(lambda r: True),
        "severe_only": split(lambda r: r["severity"] == "block"),
        "audit_sample_keys": [r["atom"][:80] for r in sample],
        "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reports", type=Path, default=None,
                    help="dir of <request>/_bmv_visual_critique.json "
                         "(default: extract the committed evidence tarball)")
    ap.add_argument("--json", type=Path, default=None, help="write full evidence JSON here")
    ap.add_argument("--check", type=Path, default=None,
                    help="archived census JSON; red-exit on any drift in the summary numbers")
    args = ap.parse_args()

    root = args.reports
    if root is None:
        if not DEFAULT_TARBALL.exists():
            raise SystemExit(f"--reports not given and {DEFAULT_TARBALL} missing")
        tmp = Path(tempfile.mkdtemp(prefix="bmv-critiques-"))
        with tarfile.open(DEFAULT_TARBALL) as tf:
            tf.extractall(tmp, filter="data")
        root = tmp

    result = run_census(root)

    print(f"reports: {result['corpus']['reports']}  "
          f"defect findings: {result['corpus']['defect_findings']}  "
          f"atoms: {result['corpus']['atoms_punctuation_split']} "
          f"(naive split would give {result['corpus']['atoms_naive_split']})")
    for scope in ("all", "severe_only"):
        s = result[scope]
        print(f"\n[{scope}] {s['total_atoms']} atoms")
        for cat, n in s["categories"].items():
            mark = "content" if cat in CONTENT_KEY else (
                "structural" if cat in STRUCTURAL else "?")
            print(f"  {cat:<18} {n:>4}  ({mark})")
        print(f"  content-key expressible: {s['content_key']} "
              f"({s['content_share_pct']} %)  structural: {s['structural']}  "
              f"unclassified: {s['unclassified']}")
        print(f"  if missing/contract sections count as pages-as-data: "
              f"{s['content_share_if_sections_are_data_pct']} %")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1, ensure_ascii=False),
                             encoding="utf-8")
        print(f"\nwrote {args.json}")

    if args.check:
        archived = json.loads(args.check.read_text(encoding="utf-8"))
        drift = []
        for scope in ("corpus", "all", "severe_only"):
            a, b = archived.get(scope), result.get(scope)
            if a != b:
                drift.append(scope)
        if drift:
            print(f"\nDRIFT against {args.check}: {', '.join(drift)} differ — "
                  "the stored corpus or the rubric changed; re-derive before citing "
                  "the archived numbers", file=sys.stderr)
            raise SystemExit(1)
        print(f"\ncheck OK — matches {args.check}")


if __name__ == "__main__":
    main()
