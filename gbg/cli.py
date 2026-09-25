"""Shared CLI plumbing: one ``gbg`` entry point, violations, exit codes.

The contract is auto-zettel-skill's (``scripts/zettel_lib/cli.py``), kept on
purpose so the two repos read alike: every command answers ``--help``, exits 0
on success, 1 when a gate finds violations, 2 on a usage error, and a lint
prints one ``FILE\\tRULE\\tREASON`` line per finding. What is dropped is the
``log.md`` append -- this repo has no content-repo log; a build is idempotent
and its record is ``build-manifest.json``.

Subcommands live in their own modules and are imported here, not discovered:
a command nobody registered is a command that does not exist, and the smoke
test's ``--help`` sweep is what proves the list is complete.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2

#: (subcommand, module, one-line help). Each module defines
#: ``add_arguments(parser)`` and ``run(args) -> int``.
COMMANDS: list[tuple[str, str, str]] = [
    ("fetch", "gbg.sources", "download the pinned upstream files into the cache"),
    ("build", "gbg.store", "build the corpus graph (Parquet + DuckDB) from the pinned sources"),
    ("lint", "gbg.lint", "check the built graph's integrity (FILE\\tRULE\\tREASON)"),
]


class UsageError(Exception):
    """A malformed invocation or input: exit 2, never a traceback."""


@dataclass(frozen=True, order=True)
class Violation:
    """One lint finding, rendered as ``FILE\\tRULE\\tREASON``."""

    file: str
    rule: str
    reason: str

    def render(self) -> str:
        return f"{self.file}\t{self.rule}\t{self.reason}"


def report(violations: list[Violation], tool: str) -> int:
    """Print violations sorted, summarise on stderr, return the exit code."""
    for v in sorted(violations):
        print(v.render())
    if violations:
        print(f"\n{tool}: {len(violations)} violation(s)", file=sys.stderr)
        return EXIT_VIOLATION
    print(f"{tool}: clean")
    return EXIT_OK


def find_root(start: Path | None = None) -> Path:
    """The checkout this command belongs to: the nearest ``sources.lock.json``.

    Falls back to the directory above the installed package, so ``gbg`` works
    from anywhere inside the checkout and from an editable install alike.
    """
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "sources.lock.json").is_file():
            return d
    return Path(__file__).resolve().parent.parent


def add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=None,
                        help="repository checkout (default: nearest dir with sources.lock.json)")


def add_db(parser: argparse.ArgumentParser) -> None:
    add_root(parser)
    parser.add_argument("--db", type=Path, default=None,
                        help="built database (default: <root>/build/gbg.duckdb)")


def root_of(args) -> Path:
    return (args.root or find_root()).resolve()


def db_of(args) -> Path:
    if getattr(args, "db", None):
        return args.db
    return root_of(args) / "build" / "gbg.duckdb"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gbg",
        description="Greek Bible graph: build, check and query the corpus graph.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, module_name, help_text in COMMANDS:
        module = importlib.import_module(module_name)
        p = sub.add_parser(name, help=help_text, description=help_text,
                           formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        module.add_arguments(p)
        p.set_defaults(_run=module.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "_run", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return int(args._run(args) or 0)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except BrokenPipeError:  # `gbg ref ... | head` is not an error
        return EXIT_OK
