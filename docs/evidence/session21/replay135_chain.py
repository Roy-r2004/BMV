"""Predict run 135's post-fix gate verdict: replay the full architect chain."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path("/repo/backend")
sys.path.insert(0, str(BACKEND))

from app.application.appspec.projection import (
    select_preview_scope,
    to_architecture_seed,
    merge_architecture_enrichment,
)
from app.application.preview_app.product_kind import (
    context_from_request,
    lock_chrome_on_architecture_seed,
    resolve_product_kind_contract,
    apply_product_kind_to_architect,
    validate_product_kind_chrome,
)
from app.application.preview_app.internal_desk import ensure_internal_desk_architect
from app.application.preview_app.saas_accounting import ensure_saas_accounting_architect

spec = json.loads(Path("/repo/docs/evidence/session21/run135-accepted-spec.json").read_text())
request = json.loads(Path("/repo/docs/evidence/session21/run135-request.json").read_text())
context = context_from_request(SimpleNamespace(**request))
contract = resolve_product_kind_contract(context)
print("kind:", contract.kind, "/", contract.subtype)

scope = select_preview_scope(spec)
seed = lock_chrome_on_architecture_seed(to_architecture_seed(spec, scope), contract)
# Run 135's architect enrichment died past-deadline; the merge keeps canonical.
architect = merge_architecture_enrichment(seed, {})
architect = apply_product_kind_to_architect(architect, contract, {})
architect = ensure_internal_desk_architect(architect, context=context)
architect = ensure_saas_accounting_architect(architect, context=context)
architect = apply_product_kind_to_architect(architect, contract, {})

paths = [(r.get("path"), r.get("surface"), r.get("skeleton_id")) for r in architect["routes"]]
print("final routes:")
for p in paths:
    print("  ", p)
issues = validate_product_kind_chrome(architect)
print("final gate issues:", issues or "NONE — gate passes")
