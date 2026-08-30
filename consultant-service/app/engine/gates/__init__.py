"""app/engine/gates - the gate, and the release it decides.

Three modules:

- laws.py          L1-L14 as registry and artifact queries, plus the contract
                   they are registered through (`LawId`, `ArtifactRef`, `Law`,
                   `LAWS`). The list IS the gate: removing an entry is the
                   mutation its test catches
- presentation.py  the page rather than the words - export_pdf's font, glyph
                   and orphan checks, tools/inspect_pdf.inspect UNCHANGED, and
                   the clipping check r30 had to leave to a human (MF2.5)
- release.py       release_status, the record in tools/release_audit's own
                   shape validated by its own validator, and the immutable
                   revision the artifacts are frozen into

Only `laws` is re-exported here, and deliberately: `app.engine.work_products`
imports `ArtifactRef` from this package while it is itself being imported, so
anything this module pulls in eagerly must not reach back into the renderers.
`presentation` and `release` are imported by name.
"""
from app.engine.gates.laws import (  # noqa: F401
    LAWS,
    ArtifactRef,
    Law,
    LawId,
    LawRegistry,
    blocking,
    run_laws,
)

__all__ = ["LAWS", "ArtifactRef", "Law", "LawId", "LawRegistry", "blocking", "run_laws"]
