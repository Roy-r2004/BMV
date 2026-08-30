"""The typed adapter to the r30 technology pipeline.

`app/pipeline`, `app/prompts` and `tools` are imported, never modified: the
frozen manifest (design 13.5, `tests/engine/test_engine_r30_frozen.py`) pins
every byte of them. Everything this package does is composed from registry
entities on the way in and read back through r30's own public functions on
the way out; nothing here writes to the Request row after the pipeline
returns (design 13.4).
"""
