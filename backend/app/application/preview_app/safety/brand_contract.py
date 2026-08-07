"""Preview safety — Brand Contract."""
from __future__ import annotations

import json
import re

from app.application.preview_app.patterns import (
    DEFAULT_DYNAMIC_ARRAY_LEN,
    MAX_BRAND_ARRAY_LEN,
    _BRAND_ACCESS_RE,
    _BRAND_CHAIN_PART_RE,
    _BRAND_EXPORT_RE,
    design_system_dict as _design_system_dict,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def _brand_object_span(mock: str) -> tuple[int, int] | None:
    """Return (body_start, close_brace_index) for `export const brand = { ... }`."""
    m = _BRAND_EXPORT_RE.search(mock)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(mock) and depth:
        ch = mock[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return start, i - 1

def _toplevel_string_array(mock: str, name: str) -> list[str] | None:
    """Parse `export const name = ["a", "b"]` if present; else None."""
    m = re.search(
        rf"export\s+const\s+{re.escape(name)}\s*=\s*\[([\s\S]*?)\];",
        mock,
    )
    if not m:
        return None
    vals = re.findall(r"""["']([^"']+)["']""", m.group(1))
    return vals or None

def _default_client_names(brand_name: str) -> list[str]:
    label = (brand_name or "Brand").split()[0]
    return [
        f"Maya {label}",
        "Jordan Cohen",
        "Sam Levi",
        "Noa Ben-David",
        "Alex Mizrahi",
        "Dana Peretz",
    ]

def _strip_ts_comments_and_strings(src: str) -> str:
    """Replace comments and string/template literal contents with spaces.

    Keeps newlines so line structure stays stable. Conservative — does not
    evaluate code. Used only to avoid matching `brand.foo` inside comments/strings.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            out.append(" ")
            out.append(" ")
            i += 2
            while i < n - 1 and not (src[i] == "*" and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            if i < n - 1:
                out.append(" ")
                out.append(" ")
                i += 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            out.append(" ")
            i += 1
            while i < n:
                c = src[i]
                if c == "\\" and i + 1 < n:
                    out.append(" ")
                    out.append(" ")
                    i += 2
                    continue
                if c == quote:
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)

def _parse_brand_chain(chain: str) -> tuple:
    """Return segments: strings for props, ints for numeric indexes, '*' for dynamic indexes."""
    parts: list = []
    for m in _BRAND_CHAIN_PART_RE.finditer(chain or ""):
        if m.group(1):
            parts.append(m.group(1))
        elif m.group(2):
            parts.append(m.group(2))
        elif m.group(3):
            parts.append(int(m.group(3)))
        elif m.group(4):
            parts.append("*")
    return tuple(parts)

def normalize_brand_path(parts: tuple) -> str:
    """Normalize a parsed chain to `brand.foo[].bar` form."""
    if not parts:
        return "brand"
    bits = ["brand"]
    for p in parts:
        if isinstance(p, int) or p == "*":
            bits.append("[]")
        else:
            bits.append(str(p))
    # Join: brand + .prop or [] without extra dots before []
    out = bits[0]
    for b in bits[1:]:
        if b == "[]":
            out += "[]"
        else:
            out += f".{b}"
    return out

def collect_brand_property_paths(workspace) -> set[tuple]:
    """Scan TS/TSX for `brand.foo` / `brand.foo[i].bar` usage paths (deduped).

    Ignores matches inside comments and string literals where possible.
    Does not evaluate generated code.
    """
    found: set[tuple] = set()
    for rel in list_source_files(workspace):
        norm = rel.replace("\\", "/")
        if not norm.endswith((".tsx", ".ts", ".jsx", ".js")):
            continue
        if norm.startswith("src/data/"):
            continue
        raw = read_file(workspace, rel)
        text = _strip_ts_comments_and_strings(raw)
        for m in _BRAND_ACCESS_RE.finditer(text):
            parts = _parse_brand_chain(m.group("chain"))
            if parts and all(
                isinstance(p, (str, int)) or p == "*" for p in parts
            ):
                # Drop unsupported empty / malformed chains
                if isinstance(parts[0], str):
                    found.add(parts)
    return found

def _brand_scalar_default(field: str, brand_name: str, primary: str) -> object:
    """Small stable schema library — keyed by field *role*, not product field lists."""
    fl = (field or "").lower()
    name = brand_name or "Brand"
    if "color" in fl or fl in {"accent", "primary", "secondary"}:
        return primary or "#6366f1"
    if fl in {"price", "amount", "revenue", "cost", "count", "qty", "quantity"}:
        return 0
    if fl in {"rating", "score", "stars"}:
        return 5
    if fl in {"name", "title", "label", "heading"}:
        return f"{name} item"
    if fl in {"description", "text", "quote", "detail", "summary", "bio"}:
        return f"Sample {field} for {name}."
    if fl in {"image", "img", "url", "href", "link", "path", "src", "photo"}:
        return ""
    if fl in {"badge", "status", "role", "category", "type", "tag"}:
        return "Demo"
    if fl in {"initials"}:
        return "AA"
    if fl in {"duration", "time", "date", "timestamp"} or fl.endswith("_at"):
        return "30 min" if fl == "duration" else "Today"
    if fl in {"email"}:
        return "client@example.com"
    if fl in {"phone"}:
        return "+1 555 0100"
    return f"Sample {field}"

def _infer_brand_requirements(paths: set[tuple]) -> dict[str, dict]:
    """Group usage paths by top-level brand key → array/object requirements."""
    reqs: dict[str, dict] = {}
    for path in paths:
        if not path or not isinstance(path[0], str):
            continue
        top = path[0]
        rest = path[1:]
        req = reqs.setdefault(
            top,
            {"min_len": 0, "item_fields": set(), "object_fields": set(), "is_array": False},
        )
        idx_at = next((i for i, p in enumerate(rest) if p == "*" or isinstance(p, int)), None)
        if idx_at is None:
            for p in rest:
                if isinstance(p, str):
                    req["object_fields"].add(p)
            continue
        req["is_array"] = True
        idx = rest[idx_at]
        if isinstance(idx, int):
            # Cap — never grow to brand.foo[999]
            req["min_len"] = max(req["min_len"], min(idx + 1, MAX_BRAND_ARRAY_LEN))
        else:
            req["min_len"] = max(req["min_len"], DEFAULT_DYNAMIC_ARRAY_LEN)
        for p in rest[idx_at + 1 :]:
            if isinstance(p, str):
                req["item_fields"].add(p)
    for req in reqs.values():
        if req["is_array"]:
            req["min_len"] = min(max(req["min_len"], DEFAULT_DYNAMIC_ARRAY_LEN), MAX_BRAND_ARRAY_LEN)
    return reqs

def _contract_type_label(req: dict) -> str:
    if req["is_array"] and req["item_fields"]:
        fields = ",".join(sorted(req["item_fields"])[:4])
        return f"Array<{{{fields}}}>"
    if req["is_array"]:
        return "string[]"
    if req["object_fields"]:
        fields = ",".join(sorted(req["object_fields"])[:4])
        return f"{{{fields}}}"
    return "unknown"

def _default_brand_top_value(
    key: str,
    req: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    mock: str,
    design: dict | None = None,
) -> object:
    name = brand_name or "Brand"
    if key in {"design_system", "designSystem"} or (
        req["object_fields"] and not req["is_array"] and "system" in key.lower()
    ):
        base = (
            _design_system_dict(primary, secondary, font, design)
            if "design" in key.lower()
            else {}
        )
        for field in req["object_fields"]:
            if field not in base:
                base[field] = _brand_scalar_default(field, name, primary)
        return base

    if req["is_array"]:
        n = min(req["min_len"], MAX_BRAND_ARRAY_LEN)
        fields = sorted(req["item_fields"])
        if not fields:
            existing = _toplevel_string_array(mock, key)
            if existing:
                vals = list(existing)
                while len(vals) < n:
                    vals.append(f"Client {len(vals) + 1}")
                return vals[:MAX_BRAND_ARRAY_LEN]
            if key.lower() in {"client_names", "clientnames", "customers", "patients"}:
                vals = _default_client_names(name)
                while len(vals) < n:
                    vals.append(f"Client {len(vals) + 1}")
                return vals[:MAX_BRAND_ARRAY_LEN]
            return [f"Item {i + 1}" for i in range(n)]
        return [
            {f: _brand_scalar_default(f, name, primary) for f in fields}
            for _ in range(n)
        ]

    if req["object_fields"]:
        return {
            f: _brand_scalar_default(f, name, primary) for f in sorted(req["object_fields"])
        }
    return name if key in {"name", "brand_name", "owner_name"} else {}

def _brand_key_re(key: str) -> str:
    """Match `key:` whether or not the key is quoted.

    `assemble.py` writes brand with `json.dumps`, so every original key arrives
    as `"name":`. A regex anchored on `[,{\\s]` sees the opening quote instead of
    a delimiter and reports the key missing — so request 44 appended a second
    `name` and a second `tagline` to an object that already had both (TS1117),
    and the `tagline` it invented was `{}`, which `PublicLayout` then rendered as
    a ReactNode (TS2322).
    """
    k = re.escape(key)
    return rf"""(?:^|[,{{\s])['"]?{k}['"]?\s*:"""


def _brand_has_top_key(body: str, key: str) -> bool:
    return re.search(_brand_key_re(key), body) is not None

def _find_brand_prop_span(body: str, key: str) -> tuple[int, int] | None:
    """Return [value_start, value_end) for a top-level `key:` inside brand body."""
    pattern = _brand_key_re(key)
    m = re.search(pattern, body)
    if not m:
        m = re.search(rf"""(?:^|\n)\s*['"]?{re.escape(key)}['"]?\s*:""", body)
    if not m:
        return None
    val_start = m.end()
    while val_start < len(body) and body[val_start] in " \t\n\r":
        val_start += 1
    if val_start >= len(body):
        return None
    j = val_start
    if body[j] in "\"'":
        quote = body[j]
        j += 1
        while j < len(body):
            if body[j] == "\\":
                j += 2
                continue
            if body[j] == quote:
                j += 1
                break
            j += 1
        return val_start, j
    if body[j] in "{[":
        opener = body[j]
        closer = "}" if opener == "{" else "]"
        depth = 1
        j += 1
        in_s = None
        esc = False
        while j < len(body) and depth:
            ch = body[j]
            if in_s:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == in_s:
                    in_s = None
            else:
                if ch in ("'", '"', "`"):
                    in_s = ch
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
            j += 1
        return val_start, j
    while j < len(body) and body[j] not in ",\n}":
        j += 1
    return val_start, j

def _count_array_items(array_src: str) -> int:
    """Count top-level elements in a TS array literal."""
    s = array_src.strip()
    if not s.startswith("["):
        return 0
    # Prefer object-item count when present
    obj_count = 0
    depth = 0
    in_s = None
    esc = False
    for i, ch in enumerate(s):
        if in_s:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_s:
                in_s = None
            continue
        if ch in ("'", '"', "`"):
            in_s = ch
            continue
        if ch == "{":
            if depth == 1:  # inside outer [
                obj_count += 1
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
    if obj_count:
        return obj_count
    return len(re.findall(r"""["'][^"']+["']""", s))

def _pad_array_literal(
    array_src: str,
    need: int,
    item_fields: set[str],
    brand_name: str,
    primary: str,
) -> str:
    need = min(need, MAX_BRAND_ARRAY_LEN)
    have = _count_array_items(array_src)
    if have >= need:
        return array_src  # never overwrite / never shrink
    pads = []
    for i in range(have, need):
        if item_fields:
            obj = {f: _brand_scalar_default(f, brand_name, primary) for f in sorted(item_fields)}
            pads.append(json.dumps(obj, ensure_ascii=False))
        else:
            pads.append(json.dumps(f"Item {i + 1}", ensure_ascii=False))
    core = array_src.rstrip()
    if not core.endswith("]"):
        return array_src
    inner = core[:-1].rstrip().rstrip(",")
    addition = (",\n    " if inner.strip() not in {"", "["} else "") + ",\n    ".join(pads)
    return inner + addition + "\n  ]"

def _inject_object_fields(obj_src: str, fields: set[str], brand_name: str, primary: str) -> str:
    """Add missing keys into a TS object literal `{ ... }` — never removes existing keys."""
    if not obj_src.strip().startswith("{"):
        return obj_src
    missing = [f for f in sorted(fields) if not re.search(_brand_key_re(f), obj_src)]
    if not missing:
        return obj_src
    pieces = [
        f"{f}: {json.dumps(_brand_scalar_default(f, brand_name, primary), ensure_ascii=False)}"
        for f in missing
    ]
    core = obj_src.rstrip()
    if not core.endswith("}"):
        return obj_src
    inner = core[:-1].rstrip().rstrip(",")
    addition = (",\n    " if inner.strip() not in {"", "{"} else "") + ",\n    ".join(pieces)
    return inner + addition + "\n  }"

def ensure_brand_paths(
    mock: str,
    paths: set[tuple] | list[tuple],
    *,
    brand_name: str = "Brand",
    primary: str = "#6366f1",
    secondary: str = "#0d9488",
    font: str = "Inter",
    design: dict | None = None,
) -> tuple[str, list[str]]:
    """Ensure `brand` in mock.ts satisfies scanned usage paths.

    Returns `(updated_mock, contract_log_lines)`. Never overwrites valid existing
    values — only injects missing keys / pads arrays up to MAX_BRAND_ARRAY_LEN.
    Deterministic. No LLM.
    """
    path_set = set(paths or [])
    if not mock.strip() or not path_set:
        return mock, []

    reqs = _infer_brand_requirements(path_set)
    span = _brand_object_span(mock)
    if not span:
        return mock, []
    body_start, close_at = span
    body = mock[body_start:close_at]
    logs: list[str] = []
    injections: list[str] = []

    for key, req in sorted(reqs.items()):
        type_label = _contract_type_label(req)
        path_label = normalize_brand_path(
            (key, "*", *sorted(req["item_fields"])) if req["is_array"] and req["item_fields"]
            else (key, "*") if req["is_array"]
            else (key, *sorted(req["object_fields"])) if req["object_fields"]
            else (key,)
        )

        if not _brand_has_top_key(body, key):
            value = _default_brand_top_value(
                key, req, brand_name, primary, secondary, font, mock, design,
            )
            injections.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            logs.append(f"contract: ensured {path_label} as {type_label}")
            continue

        prop = _find_brand_prop_span(body, key)
        if not prop:
            continue
        val_start, val_end = prop
        current = body[val_start:val_end]

        if req["is_array"] and current.lstrip().startswith("["):
            padded = _pad_array_literal(
                current, req["min_len"], req["item_fields"], brand_name, primary,
            )
            if padded != current:
                body = body[:val_start] + padded + body[val_end:]
                logs.append(
                    f"contract: ensured {path_label} as {type_label} "
                    f"(padded to {min(req['min_len'], MAX_BRAND_ARRAY_LEN)})"
                )
                mock = mock[:body_start] + body + mock[close_at:]
                span = _brand_object_span(mock)
                if not span:
                    break
                body_start, close_at = span
                body = mock[body_start:close_at]
            continue

        if req["object_fields"] and current.lstrip().startswith("{"):
            enriched = _inject_object_fields(
                current, req["object_fields"], brand_name, primary,
            )
            if enriched != current:
                body = body[:val_start] + enriched + body[val_end:]
                logs.append(f"contract: ensured {path_label} as {type_label}")
                mock = mock[:body_start] + body + mock[close_at:]
                span = _brand_object_span(mock)
                if not span:
                    break
                body_start, close_at = span
                body = mock[body_start:close_at]

    if injections:
        patch = ",\n  ".join(injections)
        span = _brand_object_span(mock)
        if span:
            _body_start, close_at = span
            before = mock[:close_at].rstrip()
            if before.endswith(","):
                injection = f"\n  {patch},\n"
            else:
                injection = f",\n  {patch},\n"
            mock = mock[:close_at] + injection + mock[close_at:]

    return mock, logs

def ensure_brand_usage_paths(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    design: dict | None = None,
) -> list[str]:
    """Workspace wrapper: collect paths → ensure_brand_paths → write mock.ts."""
    paths = collect_brand_property_paths(workspace)
    if not paths:
        return []
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return []
    updated, logs = ensure_brand_paths(
        mock,
        paths,
        brand_name=brand_name,
        primary=primary,
        secondary=secondary,
        font=font,
        design=design,
    )
    if updated != mock:
        write_file(workspace, mock_path, updated)
    for line in logs:
        guard_log.debug("%s", line)
    return logs

def _brand_completeness_patch(
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    *,
    client_names: list[str] | None = None,
    design: dict | None = None,
) -> str:
    """TS snippet merged into brand so pages that expect design_system don't white-screen."""
    name = brand_name or "Brand"
    services = [
        {
            "name": f"{name} Signature",
            "title": f"{name} Signature",
            "description": "Flagship service with clear results and a calm, premium feel.",
            "image": "",
            "badge": "Popular",
            "price": 280,
            "duration": "60 min",
        },
        {
            "name": "AI-guided consult",
            "title": "AI-guided consult",
            "description": "Personalized recommendations from your goals — then book in minutes.",
            "image": "",
            "badge": "AI",
            "price": 0,
            "duration": "15 min",
        },
        {
            "name": "Member aftercare",
            "title": "Member aftercare",
            "description": "Recovery tips and check-ins so results last and WhatsApp stays quiet.",
            "image": "",
            "price": 0,
            "duration": "Ongoing",
        },
        {
            "name": "Follow-up visit",
            "title": "Follow-up visit",
            "description": "Quick check-in to fine-tune results and keep your plan on track.",
            "image": "",
            "badge": "Care",
            "price": 120,
            "duration": "30 min",
        },
    ]
    testimonials = [
        {
            "name": "Maya R.",
            "initials": "MR",
            "quote": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "text": f"Finally a {name} experience that feels personal — the AI consult nailed what I needed.",
            "role": "Client",
            "rating": 5,
        },
        {
            "name": "Jordan K.",
            "initials": "JK",
            "quote": "Booking and aftercare in one place. No more chasing answers on chat.",
            "text": "Booking and aftercare in one place. No more chasing answers on chat.",
            "role": "Member",
            "rating": 5,
        },
        {
            "name": "Sam T.",
            "initials": "ST",
            "quote": "The owner hub's no-show risk view alone paid for itself in a week.",
            "text": "The owner hub's no-show risk view alone paid for itself in a week.",
            "role": "Owner",
            "rating": 5,
        },
    ]
    design_system = _design_system_dict(primary, secondary, font, design)
    names = client_names or _default_client_names(name)
    return (
        f"design_system: {json.dumps(design_system, ensure_ascii=False)},\n"
        f"  services: {json.dumps(services, ensure_ascii=False)},\n"
        f"  testimonials: {json.dumps(testimonials, ensure_ascii=False)},\n"
        f"  client_names: {json.dumps(names, ensure_ascii=False)},\n"
        f"  social_proof: {json.dumps(f'Trusted by over 2,400 delighted {name} clients.', ensure_ascii=False)}"
    )

_DESIGN_SYSTEM_KEY_RE = re.compile(r"\bdesign_system\s*:\s*\{")


def _fill_design_system_gaps(body: str, primary: str, secondary: str, font: str) -> str:
    """Add only the scalar keys a present-but-thin `design_system` is missing.

    Returns `body` unchanged when nothing is missing or the object cannot be
    spanned — a brand contract guard must never be the thing that corrupts
    `mock.ts`.
    """
    m = _DESIGN_SYSTEM_KEY_RE.search(body)
    if not m:
        return body
    start = m.end()
    depth = 1
    i = start
    while i < len(body) and depth:
        ch = body[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return body
    inner = body[start : i - 1]
    missing = [
        (key, value)
        for key, value in (
            ("primary_color", primary or "#0f172a"),
            ("secondary_color", secondary or "#0369a1"),
            ("font_family", font or "Inter"),
        )
        # `mock.ts` carries both `primary_color:` (authored) and `"primary_color":`
        # (JSON-dumped by this guard's own earlier pass) — a check that misses the
        # quoted form re-inserts the key on every call and never converges.
        if not re.search(rf"""['"]?\b{key}\b['"]?\s*:""", inner)
    ]
    if not missing:
        return body
    addition = "".join(f"\n    {key}: {json.dumps(value)}," for key, value in missing)
    return body[:start] + addition + body[start:]


def ensure_brand_shape(
    workspace,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    design: dict | None = None,
) -> bool:
    """Guarantee missing brand nested fields so home/ops pages don't crash white.

    AI pages often read `brand.design_system.primary_color`, `brand.services[i].name`,
    and `brand.client_names[i]`. Only inject fields that are actually missing —
    re-injecting `services` when it already exists creates duplicate object keys
    (last wins) and can shrink a 4-item AI list to a 3-item stub, crashing on
    `brand.services[3].name`.
    """
    mock_path = "src/data/mock.ts"
    mock = read_file(workspace, mock_path)
    if not mock.strip():
        return False
    span = _brand_object_span(mock)
    if not span:
        return False
    body_start, close_at = span
    body = mock[body_start:close_at]

    # A `design_system` that exists but is missing a colour must be *completed*,
    # never re-declared: appending a sibling key makes the last one win, so the
    # sealed brand (display font, radius, recipe tokens) was silently replaced by
    # this generic patch. `tsc` reported it as TS1117 on request 40 and nothing
    # read that. `_fill_design_system_gaps` patches inside the existing object.
    has_ds = _brand_has_top_key(body, "design_system")
    needs_ds = not has_ds
    filled_ds = False
    if has_ds:
        filled_body = _fill_design_system_gaps(body, primary, secondary, font)
        if filled_body != body:
            mock = mock[:body_start] + filled_body + mock[close_at:]
            close_at += len(filled_body) - len(body)
            body = filled_body
            filled_ds = True
    needs_services = not re.search(r"\bservices\s*:", body)
    needs_testimonials = not re.search(r"\btestimonials\s*:", body)
    needs_proof = "social_proof" not in body
    needs_client_names = not re.search(r"\bclient_names\s*:", body)
    if not (needs_ds or needs_services or needs_testimonials or needs_proof or needs_client_names):
        if filled_ds:
            write_file(workspace, mock_path, mock)
            return True
        return False

    names = _toplevel_string_array(mock, "client_names") or _default_client_names(brand_name)
    testimonial_count = len(re.findall(r"\binitials\s*:|\bquote\s*:|\btext\s*:", body))
    while len(names) < max(8, testimonial_count, 3):
        names.append(f"Client {len(names) + 1}")

    # Build a full patch once, then keep only the missing keys (avoids duplicate-key overwrite).
    full = _brand_completeness_patch(
        brand_name, primary, secondary, font, client_names=names, design=design,
    )
    keep: list[str] = []
    if needs_ds:
        keep.append("design_system")
    if needs_services:
        keep.append("services")
    if needs_testimonials:
        keep.append("testimonials")
    if needs_client_names:
        keep.append("client_names")
    if needs_proof:
        keep.append("social_proof")

    pieces: list[str] = []
    for key in keep:
        # Match `key: <value>` through the next top-level key or end.
        m = re.search(
            rf"(?:^|\n)\s*({re.escape(key)}\s*:\s*)([\s\S]*?)(?=(?:\n\s*(?:design_system|services|testimonials|client_names|social_proof)\s*:)|$)",
            "\n" + full,
        )
        if m:
            pieces.append(m.group(1) + m.group(2).rstrip().rstrip(","))
        elif key == "client_names":
            pieces.append(f"client_names: {json.dumps(names, ensure_ascii=False)}")

    if not pieces:
        return False

    patch = ",\n  ".join(pieces)
    before = mock[:close_at].rstrip()
    if before.endswith(","):
        injection = f"\n  {patch},\n"
    else:
        injection = f",\n  {patch},\n"
    updated = mock[:close_at] + injection + mock[close_at:]
    write_file(workspace, mock_path, updated)
    return True
