"""Deterministic JSON → TSX compositor for public-utility pages.

AI fills content only. Layout type is inferred from the route. The page frame
(PublicShell + SkeletonComposer + typed workspace) is always authored here so
freeform React cannot invent crashing prop/import patterns.
"""
from __future__ import annotations

import json
import re
from typing import Any


UTILITY_SKELETON_ID = "public-utility"

_WORKSPACE_TYPES = frozenset(
    {"cart", "checkout", "tracking", "account", "confirmation", "generic"}
)


def infer_utility_workspace_type(path: str = "", title: str = "", page_type: str = "") -> str:
    """Map route text → fixed workspace layout. Never ask the model for architecture."""
    blob = f"{path} {title} {page_type}".lower()
    if re.search(
        r"waitlist|confirm|confirmation|success|thank[- ]?you|booked|you're on",
        blob,
    ):
        return "confirmation"
    if re.search(r"\bcart\b|basket|bag\b", blob):
        return "cart"
    if re.search(r"checkout|payment|pay\b|billing", blob):
        return "checkout"
    if re.search(r"track|tracking|shipment|delivery status|order status", blob):
        return "tracking"
    if re.search(r"account|profile|login|sign[- ]?in|wishlist|orders?\b", blob):
        return "account"
    return "generic"


def _s(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, (int, float, bool)):
        return str(value)
    text = str(value).strip()
    return text or fallback


def _money(value: Any) -> str:
    """Format amounts as plain numbers (no currency symbols) for kit consistency."""
    if isinstance(value, (int, float)):
        if float(value) == int(value):
            return str(int(value))
        return f"{float(value):.2f}"
    text = _s(value).replace("$", "").replace(",", "").strip()
    try:
        num = float(text)
    except ValueError:
        return text or "0"
    if num == int(num):
        return str(int(num))
    return f"{num:.2f}"


def _js(value: Any) -> str:
    return json.dumps("" if value is None else value, ensure_ascii=False)


def default_utility_content(
    workspace_type: str,
    *,
    brand_name: str,
    title: str,
    path: str = "",
) -> dict[str, Any]:
    """Deterministic fallback content when AI JSON is missing/invalid."""
    brand = brand_name or "Brand"
    page_title = title or workspace_type.title()
    if workspace_type == "cart":
        return {
            "header": {
                "title": page_title or "Your cart",
                "description": f"Review items before checkout at {brand}.",
            },
            "workspace": {
                "lines": [
                    {
                        "name": f"{brand} Signature Item",
                        "detail": "Standard configuration",
                        "qty": "1",
                        "price": "149",
                    },
                    {
                        "name": "Care package",
                        "detail": "Optional add-on",
                        "qty": "1",
                        "price": "29",
                    },
                ]
            },
            "summary": {
                "title": "Order summary",
                "rows": [
                    {"label": "Subtotal", "value": "178"},
                    {"label": "Shipping", "value": "12"},
                    {"label": "Total", "value": "190"},
                ],
                "primary_cta": {"label": "Checkout", "href": "/checkout"},
            },
            "footer": {
                "description": f"{brand} — clear checkout, real inventory, no surprises."
            },
        }
    if workspace_type == "checkout":
        return {
            "header": {
                "title": page_title or "Checkout",
                "description": "Confirm delivery details and place your order.",
            },
            "workspace": {
                "fields": [
                    {"label": "Full name", "placeholder": "Alex Rivera", "type": "text"},
                    {"label": "Email", "placeholder": "alex@email.com", "type": "email"},
                    {"label": "Phone", "placeholder": "+1 555 0100", "type": "tel"},
                    {"label": "Delivery address", "placeholder": "Street, city, zip", "type": "text"},
                ],
                "note": "Payment is collected at confirmation — this preview uses mock checkout.",
            },
            "summary": {
                "title": "Payment summary",
                "rows": [
                    {"label": "Items", "value": "178"},
                    {"label": "Delivery", "value": "12"},
                    {"label": "Total due", "value": "190"},
                ],
                "primary_cta": {"label": "Place order", "href": "/order-tracking"},
            },
            "footer": {"description": f"Secure checkout powered by {brand}."},
        }
    if workspace_type == "tracking":
        return {
            "header": {
                "title": page_title or "Track your order",
                "description": "Live status for your most recent purchase.",
            },
            "workspace": {
                "order_id": "VB-10482",
                "status": "In transit",
                "carrier": "Express Freight",
                "steps": [
                    {"label": "Order placed", "done": True},
                    {"label": "Prepared", "done": True},
                    {"label": "Shipped", "done": True},
                    {"label": "Delivered", "done": False},
                ],
            },
            "summary": {
                "title": "Shipment",
                "rows": [
                    {"label": "ETA", "value": "Thu · afternoon"},
                    {"label": "Items", "value": "2"},
                ],
                "primary_cta": {"label": "View catalog", "href": "/"},
            },
            "footer": {"description": f"{brand} keeps you updated until delivery."},
        }
    if workspace_type == "account":
        return {
            "header": {
                "title": page_title or "Your account",
                "description": "Orders, saved items, and preferences.",
            },
            "workspace": {
                "cards": [
                    {
                        "title": "Recent orders",
                        "description": "2 open · 1 delivered this month",
                        "cta_label": "Track orders",
                        "cta_href": path or "/order-tracking",
                    },
                    {
                        "title": "Saved items",
                        "description": "3 products waiting in your list",
                        "cta_label": "Continue shopping",
                        "cta_href": "/",
                    },
                ]
            },
            "footer": {"description": f"Signed-in experience for {brand} customers."},
        }
    if workspace_type == "confirmation":
        return {
            "header": {
                "title": page_title or "You're all set",
                "description": f"We'll follow up with next steps from {brand}.",
            },
            "detail": "Confirmation on file",
            "eyebrow": "Confirmed",
            "primary_cta": {"label": "Back to home", "href": "/"},
            "workspace": {
                "cards": [
                    {
                        "title": "Explore more",
                        "description": f"See what else {brand} offers.",
                        "cta_label": "Browse",
                        "cta_href": "/",
                    },
                    {
                        "title": "Get help",
                        "description": "Questions? Reach out anytime.",
                        "cta_label": "Contact",
                        "cta_href": "/contact",
                    },
                    {
                        "title": "AI features",
                        "description": "Try the assistants built for this business.",
                        "cta_label": "Open hub",
                        "cta_href": "/ai-features",
                    },
                ]
            },
            "footer": {"description": f"Thank you for choosing {brand}."},
        }
    return {
        "header": {
            "title": page_title or "Workspace",
            "description": f"Transactional flow for {brand}.",
        },
        "workspace": {
            "cards": [
                {
                    "title": "Continue",
                    "description": "Complete this step to move forward.",
                    "cta_label": "Get started",
                    "cta_href": "/",
                }
            ]
        },
        "footer": {"description": f"{brand} — built for daily use."},
    }


def normalize_utility_content(
    raw: dict[str, Any] | None,
    workspace_type: str,
    *,
    brand_name: str,
    title: str,
    path: str = "",
) -> dict[str, Any]:
    """Merge AI JSON onto defaults; coerce types so the compositor never crashes."""
    base = default_utility_content(
        workspace_type, brand_name=brand_name, title=title, path=path
    )
    data = raw if isinstance(raw, dict) else {}

    header_in = data.get("header") if isinstance(data.get("header"), dict) else {}
    base["header"] = {
        "title": _s(header_in.get("title"), base["header"]["title"]),
        "description": _s(header_in.get("description"), base["header"]["description"]),
    }

    footer_in = data.get("footer") if isinstance(data.get("footer"), dict) else {}
    base["footer"] = {
        "description": _s(
            footer_in.get("description"), base["footer"]["description"]
        )
    }

    summary_in = data.get("summary") if isinstance(data.get("summary"), dict) else None
    if summary_in is not None or workspace_type in {"cart", "checkout", "tracking"}:
        summary_base = base.get("summary") or {
            "title": "Summary",
            "rows": [],
            "primary_cta": {"label": "Continue", "href": "/"},
        }
        src = summary_in or {}
        rows_in = src.get("rows") if isinstance(src.get("rows"), list) else summary_base.get("rows")
        cta_in = src.get("primary_cta") if isinstance(src.get("primary_cta"), dict) else {}
        cta_base = summary_base.get("primary_cta") or {}
        base["summary"] = {
            "title": _s(src.get("title"), summary_base.get("title", "Summary")),
            "rows": [
                {
                    "label": _s(row.get("label"), "Item"),
                    "value": _money(row.get("value")),
                }
                for row in (rows_in or [])
                if isinstance(row, dict)
            ]
            or list(summary_base.get("rows") or []),
            "primary_cta": {
                "label": _s(cta_in.get("label"), cta_base.get("label", "Continue")),
                "href": _s(cta_in.get("href"), cta_base.get("href", "/")),
            },
        }

    ws_in = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    ws_base = base["workspace"]

    if workspace_type == "cart":
        lines_in = ws_in.get("lines") if isinstance(ws_in.get("lines"), list) else None
        lines = []
        for line in lines_in or ws_base.get("lines") or []:
            if not isinstance(line, dict):
                continue
            lines.append(
                {
                    "name": _s(line.get("name"), "Item"),
                    "detail": _s(line.get("detail") or line.get("sku") or line.get("meta")),
                    "qty": _s(line.get("qty") or line.get("quantity"), "1"),
                    "price": _money(line.get("price")),
                }
            )
        base["workspace"] = {"lines": lines or list(ws_base.get("lines") or [])}
    elif workspace_type == "checkout":
        fields_in = ws_in.get("fields") if isinstance(ws_in.get("fields"), list) else None
        fields = []
        for field in fields_in or ws_base.get("fields") or []:
            if not isinstance(field, dict):
                continue
            fields.append(
                {
                    "label": _s(field.get("label"), "Field"),
                    "placeholder": _s(field.get("placeholder"), ""),
                    "type": _s(field.get("type"), "text"),
                }
            )
        base["workspace"] = {
            "fields": fields or list(ws_base.get("fields") or []),
            "note": _s(ws_in.get("note"), ws_base.get("note", "")),
        }
    elif workspace_type == "tracking":
        steps_in = ws_in.get("steps") if isinstance(ws_in.get("steps"), list) else None
        steps = []
        for step in steps_in or ws_base.get("steps") or []:
            if not isinstance(step, dict):
                continue
            steps.append(
                {
                    "label": _s(step.get("label"), "Step"),
                    "done": bool(step.get("done")),
                }
            )
        base["workspace"] = {
            "order_id": _s(ws_in.get("order_id"), ws_base.get("order_id", "ORDER-1")),
            "status": _s(ws_in.get("status"), ws_base.get("status", "Processing")),
            "carrier": _s(ws_in.get("carrier"), ws_base.get("carrier", "")),
            "steps": steps or list(ws_base.get("steps") or []),
        }
    else:
        cards_in = ws_in.get("cards") if isinstance(ws_in.get("cards"), list) else None
        cards = []
        for card in cards_in or ws_base.get("cards") or []:
            if not isinstance(card, dict):
                continue
            cards.append(
                {
                    "title": _s(card.get("title"), "Item"),
                    "description": _s(card.get("description"), ""),
                    "cta_label": _s(card.get("cta_label"), "Open"),
                    "cta_href": _s(card.get("cta_href"), "/"),
                }
            )
        base["workspace"] = {"cards": cards or list(ws_base.get("cards") or [])}

    if workspace_type == "confirmation":
        cta_in = data.get("primary_cta") if isinstance(data.get("primary_cta"), dict) else {}
        cta_base = base.get("primary_cta") if isinstance(base.get("primary_cta"), dict) else {}
        base["detail"] = _s(data.get("detail"), base.get("detail", ""))
        base["eyebrow"] = _s(data.get("eyebrow"), base.get("eyebrow", "Confirmed"))
        base["primary_cta"] = {
            "label": _s(cta_in.get("label"), cta_base.get("label", "Continue")),
            "href": _s(cta_in.get("href"), cta_base.get("href", "/")),
        }

    return base


def _workspace_jsx(workspace_type: str, workspace: dict[str, Any]) -> str:
    if workspace_type == "cart":
        columns = [
            {"key": "name", "header": "Item"},
            {"key": "detail", "header": "Details"},
            {"key": "qty", "header": "Qty"},
            {"key": "price", "header": "Price"},
        ]
        rows = [
            {
                "name": line["name"],
                "detail": line.get("detail") or "—",
                "qty": line["qty"],
                "price": line["price"],
            }
            for line in workspace.get("lines") or []
        ]
        return (
            "<Card className=\"space-y-4 p-6\">\n"
            f"          <Table columns={{{_js(columns)}}} rows={{{_js(rows)}}} caption=\"Cart line items\" />\n"
            "        </Card>"
        )
    if workspace_type == "checkout":
        field_blocks = []
        for field in workspace.get("fields") or []:
            field_blocks.append(
                "          <Input\n"
                f"            label={{{_js(field['label'])}}}\n"
                f"            placeholder={{{_js(field.get('placeholder') or '')}}}\n"
                f"            type={{{_js(field.get('type') or 'text')}}}\n"
                "          />"
            )
        note = _s(workspace.get("note"))
        note_jsx = (
            f"\n          <p className=\"text-sm text-muted\">{_js(note)[1:-1]}</p>"
            if note
            else ""
        )
        # note uses json string without quotes for JSX text - better use {'...'}
        if note:
            note_jsx = f"\n          <p className=\"text-sm text-muted\">{{{_js(note)}}}</p>"
        else:
            note_jsx = ""
        return (
            "<Card className=\"space-y-4 p-6\">\n"
            "          <div className=\"grid gap-4 md:grid-cols-2\">\n"
            + "\n".join(field_blocks)
            + "\n          </div>"
            + note_jsx
            + "\n        </Card>"
        )
    if workspace_type == "tracking":
        steps = workspace.get("steps") or []
        step_items = []
        for step in steps:
            badge = "Done" if step.get("done") else "Next"
            step_items.append(
                "            <li className=\"flex items-center justify-between gap-3 border-t border-border-subtle py-3 first:border-t-0 first:pt-0\">\n"
                f"              <span className=\"text-sm text-foreground\">{{{_js(step['label'])}}}</span>\n"
                f"              <Badge>{badge}</Badge>\n"
                "            </li>"
            )
        carrier = _s(workspace.get("carrier"))
        carrier_jsx = (
            f"\n          <p className=\"text-sm text-muted\">Carrier · {{{_js(carrier)}}}</p>"
            if carrier
            else ""
        )
        return (
            "<Card className=\"space-y-4 p-6\">\n"
            "          <div className=\"flex flex-wrap items-center gap-3\">\n"
            f"            <p className=\"text-sm text-muted\">Order {{{_js(workspace.get('order_id'))}}}</p>\n"
            f"            <Badge>{{{_js(_s(workspace.get('status'), 'Processing'))}}}</Badge>\n"
            "          </div>"
            + carrier_jsx
            + "\n          <ul className=\"mt-2\">\n"
            + "\n".join(step_items)
            + "\n          </ul>\n"
            "        </Card>"
        )
    # account / generic (never ship 3 cards in a 2-col grid — orphan column)
    cards = workspace.get("cards") or []
    card_blocks = []
    for card in cards:
        card_blocks.append(
            "          <Card className=\"flex flex-col gap-3 p-5\">\n"
            f"            <h3 className=\"font-display text-xl text-foreground\">{{{_js(card['title'])}}}</h3>\n"
            f"            <p className=\"text-sm leading-6 text-muted\">{{{_js(card.get('description') or '')}}}</p>\n"
            f"            <Button href={{{_js(card.get('cta_href') or '/')}}} className=\"mt-auto w-fit\">\n"
            f"              {{{_js(card.get('cta_label') or 'Open')}}}\n"
            "            </Button>\n"
            "          </Card>"
        )
    grid = (
        "sm:grid-cols-2 lg:grid-cols-3"
        if len(cards) >= 3
        else "sm:grid-cols-2"
        if len(cards) == 2
        else "grid-cols-1"
    )
    return (
        f"<div className=\"grid gap-4 {grid}\">\n"
        + "\n".join(card_blocks)
        + "\n        </div>"
    )


def _summary_jsx(summary: dict[str, Any] | None) -> str | None:
    if not summary:
        return None
    rows = summary.get("rows") or []
    row_jsx = "\n".join(
        "            <div className=\"flex items-center justify-between gap-3 text-sm\">\n"
        f"              <span className=\"text-muted\">{{{_js(row['label'])}}}</span>\n"
        f"              <span className=\"font-semibold tabular-nums text-foreground\">{{{_js(row['value'])}}}</span>\n"
        "            </div>"
        for row in rows
        if isinstance(row, dict)
    )
    cta = summary.get("primary_cta") or {}
    return (
        "<Card className=\"space-y-4 p-6\">\n"
        f"          <h3 className=\"font-display text-2xl text-foreground\">{{{_js(summary.get('title') or 'Summary')}}}</h3>\n"
        "          <div className=\"space-y-2\">\n"
        + row_jsx
        + "\n          </div>\n"
        f"          <Button href={{{_js(cta.get('href') or '/')}}} className=\"w-full sm:w-auto\">\n"
        f"            {{{_js(cta.get('label') or 'Continue')}}}\n"
        "          </Button>\n"
        "        </Card>"
    )


def compose_utility_page_tsx(
    *,
    file_path: str,
    route: dict,
    content: dict[str, Any],
    brand_name: str,
    workspace_type: str | None = None,
) -> str:
    """Emit a catalogue-valid public-utility page from normalized content."""
    stem = (file_path or "UtilityPage").replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
    component = re.sub(r"[^A-Za-z0-9_]", "", stem) or "UtilityPage"
    if component[0].isdigit():
        component = f"Page{component}"

    path = str(route.get("path") or "")
    title = str(route.get("title") or component)
    wtype = workspace_type or infer_utility_workspace_type(
        path, title, str(route.get("page_type") or "")
    )
    if wtype not in _WORKSPACE_TYPES:
        wtype = "generic"

    normalized = normalize_utility_content(
        content,
        wtype,
        brand_name=brand_name or "Brand",
        title=title,
        path=path,
    )

    header = normalized["header"]
    footer = normalized["footer"]

    # Confirmation / waitlist / success → ConfirmStage (centered, equal next steps).
    if wtype == "confirmation":
        cards = (normalized.get("workspace") or {}).get("cards") or []
        steps_js = _js(
            [
                {
                    "title": c.get("title"),
                    "description": c.get("description") or "",
                    "ctaLabel": c.get("cta_label") or "Open",
                    "href": c.get("cta_href") or "/",
                }
                for c in cards
                if isinstance(c, dict)
            ]
        )
        cta = normalized.get("primary_cta") or {"label": "Continue", "href": "/"}
        return f"""// composed confirmation page (ConfirmStage)
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ PublicShell, PublicNav, BrandFooter, ConfirmStage }} from '@/ui';

export default function {component}() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();

  return (
    <PublicShell
      brandName={{{_js(brand_name or "Brand")}}}
      chrome="solid"
      nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}
    >
      <ConfirmStage
        eyebrow={{{_js(normalized.get("eyebrow") or "Confirmed")}}}
        title={{{_js(header["title"])}}}
        detail={{{_js(normalized.get("detail") or "")}}}
        description={{{_js(header["description"])}}}
        primaryCta={{{_js({"label": cta.get("label") or "Continue", "href": cta.get("href") or "/"})}}}
        nextSteps={{{steps_js}}}
      />
      <BrandFooter
        brandName={{{_js(brand_name or "Brand")}}}
        description={{{_js(footer["description"])}}}
      />
    </PublicShell>
  );
}}
"""

    workspace_jsx = _workspace_jsx(wtype, normalized["workspace"])
    summary_jsx = _summary_jsx(normalized.get("summary"))

    components = [
        "PublicShell",
        "PublicNav",
        "PageHeader",
        "BrandFooter",
        "Card",
        "Button",
        "SkeletonComposer",
        "getSkeleton",
    ]
    if wtype == "cart":
        components.append("Table")
    elif wtype == "checkout":
        components.append("Input")
    elif wtype == "tracking":
        components.append("Badge")

    slot_parts = [
        "    header: (\n"
        "      <PageHeader\n"
        f"        title={{{_js(header['title'])}}}\n"
        f"        description={{{_js(header['description'])}}}\n"
        "      />\n"
        "    ),",
        f"    workspace: (\n      {workspace_jsx}\n    ),",
    ]
    if summary_jsx:
        slot_parts.append(f"    summary: (\n      {summary_jsx}\n    ),")
    slot_parts.append(
        "    footer: (\n"
        "      <BrandFooter\n"
        f"        brandName={{{_js(brand_name or 'Brand')}}}\n"
        f"        description={{{_js(footer['description'])}}}\n"
        "      />\n"
        "    ),"
    )

    return f"""// composed public-utility page (content JSON → kit)
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ {", ".join(components)} }} from '@/ui';

const SKELETON_ID = {json.dumps(UTILITY_SKELETON_ID)} as const;

export default function {component}() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
{chr(10).join(slot_parts)}
  }};

  return (
    <PublicShell
      brandName={{{_js(brand_name or "Brand")}}}
      chrome="solid"
      nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}
    >
      <div data-skeleton={{skeleton.id}} data-utility-type={{{_js(wtype)}}}>
        <SkeletonComposer skeletonId={{SKELETON_ID}} slots={{slots}} />
      </div>
    </PublicShell>
  );
}}
"""


def is_utility_catalogue_route(route: dict | None, skeleton_id: str = "") -> bool:
    sid = str(skeleton_id or (route or {}).get("skeleton_id") or "")
    return sid == UTILITY_SKELETON_ID


def _is_ai_feature_hub_route(
    route: dict | None,
    page_plan: dict | None = None,
) -> bool:
    """AI hub is a dedicated AiFeatureDeck face — never a utility checkout layout."""
    route = route or {}
    page_plan = page_plan or {}
    path = str(route.get("path") or page_plan.get("path") or "").rstrip("/").lower()
    page_id = str(
        route.get("app_spec_page_id")
        or route.get("page_id")
        or page_plan.get("app_spec_page_id")
        or page_plan.get("page_id")
        or page_plan.get("id")
        or ""
    ).casefold()
    component = str(
        route.get("component_file") or page_plan.get("component_file") or ""
    ).replace("\\", "/").lower()
    page_type = str(route.get("page_type") or page_plan.get("page_type") or "").casefold()
    if path == "/ai-features" or path.endswith("/ai-features"):
        return True
    if page_id == "page-ai-features":
        return True
    if page_type == "ai_hub":
        return True
    if component.endswith("aifeaturespage.tsx"):
        return True
    return False


def should_compose_utility_page(
    route: dict | None,
    skeleton_id: str = "",
    page_plan: dict | None = None,
) -> bool:
    """True when layout must come from the utility compositor (never freeform).

    AppSpec contracts must not bypass this — they only add content hooks.
    Also recovers when architect assigns the wrong skeleton to a transactional
    path (cart / checkout / confirm / tracking / account).
    """
    route = route or {}
    page_plan = page_plan or {}
    if _is_ai_feature_hub_route(route, page_plan):
        return False
    if is_utility_catalogue_route(route, skeleton_id):
        return True
    path = str(route.get("path") or page_plan.get("path") or "")
    title = str(route.get("title") or page_plan.get("title") or "")
    page_type = str(route.get("page_type") or page_plan.get("page_type") or "")
    workspace_type = infer_utility_workspace_type(path, title, page_type)
    return workspace_type in {"cart", "checkout", "tracking", "account", "confirmation"}
