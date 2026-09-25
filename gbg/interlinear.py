"""``gbg ref``: a passage as an interlinear -- the view a reader checks first.

Four stacked lines per word -- the Greek as printed, its lemma, its
morphology, its gloss -- wrapped to the terminal. ``--tsv`` / ``--json`` give
the same tokens as rows (with ids, so anything read here can be cited), and
``--tree`` prints the syntax trees of the sentences the passage touches.

Blank glosses are shown blank. 830 SBLGNT words have no Berean gloss and
4,637 no Cherith English; inventing one here would put words in the text's
mouth that no source vouches for.
"""

from __future__ import annotations

import json
import shutil

from . import cli, db as dbmod, refs
from .resolve import resolve

COLS = ["id", "ref", "surface", "after", "lemma", "morph", "gloss", "english", "role"]


def tokens(con, text: str) -> tuple[list[dict], object]:
    res = resolve(con, text)
    if not res.found:
        return [], res
    rows = []
    # One ordered scan from the passage's first to last token, kept to the
    # resolved verses (a list like "Rom 3; 5" skips the verses between).
    q = ("SELECT " + ", ".join(COLS) + ", verse_id, sentence_id, ord FROM token "
         "WHERE ord BETWEEN (SELECT ord FROM token WHERE id = ?) "
         "AND (SELECT ord FROM token WHERE id = ?) ORDER BY ord")
    names = COLS + ["verse_id", "sentence_id", "ord"]
    wanted = set(res.verses)
    for r in con.execute(q, [res.first_token, res.last_token]).fetchall():
        row = dict(zip(names, r))
        if row["verse_id"] in wanted:
            rows.append(row)
    words = [s for s in refs.parse(text).spans if s.w1 is not None]
    if words:  # MACULA word ranges: keep only the named words
        keep = set()
        for s in words:
            for w in range(s.w1, s.w2 + 1):
                keep.add(f"{s.book} {s.c1}:{s.v1}!{w}")
        rows = [r for r in rows if r["ref"] in keep]
    return rows, res


def render_stacked(rows: list[dict], width: int) -> str:
    out, by_verse = [], {}
    for r in rows:
        by_verse.setdefault(r["verse_id"], []).append(r)
    for verse, toks in by_verse.items():
        first = toks[0]["ref"].split("!")[0]
        out.append(f"{first}  ({verse})")
        cells = []
        for t in toks:
            surface = t["surface"] + ("" if t["after"] == " " else t["after"])
            col = [surface, t["lemma"] or "", t["morph"] or "", t["gloss"] or ""]
            cells.append((col, max(len(c) for c in col) + 2))
        line: list = []
        used = 0
        for col, w in cells + [(None, 0)]:
            if col is None or (used + w > width and line):
                for i in range(4):
                    out.append("".join(c[i].ljust(cw) for c, cw in line).rstrip())
                out.append("")
                line, used = [], 0
            if col is not None:
                line.append((col, w))
                used += w
    return "\n".join(out).rstrip() + "\n"


def render_tree(con, rows: list[dict]) -> str:
    out = []
    sentences = []
    for r in rows:
        if r["sentence_id"] not in sentences:
            sentences.append(r["sentence_id"])
    for sid in sentences:
        out.append(f"sentence {sid}")
        nodes = con.execute("""
            SELECT 'wg' AS k, id, parent_wg, child_ord, depth,
                   concat_ws(' ', class, CASE WHEN role IS NOT NULL THEN 'role=' || role END,
                             CASE WHEN rule IS NOT NULL THEN 'rule=' || rule END) AS label
            FROM wg WHERE sentence_id = ?
            UNION ALL
            SELECT 'w', id, parent_wg, child_ord, depth,
                   surface || '  ' || lemma || '  ' || morph ||
                   CASE WHEN role IS NOT NULL THEN '  role=' || role ELSE '' END
                   || '  ' || coalesce(gloss, '')
            FROM token WHERE sentence_id = ?""", [sid, sid]).fetchall()
        kids: dict = {}
        for k, i, parent, co, depth, label in nodes:
            kids.setdefault(parent, []).append((co, k, i, label))

        def walk(parent, depth):
            for co, k, i, label in sorted(kids.get(parent, [])):
                out.append("  " * depth + label)
                if k == "wg":
                    walk(i, depth + 1)
        walk(None, 1)
        out.append("")
    return "\n".join(out)


def add_arguments(p) -> None:
    cli.add_db(p)
    p.add_argument("passage", help='e.g. "Phlm 2", "Rom 3:21-26", "PHM 1:1!3-5"')
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--tsv", dest="fmt", action="store_const", const="tsv")
    fmt.add_argument("--json", dest="fmt", action="store_const", const="json")
    fmt.add_argument("--tree", dest="fmt", action="store_const", const="tree",
                     help="syntax trees of the sentences the passage touches")
    p.add_argument("--width", type=int, default=0, help="wrap width (default: terminal)")


def run(args) -> int:
    con = dbmod.connect(cli.db_of(args))
    try:
        try:
            rows, res = tokens(con, args.passage)
        except refs.RefError as exc:
            raise cli.UsageError(str(exc)) from None
        if not res.found:
            for m in res.missing:
                print(f"not found: {m}")
            return cli.EXIT_VIOLATION
        if args.fmt == "tsv":
            print("\t".join(COLS))
            for r in rows:
                print("\t".join("" if r[c] is None else str(r[c]) for c in COLS))
        elif args.fmt == "json":
            print(json.dumps([{c: r[c] for c in COLS} for r in rows], ensure_ascii=False,
                             indent=1))
        elif args.fmt == "tree":
            print(render_tree(con, rows), end="")
        else:
            width = args.width or shutil.get_terminal_size((100, 20)).columns
            print(render_stacked(rows, width), end="")
    finally:
        con.close()
    return cli.EXIT_OK
