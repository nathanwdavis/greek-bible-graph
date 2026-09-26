#!/usr/bin/env python3
"""Derive the checked-in test fixture from the pinned upstream cache.

The fixture is Philemon, 2 John and 3 John -- 798 tokens -- chosen because
together they exercise nearly every quirk the full build has to handle:
sentences spanning verses (Phlm 1:1-2) and a verse split across sentences
(Phlm 1:20), discontinuous tokens, upstream nodeIds, elision (κατ’),
multi-target referents, frames with ';', the implicit-participant sentinel,
three books, and a shared-wording golden (2 John and 3 John share lemma
trigrams).

It cannot be a verbatim copy of upstream. MACULA's Louw-Nida attributes
(``domain``/``ln``) come from UBS MARBLE "used with permission" -- not an open
license -- and committing the upstream files would redistribute them. So this
tool removes exactly the fields the lock marks as non-open, using the same
derivation the build uses (``Source.excluded_fields``), and records the input
and output hashes plus the transformation in ``fixture.lock.json``. The
fixture is a generated artifact: regenerate it with this tool, never by hand.

Usage:  python tools/make_fixture.py [--root .] [--out tests/fixtures]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbg import sources  # noqa: E402

SOURCE = "macula-greek"
#: (MACULA xml:id book number, lowfat file)
BOOKS = [("57", "18-philemon"), ("63", "24-2john"), ("64", "25-3john")]
TSV = "SBLGNT/tsv/macula-greek-SBLGNT.tsv"
PROXIMITY = "sources/Clear/synonyms/Proximity.tsv"


def strip_tsv(text: str, excluded: frozenset[str], prefixes: tuple[str, ...]) -> str:
    rows = list(csv.reader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))
    header, body = rows[0], rows[1:]
    keep = [i for i, name in enumerate(header) if name not in excluded]
    out = io.StringIO()
    w = csv.writer(out, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n",
                   escapechar=None, quotechar=None)
    w.writerow([header[i] for i in keep])
    for r in body:
        if r[0][1:3] in prefixes:
            w.writerow([r[i] for i in keep])
    return out.getvalue()


def subset_proximity(text: str, tsv_subset: str) -> str:
    """Proximity rows touching a Strong's number the fixture's words carry.

    Either side may match, so the subset keeps what the build must count
    rather than load: Hebrew/Aramaic partners and Greek numbers no fixture
    lemma carries.
    """
    rows = list(csv.reader(io.StringIO(tsv_subset), delimiter="\t", quoting=csv.QUOTE_NONE))
    col = rows[0].index("strong")
    strongs = {"G" + r[col] for r in rows[1:]}
    lines = text.splitlines(keepends=True)
    keep = [ln for ln in lines[1:] if set(ln.split("\t")[:2]) & strongs]
    return lines[0] + "".join(keep)


def strip_xml(text: str, excluded: frozenset[str]) -> str:
    # Attribute removal by pattern, not by re-serialising the tree: ElementTree
    # would rewrite namespaces, quoting and whitespace, and the fixture should
    # differ from upstream in the excluded fields and nothing else.
    names = "|".join(re.escape(n) for n in sorted(excluded))
    stripped = re.sub(rf'\s+(?:{names})="[^"]*"', "", text)
    left = re.findall(rf'\s(?:{names})="', stripped)
    if left:
        raise SystemExit(f"excluded attributes survived stripping: {left[:3]}")
    return stripped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    out = (args.out or root / "tests" / "fixtures").resolve()

    lock = sources.load_lock(root / "sources.lock.json")
    src = lock.source(SOURCE)
    problems = sources.verify_files(lock, SOURCE, root)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    base = lock.source_dir(SOURCE, root)
    excluded = src.excluded_fields()
    by_path = {f.path: f for f in src.files}

    data_dir = out / "macula"
    wanted = [TSV] + [f"SBLGNT/lowfat/{name}.xml" for _, name in BOOKS] + [PROXIMITY]
    written = []
    tsv_subset = ""
    for path in wanted:
        text = (base / path).read_text(encoding="utf-8")
        if path == TSV:
            new = tsv_subset = strip_tsv(text, excluded, tuple(n for n, _ in BOOKS))
        elif path == PROXIMITY:
            new = subset_proximity(text, tsv_subset)
        else:
            new = strip_xml(text, excluded)
        target = data_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8", newline="")
        written.append(path)

    fixture_files = []
    for path in written:
        p = data_dir / path
        fixture_files.append({"path": path, "sha256": sources.sha256_file(p),
                              "bytes": p.stat().st_size})
    raw = json.loads((root / "sources.lock.json").read_text(encoding="utf-8"))["sources"][SOURCE]
    fixture = {
        "_comment": ["GENERATED by tools/make_fixture.py -- do not edit. A subset of the pinned",
                     "upstream with non-open fields removed; see 'derived'."],
        "sources": {SOURCE: {
            "repo": raw["repo"], "raw_url": raw["raw_url"], "commit": src.commit,
            "license": src.license, "attribution": src.attribution,
            "local_dir": "macula",
            "files": fixture_files,
            "components": raw["components"],
            "derived": {
                "tool": "tools/make_fixture.py",
                "books": [b for b, _ in BOOKS],
                "removed_fields": sorted(excluded),
                "inputs": {p: by_path[p].sha256 for p in written},
            },
        }},
    }
    (out / "fixture.lock.json").write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# Fixture attribution", "",
             "The files under `macula/` are a subset of MACULA Greek (commit "
             f"`{src.commit}`), generated by `tools/make_fixture.py`: rows and files for",
             "Philemon, 2 John and 3 John only (and the Clear proximity rows touching",
             "their Strong's numbers), with the fields of non-open components",
             f"removed ({', '.join(sorted(excluded))}).", "",
             f"- {src.attribution} ({src.license})"]
    for c in src.components:
        state = "excluded" if c.name in {x.name for x in src.components if set(x.fields) & excluded} \
            else c.license
        lines.append(f"- `{c.name}` ({state}): {c.attribution}")
    (out / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fixture written to {out.relative_to(root) if out.is_relative_to(root) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
