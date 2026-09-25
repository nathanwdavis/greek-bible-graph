import subprocess
import sys

from conftest import ROOT
from gbg import graphdef, schemadoc


def test_committed_schema_doc_is_current():
    out = subprocess.run([sys.executable, "-m", "gbg", "schema", "--check"], capture_output=True,
                         text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr


def test_every_table_and_column_is_documented():
    doc = schemadoc.static_doc()
    for t in graphdef.TABLES:
        assert f"### `{t.name}`" in doc
        for c in t.columns:
            assert f"| `{c.name}` |" in doc, f"{t.name}.{c.name}"


def test_pitfalls_come_first_and_name_the_subject_trap():
    doc = schemadoc.static_doc()
    assert doc.index("## Read this first") < doc.index("## Tables")
    assert "`has_subject` is coreference, not grammar" in doc


def test_live_doc_reports_actual_enum_values(fixture_db):
    live = schemadoc.live_doc(fixture_db)
    assert "`token.gcase`" in live and "`nominative`" in live
    assert "| `token` | 798 |" in live
