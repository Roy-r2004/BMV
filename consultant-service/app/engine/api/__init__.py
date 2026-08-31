"""The engagement API (design 16.2, 16.3).

Three modules:

- schemas.py   the pydantic bodies the client sends and the serialisers that
               turn registry rows into JSON. Nothing here summarises: every
               response is built from a query at the moment it is read
- router.py    /api/engagements - intake, turns, answers, charter, resolution,
               reads, exports, release, review
- startup.py   engine_startup(), the stranded-engagement sweep main.py calls
               AFTER init_db() (MF3.2)

Importing this package imports router.py, which imports
app.engine.persistence - so the engine's tables are registered on Base before
main.py's init_db() runs create_all over it. That import order is the whole
reason main.py imports the router at module level and calls the sweep inside
on_startup rather than the other way round.
"""
from app.engine.api import router  # noqa: F401  -- table registration + routes
from app.engine.api.startup import engine_startup  # noqa: F401

__all__ = ["engine_startup", "router"]
