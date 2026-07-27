"""Request #40 reproduction fixture: generated-data API and strict TypeScript.

Production request #40 completed every generation stage and then failed
deterministic pre-build validation with 13 ``typescript_no_emit`` diagnostics.
The recorded production diagnostics were:

    src/components/business/CompHomeComponent.tsx:3:10
        Module '"@/generated/content-data"' has no exported member
        'getServiceSeedData'.
    src/components/business/CompHomeComponent.tsx:13:54
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceDetailComponent.tsx:3:10
        Module '"@/generated/content-data"' has no exported member
        'getServiceSeedData'.
    src/components/business/CompServiceDetailComponent.tsx:9:33
        Parameter 's' implicitly has an 'any' type.
    src/components/business/CompServiceDetailComponent.tsx:9:52
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceDetailComponent.tsx:15:43
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceDetailComponent.tsx:16:50
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceDetailComponent.tsx:17:47
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceListComponent.tsx:3:10
        Module '"@/generated/content-data"' has no exported member
        'getServiceSeedData'.
    src/components/business/CompServiceListComponent.tsx:17:24
        Parameter 'service' implicitly has an 'any' type.
    src/components/business/CompServiceListComponent.tsx:18:49
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceListComponent.tsx:19:51
        Parameter 'v' implicitly has an 'any' type.
    src/components/business/CompServiceListComponent.tsx:20:58
        Parameter 'v' implicitly has an 'any' type.

The component sources below reproduce that diagnostic set on the same files and
the same lines. Exact columns depend on the original formatting, which the
persisted failure record does not retain, so tests compare file, line,
diagnostic class, and parameter symbol.
"""
from __future__ import annotations

from types import SimpleNamespace


REQUEST_40_COMPONENT_PATHS = (
    "src/components/business/CompHomeComponent.tsx",
    "src/components/business/CompServiceDetailComponent.tsx",
    "src/components/business/CompServiceListComponent.tsx",
)

# (path, line, diagnostic_class, symbol) recorded from production request #40.
REQUEST_40_EXPECTED_DIAGNOSTICS = (
    ("src/components/business/CompHomeComponent.tsx", 3, "missing_export", "getServiceSeedData"),
    ("src/components/business/CompHomeComponent.tsx", 13, "implicit_any", "v"),
    ("src/components/business/CompServiceDetailComponent.tsx", 3, "missing_export", "getServiceSeedData"),
    ("src/components/business/CompServiceDetailComponent.tsx", 9, "implicit_any", "s"),
    ("src/components/business/CompServiceDetailComponent.tsx", 9, "implicit_any", "v"),
    ("src/components/business/CompServiceDetailComponent.tsx", 15, "implicit_any", "v"),
    ("src/components/business/CompServiceDetailComponent.tsx", 16, "implicit_any", "v"),
    ("src/components/business/CompServiceDetailComponent.tsx", 17, "implicit_any", "v"),
    ("src/components/business/CompServiceListComponent.tsx", 3, "missing_export", "getServiceSeedData"),
    ("src/components/business/CompServiceListComponent.tsx", 17, "implicit_any", "service"),
    ("src/components/business/CompServiceListComponent.tsx", 18, "implicit_any", "v"),
    ("src/components/business/CompServiceListComponent.tsx", 19, "implicit_any", "v"),
    ("src/components/business/CompServiceListComponent.tsx", 20, "implicit_any", "v"),
)

REQUEST_40_HOME_COMPONENT = """import { useState } from "react";
import { Link } from "react-router-dom";
import { getServiceSeedData } from "@/generated/content-data";

export function CompHomeComponent() {
  const [activeState] = useState("STATE-HOME-VIEWING");
  const services = getServiceSeedData();

  return (
    <section data-bmv-component-id="COMP-HOME">
      <span data-bmv-state-id="STATE-HOME-VIEWING">{activeState}</span>
      <p data-bmv-evidence-id="EVIDENCE-HOME-CONTENT">Book in three steps.</p>
      <p>{services.filter((v) => v.serviceName).length} services available</p>
      <Link to="/services" data-bmv-action-id="ACTION-NAV-TO-SERVICE-LIST">
        Browse services
      </Link>
    </section>
  );
}
"""

REQUEST_40_SERVICE_DETAIL_COMPONENT = """import { useState } from "react";
import { Link } from "react-router-dom";
import { getServiceSeedData } from "@/generated/content-data";

export function CompServiceDetailComponent() {
  const [activeState] = useState("STATE-SERVICE-DETAIL-VIEWING");
  const services = getServiceSeedData();

  const detail = services.find((s) => s.values.some((v) => v.serviceName));

  return (
    <section data-bmv-component-id="COMP-SERVICE-DETAIL">
      <span data-bmv-state-id="STATE-SERVICE-DETAIL-VIEWING">{activeState}</span>
      <p data-bmv-evidence-id="EVIDENCE-SERVICE-DETAIL-CONTENT">
        {detail?.values.find((v) => v.serviceName)?.value}
        {detail?.values.find((v) => v.serviceDuration)?.value}
        {detail?.values.find((v) => v.servicePrice)?.value}
      </p>
      <Link to="/booking" data-bmv-action-id="ACTION-INITIATE-BOOKING">
        Book this service
      </Link>
    </section>
  );
}
"""

REQUEST_40_SERVICE_LIST_COMPONENT = """import { useState } from "react";
import { Link } from "react-router-dom";
import { getServiceSeedData } from "@/generated/content-data";

export function CompServiceListComponent() {
  const [activeState] = useState("STATE-SERVICE-LIST-VIEWING");
  const services = getServiceSeedData();

  return (
    <section data-bmv-component-id="COMP-SERVICE-LIST">
      <span data-bmv-state-id="STATE-SERVICE-LIST-VIEWING">{activeState}</span>
      <h2>Our services</h2>
      <p data-bmv-evidence-id="EVIDENCE-SERVICE-LIST-DISPLAY">
        Select a service to continue.
      </p>
      <ul>
        {services.map((service) => (
          <li key={service.values.find((v) => v.serviceId)?.value}>
            <h3>{service.values.find((v) => v.serviceName)?.value}</h3>
            <p>{service.values.find((v) => v.serviceDuration)?.value}</p>
          </li>
        ))}
      </ul>
      <Link to="/services/first" data-bmv-action-id="ACTION-SELECT-SERVICE">
        Select
      </Link>
    </section>
  );
}
"""

REQUEST_40_COMPONENTS = {
    "src/components/business/CompHomeComponent.tsx": REQUEST_40_HOME_COMPONENT,
    "src/components/business/CompServiceDetailComponent.tsx": (
        REQUEST_40_SERVICE_DETAIL_COMPONENT
    ),
    "src/components/business/CompServiceListComponent.tsx": (
        REQUEST_40_SERVICE_LIST_COMPONENT
    ),
}

# The same components written against the canonical generated-data API that the
# component prompt now hands to the model.
CANONICAL_API_COMPONENTS = {
    "src/components/business/CompHomeComponent.tsx": """import { useState } from "react";
import { Link } from "react-router-dom";
import { getServiceSeedData } from "@/generated/content-data";
import type { ServiceRecord } from "@/generated/content-data";

export function CompHomeComponent() {
  const [activeState] = useState("STATE-HOME-VIEWING");
  const services: readonly ServiceRecord[] = getServiceSeedData();

  return (
    <section data-bmv-component-id="COMP-HOME">
      <span data-bmv-state-id="STATE-HOME-VIEWING">{activeState}</span>
      <p data-bmv-evidence-id="EVIDENCE-HOME-CONTENT">Book in three steps.</p>
      <p>{services.filter((v) => v.serviceName).length} services available</p>
      <Link to="/services" data-bmv-action-id="ACTION-NAV-TO-SERVICE-LIST">
        Browse services
      </Link>
    </section>
  );
}
""",
    "src/components/business/CompServiceDetailComponent.tsx": """import { useState } from "react";
import { Link } from "react-router-dom";
import { serviceSeedData } from "@/generated/content-data";

export function CompServiceDetailComponent() {
  const [activeState] = useState("STATE-SERVICE-DETAIL-VIEWING");
  const detail = serviceSeedData[0];

  return (
    <section data-bmv-component-id="COMP-SERVICE-DETAIL">
      <span data-bmv-state-id="STATE-SERVICE-DETAIL-VIEWING">{activeState}</span>
      <p data-bmv-evidence-id="EVIDENCE-SERVICE-DETAIL-CONTENT">
        {detail?.serviceName}
        {detail?.serviceDuration}
        {detail?.servicePrice}
      </p>
      <Link to="/booking" data-bmv-action-id="ACTION-INITIATE-BOOKING">
        Book this service
      </Link>
    </section>
  );
}
""",
    "src/components/business/CompServiceListComponent.tsx": """import { getServiceSeedData } from "@/generated/content-data";

export function CompServiceListComponent() {
  const services = getServiceSeedData();

  return (
    <section data-bmv-component-id="COMP-SERVICE-LIST">
      <span data-bmv-state-id="STATE-SERVICE-LIST-VIEWING">list</span>
      <ul>
        {services.map((service) => (
          <li key={service.serviceId} data-bmv-action-id="ACTION-SELECT-SERVICE">
            <h3>{service.serviceName}</h3>
            <p>{service.serviceDuration} minutes</p>
            <p>{service.servicePrice}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
""",
}

APP_STUB = """export default function App() {
  return <main data-bmv-app-root="request-40-fixture" />;
}
"""


def _seed_record(values: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        values=tuple(
            SimpleNamespace(field_id=field_id, value=value)
            for field_id, value in values.items()
        )
    )


_SERVICE_SEEDS = (
    {
        "FIELD-SERVICE-ID": "svc-consultation",
        "FIELD-SERVICE-NAME": "Consultation",
        "FIELD-SERVICE-DESCRIPTION": "A 30 minute intake conversation.",
        "FIELD-SERVICE-DURATION": 30,
        "FIELD-SERVICE-PRICE": "45.00",
    },
    {
        "FIELD-SERVICE-ID": "svc-full-session",
        "FIELD-SERVICE-NAME": "Full session",
        "FIELD-SERVICE-DESCRIPTION": "A full 60 minute working session.",
        "FIELD-SERVICE-DURATION": 60,
        "FIELD-SERVICE-PRICE": "90.00",
    },
)


def request40_content_data() -> SimpleNamespace:
    """A request #40 shaped ContentDataPlan projection (services collection)."""

    payload = {
        "schema_version": "1.0",
        "content_items": [
            {
                "content_id": "CONTENT-HOME-HEADLINE",
                "semantic_kind": "headline",
                "value": "Book your next appointment",
            }
        ],
        "data_collections": [
            {
                "collection_id": "COLLECTION-SERVICES",
                "entity_id": "ENTITY-SERVICE",
                "field_ids": sorted(_SERVICE_SEEDS[0]),
                "seed_records": [
                    {
                        "record_id": f"RECORD-SERVICE-{index}",
                        "values": [
                            {"field_id": field_id, "value": value}
                            for field_id, value in seed.items()
                        ],
                    }
                    for index, seed in enumerate(_SERVICE_SEEDS)
                ],
            }
        ],
    }
    return SimpleNamespace(
        content_items=(SimpleNamespace(content_id="CONTENT-HOME-HEADLINE"),),
        data_collections=(
            SimpleNamespace(
                collection_id="COLLECTION-SERVICES",
                entity_id="ENTITY-SERVICE",
                field_ids=tuple(sorted(_SERVICE_SEEDS[0])),
                seed_records=tuple(_seed_record(seed) for seed in _SERVICE_SEEDS),
            ),
        ),
        relationships=(),
        model_dump=lambda mode="json": payload,
    )


def request40_context() -> SimpleNamespace:
    """Minimal candidate context for the deterministic data-export emitter."""

    return SimpleNamespace(
        content_data=request40_content_data(),
        page_purpose=SimpleNamespace(
            pages=(),
            model_dump=lambda mode="json": {"pages": []},
        ),
        interactions=SimpleNamespace(
            interactions=(),
            model_dump=lambda mode="json": {"interactions": []},
        ),
        refs=SimpleNamespace(
            content_data_plan_ref=SimpleNamespace(
                sha256=(
                    "dcc90336cb2431e010140559f72fb6e88c9c307927573f4c5b8b8a8b"
                    "7403ee24"
                )
            ),
        ),
    )


_CANONICAL_API_MARKER = "// Canonical generated-data API"


def legacy_content_data_module(source: str) -> str:
    """Strip the canonical API block to recreate the pre-fix module."""

    head, marker, _tail = source.partition(_CANONICAL_API_MARKER)
    if not marker:
        return source
    return head.rstrip("\n") + "\n"


__all__ = [
    "APP_STUB",
    "CANONICAL_API_COMPONENTS",
    "REQUEST_40_COMPONENTS",
    "REQUEST_40_COMPONENT_PATHS",
    "REQUEST_40_EXPECTED_DIAGNOSTICS",
    "legacy_content_data_module",
    "request40_content_data",
    "request40_context",
]
