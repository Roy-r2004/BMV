"""Persistence for the universal engine: seven tables on app.database.Base
and the append-only RegistryStore. Importing this package registers the
tables, so init_db()'s create_all and _ensure_columns cover them."""
from app.engine.persistence import models  # noqa: F401  -- table registration on Base
from app.engine.persistence.models import ENGINE_TABLES  # noqa: F401
from app.engine.persistence.store import (  # noqa: F401
    RegistryStore,
    documents_dir,
    emit_engine,
    record_model_call,
)
