"""Typed figures: every number a client can see says whose it is.

The package sits outside the r30 freeze and imports nothing from `app.engine`.
`model` is the pure data model (Figure, FigureSet, display rules, the mapping
from the pipeline's claim dicts); `labels` is the closed list of words our own
renderers number. Import from the submodules; this file re-exports nothing so
that importing one module never loads another.
"""
