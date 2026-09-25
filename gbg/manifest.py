"""The build manifest: what the build produced, as a deterministic fingerprint.

auto-zettel-skill's ``build_manifest.py`` is the model: sort everything, never
read a clock, serialise with sorted keys, and let ``--check`` compare bytes.
Its lesson is in this repo's CLAUDE.md -- a generated artifact is whatever the
tool emits, and a hand-written "fix" is a guess the next regeneration throws
away.

One adaptation. Hashing the Parquet files would flake: their bytes depend on
the DuckDB version, row-group sizing and thread count, none of which change
what the data *says*. So each table is hashed LOGICALLY -- rows in primary-key
order, each row serialised as a canonical JSON array -- and the ``.duckdb``
file is a query store that is never hashed at all.

Anomaly counts are in the manifest on purpose. They are upstream facts the
build tolerates (non-NFC input, self-references, empty frame roles); pinning
them means a new upstream commit that changes one fails ``--check`` and shows
up as a reviewed diff, instead of being silently absorbed.
"""

from __future__ import annotations

import difflib
import hashlib
import json

from . import graphdef


def _canon(value):
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return value


def table_fingerprint(con, table: graphdef.Table) -> dict:
    cols = [c.name for c in table.columns]
    schema = "\n".join(f"{c.name} {c.type}" for c in table.columns)
    order = ", ".join(f'"{k}"' for k in table.pk)
    sel = ", ".join(f'"{c}"' for c in cols)
    h = hashlib.sha256()
    rows = 0
    cur = con.execute(f'SELECT {sel} FROM "{table.name}" ORDER BY {order}')
    while True:
        batch = cur.fetchmany(20000)
        if not batch:
            break
        for row in batch:
            h.update(json.dumps([_canon(v) for v in row], ensure_ascii=False,
                                separators=(",", ":")).encode("utf-8"))
            h.update(b"\n")
        rows += len(batch)
    return {"rows": rows,
            "schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest(),
            "content_sha256": h.hexdigest()}


def serialize(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def diff(committed: str, fresh: str, label: str) -> str:
    return "".join(difflib.unified_diff(committed.splitlines(True), fresh.splitlines(True),
                                        f"{label} (committed)", f"{label} (rebuilt)"))
