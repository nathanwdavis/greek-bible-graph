"""``gbg resolve``: a reference -> the ids it denotes in the built edition.

This is the bridge to auto-zettel-skill. There, a literature note's
``locator`` is free text that the gates only check is non-empty. Here a
reference either resolves -- to verse ids, token bounds, a canonical form and
an SBL display form, stamped with the build and source commit -- or it does
not, and the exit code says which:

    0  resolved
    1  well-formed, but not in this edition (Acts 8:37 is not in the SBLGNT;
       Genesis is not in a New Testament)
    2  malformed or ambiguous ("Jud 3", "Rom 3:21ff")

A zettel lint can shell out to ``gbg resolve --json`` and fail a note whose
citation does not resolve -- see docs/DESIGN.md, "Citing the corpus".
Works in reverse too: an id resolves to its reference.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

from . import books, cli, db as dbmod, ids, refs


@dataclass
class Resolution:
    input: str
    kind: str                     # "passage" | "lemma"
    found: bool
    canonical: str = ""
    sbl: str = ""
    partial: bool = False
    verses: list[str] = field(default_factory=list)
    first_token: str | None = None
    last_token: str | None = None
    n_tokens: int = 0
    missing: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def as_dict(self, build_id: str, commits: dict) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        d.update(edition=ids.EDITION, build_id=build_id, source_commits=commits)
        return d


def _span_verses(con, span: refs.Span) -> tuple[list[tuple], str | None]:
    """Verses (id, ord) covered by a span, or a reason it is absent."""
    b = f"{ids.EDITION}:{span.book}"
    if not con.execute("SELECT 1 FROM book WHERE id = ?", [b]).fetchone():
        return [], f"{books.BY_CODE[span.book].name} is not in this edition"
    if span.whole_book:
        return con.execute("SELECT id, ord FROM verse WHERE book_id = ? ORDER BY ord",
                           [b]).fetchall(), None
    if span.v1 is None:
        rows = con.execute("SELECT id, ord FROM verse WHERE book_id = ? AND chapter BETWEEN ? "
                           "AND ? ORDER BY ord", [b, span.c1, span.c2]).fetchall()
        have = {c for (c,) in con.execute("SELECT DISTINCT chapter FROM verse WHERE book_id = ? "
                                          "AND chapter BETWEEN ? AND ?",
                                          [b, span.c1, span.c2]).fetchall()}
        gone = [c for c in range(span.c1, span.c2 + 1) if c not in have]
        return (rows, None) if not gone else ([], f"{span.canonical()}: chapter "
                                                  f"{gone[0]} is not in this edition")
    ends = {}
    for tag, c, v in (("start", span.c1, span.v1), ("end", span.c2, span.v2)):
        row = con.execute("SELECT ord FROM verse WHERE id = ?",
                          [ids.verse_id(span.book, c, v)]).fetchone()
        if row is None:
            return [], f"{span.book} {c}:{v} is not in this edition"
        ends[tag] = row[0]
    return con.execute("SELECT id, ord FROM verse WHERE book_id = ? AND ord BETWEEN ? AND ? "
                       "ORDER BY ord", [b, ends["start"], ends["end"]]).fetchall(), None


def resolve(con, text: str) -> Resolution:
    text = text.strip()
    if ids.kind_of(text) == "lemma":
        row = con.execute("SELECT id, lemma, key, n_tokens, strongs FROM lemma WHERE id = ?",
                          [text]).fetchone()
        if not row:
            return Resolution(text, "lemma", False, canonical=text,
                              missing=[f"{text} does not occur in this edition"])
        return Resolution(text, "lemma", True, canonical=row[0], n_tokens=row[3],
                          extra={"lemma": row[1], "key": row[2], "strongs": row[4]})
    passage = refs.parse(text)  # RefError -> exit 2
    res = Resolution(text, "passage", True, canonical=passage.canonical(), sbl=passage.sbl(),
                     partial=passage.partial)
    bounds: list[tuple[int, int, str, str]] = []
    for span in passage.spans:
        if span.w1 is not None:
            first = ids.token_id(f"n{books.BY_CODE[span.book].num:02d}{span.c1:03d}"
                                 f"{span.v1:03d}{span.w1:03d}")
            last = ids.token_id(f"n{books.BY_CODE[span.book].num:02d}{span.c1:03d}"
                                f"{span.v1:03d}{span.w2:03d}")
            got = con.execute("SELECT min(ord), max(ord), count(*) FROM token WHERE id IN (?, ?)",
                              [first, last]).fetchone()
            if got[2] != (1 if first == last else 2):
                res.found = False
                res.missing.append(f"{span.canonical()} is not in this edition")
                continue
            res.verses.append(ids.verse_id(span.book, span.c1, span.v1))
            bounds.append((got[0], got[1], first, last))
            continue
        verses, why = _span_verses(con, span)
        if why:
            res.found = False
            res.missing.append(why)
            continue
        res.verses += [v for v, _ in verses]
        f, l, n = con.execute("SELECT arg_min(id, ord), arg_max(id, ord), count(*) FROM token "
                              "WHERE verse_id IN (SELECT unnest(?))",
                              [[v for v, _ in verses]]).fetchone()
        o1, o2 = con.execute("SELECT (SELECT ord FROM token WHERE id = ?), "
                             "(SELECT ord FROM token WHERE id = ?)", [f, l]).fetchone()
        bounds.append((o1, o2, f, l))
    if bounds:
        res.first_token = min(bounds)[2]
        res.last_token = max(bounds, key=lambda b: b[1])[3]
        res.n_tokens = sum(con.execute("SELECT count(*) FROM token WHERE ord BETWEEN ? AND ?",
                                       [a, b]).fetchone()[0] for a, b, *_ in bounds)
    if res.found and len(passage.spans) == 1 and ids.kind_of(text) == "token":
        tok = con.execute("SELECT ref, surface, lemma, verse_id FROM token WHERE id = ?",
                          [text]).fetchone()
        res.extra = {"ref": tok[0], "surface": tok[1], "lemma": tok[2], "verse_id": tok[3]}
    return res


def add_arguments(p) -> None:
    cli.add_db(p)
    p.add_argument("reference", help='e.g. "Rom 3:21-26", "Phlm 10", sblgnt:n57001010007, lemma:θεός')
    p.add_argument("--json", action="store_true", help="machine-readable result")


def run(args) -> int:
    con = dbmod.connect(cli.db_of(args))
    try:
        try:
            res = resolve(con, args.reference)
        except refs.RefError as exc:
            raise cli.UsageError(str(exc)) from None
        build_id, commits = dbmod._meta(con)
    finally:
        con.close()
    if args.json:
        print(json.dumps(res.as_dict(build_id, commits), ensure_ascii=False, indent=1))
    elif res.found and res.kind == "lemma":
        print(f"{res.canonical}\t{res.n_tokens} occurrence(s)")
    elif res.found:
        head = res.sbl or res.canonical
        print(f"{head}\t{res.canonical}" + ("\t(partial verse: widened to the whole verse)"
                                            if res.partial else ""))
        for v in res.verses:
            print(v)
    for m in res.missing:
        print(f"not found: {m}", file=sys.stderr)
    return cli.EXIT_OK if res.found else cli.EXIT_VIOLATION
