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

from gbg import parse_topics, sources, store  # noqa: E402

SOURCE = "macula-greek"
#: (MACULA xml:id book number, lowfat file)
BOOKS = [("57", "18-philemon"), ("63", "24-2john"), ("64", "25-3john")]
TSV = "SBLGNT/tsv/macula-greek-SBLGNT.tsv"
#: The fixture books as the topical indexes name them.
NAVES_CODES = {"PHM", "2JN", "3JN"}
OSIS_BOOKS = ("Phlm.", "2John.", "3John.")
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


def subset_openbible(zip_bytes: bytes) -> bytes:
    """Every row of each topic that touches a fixture book, re-zipped deterministically.

    Whole topics, so their Old Testament rows exercise the "not in this edition"
    counts. ZIP_STORED with a fixed timestamp: the bytes depend on the rows alone.
    """
    import zipfile
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        [name] = [n for n in z.namelist() if n.endswith(".txt")]
        lines = z.read(name).decode("utf-8").splitlines(keepends=True)
    topics = {ln.split("\t")[0] for ln in lines[1:] if ln.split("\t")[1].startswith(OSIS_BOOKS)}
    keep = [lines[0]] + [ln for ln in lines[1:] if ln.split("\t")[0] in topics]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        z.writestr(info, "".join(keep).encode("utf-8"))
    return buf.getvalue()


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
    # The topical indexes: the entries/topics that cite the fixture books.
    topical = {}
    for name, path, subdir, subset in (
            (store.NAVES, store.NAVES_PATH, "naves",
             lambda b: parse_topics.fixture_subset_naves(b.decode("utf-8-sig"),
                                                         NAVES_CODES).encode("utf-8")),
            (store.OPENBIBLE, store.OPENBIBLE_PATH, "openbible", subset_openbible)):
        tsrc = lock.source(name)
        problems = sources.verify_files(lock, name, root)
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        data = subset((lock.source_dir(name, root) / path).read_bytes())
        target = out / subdir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        raw_t = json.loads((root / "sources.lock.json").read_text(encoding="utf-8"))["sources"][name]
        topical[name] = {
            "repo": raw_t["repo"], "raw_url": raw_t["raw_url"], "commit": tsrc.commit,
            "license": tsrc.license, "attribution": tsrc.attribution, "local_dir": subdir,
            "files": [{"path": path, "sha256": sources.sha256_file(target),
                       "bytes": target.stat().st_size}],
            "components": raw_t["components"],
            "derived": {"tool": "tools/make_fixture.py", "books": sorted(NAVES_CODES),
                        "inputs": {path: tsrc.files[0].sha256}},
        }

    raw = json.loads((root / "sources.lock.json").read_text(encoding="utf-8"))["sources"][SOURCE]
    fixture = {
        "_comment": ["GENERATED by tools/make_fixture.py -- do not edit. A subset of the pinned",
                     "upstream with non-open fields removed; see 'derived'."],
        "sources": {**topical, SOURCE: {
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
    # the macula source first, as in the real lock
    fixture["sources"] = {SOURCE: fixture["sources"][SOURCE],
                          **{k: v for k, v in fixture["sources"].items() if k != SOURCE}}
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
    lines += ["", "`naves/` and `openbible/` are subsets of the topical indexes: the Nave's entries",
              "and the OpenBible topics that cite Philemon, 2 John or 3 John.", ""]
    for name in (store.NAVES, store.OPENBIBLE):
        t = lock.source(name)
        lines.append(f"- {t.attribution} ({t.license}), {name} @ {t.commit}")
    (out / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fixture written to {out.relative_to(root) if out.is_relative_to(root) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
