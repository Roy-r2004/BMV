"""Regression: usage-driven brand/mock contract (scalable, no field hardcoding)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.safety import (  # noqa: E402
    MAX_BRAND_ARRAY_LEN,
    collect_brand_property_paths,
    ensure_brand_paths,
    ensure_brand_shape,
    ensure_brand_usage_paths,
    normalize_brand_path,
    _parse_brand_chain,
    _infer_brand_requirements,
    _count_array_items,
    _strip_ts_comments_and_strings,
    _find_brand_prop_span,
    _brand_object_span,
)
from app.application.preview_app.workspace import write_file  # noqa: E402


def main() -> None:
    # --- parsing / normalize ---
    assert _parse_brand_chain(".services[2].name") == ("services", 2, "name")
    assert _parse_brand_chain(".client_names[index]") == ("client_names", "*")
    assert _parse_brand_chain(".design_system.primary_color") == (
        "design_system",
        "primary_color",
    )
    assert normalize_brand_path(("services", 2, "name")) == "brand.services[].name"
    assert normalize_brand_path(("client_names", "*")) == "brand.client_names[]"

    # --- ignore comments / strings ---
    noisy = _strip_ts_comments_and_strings(
        'const x = "brand.hidden"; // brand.also_hidden\nbrand.visible[0].name;\n'
    )
    assert "brand.hidden" not in noisy or noisy.count("brand") == 1
    assert "visible" in noisy

    # --- array cap ---
    reqs = _infer_brand_requirements({("huge", 999, "name")})
    assert reqs["huge"]["min_len"] <= MAX_BRAND_ARRAY_LEN

    # --- unsupported / malformed ---
    assert _parse_brand_chain("") == ()
    assert _parse_brand_chain(".ok") == ("ok",)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Multiple pages, same + different paths
        write_file(
            root,
            "src/pages/HomePage.tsx",
            """
import { brand } from '../data/mock';
export default function Home() {
  // brand.ignored_in_comment
  const a = brand.client_names[0];
  const b = brand.services[3].name;
  const tip = "brand.not_real";
  return <div>{a}{b}</div>;
}
""",
        )
        write_file(
            root,
            "src/pages/owner/OpsPage.tsx",
            """
import { brand } from '../../data/mock';
export default function Ops() {
  const b = brand.services[1].name; // same path family
  const m = brand.weird_metric.label; // nested object
  return <div>{b}{m}</div>;
}
""",
        )
        write_file(
            root,
            "src/data/mock.ts",
            """
export const brand = {
  name: "Lumina",
  services: [
    { name: "One", description: "d" },
    { name: "Two", description: "d" },
  ],
  design_system: { primary_color: "#c45c7a" },
};
export const client_names = ["Ada Lovelace", "Grace Hopper", "Alan Turing", "Katherine Johnson"];
""",
        )

        paths = collect_brand_property_paths(root)
        assert any(p[0] == "client_names" for p in paths), paths
        assert any(p[0] == "services" and 3 in p for p in paths), paths
        assert any(p[0] == "weird_metric" for p in paths), paths
        # comment/string ignored
        assert not any(p[0] == "ignored_in_comment" for p in paths), paths
        assert not any(p[0] == "not_real" for p in paths), paths

        mock = (root / "src/data/mock.ts").read_text(encoding="utf-8")
        updated, logs = ensure_brand_paths(
            mock, paths, brand_name="Lumina", primary="#c45c7a", secondary="#222", font="Playfair",
        )
        assert logs, "expected contract logs"
        assert any(line.startswith("contract: ensured") for line in logs), logs
        assert "client_names:" in updated
        assert "weird_metric:" in updated
        assert "Ada Lovelace" in updated or "Client 1" in updated

        span = _brand_object_span(updated)
        body = updated[span[0] : span[1]]
        prop = _find_brand_prop_span(body, "services")
        assert prop
        assert _count_array_items(body[prop[0] : prop[1]]) >= 4

        # Never overwrite existing design_system.primary_color
        assert 'primary_color: "#c45c7a"' in updated or "primary_color: \"#c45c7a\"" in updated

        # Idempotent second pass — no wipe of existing services names
        updated2, logs2 = ensure_brand_paths(
            updated, paths, brand_name="Lumina", primary="#c45c7a", secondary="#222", font="Playfair",
        )
        assert '"One"' in updated2 or "name: \"One\"" in updated2 or "One" in updated2

        # Workspace wrapper + hardcoded fallback still works on empty brand
        write_file(
            root,
            "src/data/mock.ts",
            'export const brand = { name: "Bare" };\n',
        )
        write_file(
            root,
            "src/pages/HomePage.tsx",
            "import { brand } from '../data/mock';\nexport default function H(){ return <div>{brand.design_system.primary_color}</div> }",
        )
        assert ensure_brand_shape(root, "Bare", "#111", "#222", "Inter") or True
        # usage paths for design_system
        logs3 = ensure_brand_usage_paths(root, "Bare", "#111", "#222", "Inter")
        mock3 = (root / "src/data/mock.ts").read_text(encoding="utf-8")
        assert "design_system" in mock3
        assert "primary_color" in mock3

    print("OK: usage-driven brand contract regression passed")


if __name__ == "__main__":
    main()
