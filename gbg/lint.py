"""``gbg lint``: the built graph's integrity gate, ``FILE\\tRULE\\tREASON``.

auto-zettel-skill's ``lint_links.py`` / ``lint_citations.py`` shape, pointed at
a database: FILE is the table, one line per rule that fails, exit 1 on any.

The build already refuses what it can at write time (coverage mismatches,
non-open fields, a tree that does not parse). These rules re-check the
*result*, so a bug in the build code -- not just bad data -- is caught before
anyone queries the graph. Several of them cannot fire on a correct build
from XML nesting (a tree parsed from nested elements has no cycles), and
that is the point: they guard the code. Each rule has a planted-violation
test that fires it, alone, on a copy of the fixture database.

The rules are deliberately disjoint -- one defect, one rule -- so that the
report names the actual problem instead of its cascade.
"""

from __future__ import annotations

import json
import sys

import duckdb

from . import cli, graphdef, ids, licenses

MAX_SHOWN = 20

#: node table -> id regex (the Python regexes are RE2-compatible)
ID_PATTERNS = {
    "token": ids.TOKEN_RE.pattern, "verse": ids.VERSE_RE.pattern, "book": ids.BOOK_RE.pattern,
    "sentence": ids.SENTENCE_RE.pattern, "wg": ids.WG_RE.pattern, "lemma": ids.LEMMA_RE.pattern,
}


def _v(table: str, rule: str, rows: list, what: str) -> list[cli.Violation]:
    if not rows:
        return []
    shown = ", ".join(str(r[0]) for r in rows[:MAX_SHOWN])
    more = f" (+{len(rows) - MAX_SHOWN} more)" if len(rows) > MAX_SHOWN else ""
    return [cli.Violation(table, rule, f"{len(rows)} {what}: {shown}{more}")]


def _rows(con, sql: str) -> list:
    return con.execute(sql).fetchall()


# --- ids and order ---------------------------------------------------------------

def id_format(con):
    out = []
    for table, pattern in ID_PATTERNS.items():
        out += _v(table, "id-format", _rows(con, f"""
            SELECT id FROM "{table}" WHERE NOT regexp_matches(id, '{pattern}') ORDER BY id"""),
            "ids do not match the id grammar")
    return out


def id_ref_mismatch(con):
    return _v("token", "id-ref-mismatch", _rows(con, f"""
        SELECT t.id FROM token t JOIN book b ON b.id = t.book_id
        WHERE t.id <> '{ids.EDITION}:' || t.xml_id
           OR t.xml_id <> 'n' || lpad(b.num::VARCHAR, 2, '0')
                            || lpad(t.chapter::VARCHAR, 3, '0')
                            || lpad(t.verse::VARCHAR, 3, '0') || lpad(t.word::VARCHAR, 3, '0')
           OR t.ref <> b.code || ' ' || t.chapter || ':' || t.verse || '!' || t.word
           OR t.verse_id <> '{ids.EDITION}:' || b.code || '.' || t.chapter || '.' || t.verse
        ORDER BY t.id"""), "tokens whose id, xml_id, ref and verse disagree")


def token_order(con):
    out = _v("token", "token-order", _rows(con, """
        SELECT id FROM (SELECT id, ord, row_number() OVER (ORDER BY id) AS expect,
                               next_id, lead(id) OVER (PARTITION BY book_id ORDER BY ord) AS nxt
                        FROM token)
        WHERE ord <> expect OR next_id IS DISTINCT FROM nxt ORDER BY id"""),
        "tokens out of surface order or with a broken next_id chain")
    out += _v("verse", "token-order", _rows(con, """
        SELECT verse_id FROM token GROUP BY verse_id
        HAVING min(word) <> 1 OR max(word) <> count(*) OR count(DISTINCT word) <> count(*)
        ORDER BY verse_id"""), "verses whose word numbers are not 1..n")
    return out


# --- spans -------------------------------------------------------------------------

_SPAN = """
    SELECT x.id FROM "{table}" x LEFT JOIN (
        SELECT {key} AS k, arg_min(t.id, t.ord) AS f, arg_max(t.id, t.ord) AS l, count(*) AS n
        {src} GROUP BY 1) a ON a.k = x.id
    WHERE a.k IS NULL OR x.first_token <> a.f OR x.last_token <> a.l OR x.n_tokens <> a.n
    {extra} ORDER BY x.id"""


def spans(con):
    out = _v("verse", "verse-span", _rows(con, _SPAN.format(
        table="verse", key="t.verse_id", src="FROM token t", extra="")),
        "verses whose first/last/count disagree with their tokens")
    out += _v("sentence", "sentence-span", _rows(con, _SPAN.format(
        table="sentence", key="t.sentence_id", src="FROM token t", extra="")),
        "sentences whose first/last/count disagree with their tokens")
    # Word groups absent from dominance are wg-empty's business, not this rule's.
    out += _v("wg", "wg-span", _rows(con, """
        SELECT w.id FROM wg w JOIN (
            SELECT d.wg_id, arg_min(t.id, t.ord) AS f, arg_max(t.id, t.ord) AS l,
                   count(*) AS n, max(t.ord) - min(t.ord) + 1 AS width
            FROM dominance d JOIN token t ON t.id = d.token_id GROUP BY 1) a ON a.wg_id = w.id
        WHERE w.first_token <> a.f OR w.last_token <> a.l OR w.n_tokens <> a.n
           OR w.contiguous <> (a.width = a.n) ORDER BY w.id"""),
        "word groups whose span disagrees with the tokens they dominate")
    return out


# --- edges -------------------------------------------------------------------------

def dangling_edges(con):
    """One check per declared reference -- generated from graphdef, never listed."""
    out = []
    for t in graphdef.TABLES:
        for c in t.refs:
            out += _v(t.name, "dangling-edge", _rows(con, f"""
                SELECT DISTINCT x."{c.name}" FROM "{t.name}" x
                LEFT JOIN "{c.ref}" r ON r.id = x."{c.name}"
                WHERE x."{c.name}" IS NOT NULL AND r.id IS NULL ORDER BY 1"""),
                f"{c.name} values that resolve to no {c.ref}")
    return out


def implicit_target(con):
    out = []
    for t in graphdef.TABLES:
        # Only relations that can name an unexpressed participant carry `implicit`.
        if t.kind == "edge" and any(c.name == "implicit" for c in t.columns):
            out += _v(t.name, "implicit-target", _rows(con, f"""
                SELECT src FROM "{t.name}" WHERE implicit <> (dst IS NULL) ORDER BY src"""),
                "edges where implicit and a NULL target disagree")
    return out


def tiers(con):
    out = []
    allowed = ", ".join(f"'{x}'" for x in graphdef.TIERS)
    for t in graphdef.TABLES:
        if t.kind != "edge":
            continue
        out += _v(t.name, "tier-unknown", _rows(con, f"""
            SELECT src FROM "{t.name}" WHERE tier NOT IN ({allowed}) ORDER BY src"""),
            f"edges with a tier outside {graphdef.TIERS}")
        out += _v(t.name, "computed-in-canonical", _rows(con, f"""
            SELECT src FROM "{t.name}" WHERE tier = 'computed' ORDER BY src"""),
            "computed edges in a canonical table (they belong in a proposed_* table)")
    return out


# --- the syntax forest ---------------------------------------------------------------

def forest(con):
    out = _v("sentence", "forest-root", _rows(con, """
        WITH roots AS (
            SELECT sentence_id, id, 'wg' AS kind FROM wg WHERE parent_wg IS NULL
            UNION ALL
            SELECT sentence_id, id, 'token' FROM token WHERE parent_wg IS NULL)
        SELECT s.id FROM sentence s LEFT JOIN (
            SELECT sentence_id, count(*) AS n, any_value(id) AS root, any_value(kind) AS kind
            FROM roots GROUP BY 1) r ON r.sentence_id = s.id
        WHERE r.n IS DISTINCT FROM 1
           OR (r.kind = 'wg' AND s.root_wg IS DISTINCT FROM r.root)
           OR (r.kind = 'token' AND s.root_wg IS NOT NULL)
        ORDER BY s.id"""), "sentences without exactly one root node")
    for table in ("wg", "token"):
        out += _v(table, "forest-depth", _rows(con, f"""
            SELECT c.id FROM "{table}" c LEFT JOIN wg p ON p.id = c.parent_wg
            WHERE (c.parent_wg IS NULL AND c.depth <> 0)
               OR (p.id IS NOT NULL AND c.depth <> p.depth + 1) ORDER BY c.id"""),
            "nodes whose depth is not their parent's depth + 1")
        out += _v(table, "forest-sentence", _rows(con, f"""
            SELECT c.id FROM "{table}" c JOIN wg p ON p.id = c.parent_wg
            WHERE c.sentence_id <> p.sentence_id ORDER BY c.id"""),
            "nodes in a different sentence from their parent")
    out += _v("wg", "wg-empty", _rows(con, """
        SELECT w.id FROM wg w WHERE NOT EXISTS (SELECT 1 FROM dominance d WHERE d.wg_id = w.id)
        ORDER BY w.id"""), "word groups that dominate no token")
    # The closure has one row per (ancestor, token): sum of token depths. And its
    # distance-1 rows must be exactly the parent links.
    [(n_dom, expect)] = _rows(con, "SELECT (SELECT count(*) FROM dominance), "
                                   "(SELECT coalesce(sum(depth), 0) FROM token)")
    if n_dom != expect:
        out.append(cli.Violation("dominance", "dominance-closure",
                                 f"{n_dom} rows, expected {expect} (sum of token depths)"))
    out += _v("dominance", "dominance-closure", _rows(con, """
        SELECT coalesce(d.token_id, t.id) FROM
          (SELECT token_id, wg_id FROM dominance WHERE dist = 1) d
          FULL JOIN (SELECT id, parent_wg FROM token WHERE parent_wg IS NOT NULL) t
            ON t.id = d.token_id AND t.parent_wg = d.wg_id
        WHERE d.token_id IS NULL OR t.id IS NULL ORDER BY 1"""),
        "tokens whose distance-1 dominance row is not their parent link")
    return out


# --- normalisation -----------------------------------------------------------------

def normalisation(con):
    out = []
    for table, cols in (("token", ("surface", "lemma", "normalized")), ("lemma", ("lemma",))):
        cond = " OR ".join(f'"{c}" <> nfc_normalize("{c}")' for c in cols)
        out += _v(table, "not-nfc", _rows(con, f'SELECT id FROM "{table}" WHERE {cond} ORDER BY id'),
                  "rows with a non-NFC identity string")
    out += _v("token", "lemma-key", _rows(con, """
        SELECT id FROM token WHERE lemma_key <> gbg_key(lemma) OR surface_key <> gbg_key(surface)
        ORDER BY id"""), "tokens whose stored key is not gbg_key() of the value")
    out += _v("lemma", "lemma-key", _rows(con, """
        SELECT id FROM lemma WHERE key <> gbg_key(lemma) OR id <> 'lemma:' || lemma ORDER BY id"""),
        "lemmas whose id or key does not derive from the lemma")
    return out


# --- licensing ---------------------------------------------------------------------

def license_rules(con):
    out = []
    comps = json.loads(con.execute("SELECT value FROM meta WHERE key = 'components'").fetchone()[0])
    excluded = {f for c in comps.values() if not licenses.is_open(c["license"]) for f in c["fields"]}
    actual = {}
    for table, column in _rows(con, "SELECT table_name, column_name FROM information_schema.columns "
                                    "WHERE table_schema = 'main' AND table_name <> 'meta' "
                                    "AND table_name <> 'edge'"):
        actual.setdefault(table, set()).add(column)
    for table, cols in sorted(actual.items()):
        declared = graphdef.BY_NAME.get(table)
        for col in sorted(cols):
            if col in excluded:
                out.append(cli.Violation(f"{table}.{col}", "license-not-open",
                                         "column carries a field excluded by license"))
                continue
            if declared is None or col not in {c.name for c in declared.columns}:
                out.append(cli.Violation(f"{table}.{col}", "license-unmapped",
                                         "column is not declared in graphdef, so no license "
                                         "component vouches for it"))
                continue
            comp = declared.column(col).component
            if comp == graphdef.GBG:
                continue
            if comp not in comps:
                out.append(cli.Violation(f"{table}.{col}", "license-unmapped",
                                         f"component {comp!r} is not in the build's lock"))
            elif not licenses.is_open(comps[comp]["license"]):
                out.append(cli.Violation(f"{table}.{col}", "license-not-open",
                                         f"component {comp!r} is {comps[comp]['license']}"))
    for t in graphdef.TABLES:
        missing = {c.name for c in t.columns} - actual.get(t.name, set())
        if missing:
            out.append(cli.Violation(t.name, "schema-mismatch",
                                     f"declared columns missing: {', '.join(sorted(missing))}"))
    return out


RULES = (id_format, id_ref_mismatch, token_order, spans, dangling_edges, implicit_target,
         tiers, forest, normalisation, license_rules)


def lint(db_path) -> list[cli.Violation]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        out: list[cli.Violation] = []
        for rule in RULES:
            out += rule(con)
        return out
    finally:
        con.close()


def add_arguments(p) -> None:
    cli.add_db(p)


def run(args) -> int:
    db = cli.db_of(args)
    if not db.is_file():
        print(f"error: no database at {db} (run `gbg build`)", file=sys.stderr)
        return cli.EXIT_USAGE
    return cli.report(lint(db), "gbg lint")
