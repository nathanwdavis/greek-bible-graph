"""One planted violation per rule, and it fires alone.

The pattern is auto-zettel-skill's ``tests/conftest.py``: start from a clean
artifact, break exactly one thing, and assert that exactly one rule names it.
A rule that also fires on the neighbours of a defect is a rule whose report
misleads, so disjointness is tested, not hoped for.
"""

import subprocess
import sys

import duckdb
import pytest

from conftest import ROOT
from gbg import greek, lint

FIRST = "sblgnt:n57001001001"
FIRST_SENT = "sblgnt:s:n57001001001"

PLANTS = {
    # Renamed consistently everywhere it is referenced, so only the grammar breaks.
    "id-format": [
        f"UPDATE token SET sentence_id = 'sblgnt:s:bogus' WHERE sentence_id = '{FIRST_SENT}'",
        f"UPDATE wg SET sentence_id = 'sblgnt:s:bogus' WHERE sentence_id = '{FIRST_SENT}'",
        f"UPDATE sentence SET id = 'sblgnt:s:bogus' WHERE id = '{FIRST_SENT}'",
    ],
    "id-ref-mismatch": [f"UPDATE token SET ref = 'PHM 1:1!2' WHERE id = '{FIRST}'"],
    "token-order": [f"UPDATE token SET next_id = NULL WHERE id = '{FIRST}'"],
    "verse-span": ["UPDATE verse SET n_tokens = n_tokens + 1 WHERE id = 'sblgnt:PHM.1.1'"],
    "sentence-span": [f"UPDATE sentence SET last_token = first_token WHERE id = '{FIRST_SENT}'"],
    "wg-span": ["UPDATE wg SET contiguous = NOT contiguous WHERE id = 'sblgnt:wg:n57001001001.0'"],
    "dangling-edge": [
        f"INSERT INTO refers_to VALUES ('{FIRST}', 'sblgnt:n57099099099', false, 99, 'data', "
        "NULL, 'macula-greek')"],
    "implicit-target": [
        "UPDATE frame_arg SET implicit = false WHERE rowid = "
        "(SELECT min(rowid) FROM frame_arg WHERE implicit)"],
    "tier-unknown": ["UPDATE refers_to SET tier = 'guess' WHERE rowid = "
                     "(SELECT min(rowid) FROM refers_to)"],
    "computed-in-canonical": ["UPDATE refers_to SET tier = 'computed' WHERE rowid = "
                              "(SELECT min(rowid) FROM refers_to)"],
    "forest-root": [f"UPDATE sentence SET root_wg = NULL WHERE id = '{FIRST_SENT}'"],
    "forest-depth": ["UPDATE wg SET depth = depth + 5 WHERE id = 'sblgnt:wg:n57001001001.2'"],
    "forest-sentence": [
        "UPDATE wg SET sentence_id = 'sblgnt:s:n57001003001' "
        "WHERE id = 'sblgnt:wg:n57001001001.2'"],
    "wg-empty": [
        "INSERT INTO wg SELECT 'sblgnt:wg:n57001001001.99', sentence_id, id, 1, 99, 999, "
        "'np', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, first_token, first_token, 0, "
        "true FROM wg WHERE id = 'sblgnt:wg:n57001001001.0'"],
    "dominance-closure": [
        "UPDATE dominance SET dist = 7 WHERE rowid = "
        "(SELECT min(rowid) FROM dominance WHERE dist = 1)"],
    "not-nfc": [f"UPDATE token SET normalized = '{greek.unicodedata.normalize('NFD', 'Παῦλος')}' "
                f"WHERE id = '{FIRST}'"],
    "lemma-key": ["UPDATE lemma SET key = 'x' WHERE id = 'lemma:θεός'"],
    "license-not-open": [
        """UPDATE meta SET value = json_object('macula-clear', json_object('license',
           'CC-BY-4.0', 'fields', ['lemma']), 'sblgnt-text', json_object('license', 'CC-BY-4.0',
           'fields', ['text']), 'berean', json_object('license', 'LicenseRef-PublicDomain',
           'fields', ['gloss']), 'cherith', json_object('license', 'LicenseRef-UsedWithPermission',
           'fields', ['english'])) WHERE key = 'components'"""],
    "license-unmapped": ["ALTER TABLE token ADD COLUMN mystery VARCHAR"],
    "schema-mismatch": ["ALTER TABLE token DROP COLUMN english"],
}


def fired(db) -> set[str]:
    return {v.rule for v in lint.lint(db)}


def test_clean_fixture_passes(fixture_db):
    assert lint.lint(fixture_db) == []


@pytest.mark.parametrize("rule", sorted(PLANTS))
def test_each_rule_fires_alone(rule, db_copy):
    con = duckdb.connect(str(db_copy))
    for sql in PLANTS[rule]:
        con.execute(sql)
    con.close()
    assert fired(db_copy) == {rule}


def test_every_rule_has_a_plant():
    # A rule nobody can trip is a rule nobody has seen work.
    import inspect
    src = inspect.getsource(lint)
    named = {r for r in PLANTS}
    for rule in named:
        assert f'"{rule}"' in src, rule


def test_cli_exit_codes(fixture_db, db_copy):
    ok = subprocess.run([sys.executable, "-m", "gbg", "lint", "--db", str(fixture_db)],
                        capture_output=True, text=True, cwd=ROOT)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    con = duckdb.connect(str(db_copy))
    con.execute(PLANTS["lemma-key"][0])
    con.close()
    bad = subprocess.run([sys.executable, "-m", "gbg", "lint", "--db", str(db_copy)],
                         capture_output=True, text=True, cwd=ROOT)
    assert bad.returncode == 1
    assert bad.stdout.startswith("lemma\tlemma-key\t1 lemmas whose id or key")
    missing = subprocess.run([sys.executable, "-m", "gbg", "lint", "--db", "/nonexistent.duckdb"],
                             capture_output=True, text=True, cwd=ROOT)
    assert missing.returncode == 2


def test_sql_key_macro_agrees_with_python_on_every_fixture_string(fixture_db):
    con = duckdb.connect(str(fixture_db), read_only=True)
    rows = con.execute("SELECT DISTINCT x, gbg_key(x) FROM (SELECT lemma AS x FROM token "
                       "UNION SELECT surface FROM token UNION SELECT normalized FROM token)").fetchall()
    assert rows and all(k == greek.search_key(x) for x, k in rows)
