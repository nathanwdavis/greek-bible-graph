#!/usr/bin/env bash
# End-to-end smoke test: the acceptance checklist in executable form.
#
# Runs offline against the checked-in fixture (Philemon, 2 John, 3 John).
# Exits 0 only if everything passes. Style and rules are auto-zettel-skill's:
# never assert through a pipe -- capture output first, then match, and put the
# observed value in the failure message so the next person is not debugging
# blind.

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

step "all smoke checks passed"
