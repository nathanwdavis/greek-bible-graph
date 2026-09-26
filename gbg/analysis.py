"""``gbg analysis``: the checked record of an interpretation.

A thematic question -- "every NT passage about God's knowledge, classified
against my taxonomy" -- ends in a judgement per passage, and a judgement is
not data. auto-zettel-skill keeps interpretation in notes and gates the notes'
citations; this does the same for a whole analysis held in one YAML file, so
that everything a gate *can* check is checked:

* every id exists in this build (a fabricated id is the worst failure);
* every ``cite`` resolves to exactly its ``ids`` (write them with gbg resolve);
* every piece of ``evidence`` sits inside the passage it supports;
* every label is one of the taxonomy's, and subset rules hold
  (``implies: {F: [A]}`` for F ⊆ A: a passage labelled F must carry A);
* every retrieval step reruns to the row count recorded, so the funnel is
  reproducible on this build;
* every candidate a retrieval step names is accounted for -- kept as a passage
  or rejected with a reason. Nothing is dropped silently: the skill's "zero rows
  is a finding" rule, applied to triage.

What no gate can check -- whether a passage is really D rather than merely A --
stays in ``basis`` (what the rows show) and ``reading`` (the interpretation,
labelled as such), for a person to review. `gbg analysis --template` prints
the file format (TEMPLATE below).

Exit codes follow the lint contract: 0 clean, 1 violations
(``FILE\\tRULE\\tREASON``), 2 a file that is not an analysis at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from . import cli, db as dbmod, ids, queries, refs
from .resolve import resolve

#: The format, printed by ``gbg analysis --template``. The example is deliberately
#: unrelated to any eval question, so reading it cannot anchor an answer.
TEMPLATE = """\
# A thematic analysis: gbg analysis FILE --check, then --render --out FILE.md
title: Who loves in 2 and 3 John          # optional
question: Where in 2 and 3 John is the Elder the one who loves?   # the user's words
build: 0bc4e52ebae67568                   # meta.build_id the rows came from (gbg sql envelope)
taxonomy:
  labels:                                 # the user's labels, verbatim, criteria included
    L: love is spoken of
    E: the Elder is the lover
    C: the analyst's own extra label       # say so -- and list it under `added`
  implies: {E: [L]}                       # subset rules: E ⊆ L (optional)
  added: [C]                              # labels the analyst added (optional)
retrieval:                                # every recall step, rerunnable on this build
  - id: love-verbs
    query: predicate_participants         # a saved query ...
    params: {lemmas: ἀγαπάω}
    rows: 19                              # must match on rerun
    candidates: predicate_id              # every verse in this column must be kept or rejected
  - id: known-passages
    sql: SELECT id FROM verse WHERE id IN ('sblgnt:3JN.1.1')   # ... or one SELECT
    rows: 1
    candidates: id
passages:
  - cite: 2 John 1                        # as a reader writes it
    ids: [sblgnt:2JN.1.1]                 # exactly what `gbg resolve` gives for cite
    evidence: [sblgnt:n63001001011]       # words INSIDE the passage the claim rests on
    related: [sblgnt:n63001001002]        # optional: supporting words elsewhere (a referent)
    labels: [E, L]
    basis: ἀγαπῶ has ἐγώ as subject (tree, frame agree), referring to πρεσβύτερος.
    reading: The Elder's own love for the elect lady.   # interpretation, labelled as such
  - cite: 3 John 1
    ids: [sblgnt:3JN.1.1]
    evidence: [sblgnt:n64001001008]
    labels: [E, L]
    basis: ἀγαπῶ with ἐγώ written out; tree and frame both reach πρεσβύτερος.
rejected:
  - cite: 2 John 5
    ids: [sblgnt:2JN.1.5]
    reason: 'we love one another: the community, not the Elder alone.'
blind_spots:
  - Only ἀγαπάω was searched; φιλέω and ἀγάπη were not.
"""

REQUIRED = (("question", str), ("build", str), ("taxonomy", dict), ("retrieval", list),
            ("passages", list))


def load(path: Path) -> dict:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise cli.UsageError(f"no analysis file at {path}") from None
    except yaml.YAMLError as exc:
        raise cli.UsageError(f"{path}: not YAML ({exc})") from None
    if not isinstance(data, dict):
        raise cli.UsageError(f"{path}: an analysis is a mapping (see `gbg analysis --help`)")
    for key, typ in REQUIRED:
        if not isinstance(data.get(key), typ):
            raise cli.UsageError(f"{path}: '{key}' must be a {typ.__name__}")
    labels = data["taxonomy"].get("labels")
    if not isinstance(labels, dict) or not labels:
        raise cli.UsageError(f"{path}: taxonomy.labels must map each label to its meaning")
    for key in ("rejected", "blind_spots"):
        if not isinstance(data.setdefault(key, []) or [], list):
            raise cli.UsageError(f"{path}: '{key}' must be a list")
        data[key] = data[key] or []
    return data


def rerun(root: Path, db: Path, step: dict):
    """A retrieval step's result on the installed build."""
    if "query" in step:
        params = {k: str(v) for k, v in (step.get("params") or {}).items()}
        return queries.run_saved(root, db, str(step["query"]), params, limit=dbmod.MAX_LIMIT)
    if "sql" in step:
        return dbmod.run_query(db, str(step["sql"]), limit=dbmod.MAX_LIMIT)
    raise cli.UsageError("a retrieval step needs 'query' (a saved query) or 'sql'")


def _where(entry: dict, n: int, kind: str) -> str:
    return str(entry.get("cite") or f"{kind} {n}")


def check(path: Path, db: Path, root: Path) -> list[cli.Violation]:
    a = load(path)
    out: list[cli.Violation] = []

    def v(rule: str, reason: str) -> None:
        out.append(cli.Violation(str(path), rule, reason))

    # Rerun the funnel first: the sandbox opens its own connections.
    reruns = []
    for n, step in enumerate(a["retrieval"], 1):
        sid = str(step.get("id") or f"step {n}")
        try:
            reruns.append((sid, step, rerun(root, db, step)))
        except cli.UsageError as exc:
            v("retrieval-invalid", f"{sid}: {exc}")

    con = dbmod.connect(db)
    try:
        build_id, _ = dbmod._meta(con)
        if a["build"] != build_id:
            v("build-stale", f"written against build {a['build']}; the installed build is "
                             f"{build_id} -- rerun the retrieval and recheck every passage")

        def exists(i: str) -> bool:
            table = {"token": "token", "verse": "verse", "book": "book",
                     "lemma": "lemma"}.get(ids.kind_of(i) or "")
            return bool(table) and con.execute(f"SELECT 1 FROM {table} WHERE id = ?",
                                               [i]).fetchone() is not None

        def verse_of(i: str) -> str | None:
            if ids.kind_of(i) == "verse":
                return i
            if ids.kind_of(i) == "token":
                row = con.execute("SELECT verse_id FROM token WHERE id = ?", [i]).fetchone()
                return row[0] if row else None
            return None

        def resolved(cite) -> set[str] | str:
            if not cite:
                return "no cite"
            try:
                res = resolve(con, str(cite))
            except refs.RefError as exc:
                return f"{cite!r} is malformed ({exc})"
            if not res.found:
                return f"{cite!r}: {'; '.join(res.missing)}"
            return set(res.verses)

        labels = set(a["taxonomy"]["labels"])
        implies = a["taxonomy"].get("implies") or {}
        for lab in a["taxonomy"].get("added") or []:
            if lab not in labels:
                v("label-unknown", f"taxonomy.added names {lab!r}, not a taxonomy label")
        for sub, supers in implies.items():
            for lab in [sub, *(supers or [])]:
                if lab not in labels:
                    v("label-unknown", f"taxonomy.implies names {lab!r}, not a taxonomy label")

        covered: set[str] = set()
        for kind, entries in (("passage", a["passages"]), ("rejected", a["rejected"])):
            for n, e in enumerate(entries, 1):
                if not isinstance(e, dict):
                    v("entry-malformed", f"{kind} {n} is not a mapping")
                    continue
                where = _where(e, n, kind)
                own = [str(i) for i in e.get("ids") or []]
                evidence = [str(i) for i in e.get("evidence") or []]
                related = [str(i) for i in e.get("related") or []]
                for i in own + evidence + related:
                    if not exists(i):
                        v("id-fabricated", f"{where}: {i} is not in this build")
                r = resolved(e.get("cite"))
                if isinstance(r, str):
                    v("cite-unresolved", f"{where}: {r}")
                elif set(own) != r:
                    v("cite-mismatch", f"{where}: resolves to {sorted(r)}, the file lists "
                                       f"{sorted(own)} (write ids with gbg resolve)")
                for i in evidence:
                    vid = verse_of(i)
                    if vid is not None and vid not in own:
                        v("evidence-outside", f"{where}: {i} is in {vid}, outside the passage")
                covered |= set(own)
                if kind == "rejected":
                    if not str(e.get("reason") or "").strip():
                        v("reason-missing", f"{where}: a rejection must say why")
                    continue
                if not evidence:
                    v("evidence-missing", f"{where}: cite the words the passage was kept for")
                if not str(e.get("basis") or "").strip():
                    v("basis-missing", f"{where}: say what the rows show")
                mine = [str(x) for x in e.get("labels") or []]
                if not mine:
                    v("label-missing", f"{where}: a kept passage carries at least one label")
                for lab in mine:
                    if lab not in labels:
                        v("label-unknown", f"{where}: {lab!r} is not a taxonomy label")
                    for need in implies.get(lab) or []:
                        if need not in mine:
                            v("label-implies", f"{where}: {lab} implies {need} "
                                               f"({lab} ⊆ {need}), but {need} is missing")

        for sid, step, res in reruns:
            if res.truncated:
                v("retrieval-truncated", f"{sid}: more than {dbmod.MAX_LIMIT} rows; narrow it")
            if step.get("rows") != len(res.rows):
                v("retrieval-drift", f"{sid}: returns {len(res.rows)} rows on this build, "
                                     f"the file records {step.get('rows')!r}")
            col = step.get("candidates")
            if not col:
                continue
            if col not in res.columns:
                v("retrieval-invalid", f"{sid}: no column {col!r} to take candidates from")
                continue
            k = res.columns.index(col)
            verses = {verse_of(str(r[k])) for r in res.rows if r[k] is not None}
            verses.discard(None)
            if not verses:
                v("retrieval-invalid", f"{sid}: column {col!r} holds no token or verse ids")
            missing = sorted(verses - covered, key=lambda x: con.execute(
                "SELECT ord FROM verse WHERE id = ?", [x]).fetchone()[0])
            if missing:
                shown = ", ".join(missing[:20]) + (f" (+{len(missing) - 20} more)"
                                                   if len(missing) > 20 else "")
                v("candidate-unaccounted", f"{sid}: {len(missing)} candidate verse(s) neither "
                                           f"kept nor rejected: {shown}")
    finally:
        con.close()
    return out


def render(path: Path, db: Path, root: Path) -> str:
    """The analysis as a Markdown report: funnel, passages with text, index, rejections."""
    a = load(path)
    labels: dict = a["taxonomy"]["labels"]
    con = dbmod.connect(db)
    try:
        def order(e: dict) -> int:
            got = [str(i) for i in e.get("ids") or []]
            row = con.execute("SELECT min(ord) FROM verse WHERE list_contains(?, id)",
                              [got]).fetchone() if got else None
            return row[0] if row and row[0] is not None else 1 << 30

        passages = sorted(a["passages"], key=order)
        out = [f"# {a.get('title') or 'Analysis'}", "", f"> {a['question']}", "",
               f"Corpus: SBLGNT, build `{a['build']}`. Every passage below cites verse and word "
               "ids from that build; `gbg analysis --check` verified them. What the rows "
               "show is kept apart from the reading placed on them.", "",
               "## Taxonomy", "", "| label | meaning |", "|---|---|"]
        added = set(a["taxonomy"].get("added") or [])
        out += [f"| **{k}** | {' '.join(str(m).split())}"
                + (" *(added by the analyst, not in the question)*" if k in added else "") + " |"
                for k, m in labels.items()]
        for sub, supers in (a["taxonomy"].get("implies") or {}).items():
            out.append(f"\n{sub} ⊆ {', '.join(supers)}: every passage labelled {sub} also "
                       f"carries {', '.join(supers)}.")
        out += ["", "## How the passages were found", "",
                "| step | how | rows |", "|---|---|---|"]
        for n, s in enumerate(a["retrieval"], 1):
            how = (f"saved query `{s['query']}`" + "".join(
                f" {k}={v}" for k, v in (s.get("params") or {}).items())) if "query" in s \
                else f"SQL `{' '.join(str(s.get('sql', '')).split())[:160]}`"
            cand = f" (candidates: `{s['candidates']}`)" if s.get("candidates") else ""
            out.append(f"| {s.get('id') or n} | {how}{cand} | {s.get('rows')} |")
        counts = {k: sum(k in (p.get("labels") or []) for p in passages) for k in labels}
        out += ["", f"{len(passages)} passage(s) kept, {len(a['rejected'])} rejected. By label: "
                + ", ".join(f"{k} {n}" for k, n in counts.items()) + ".", "", "## Passages", ""]
        for p in passages:
            vids = [str(i) for i in p.get("ids") or []]
            out += [f"### {p.get('cite')} — {', '.join(p.get('labels') or [])}", ""]
            for vid, text, eng in con.execute(
                    "SELECT v.id, v.text, (SELECT string_agg(coalesce(t.english, '·'), ' ' "
                    "ORDER BY t.ord) FROM token t WHERE t.verse_id = v.id) "
                    "FROM verse v WHERE list_contains(?, v.id) ORDER BY v.ord", [vids]).fetchall():
                out += [f"> {text}  ", f"> *{eng}* (`{vid}`)", ""]
            out += [f"**The rows show:** {' '.join(str(p.get('basis', '')).split())}", ""]
            if p.get("reading"):
                out += [f"**Reading (interpretation):** {' '.join(str(p['reading']).split())}",
                        ""]
            for name in ("evidence", "related"):
                got = [str(i) for i in p.get(name) or []]
                if got:
                    words = dict((i, f"{r} {w}") for i, r, w in con.execute(
                        "SELECT id, ref, surface FROM token WHERE list_contains(?, id)",
                        [got]).fetchall())
                    out += [f"{name.capitalize()}: " + ", ".join(
                        f"{words.get(i, '')} (`{i}`)".strip() for i in got), ""]
        out += ["## Label index", ""]
        for k in labels:
            cites = [str(p.get("cite")) for p in passages if k in (p.get("labels") or [])]
            out.append(f"- **{k}** ({len(cites)}): {'; '.join(cites) or 'none found'}")
        if a["rejected"]:
            out += ["", "## Candidates rejected", "", "| passage | why |", "|---|---|"]
            out += [f"| {r.get('cite')} | {' '.join(str(r.get('reason', '')).split())} |"
                    for r in sorted(a["rejected"], key=order)]
        if a["blind_spots"]:
            out += ["", "## What this analysis cannot see", ""]
            out += [f"- {' '.join(str(b).split())}" for b in a["blind_spots"]]
        return "\n".join(out) + "\n"
    finally:
        con.close()


def add_arguments(p) -> None:
    cli.add_db(p)
    p.add_argument("file", type=Path, nargs="?", help="analysis YAML (see --template)")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template", action="store_true",
                      help="print the analysis file format, with a worked example")
    mode.add_argument("--check", action="store_true",
                      help="verify ids, cites, evidence, labels and the retrieval funnel")
    mode.add_argument("--render", action="store_true", help="write the analysis as Markdown")
    p.add_argument("--out", type=Path, default=None, help="with --render: write here, not stdout")


def run(args) -> int:
    root, db = cli.root_of(args), cli.db_of(args)
    if args.template:
        sys.stdout.write(TEMPLATE)
        return cli.EXIT_OK
    if args.file is None:
        raise cli.UsageError("an analysis FILE is required with --check and --render")
    if args.check:
        return cli.report(check(args.file, db, root), "gbg analysis --check")
    text = render(args.file, db, root)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return cli.EXIT_OK
