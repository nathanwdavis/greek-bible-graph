"""``gbg query``: saved queries, with typed parameters.

A saved query is a ``.sql`` file in ``queries/`` whose header says what it
answers and what it needs::

    -- name: lemma_occurrences
    -- description: Every occurrence of a lemma ...
    -- param: lemma lemma -- the dictionary form, e.g. θεός
    -- param: scope passage optional -- limit to a passage
    -- cites: token

Parameter types do the fiddly part once, so neither a person nor Claude has
to: ``lemma`` is NFC-normalised (so an oxia-typed ἀγάπη still matches);
``token`` accepts an id or a MACULA ref; ``passage`` is resolved with
``gbg resolve`` into ``$NAME_first`` / ``$NAME_last`` token-order bounds
(absent and optional means the whole edition). ``optional=VALUE`` gives a
default. Everything then runs through the same sandbox as ``gbg sql``.

List types take comma-separated values and bind as a DuckDB list (use
``list_contains($name, x)``): ``lemmas`` (each NFC'd, like ``lemma``),
``tokens`` (each like ``token``, so hits from one query can feed the next),
and ``english`` -- plain English words put through ``gbg.english``'s gloss
normalisation, so ``know, hide`` matches the stored ``token.english_terms``.

Twins under ``queries/pgq/`` express the same question in SQL/PGQ; a test
holds each to the same rows as its SQL original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cli, db as dbmod, english, ids, refs
from .greek import nfc
from .resolve import resolve

TYPES = ("lemma", "lemmas", "text", "int", "float", "token", "tokens", "passage",
         "english")


@dataclass
class Param:
    name: str
    type: str
    optional: bool
    default: str | None
    doc: str


@dataclass
class Saved:
    name: str
    path: Path
    description: str
    params: list[Param]
    cites: str
    sql: str
    extra: dict = field(default_factory=dict)


_PARAM = re.compile(r"^(\w+)\s+(\w+)(?:\s+optional(?:=(\S+))?)?\s*(?:--\s*(.*))?$")


def parse_file(path: Path) -> Saved:
    head: dict[str, list[str]] = {}
    body = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^--\s*(name|description|param|cites):\s*(.*)$", line)
        if m and not body:
            head.setdefault(m.group(1), []).append(m.group(2).strip())
        else:
            body.append(line)
    if "name" not in head or head["name"][0] != path.stem:
        raise cli.UsageError(f"{path}: header 'name' must match the file name")
    params = []
    for p in head.get("param", []):
        m = _PARAM.match(p)
        if not m or m.group(2) not in TYPES:
            raise cli.UsageError(f"{path}: bad param line {p!r}")
        optional = " optional" in f" {p}"
        params.append(Param(m.group(1), m.group(2), optional, m.group(3), m.group(4) or ""))
    return Saved(path.stem, path, " ".join(head.get("description", [])), params,
                 (head.get("cites") or [""])[0], "\n".join(body).strip())


def load_all(root: Path, pgq: bool = False) -> dict[str, Saved]:
    d = root / "queries" / ("pgq" if pgq else "")
    return {p.stem: parse_file(p) for p in sorted(d.glob("*.sql"))}


def bind(saved: Saved, raw: dict[str, str], db: Path) -> dict:
    unknown = set(raw) - {p.name for p in saved.params}
    if unknown:
        raise cli.UsageError(f"{saved.name}: unknown parameter(s) {sorted(unknown)}")
    out: dict = {}
    con = dbmod.connect(db)
    try:
        max_ord = con.execute("SELECT max(ord) FROM token").fetchone()[0]
        for p in saved.params:
            value = raw.get(p.name, p.default)
            if value is None and not p.optional:
                raise cli.UsageError(f"{saved.name}: --param {p.name}=... is required "
                                     f"({p.type}: {p.doc})")
            if p.type == "passage":
                if value is None:
                    out[f"{p.name}_first"], out[f"{p.name}_last"] = 1, max_ord
                    continue
                try:
                    res = resolve(con, str(value))
                except refs.RefError as exc:
                    raise cli.UsageError(f"{p.name}: {exc}") from None
                if not res.found:
                    raise cli.UsageError(f"{p.name}: {'; '.join(res.missing)}")
                f, l = con.execute("SELECT (SELECT ord FROM token WHERE id = ?), "
                                   "(SELECT ord FROM token WHERE id = ?)",
                                   [res.first_token, res.last_token]).fetchone()
                out[f"{p.name}_first"], out[f"{p.name}_last"] = f, l
            elif p.type == "lemma":
                out[p.name] = _lemma(str(value))
            elif p.type == "lemmas":
                out[p.name] = [_lemma(v) for v in _split(p.name, value)]
            elif p.type == "token":
                out[p.name] = _token(con, p.name, str(value))
            elif p.type == "tokens":
                out[p.name] = [_token(con, p.name, v) for v in _split(p.name, value)]
            elif p.type == "english":
                terms = english.query_terms(str(value))
                if not terms:
                    raise cli.UsageError(f"{p.name}: {value!r} has no content words "
                                         "(only stopwords)")
                out[p.name] = terms
            elif p.type == "float":
                out[p.name] = float(value) if value is not None else None
            elif p.type == "int":
                out[p.name] = int(value) if value is not None else None
            else:
                out[p.name] = value
    finally:
        con.close()
    return out


def _lemma(v: str) -> str:
    return nfc(v[len("lemma:"):] if v.startswith("lemma:") else v)


def _split(name: str, value) -> list[str]:
    items = [v.strip() for v in str(value).split(",") if v.strip()]
    if not items:
        raise cli.UsageError(f"{name}: expected one or more comma-separated values")
    return items


def _token(con, name: str, v: str) -> str:
    """A token id, from an id or a MACULA ref (BOOK C:V!W)."""
    if ids.kind_of(v) == "token":
        return v
    try:
        span = refs.parse(v).spans[0]
    except refs.RefError as exc:
        raise cli.UsageError(f"{name}: {exc}") from None
    if span.w1 is None:
        raise cli.UsageError(f"{name}: {v!r} is not a single word (use an id or BOOK C:V!W)")
    row = con.execute("SELECT id FROM token WHERE ref = ?",
                      [f"{span.book} {span.c1}:{span.v1}!{span.w1}"]).fetchone()
    if not row:
        raise cli.UsageError(f"{name}: {v!r} is not in this edition")
    return row[0]


def run_saved(root: Path, db: Path, name: str, raw: dict, *, pgq: bool = False,
              limit: int = dbmod.DEFAULT_LIMIT, timeout: float = dbmod.DEFAULT_TIMEOUT):
    saved = load_all(root, pgq).get(name)
    if saved is None:
        where = "queries/pgq/" if pgq else "queries/"
        raise cli.UsageError(f"no saved query {name!r} in {where} (see `gbg query --list`)")
    params = bind(saved, raw, db)
    used = set(re.findall(r"\$(\w+)", saved.sql))
    return dbmod.run_query(db, saved.sql, {k: v for k, v in params.items() if k in used},
                           limit=limit, timeout=timeout, pgq=pgq)


def add_arguments(p) -> None:
    cli.add_db(p)
    p.add_argument("name", nargs="?", help="saved query (see --list)")
    p.add_argument("--list", action="store_true", help="list saved queries and their parameters")
    p.add_argument("--param", action="append", metavar="NAME=VALUE", help="repeatable")
    p.add_argument("--pgq", action="store_true", help="run the SQL/PGQ twin from queries/pgq/")
    dbmod.add_output(p)


def run(args) -> int:
    root = cli.root_of(args)
    if args.list or not args.name:
        for pgq in (False, True):
            for s in load_all(root, pgq).values():
                tag = " [pgq]" if pgq else ""
                print(f"{s.name}{tag}: {s.description}")
                for prm in s.params:
                    opt = " (optional" + (f", default {prm.default}" if prm.default else "") + ")" \
                        if prm.optional else ""
                    print(f"    --param {prm.name}=<{prm.type}>{opt}  {prm.doc}")
        return cli.EXIT_OK if args.list else cli.EXIT_USAGE
    raw = {}
    for pair in args.param or []:
        k, sep, v = pair.partition("=")
        if not sep:
            raise cli.UsageError(f"--param expects name=value, got {pair!r}")
        raw[k] = v
    res = run_saved(root, cli.db_of(args), args.name, raw, pgq=args.pgq, limit=args.limit,
                    timeout=args.timeout)
    dbmod.emit(res, args.fmt)
    return cli.EXIT_OK
