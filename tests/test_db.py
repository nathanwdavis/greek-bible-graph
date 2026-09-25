"""The SQL sandbox. Every escape the spike found has a test here."""

import os

import duckdb
import pytest

from gbg import db


def test_select_runs_and_carries_provenance(fixture_db):
    res = db.run_query(fixture_db, "SELECT id, surface FROM token WHERE lemma = $l ORDER BY ord",
                       {"l": "θεός"})
    assert len(res.rows) == 7
    env = res.envelope()
    assert env["build_id"] and env["source_commits"]["macula-greek"]
    assert env["citable"] and env["citable_columns"] == ["id"]


def test_row_cap_detects_truncation(fixture_db):
    res = db.run_query(fixture_db, "SELECT id FROM token", limit=5)
    assert len(res.rows) == 5 and res.truncated
    res = db.run_query(fixture_db, "SELECT id FROM token WHERE lemma = 'θεός'", limit=7)
    assert len(res.rows) == 7 and not res.truncated


def test_aggregates_are_flagged_not_citable(fixture_db):
    res = db.run_query(fixture_db, "SELECT count(*) FROM token")
    assert not res.envelope()["citable"]


@pytest.mark.parametrize("sql", [
    "COPY token TO '{tmp}/x.csv'",
    "SELECT * FROM read_text('/etc/hostname')",
    "SELECT * FROM read_csv('/etc/hostname')",
    "ATTACH '{tmp}/y.duckdb'",
    "SET enable_external_access = true",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SELECT 1; SELECT 2",
    "CREATE TEMP TABLE t AS SELECT 1",
    "CALL pragma_version()",
    "EXPORT DATABASE '{tmp}/exp'",
    "DELETE FROM token",
])
def test_escapes_are_refused(fixture_db, tmp_path, sql):
    with pytest.raises(db.QueryError):
        db.run_query(fixture_db, sql.format(tmp=tmp_path))
    assert os.listdir(tmp_path) == []


def test_table_function_pragmas_are_plain_selects(fixture_db):
    # DuckDB rewrites PRAGMA database_list into SELECT * FROM pragma_database_list():
    # read-only and harmless, so it passes the one-SELECT check by design.
    assert db.run_query(fixture_db, "PRAGMA database_list").rows


def test_file_access_inside_a_select_is_refused_by_configuration(fixture_db):
    with pytest.raises(db.QueryError, match="disabled by configuration"):
        db.run_query(fixture_db, "SELECT * FROM read_text('/etc/hostname')")


def test_timeout_interrupts(fixture_db):
    with pytest.raises(db.QueryError, match="timeout"):
        db.run_query(fixture_db, "SELECT sum(a.ord * b.ord * c.ord) FROM token a, token b, "
                                 "token c", timeout=0.2)


def test_limit_bounds(fixture_db):
    with pytest.raises(db.QueryError):
        db.run_query(fixture_db, "SELECT 1", limit=0)
    with pytest.raises(db.QueryError):
        db.run_query(fixture_db, "SELECT 1", limit=db.MAX_LIMIT + 1)


def test_database_is_never_written(fixture_db):
    before = fixture_db.stat().st_mtime_ns
    db.run_query(fixture_db, "SELECT count(*) FROM token")
    assert fixture_db.stat().st_mtime_ns == before


def test_inline_params_cannot_break_out_of_a_literal():
    sql = db.inline_params("SELECT $x, $n", {"x": "a'; DROP TABLE token; --", "n": 3})
    assert sql == "SELECT 'a''; DROP TABLE token; --', 3"
    con = duckdb.connect()
    assert con.execute(sql).fetchone() == ("a'; DROP TABLE token; --", 3)
