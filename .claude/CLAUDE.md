# Working on greek-bible-graph

Sibling of `nathanwdavis/auto-zettel-skill`. That repo grows a citation-grounded
Zettelkasten of markdown notes; this one builds the Greek Bible itself as a
queryable corpus graph that those notes can cite by stable id. The design, and
which auto-zettel-skill techniques were borrowed versus replaced, is in
`docs/DESIGN.md` -- read it before changing the data model.

## Running things

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q          # offline: fixture build, no network
.venv/bin/python -m pytest -m network  # full NT from pinned upstream (~135 MB download, cached)
./smoke_test.sh                        # the acceptance checklist; exit 0 or it isn't done
```

Never judge the smoke test through a pipe; read `$?` from the script itself.
Never assert through a pipe under `pipefail` either: capture, then match.

## The invariant everything else rests on

**Never make a gate pass by weakening it**, and never hand-edit a generated
artifact to match one. `build-manifest.json`, `tests/fixtures/build-manifest.json`
and `docs/SCHEMA.md` are generated; when `--check` fails, find out *why* the
output changed and regenerate with the tool. Anomaly counts in the manifest are
pinned on purpose: a changed count is a finding to explain in the PR, not noise.

## Licensing is per field, and it is enforced

Open licenses only (CC BY / CC0 / public domain). MACULA licenses by component,
and its Louw-Nida columns (`domain`, `ln`, from UBS MARBLE) are "used with
permission", not open. They are excluded at parse time, stripped from the
fixtures by `tools/make_fixture.py`, and a test greps the fixtures for them.
Every output column declares its source component in `gbg/graphdef.py`; the
build refuses an unmapped or non-open one. Do not add a column without a
component, and do not add a component without a license in `sources.lock.json`.

## Environment facts

- `api.github.com` answers 403 from the cloud sandbox; `git ls-remote` and
  SHA-pinned `raw.githubusercontent.com` URLs work. `gh` is absent -- use the
  GitHub MCP tools.
- DuckDB is pinned exactly (`duckdb==1.5.4`): DuckPGQ builds lag PyPI.
- DuckPGQ cannot create a property graph on a read-only database, nor over
  views. `--pgq` therefore attaches the database read-only into an in-memory
  one and materialises foreign-key edge tables there (see `gbg/db.py`).
- Python UDFs in DuckDB need numpy; `gbg_key`/`gbg_nfc` are SQL macros stored
  in the database instead (`gbg/greek.py`).

## Conventions (carried over from auto-zettel-skill)

- Comments and docstrings carry the *why*.
- Lints print `FILE\tRULE\tREASON` and exit 1; usage errors exit 2.
- Every subcommand answers `--help`; the smoke test sweeps them.
- One definition per concept: the graph lives in `gbg/graphdef.py`, Greek
  normalisation in `gbg/greek.py`, book names in `gbg/books.py`.
- Develop on `claude/<slug>`; never push to `main`; never merge your own PR.
