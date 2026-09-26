"""Pinned upstream sources: the lock, the cache, and the license gate.

This is auto-zettel-skill's ``raw/`` discipline, adapted. There, a capture is
immutable and a reference counts as verified only if the capture exists or a
registry confirmed it. Here, every input is pinned by *commit and sha256* in
``sources.lock.json``, downloaded from a SHA-pinned URL into
``cache/<source>/<commit>/<path>``, and written only after its hash verifies
-- to a temporary name first, so an interrupted download can never look like
a valid one. Upstream bytes are never modified; the build reads, never writes,
the cache.

Two details forced by the environment. There is no directory listing (the
GitHub API answers 403 from the cloud sandbox), so the lock enumerates every
file. And ``git ls-remote`` does work, so ``--update`` uses it to find the new
commit rather than the API.

The license gate lives here too, at two levels:

* a *source* whose headline license is not open is refused before download;
* a *component* (a set of fields) whose license is not open is allowed in the
  lock -- declaring it is how its fields get excluded. :meth:`Lock.excluded_fields`
  derives the exclusion list from the licenses; nobody maintains it by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import cli, licenses
from .http import NetworkUnavailable, Transport, urllib_transport


class LockError(cli.UsageError):
    pass


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class Component:
    name: str
    fields: tuple[str, ...]
    license: str
    attribution: str


@dataclass(frozen=True)
class Source:
    name: str
    repo: str
    raw_url: str            # with {commit} and {path} placeholders
    commit: str
    license: str
    attribution: str
    files: tuple[SourceFile, ...]
    components: tuple[Component, ...]
    #: For a fixture lock: the directory (relative to the lock) holding the
    #: files, and how they were derived. None for a real, cached source.
    local_dir: str | None = None
    derived: dict | None = None

    def component_of(self, field_name: str) -> Component | None:
        for c in self.components:
            if field_name in c.fields:
                return c
        return None

    def excluded_fields(self) -> frozenset[str]:
        """Fields whose component license is not open: dropped at parse time."""
        return frozenset(f for c in self.components if not licenses.is_open(c.license)
                         for f in c.fields)


@dataclass(frozen=True)
class Lock:
    path: Path
    sources: dict[str, Source] = field(default_factory=dict)

    def source(self, name: str) -> Source:
        try:
            return self.sources[name]
        except KeyError:
            raise LockError(f"{self.path}: no source named {name!r}") from None

    def source_dir(self, name: str, root: Path) -> Path:
        """Where the build reads this source's files from."""
        src = self.source(name)
        if src.local_dir is not None:
            return (self.path.parent / src.local_dir).resolve()
        return root / "cache" / src.name / src.commit


def load_lock(path: Path) -> Lock:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LockError(f"lock file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise LockError(f"{path}: not JSON ({exc})") from None
    sources = {}
    for name, s in (data.get("sources") or {}).items():
        try:
            sources[name] = Source(
                name=name, repo=s["repo"], raw_url=s["raw_url"], commit=s["commit"],
                license=s["license"], attribution=s["attribution"],
                files=tuple(SourceFile(f["path"], f["sha256"], int(f["bytes"]))
                            for f in s["files"]),
                components=tuple(Component(cn, tuple(c["fields"]), c["license"],
                                           c["attribution"])
                                 for cn, c in s["components"].items()),
                local_dir=s.get("local_dir"), derived=s.get("derived"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LockError(f"{path}: source {name!r} is malformed ({exc!r})") from None
    if not sources:
        raise LockError(f"{path}: no sources")
    return Lock(Path(path), sources)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_files(lock: Lock, name: str, root: Path) -> list[str]:
    """Problems with the files the build is about to read; empty means clean."""
    src = lock.source(name)
    base = lock.source_dir(name, root)
    problems = []
    for f in src.files:
        p = base / f.path
        if not p.is_file():
            problems.append(f"{p}: missing (run `gbg fetch`)")
        elif sha256_file(p) != f.sha256:
            problems.append(f"{p}: sha256 does not match the lock")
    return problems


def fetch(lock: Lock, root: Path, *, only: str | None = None,
          transport: Transport = urllib_transport, offline: bool = False,
          log=print) -> list[str]:
    """Bring the cache up to the lock. Returns problems (empty = all verified)."""
    problems: list[str] = []
    for src in lock.sources.values():
        if only and src.name != only:
            continue
        if src.local_dir is not None:
            problems += verify_files(lock, src.name, root)
            continue
        if not licenses.is_open(src.license):
            problems.append(f"{src.name}: license {src.license!r} is not open; refusing to fetch")
            continue
        base = lock.source_dir(src.name, root)
        for f in src.files:
            target = base / f.path
            if target.is_file() and sha256_file(target) == f.sha256:
                log(f"cached   {src.name}/{f.path}")
                continue
            if offline:
                problems.append(f"{target}: not cached (offline)")
                continue
            url = src.raw_url.format(commit=src.commit, path=f.path)
            try:
                resp = transport(url)
            except NetworkUnavailable as exc:
                problems.append(f"{url}: {exc}")
                continue
            if resp.status != 200:
                problems.append(f"{url}: HTTP {resp.status}")
                continue
            digest = hashlib.sha256(resp.content).hexdigest()
            if digest != f.sha256:
                problems.append(f"{url}: sha256 {digest[:12]}... does not match the lock "
                                f"({f.sha256[:12]}...); not written")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            tmp.write_bytes(resp.content)
            os.replace(tmp, target)
            log(f"fetched  {src.name}/{f.path} ({len(resp.content)} bytes)")
    return problems


def ls_remote_head(repo: str) -> str:
    out = subprocess.run(["git", "ls-remote", repo, "HEAD"], capture_output=True,
                         text=True, timeout=60)
    if out.returncode != 0 or not out.stdout.strip():
        raise LockError(f"git ls-remote {repo} failed: {out.stderr.strip()}")
    return out.stdout.split()[0]


def update(lock_path: Path, name: str, root: Path, *, commit: str | None = None,
           transport: Transport = urllib_transport, log=print) -> None:
    """Re-pin a source to ``commit`` (default: upstream HEAD) and rewrite its hashes.

    Only ``commit``, ``sha256`` and ``bytes`` change -- the file list, the
    components and their licenses are curated, and an upstream relicensing is
    exactly the kind of change that must be made by a person, in a diff.
    """
    data = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    s = data["sources"][name]
    if s.get("local_dir"):
        # A vendored snapshot (OpenBible regenerates its data weekly, with no
        # history) is re-pinned by committing a new dated copy, in a reviewed diff.
        raise LockError(f"{name} is vendored in {s['local_dir']}; re-pin it by committing "
                        "a new snapshot, not with --update")
    new = commit or ls_remote_head(s["repo"])
    for f in s["files"]:
        url = s["raw_url"].format(commit=new, path=f["path"])
        resp = transport(url)
        if resp.status != 200:
            raise LockError(f"{url}: HTTP {resp.status}")
        f["sha256"] = hashlib.sha256(resp.content).hexdigest()
        f["bytes"] = len(resp.content)
        target = root / "cache" / name / new / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(resp.content)
        os.replace(tmp, target)
        log(f"pinned   {name}/{f['path']} @ {new[:12]}")
    s["commit"] = new
    Path(lock_path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")


# --- CLI ----------------------------------------------------------------------

def add_arguments(p) -> None:
    cli.add_root(p)
    p.add_argument("--lock", type=Path, default=None,
                   help="lock file (default: <root>/sources.lock.json)")
    p.add_argument("--source", default=None, help="only this source")
    p.add_argument("--offline", action="store_true",
                   help="verify the cache without downloading")
    p.add_argument("--update", action="store_true",
                   help="re-pin --source to upstream HEAD (or --commit) and rewrite its hashes")
    p.add_argument("--commit", default=None, help="with --update: pin this commit")


def run(args) -> int:
    root = cli.root_of(args)
    lock_path = args.lock or root / "sources.lock.json"
    if args.update:
        if not args.source:
            raise cli.UsageError("--update needs --source")
        update(lock_path, args.source, root, commit=args.commit)
    problems = fetch(load_lock(lock_path), root, only=args.source, offline=args.offline)
    for p in problems:
        print(f"error: {p}")
    return cli.EXIT_VIOLATION if problems else cli.EXIT_OK
