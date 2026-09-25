"""MACULA's flat word-level TSV -> raw word records, for the cross-check.

The build's rows come from the lowfat trees (see ``rows.py`` for why); this
file is the independent second copy the tree data is checked against.

Read with ``QUOTE_NONE``: glosses contain double quotes, and a CSV reader in
default mode silently merges rows until the next quote.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .rows import FIELDS, clean

#: Present upstream, deliberately unused: CC BY, but a Chinese gloss is
#: outside this build's scope.
UNUSED = frozenset({"mandarin"})


class TsvError(ValueError):
    pass


def read(path: Path, excluded: frozenset[str]) -> tuple[dict[str, dict], list[str]]:
    """Return ``(xml_id -> raw record, ignored upstream columns)``.

    A column neither used, unused-by-choice nor excluded-by-license is
    reported as ignored, so an upstream schema change surfaces in the
    manifest instead of vanishing.
    """
    for f in FIELDS:
        if f in excluded:  # a mapping bug would leak non-open data
            raise TsvError(f"field {f!r} is excluded by license but used")
    records: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        missing = [c for c in ("xml:id", *FIELDS) if c not in header]
        if missing:
            raise TsvError(f"{path}: missing columns {missing}")
        ignored = sorted(set(header) - {"xml:id", *FIELDS} - UNUSED - set(excluded))
        for lineno, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise TsvError(f"{path}:{lineno}: {len(row)} fields, header has {len(header)}")
            rec = dict(zip(header, row))
            xml_id = rec["xml:id"]
            if xml_id in records:
                raise TsvError(f"{path}:{lineno}: duplicate xml:id {xml_id}")
            records[xml_id] = clean(rec)
    return records, ignored
