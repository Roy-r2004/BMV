"""Tabular sections as CSV, with the stdlib `csv` module (design 11.4, MF3.8).

openpyxl is not a dependency of this service and this scope adds none, so a
table a client wants in a spreadsheet ships as CSV and as a PDF table. The
limitation is recorded in docs/engine/LIMITATIONS.md rather than worked
around.

The laws this module enforces:

  V1  one file per tabular section, with the section's own header row: a
      single file mixing three tables' columns is not a table
  V2  the cells are the registry's own strings, quoted by the csv writer, not
      escaped or shortened by this module. A claim that contains a comma or a
      newline survives it exactly - which is what keeps a client fact verbatim
      in every format (L14)
  V3  an explicit "\\n" line terminator, so the bytes - and therefore the
      artifact hash - are the same on every platform
"""
from __future__ import annotations

import csv
import hashlib
import os
from typing import Sequence

from app.engine.work_products.render_md import ArtifactRef, RenderedProduct, RenderedSection


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_table(head: Sequence[str], rows: Sequence[Sequence[str]], path: str) -> str:
    """Write one table and return its sha256. V3: newline="" on the file plus
    an explicit terminator is the only way csv writes the same bytes on
    Windows and on Linux."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(list(head))
        for row in rows:
            writer.writerow(list(row))
    return _sha256(path)


def tabular_sections(product: RenderedProduct) -> tuple[RenderedSection, ...]:
    """The sections that actually carry a table. A section whose renderer is
    tabular but which matched nothing has no rows and no file: an empty CSV
    would be a table claiming there is nothing, which is not the same as
    there being no table."""
    return tuple(s for s in product.sections if s.rows)


def render_csv(product: RenderedProduct, *, out_dir: str, registry_hash: str = "") -> tuple[ArtifactRef, ...]:
    """Every tabular section of a product as its own CSV artifact, in section
    order."""
    refs = []
    for section in tabular_sections(product):
        path = os.path.join(out_dir, f"{product.product_id}-{section.id}.csv")
        digest = write_table(section.head, section.rows, path)
        text = "\n".join([",".join(section.head)] + [",".join(r) for r in section.rows])
        refs.append(ArtifactRef(product_id=product.product_id, fmt="csv", path=path, sha256=digest,
                                registry_hash=registry_hash or product.registry_hash,
                                extracted_text=text))
    return tuple(refs)
