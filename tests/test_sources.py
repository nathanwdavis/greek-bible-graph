import hashlib
import json
from pathlib import Path

import pytest

from gbg import licenses, sources
from gbg.http import CassetteTransport, Response

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def make_lock(tmp_path: Path, content: bytes, *, license="CC-BY-4.0",
              components=None) -> Path:
    lock = {"sources": {"demo": {
        "repo": "https://example.org/demo", "commit": "abc123",
        "raw_url": "https://example.org/{commit}/{path}",
        "license": license, "attribution": "Demo data",
        "files": [{"path": "data/a.tsv", "sha256": hashlib.sha256(content).hexdigest(),
                   "bytes": len(content)}],
        "components": components or {
            "core": {"fields": ["x"], "license": "CC-BY-4.0", "attribution": "core"},
            "closed": {"fields": ["secret"], "license": "LicenseRef-UsedWithPermission",
                       "attribution": "closed"}},
    }}}
    p = tmp_path / "sources.lock.json"
    p.write_text(json.dumps(lock))
    return p


def test_open_license_allowlist_is_pinned():
    # Changing what counts as "open" is a project decision, not a refactor.
    assert licenses.OPEN_LICENSES == {"CC-BY-4.0", "CC0-1.0", "LicenseRef-PublicDomain"}
    assert not licenses.is_open("CC-BY-SA-4.0")
    assert not licenses.is_open("LicenseRef-UsedWithPermission")


def test_excluded_fields_derive_from_component_licenses(tmp_path):
    lock = sources.load_lock(make_lock(tmp_path, b"x"))
    assert lock.source("demo").excluded_fields() == {"secret"}


def test_fetch_downloads_verifies_and_caches(tmp_path):
    body = b"hello\tworld\n"
    lock = sources.load_lock(make_lock(tmp_path, body))
    t = CassetteTransport({"/abc123/data/a.tsv": Response(200, body)})
    assert sources.fetch(lock, tmp_path, transport=t, log=lambda *_: None) == []
    cached = tmp_path / "cache" / "demo" / "abc123" / "data" / "a.tsv"
    assert cached.read_bytes() == body
    # Second run is served from the cache: no network call at all.
    t2 = CassetteTransport({})
    assert sources.fetch(lock, tmp_path, transport=t2, log=lambda *_: None) == []
    assert t2.calls == []


def test_fetch_refuses_a_hash_mismatch_and_writes_nothing(tmp_path):
    lock = sources.load_lock(make_lock(tmp_path, b"expected"))
    t = CassetteTransport({"a.tsv": Response(200, b"tampered")})
    problems = sources.fetch(lock, tmp_path, transport=t, log=lambda *_: None)
    assert problems and "does not match the lock" in problems[0]
    target = tmp_path / "cache" / "demo" / "abc123" / "data" / "a.tsv"
    assert not target.exists()
    assert not target.with_name("a.tsv.part").exists()


def test_fetch_refuses_a_non_open_source_before_downloading(tmp_path):
    lock = sources.load_lock(make_lock(tmp_path, b"x", license="CC-BY-NC-SA-4.0"))
    t = CassetteTransport({})
    problems = sources.fetch(lock, tmp_path, transport=t, log=lambda *_: None)
    assert problems and "not open" in problems[0]
    assert t.calls == []


def test_offline_reports_missing_files(tmp_path):
    lock = sources.load_lock(make_lock(tmp_path, b"x"))
    problems = sources.fetch(lock, tmp_path, offline=True, transport=CassetteTransport({}),
                             log=lambda *_: None)
    assert problems and "offline" in problems[0]


def test_http_error_is_a_problem_not_a_crash(tmp_path):
    lock = sources.load_lock(make_lock(tmp_path, b"x"))
    t = CassetteTransport({"a.tsv": Response(404, b"")})
    assert "HTTP 404" in sources.fetch(lock, tmp_path, transport=t, log=lambda *_: None)[0]


def test_malformed_lock_is_a_usage_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"sources": {"x": {"repo": "r"}}}))
    with pytest.raises(sources.LockError):
        sources.load_lock(p)


# --- the real lock and the checked-in fixture ------------------------------------

def test_real_lock_is_well_formed_and_marble_is_excluded():
    src = sources.load_lock(ROOT / "sources.lock.json").source("macula-greek")
    assert licenses.is_open(src.license)
    assert src.excluded_fields() == {"domain", "ln"}
    assert len(src.commit) == 40 and all(len(f.sha256) == 64 for f in src.files)
    assert len(src.files) == 28  # the TSV + 27 lowfat books, enumerated (no listing API)


def test_fixture_matches_its_lock():
    lock = sources.load_lock(FIXTURES / "fixture.lock.json")
    assert sources.verify_files(lock, "macula-greek", ROOT) == []


def test_fixture_carries_no_marble_data():
    # The whole reason the fixture is generated rather than copied.
    for p in (FIXTURES / "macula").rglob("*"):
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            assert ' domain="' not in text and ' ln="' not in text, p
            if p.suffix == ".tsv":
                header = text.split("\n", 1)[0].split("\t")
                assert "domain" not in header and "ln" not in header


def test_fixture_components_match_the_real_lock():
    real = json.loads((ROOT / "sources.lock.json").read_text())["sources"]["macula-greek"]
    fix = json.loads((FIXTURES / "fixture.lock.json").read_text())["sources"]["macula-greek"]
    assert fix["components"] == real["components"]
    assert fix["commit"] == real["commit"]


def test_every_attribution_appears_in_notice():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    src = sources.load_lock(ROOT / "sources.lock.json").source("macula-greek")
    assert src.attribution in notice
    for c in src.components:
        if licenses.is_open(c.license):
            assert c.attribution in notice, c.name
