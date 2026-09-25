#!/usr/bin/env bash
# End-to-end smoke test: the acceptance checklist in executable form.
#
# Runs offline against the checked-in fixture (Philemon, 2 John, 3 John).
# Exits 0 only if everything passes. Style and rules are auto-zettel-skill's:
# never assert through a pipe -- capture output first, then match with a bash
# pattern ([[ "$OUT" == *x* ]]), not `echo | grep -q`: under pipefail, grep -q
# exiting early can SIGPIPE the echo on large output and fail a passing check.
# Put the observed value in the failure message so nobody debugs blind.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; else PY="$(command -v python3)"; fi
fi
GBG=("$PY" -m gbg)

pass() { printf '  \033[32mok\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1" >&2; exit 1; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 1. every subcommand answers --help ---------------------------------------
step "[1] CLI contract"
OUT="$("${GBG[@]}" --help 2>&1)" || fail "gbg --help exited non-zero (got: $OUT)"
pass "gbg --help"
CMDS="$("$PY" -c 'from gbg.cli import COMMANDS; print(" ".join(c[0] for c in COMMANDS))')"
for c in $CMDS; do
  OUT="$("${GBG[@]}" "$c" --help 2>&1)" || fail "gbg $c --help exited non-zero (got: $OUT)"
  pass "gbg $c --help"
done

# --- 2. the fixture builds offline ---------------------------------------------
step "[2] build (offline fixture)"
FXLOCK="$ROOT/tests/fixtures/fixture.lock.json"
BUILD="$WORK/build"
OUT="$("${GBG[@]}" build --lock "$FXLOCK" --out "$BUILD" 2>&1)" || fail "fixture build failed (got: $OUT)"
[[ "$OUT" == *"built: 798 tokens"* ]] || fail "fixture build did not report 798 tokens (got: $OUT)"
[[ -f "$BUILD/gbg.duckdb" && -f "$BUILD/parquet/token.parquet" ]] || fail "build outputs missing"
pass "fixture builds: DuckDB + Parquet"
DB="$BUILD/gbg.duckdb"

# --- 3. build --check: 0 when unchanged, 2 on any change -------------------------
step "[3] build --check"
OUT="$("${GBG[@]}" build --check --lock "$FXLOCK" 2>&1)" || fail "build --check failed on a clean fixture (got: $OUT)"
pass "committed fixture manifest reproduces"
BAD="$WORK/badfix"
mkdir -p "$BAD"
cp -r "$ROOT/tests/fixtures/macula" "$BAD/"
cp "$FXLOCK" "$BAD/"
"$PY" - "$BAD" <<'PYEOF'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
p = d / "macula/SBLGNT/lowfat/18-philemon.xml"
p.write_text(p.read_text(encoding="utf-8").replace('lemma="δέσμιος"', 'lemma="δεσμός"', 1), encoding="utf-8")
lock = json.loads((d / "fixture.lock.json").read_text(encoding="utf-8"))
for f in lock["sources"]["macula-greek"]["files"]:
    f["sha256"] = hashlib.sha256((d / "macula" / f["path"]).read_bytes()).hexdigest()
(d / "fixture.lock.json").write_text(json.dumps(lock, ensure_ascii=False), encoding="utf-8")
PYEOF
cp "$ROOT/tests/fixtures/build-manifest.json" "$BAD/"
set +e; OUT="$("${GBG[@]}" build --check --lock "$BAD/fixture.lock.json" 2>&1)"; RC=$?; set -e
[[ $RC -eq 2 ]] || fail "build --check should exit 2 on changed data (exit $RC, got: $OUT)"
[[ "$OUT" == *"never hand-edit"* ]] || fail "build --check did not print the regenerate hint (got: $OUT)"
pass "a one-lemma change fails --check with exit 2 and a diff"

# --- 4. lint: clean, then one planted violation ------------------------------------
step "[4] lint"
OUT="$("${GBG[@]}" lint --db "$DB" 2>&1)" || fail "lint failed on a clean build (got: $OUT)"
pass "clean build lints clean"
cp "$DB" "$WORK/planted.duckdb"
"$PY" -c "import duckdb,sys; c=duckdb.connect(sys.argv[1]); c.execute(\"UPDATE lemma SET key='x' WHERE id='lemma:θεός'\"); c.close()" "$WORK/planted.duckdb"
set +e; OUT="$("${GBG[@]}" lint --db "$WORK/planted.duckdb" 2>&1)"; RC=$?; set -e
[[ $RC -eq 1 ]] || fail "lint should exit 1 on a planted violation (exit $RC, got: $OUT)"
[[ "$OUT" == *$'lemma\tlemma-key\t'* ]] || fail "lint did not name lemma-key (got: $OUT)"
pass "planted violation: exit 1, FILE<TAB>RULE<TAB>REASON"

# --- 5. no MARBLE data anywhere in the fixture or the build -------------------------
step "[5] licensing"
if grep -rqE ' (domain|ln)="' "$ROOT/tests/fixtures/macula"; then fail "MARBLE attributes in the fixture"; fi
COLS="$("$PY" -c "import duckdb,sys; print(' '.join(r[0] for r in duckdb.connect(sys.argv[1], read_only=True).execute('select column_name from information_schema.columns').fetchall()))" "$DB")"
for c in $COLS; do [[ "$c" != "domain" && "$c" != "ln" ]] || fail "excluded column $c in the build"; done
pass "no Louw-Nida (MARBLE) fields in fixture or build"

step "all smoke checks passed"
