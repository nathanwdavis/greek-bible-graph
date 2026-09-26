"""The query sandbox, and ``gbg sql``.

Claude writes SQL here, so the connection is built to be safe whatever the
SQL says. The spike behind this (docs/DESIGN.md, D-3) found that a read-only
connection is NOT a sandbox on its own: ``read_only=True`` still allows
``COPY ... TO`` any path, ``read_text('/etc/passwd')``, ``ATTACH`` and
``INSTALL``. So, in this order:

1. open the database read-only (or, for ``--pgq``, attach it read-only into
   an in-memory database -- DuckPGQ cannot create a property graph on a
   read-only database, nor over views, so the graph's edge tables are
   materialised in memory, schema-qualified so they survive ``USE gbg``);
2. ``SET enable_external_access = false`` -- no file or network access;
3. ``SET lock_configuration = true`` -- the SQL cannot turn (2) back off;
4. accept exactly ONE statement, and only a SELECT (plus DuckPGQ's
   ``EXTENSION`` statements under ``--pgq``) -- no DDL, no PRAGMA, no CALL;
5. interrupt anything that runs past the timeout, and cap the rows returned
   (fetching limit+1 detects truncation without rewriting the SQL).

Every result carries the build id and source commit, because a count is only
citable as "this query, on this build of this text".
"""

from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from . import cli, graphdef, ids

DEFAULT_LIMIT = 200
MAX_LIMIT = 10_000
DEFAULT_TIMEOUT = 30.0
PGQ_GRAPH = "gbg_graph"


class QueryError(cli.UsageError):
    pass


@dataclass
class Result:
    sql: str
    params: dict
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    build_id: str
    source_commits: dict
    citable_columns: list[str] = field(default_factory=list)

    def envelope(self) -> dict:
        return {"build_id": self.build_id, "edition": ids.EDITION,
                "source_commits": self.source_commits, "sql": self.sql, "params": self.params,
                "columns": self.columns, "rows": [list(r) for r in self.rows],
                "row_count": len(self.rows), "truncated": self.truncated,
                "citable": bool(self.citable_columns), "citable_columns": self.citable_columns}


def pgq_edge_tables() -> list[tuple[str, str, str, str, str, str]]:
    """(memory table, SELECT that fills it, src table, src key, dst table, label)."""
    out = []
    for t, c in graphdef.fk_edges():
        out.append((f"e_{t.name}_{c.name}",
                    f'SELECT id AS src, "{c.name}" AS dst FROM gbg.main."{t.name}" '
                    f'WHERE "{c.name}" IS NOT NULL',
                    t.name, "src", c.ref, f"{t.name}_{c.label.lower()}"))
    for t in graphdef.TABLES:
        if t.kind == "edge":
            out.append((f"e_{t.name}", f'SELECT * FROM gbg.main."{t.name}" WHERE dst IS NOT NULL',
                        t.column("src").ref, "src", t.column("dst").ref, t.name))
    return out


def pgq_graph_sql() -> str:
    vertices = ", ".join(f"gbg.main.{t.name} LABEL {t.name}"
                         for t in graphdef.TABLES if t.kind == "node")
    edges = [f"memory.main.{name} SOURCE KEY (src) REFERENCES gbg.main.{src} (id) "
             f"DESTINATION KEY (dst) REFERENCES gbg.main.{dst} (id) LABEL {label}"
             for name, _, src, _, dst, label in pgq_edge_tables()]
    edges.append("gbg.main.dominance SOURCE KEY (wg_id) REFERENCES gbg.main.wg (id) "
                 "DESTINATION KEY (token_id) REFERENCES gbg.main.token (id) LABEL dominates")
    return (f"CREATE PROPERTY GRAPH {PGQ_GRAPH} VERTEX TABLES ({vertices}) "
            f"EDGE TABLES ({', '.join(edges)})")


def pgq_available() -> bool:
    try:
        con = duckdb.connect()
        _load_pgq(con)
        return True
    except Exception:  # noqa: BLE001 - any failure means "not here"
        return False


def _load_pgq(con) -> None:
    try:
        con.execute("LOAD duckpgq")
    except duckdb.Error:
        con.execute("INSTALL duckpgq FROM community")
        con.execute("LOAD duckpgq")


def connect(db: Path, *, pgq: bool = False):
    """A locked-down connection. See the module docstring for the order."""
    db = Path(db)
    if not db.is_file():
        raise QueryError(f"no database at {db} (run `gbg build`)")
    if pgq:
        con = duckdb.connect()
        try:
            _load_pgq(con)
        except duckdb.Error as exc:
            raise QueryError(f"DuckPGQ is unavailable ({exc}); plain SQL works without it") \
                from None
        con.execute(f"ATTACH '{db}' AS gbg (READ_ONLY)")
        for name, fill, *_ in pgq_edge_tables():
            con.execute(f"CREATE TABLE memory.main.{name} AS {fill}")
        con.execute(pgq_graph_sql())
        con.execute("USE gbg")
    else:
        con = duckdb.connect(str(db), read_only=True)
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def _meta(con) -> tuple[str, dict]:
    rows = dict(con.execute("SELECT key, value FROM meta").fetchall())
    return rows.get("build_id", "unknown"), json.loads(rows.get("source_commits", "{}"))


def check_statement(con, sql: str, *, pgq: bool) -> None:
    try:
        stmts = con.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryError(f"cannot parse SQL: {exc}") from None
    if len(stmts) != 1:
        raise QueryError(f"exactly one statement is allowed (got {len(stmts)})")
    allowed = {duckdb.StatementType.SELECT}
    if pgq:
        allowed.add(duckdb.StatementType.EXTENSION)
    if stmts[0].type not in allowed:
        raise QueryError(f"only SELECT queries are allowed (got {stmts[0].type.name})")


def _literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_literal(x) for x in v) + "]"
    # Standard SQL string: the only escape is a doubled quote (DuckDB does not
    # treat backslashes specially), so this cannot break out of the literal.
    return "'" + str(v).replace("'", "''") + "'"


def inline_params(sql: str, params: dict) -> str:
    """Substitute ``$name`` with literals, for SQL/PGQ only.

    DuckPGQ rewrites GRAPH_TABLE before binding and drops prepared-statement
    parameters ("Parameter argument/count mismatch"), so under ``--pgq`` the
    values are inlined as quoted literals. Plain SQL keeps real binding.
    """
    def sub(m):
        name = m.group(1)
        if name not in params:
            raise QueryError(f"no value for ${name}")
        return _literal(params[name])
    return re.sub(r"\$(\w+)", sub, sql)


def _citable(columns: list[str], rows: list[tuple]) -> list[str]:
    """Columns whose every non-null value is a citable id."""
    out = []
    for i, name in enumerate(columns):
        vals = [r[i] for r in rows if r[i] is not None]
        if vals and all(isinstance(v, str) and ids.kind_of(v) in ids.CITABLE for v in vals):
            out.append(name)
    return out


def run_query(db: Path, sql: str, params: dict | None = None, *, limit: int = DEFAULT_LIMIT,
              timeout: float = DEFAULT_TIMEOUT, pgq: bool = False) -> Result:
    if not 1 <= limit <= MAX_LIMIT:
        raise QueryError(f"--limit must be between 1 and {MAX_LIMIT}")
    con = connect(db, pgq=pgq)
    try:
        if pgq and params:
            sql_run, bound = inline_params(sql, params), {}
        else:
            sql_run, bound = sql, (params or {})
        check_statement(con, sql_run, pgq=pgq)
        build_id, commits = _meta(con)
        timer = threading.Timer(timeout, con.interrupt)
        timer.start()
        try:
            cur = con.execute(sql_run, bound)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(limit + 1)
        except duckdb.InterruptException:
            raise QueryError(f"query exceeded the {timeout:g}s timeout") from None
        except duckdb.Error as exc:
            raise QueryError(str(exc).strip()) from None
        finally:
            timer.cancel()
    finally:
        con.close()
    truncated = len(rows) > limit
    rows = rows[:limit]
    return Result(sql, dict(params or {}), columns, rows, truncated, build_id, commits,
                  _citable(columns, rows))


# --- output --------------------------------------------------------------------

def _plain(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def emit(res: Result, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(res.envelope(), ensure_ascii=False, indent=1, default=str))
        return
    print("\t".join(res.columns))
    for r in res.rows:
        print("\t".join(_plain(v) for v in r))
    note = f"-- {len(res.rows)} row(s); build {res.build_id}"
    if res.truncated:
        note += f"; TRUNCATED at {len(res.rows)} (raise --limit)"
    if not res.citable_columns and res.rows:
        note += "; no citable id column (select token/verse/lemma ids to make rows citable)"
    print(note, file=sys.stderr)


def parse_params(pairs: list[str] | None) -> dict:
    out = {}
    for p in pairs or []:
        key, sep, value = p.partition("=")
        if not sep or not key:
            raise QueryError(f"--param expects name=value, got {p!r}")
        out[key] = int(value) if value.lstrip("-").isdigit() else value
    return out


def add_output(p) -> None:
    p.add_argument("--json", dest="fmt", action="store_const", const="json", default="tsv",
                   help="JSON envelope with build id, columns, rows, truncation")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"maximum rows (hard cap {MAX_LIMIT})")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds")


def add_arguments(p) -> None:
    cli.add_db(p)
    p.add_argument("query", help="one SELECT statement")
    p.add_argument("--param", action="append", metavar="NAME=VALUE",
                   help="bind $NAME (repeatable)")
    p.add_argument("--pgq", action="store_true",
                   help=f"enable SQL/PGQ: GRAPH_TABLE ({PGQ_GRAPH} MATCH ...) via DuckPGQ")
    add_output(p)


def run(args) -> int:
    res = run_query(cli.db_of(args), args.query, parse_params(args.param), limit=args.limit,
                    timeout=args.timeout, pgq=args.pgq)
    emit(res, args.fmt)
    return cli.EXIT_OK
