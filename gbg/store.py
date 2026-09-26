"""``gbg build``: pinned sources -> DuckDB + Parquet + a manifest.

The pipeline, and the auto-zettel-skill rule each step carries over:

1. **Verify inputs** against the lock (sha256 of every file) -- raw/ is
   immutable and verification is recorded.
2. **License gate**: every column ``graphdef`` declares names a component; the
   component must exist in the lock with an open license. The build refuses
   otherwise -- ``capture.py``'s rule, refuse at write time what the gate
   refuses at check time.
3. **Parse** the lowfat trees (tokens, sentences, word groups, dominance,
   coreference, frames) and the TSV (a second copy of every word).
4. **Source agreement**, inside the build: the two must cover exactly the
   same tokens, each token in exactly one sentence -- fatal otherwise.
   Field-level disagreements are counted as anomalies and pinned; rows are
   built from the tree copy, which wins every disagreement that can be
   adjudicated (``rows.py``).
5. **Stage and load**: rows are written to staging TSVs and bulk-loaded with
   ``read_csv`` (binding Python lists as query parameters was ~100x slower).
   Derived tables (verse, sentence, lemma, spans, ordinals) are computed in
   SQL from the loaded rows, so there is one definition of each.
6. **Export** Parquet in primary-key order, with the attribution in its
   metadata, and **fingerprint** every table into the manifest.
7. **Swap in** the finished build directory only at the end: a failed build
   never leaves a half-written database where a good one was.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

import duckdb

from . import (books, cli, english, graphdef, greek, ids, licenses, manifest, parse_lowfat,
               parse_tsv, rows)
from .sources import Lock, load_lock, verify_files

SOURCE = "macula-greek"
TSV_PATH = "SBLGNT/tsv/macula-greek-SBLGNT.tsv"
LOWFAT_PREFIX = "SBLGNT/lowfat/"
PROXIMITY_PATH = "sources/Clear/synonyms/Proximity.tsv"
PROXIMITY_HEADER = ["StrongNumberX1", "StrongNumberX2", "Distance"]
#: The only things a build directory may contain; anything else means --out
#: points somewhere it should not, and the build refuses to replace it.
BUILD_ENTRIES = {"gbg.duckdb", "gbg.duckdb.wal", "parquet", "manifest.json", "staging"}


class BuildError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems[:3]))


# --- license gate --------------------------------------------------------------

def license_problems(lock: Lock) -> list[cli.Violation]:
    src = lock.source(SOURCE)
    out = []
    if not licenses.is_open(src.license):
        out.append(cli.Violation("sources.lock.json", "license-not-open",
                                 f"{SOURCE} is {src.license}"))
    comps = {c.name: c for c in src.components}
    for t in graphdef.TABLES:
        for c in t.columns:
            if c.component == graphdef.GBG:
                continue
            comp = comps.get(c.component)
            if comp is None:
                out.append(cli.Violation(f"{t.name}.{c.name}", "license-unmapped",
                                         f"component {c.component!r} is not in the lock"))
            elif not licenses.is_open(comp.license):
                out.append(cli.Violation(f"{t.name}.{c.name}", "license-not-open",
                                         f"component {c.component!r} is {comp.license}"))
    return out


# --- source agreement -----------------------------------------------------------

def agreement(tsv: dict[str, dict], tree: dict[str, dict]) -> tuple[list[str], Counter]:
    """Cross-check the TSV's copy of every word against the tree's.

    Coverage must match exactly (fatal otherwise). Field disagreements are
    counted per field and pinned in the manifest -- see ``rows.py`` for what
    they turn out to be in the pinned SBLGNT.
    """
    fatal: list[str] = []
    counts: Counter = Counter()
    if set(tsv) != set(tree):
        only_tsv = sorted(set(tsv) - set(tree))[:10]
        only_tree = sorted(set(tree) - set(tsv))[:10]
        fatal.append(f"TSV and lowfat cover different tokens: only in TSV {only_tsv}, "
                     f"only in lowfat {only_tree}")
        return fatal, counts
    for xml_id, t in tree.items():
        other = tsv[xml_id]
        for f in rows.FIELDS:
            a, b = t[f], other[f]
            if f in rows.NFC_FIELDS:
                a, b = (greek.nfc(a) if a else a), (greek.nfc(b) if b else b)
            if a != b:
                counts[f"tsv_lowfat_mismatch.{f}"] += 1
    return fatal, counts


def referent_cycles(edges: list[dict]) -> int:
    """Distinct cycles when each word's FIRST referent is followed.

    Counted, not rejected: upstream coreference legitimately contains mutual
    references. But a recursive query over refers_to must guard against them,
    and the schema doc says so -- this count is the evidence.
    """
    nxt = {e["src"]: e["dst"] for e in edges if e["ord"] == 1 and e["dst"]}
    state: dict[str, int] = {}  # 1 = on current path, 2 = done
    cycles = 0
    for start in nxt:
        path = []
        node = start
        while node in nxt and node not in state:
            state[node] = 1
            path.append(node)
            node = nxt[node]
        if node in state and state[node] == 1:
            cycles += 1
        for n in path:
            state[n] = 2
    return cycles


# --- staging ------------------------------------------------------------------

NULL = "\\N"


def _cell(v) -> str:
    if v is None:
        return NULL
    if v is True:
        return "true"
    if v is False:
        return "false"
    return str(v)


def stage(con, staging: Path, name: str, rows, columns: dict[str, str]) -> None:
    """Write rows to a staging TSV and bulk-load them as a temp table."""
    path = staging / f"{name}.tsv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        for r in rows:
            w.writerow([_cell(r[c] if isinstance(r, dict) else r[i])
                        for i, c in enumerate(columns)])
    cols = ", ".join(f"'{c}': '{t}'" for c, t in columns.items())
    con.execute(f"""CREATE TEMP TABLE "{name}" AS SELECT * FROM read_csv('{path}',
        delim='\t', header=false, quote='"', escape='"', nullstr='{NULL}',
        columns={{{cols}}}, auto_detect=false, parallel=false)""")


def insert(con, table: str, exprs: dict[str, str], from_sql: str) -> None:
    """INSERT INTO table with every column given explicitly, in graphdef order."""
    t = graphdef.BY_NAME[table]
    names = [c.name for c in t.columns]
    if set(exprs) != set(names):
        raise AssertionError(f"{table}: expressions {sorted(set(exprs) ^ set(names))} "
                             "do not match graphdef")
    cols = ", ".join(f'"{n}"' for n in names)
    sel = ",\n  ".join(f'{exprs[n]} AS "{n}"' for n in names)
    order = ", ".join(f'"{k}"' for k in t.pk)
    con.execute(f'INSERT INTO "{table}" ({cols})\nSELECT * FROM (SELECT\n  {sel}\n{from_sql}) '
                f"ORDER BY {order}")


TEXT_AGG = ("rtrim(string_agg(surface || CASE WHEN after = ' ' THEN ' ' ELSE after || ' ' END, "
            "'' ORDER BY ord))")


def load(con, staging: Path, rw: rows.Rows, lf: parse_lowfat.LowfatResult,
         proximity: Path) -> Counter:
    """Load every table; returns the anomalies only the loaded data can count."""
    V, I, B = "VARCHAR", "INTEGER", "BOOLEAN"
    stage(con, staging, "_tok", rw.tokens, {
        "id": V, "xml_id": V, "ref": V, "book": V, "chapter": I, "verse": I, "word": I,
        "surface": V, "after": V, "normalized": V, "lemma": V, "strong": V, "morph": V,
        "pos": V, "type": V, "person": V, "number": V, "gender": V, "gcase": V, "tense": V,
        "voice": V, "mood": V, "degree": V, "role": V, "gloss": V, "english": V})
    tree_rows = [{"xml_id": x, **t} for x, t in lf.token_tree.items()]
    stage(con, staging, "_tree", tree_rows, {
        "xml_id": V, "sentence_id": V, "parent_wg": V, "depth": I, "child_ord": I,
        "tree_ord": I, "discontinuous": B, "rule": V, "junction": V})
    stage(con, staging, "_sent", lf.sentences, {"id": V, "book": V, "root_wg": V})
    stage(con, staging, "_wg", lf.wgs, {
        "id": V, "sentence_id": V, "parent_wg": V, "depth": I, "child_ord": I, "tree_ord": I,
        "class": V, "rule": V, "role": V, "type": V, "articular": V, "junction": V,
        "predication": V, "clause_type": V, "upstream_node_id": V})
    stage(con, staging, "_dom", lf.dominance, {"wg_id": V, "token_id": V, "dist": I})
    edge_cols = {"src": V, "dst": V, "implicit": B, "ord": I, "tier": V,
                 "confidence": "DOUBLE", "source": V}
    stage(con, staging, "_refers_to", rw.refers_to, edge_cols)
    stage(con, staging, "_has_subject", rw.has_subject, edge_cols)
    stage(con, staging, "_frame_arg", rw.frame_arg, {**edge_cols, "arg_role": V})
    # Gloss terms once per distinct gloss (about 9k in the NT), joined back to
    # tokens -- gbg.english is the one definition, so it runs in Python.
    glosses = sorted({t["english"] for t in rw.tokens if t["english"] is not None})
    eng_rows = []
    for g in glosses:
        terms, negated = english.gloss_terms(g)
        eng_rows.append({"english": g, "terms": "|".join(terms), "negated": negated})
    stage(con, staging, "_eng", eng_rows, {"english": V, "terms": V, "negated": B})
    present = sorted({t["book"] for t in rw.tokens}, key=lambda c: books.BY_CODE[c].num)
    stage(con, staging, "_book", [{"code": c, "num": books.BY_CODE[c].num,
                                   "name": books.BY_CODE[c].name, "sbl": books.BY_CODE[c].sbl}
                                  for c in present],
          {"code": V, "num": I, "name": V, "sbl": V})

    same = lambda cols: {c: f't."{c}"' for c in cols}  # noqa: E731
    insert(con, "token", {
        **same(["id", "xml_id", "ref", "chapter", "verse", "word", "surface", "after",
                "normalized", "lemma", "strong", "morph", "pos", "type", "person", "number",
                "gender", "gcase", "tense", "voice", "mood", "degree", "role", "gloss",
                "english"]),
        "book_id": f"'{ids.EDITION}:' || t.book",
        "verse_id": f"'{ids.EDITION}:' || t.book || '.' || t.chapter || '.' || t.verse",
        "sentence_id": "tr.sentence_id", "parent_wg": "tr.parent_wg",
        "lemma_id": "'lemma:' || t.lemma",
        "next_id": "lead(t.id) OVER (PARTITION BY t.book ORDER BY t.id)",
        "ord": "row_number() OVER (ORDER BY t.id)",
        "depth": "tr.depth", "child_ord": "tr.child_ord", "tree_ord": "tr.tree_ord",
        "surface_key": "gbg_key(t.surface)", "lemma_key": "gbg_key(t.lemma)",
        "rule": "tr.rule", "junction": "tr.junction", "discontinuous": "tr.discontinuous",
        "english_terms": "CASE WHEN t.english IS NULL THEN NULL "
                         "WHEN coalesce(e.terms, '') = '' THEN []::VARCHAR[] "
                         "ELSE string_split(e.terms, '|') END",
        "english_negated": "CASE WHEN t.english IS NULL THEN NULL ELSE e.negated END",
    }, """FROM _tok t JOIN _tree tr ON tr.xml_id = t.xml_id
         LEFT JOIN _eng e ON e.english = t.english""")

    insert(con, "lemma", {
        "id": "lemma_id", "lemma": "lemma", "key": "gbg_key(lemma)", "n_tokens": "count(*)",
        "strongs": "list_sort(list_distinct(list(strong)))",
    }, "FROM token GROUP BY lemma_id, lemma")

    insert(con, "verse", {
        "id": "verse_id", "book_id": "book_id", "chapter": "chapter", "verse": "verse",
        "ord": "row_number() OVER (ORDER BY min(ord))",
        "first_token": "arg_min(id, ord)", "last_token": "arg_max(id, ord)",
        "n_tokens": "count(*)", "text": TEXT_AGG,
    }, "FROM token GROUP BY verse_id, book_id, chapter, verse")

    insert(con, "sentence", {
        "id": "s.id", "book_id": f"'{ids.EDITION}:' || s.book",
        "ord": "row_number() OVER (ORDER BY a.first_ord)", "root_wg": "s.root_wg",
        "first_token": "a.first_token", "last_token": "a.last_token",
        "n_tokens": "a.n", "text": "a.text",
    }, f"""FROM _sent s JOIN (SELECT sentence_id, min(ord) AS first_ord,
             arg_min(id, ord) AS first_token, arg_max(id, ord) AS last_token,
             count(*) AS n, {TEXT_AGG} AS text
           FROM token GROUP BY sentence_id) a ON a.sentence_id = s.id""")

    insert(con, "dominance", {"wg_id": "wg_id", "token_id": "token_id", "dist": "dist"},
           "FROM _dom")

    insert(con, "wg", {
        **{c: f'w."{c}"' for c in ["id", "sentence_id", "parent_wg", "depth", "child_ord",
                                   "tree_ord", "class", "rule", "role", "type", "articular",
                                   "junction", "predication", "clause_type",
                                   "upstream_node_id"]},
        "first_token": "a.first_token", "last_token": "a.last_token", "n_tokens": "a.n",
        "contiguous": "(a.max_ord - a.min_ord + 1 = a.n)",
    }, """FROM _wg w JOIN (SELECT d.wg_id, arg_min(t.id, t.ord) AS first_token,
             arg_max(t.id, t.ord) AS last_token, count(*) AS n,
             min(t.ord) AS min_ord, max(t.ord) AS max_ord
           FROM _dom d JOIN token t ON t.id = d.token_id GROUP BY d.wg_id) a
         ON a.wg_id = w.id""")

    insert(con, "book", {
        "id": f"'{ids.EDITION}:' || b.code", "code": "b.code", "num": "b.num",
        "name": "b.name", "sbl": "b.sbl", "ord": "row_number() OVER (ORDER BY b.num)",
        "n_chapters": "a.n_chapters", "n_verses": "a.n_verses", "n_tokens": "a.n_tokens",
    }, f"""FROM _book b JOIN (SELECT book_id, count(DISTINCT chapter) AS n_chapters,
             count(DISTINCT verse_id) AS n_verses, count(*) AS n_tokens
           FROM token GROUP BY book_id) a ON a.book_id = '{ids.EDITION}:' || b.code""")

    for name in ("refers_to", "has_subject", "frame_arg"):
        cols = [c.name for c in graphdef.BY_NAME[name].columns]
        insert(con, name, {c: c for c in cols}, f'FROM "_{name}"')

    return load_proximity(con, proximity)


def load_proximity(con, path: Path) -> Counter:
    """Clear's Strong's-keyed proximity -> lemma_proximity, via lemma.strongs.

    Upstream pairs are Strong's numbers across Greek, Hebrew and Aramaic, and
    a number can belong to several lemmas (G1492: οἶδα and ὁράω). Only
    Greek-Greek rows whose numbers some lemma carries can become edges; every
    other row is counted, never silently dropped, and never "repaired" (a
    suffixed G4894a is not guessed to be 4894).
    """
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
    if header != PROXIMITY_HEADER:
        raise BuildError([f"{path}: header {header}, expected {PROXIMITY_HEADER}"])
    con.execute(f"""CREATE TEMP TABLE _prox AS SELECT StrongNumberX1 AS a,
        StrongNumberX2 AS b, Distance AS d FROM read_csv('{path}', delim='\t', header=true,
        quote='', columns={{'StrongNumberX1': 'VARCHAR', 'StrongNumberX2': 'VARCHAR',
        'Distance': 'DOUBLE'}}, auto_detect=false, parallel=false)""")
    con.execute("CREATE TEMP TABLE _lemma_strong AS "
                "SELECT id AS lemma_id, 'G' || unnest(strongs) AS strong FROM lemma")
    insert(con, "lemma_proximity", {
        "src": "s.lemma_id", "dst": "d.lemma_id", "src_strong": "p.a", "dst_strong": "p.b",
        "distance": "p.d", "tier": "'data'", "confidence": "NULL",
        "source": f"'{SOURCE}'",
    }, """FROM _prox p JOIN _lemma_strong s ON s.strong = p.a
         JOIN _lemma_strong d ON d.strong = p.b""")
    counts = con.execute("""SELECT
        count(*) FILTER (WHERE a NOT LIKE 'G%' OR b NOT LIKE 'G%'),
        count(*) FILTER (WHERE a LIKE 'G%' AND b LIKE 'G%'
            AND (a NOT IN (SELECT strong FROM _lemma_strong)
                 OR b NOT IN (SELECT strong FROM _lemma_strong))),
        count(*) FILTER (WHERE a IN (SELECT strong FROM _lemma_strong)
            AND b IN (SELECT strong FROM _lemma_strong))
        FROM _prox""").fetchone()
    edges, selfs = con.execute("SELECT count(*), count(*) FILTER (WHERE src = dst) "
                               "FROM lemma_proximity").fetchone()
    return Counter({
        "lemma_proximity.rows_not_greek": counts[0],
        "lemma_proximity.rows_greek_unmapped": counts[1],
        # one upstream row becomes several edges when a number has several lemmas
        "lemma_proximity.edges_beyond_rows": edges - counts[2],
        "lemma_proximity.self_pairs": selfs,
    })


# --- the build ------------------------------------------------------------------

def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def build(lock_path: Path, root: Path, out: Path, *, log=print) -> dict:
    """Build into ``out``. Returns the manifest. Raises BuildError on refusal."""
    lock = load_lock(lock_path)
    src = lock.source(SOURCE)
    problems = verify_files(lock, SOURCE, root)
    if problems:
        raise BuildError(problems)
    lic = license_problems(lock)
    if lic:
        raise BuildError([v.render() for v in lic])

    base = lock.source_dir(SOURCE, root)
    excluded = src.excluded_fields()
    log(f"parsing {SOURCE} @ {src.commit[:12]}")
    tsv, ignored = parse_tsv.read(base / TSV_PATH, excluded)
    lowfat_files = [base / f.path for f in src.files if f.path.startswith(LOWFAT_PREFIX)]
    lf = parse_lowfat.parse(lowfat_files)
    fatal, mismatches = agreement(tsv, lf.token_attrs)
    if fatal:
        raise BuildError(fatal)
    rw = rows.build(lf.token_attrs)

    anomalies = Counter(rw.anomalies) + Counter(lf.anomalies) + mismatches
    anomalies["refers_to.first_target_cycles"] = referent_cycles(rw.refers_to)

    if out.exists():
        stray = {p.name for p in out.iterdir()} - BUILD_ENTRIES
        if stray:
            raise BuildError([f"{out} contains {sorted(stray)}; refusing to replace a "
                              "directory that is not a gbg build"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        staging = tmp / "staging"
        staging.mkdir()
        con = duckdb.connect(str(tmp / "gbg.duckdb"))
        con.execute(greek.SQL_KEY_MACRO)
        con.execute(greek.SQL_NFC_MACRO)
        for t in graphdef.TABLES:
            con.execute(graphdef.ddl(t))
        log("loading")
        # update(), not +=: a Counter sum drops zero counts, and a pinned zero is a finding
        anomalies.update(load(con, staging, rw, lf, base / PROXIMITY_PATH))
        con.execute(graphdef.edge_view_sql())

        log("fingerprinting")
        man = {
            "generated_by": "gbg build",
            "edition": ids.EDITION,
            "sources": {SOURCE: {"commit": src.commit,
                                 "files": {f.path: f.sha256 for f in src.files}}},
            "excluded_fields": sorted(excluded),
            "ignored_fields": ignored,
            "tables": {t.name: manifest.table_fingerprint(con, t) for t in graphdef.TABLES},
            "anomalies": dict(sorted(anomalies.items())),
        }
        text = manifest.serialize(man)
        comps = {c.name: {"license": c.license, "fields": list(c.fields)}
                 for c in src.components}
        con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("build_id", manifest.build_id(text)),
            ("edition", ids.EDITION),
            ("manifest", text),
            ("components", json.dumps(comps, sort_keys=True)),
            ("attribution", src.attribution),
            ("source_commits", json.dumps({SOURCE: src.commit})),
        ])

        log("exporting parquet")
        pq = tmp / "parquet"
        pq.mkdir()
        note = _sql_str(f"{src.attribution} ({src.license}); see NOTICE.md. "
                        f"Excluded: {', '.join(sorted(excluded))}.")
        for t in graphdef.TABLES:
            order = ", ".join(f'"{k}"' for k in t.pk)
            con.execute(f"COPY (SELECT * FROM \"{t.name}\" ORDER BY {order}) TO "
                        f"'{pq / (t.name + '.parquet')}' (FORMAT parquet, "
                        f"KV_METADATA {{attribution: {note}}})")
        con.execute("CHECKPOINT")
        con.close()
        shutil.rmtree(staging)
        (tmp / "manifest.json").write_text(text, encoding="utf-8")

        if out.exists():
            shutil.rmtree(out)
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return man


# --- CLI ----------------------------------------------------------------------

def add_arguments(p) -> None:
    cli.add_root(p)
    p.add_argument("--lock", type=Path, default=None,
                   help="lock file (default: <root>/sources.lock.json)")
    p.add_argument("--out", type=Path, default=None, help="build directory (default: <root>/build)")
    p.add_argument("--manifest", type=Path, default=None,
                   help="committed manifest (default: build-manifest.json beside the lock)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true",
                      help="rebuild in a temp dir and compare with the committed manifest "
                           "(exit 2 on any difference)")
    mode.add_argument("--record", action="store_true",
                      help="build, then write the manifest to the committed location")


def run(args) -> int:
    root = cli.root_of(args)
    lock_path = (args.lock or root / "sources.lock.json").resolve()
    committed = args.manifest or lock_path.parent / "build-manifest.json"
    quiet = (lambda *_: None) if args.check else print
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as td:
                man = build(lock_path, root, Path(td) / "build", log=quiet)
        else:
            out = (args.out or root / "build").resolve()
            man = build(lock_path, root, out, log=quiet)
    except BuildError as exc:
        for p in exc.problems:
            print(f"error: {p}", file=sys.stderr)
        return cli.EXIT_VIOLATION
    fresh = manifest.serialize(man)
    if args.record:
        committed.write_text(fresh, encoding="utf-8")
        print(f"recorded {committed}")
    old = committed.read_text(encoding="utf-8") if committed.is_file() else None
    if args.check:
        if old == fresh:
            print(f"build --check: {committed.name} matches")
            return cli.EXIT_OK
        print(manifest.diff(old or "", fresh, committed.name))
        print(f"build --check: the rebuilt data differs from {committed}.\n"
              "Find out why before regenerating it with `gbg build --record`; never "
              "hand-edit a generated manifest to make it match.", file=sys.stderr)
        return cli.EXIT_USAGE
    if old is not None and old != fresh:
        print(f"note: build differs from {committed} (run `gbg build --check` for the diff)")
    t = man["tables"]
    print(f"built: {t['token']['rows']} tokens, {t['verse']['rows']} verses, "
          f"{t['sentence']['rows']} sentences, {t['wg']['rows']} word groups, "
          f"{t['lemma']['rows']} lemmas")
    return cli.EXIT_OK
