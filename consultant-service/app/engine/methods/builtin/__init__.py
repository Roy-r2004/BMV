"""Registration by import.

Importing this package imports every module in it, and each module's
@register decorator puts its method into METHODS. The list is discovered
from the directory, not written here: a new method is one new file, and
neither this package nor the Partner loop changes to admit it (design 7.1;
the test pins that a method registered from a test module is selected by
shape without any orchestrator edit).

Modules are imported in name order so the registry's iteration order - and
therefore the id tie-break in select_methods - is the same on every run.
"""
from __future__ import annotations

import importlib
import os
import pkgutil

__all__: list[str] = []

# The package directory comes from __file__, not the implicit package
# attribute __path__: every name a module uses must be one it visibly binds
# (the undefined-name sweep enforces that at source level, and it cannot see
# the attributes the import system binds on packages).
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

for _info in sorted(pkgutil.iter_modules([_PACKAGE_DIR]), key=lambda i: i.name):
    if _info.name.startswith("_"):
        continue
    importlib.import_module(f"{__name__}.{_info.name}")
    __all__.append(_info.name)
