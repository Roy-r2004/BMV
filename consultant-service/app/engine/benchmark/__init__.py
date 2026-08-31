"""app/engine/benchmark/ - the benchmark harness (design 17).

Nothing under `app/engine` outside this package may import from here, and
nothing here is reachable from the engagement path: the harness reads the case
files, the engine never does. That separation is what makes the benchmark
evidence rather than configuration - a case file cannot teach the engine
anything, because the engine cannot see one.

The package is deliberately thin on public names: `cases` loads the data
strictly, `oracle` answers model calls from the call's own context,
`harness` runs one case to a `Bundle`, and `assertions` states what a bundle
and a set of bundles must satisfy. `__main__` is the costed real-model CLI.
"""
