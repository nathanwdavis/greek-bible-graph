"""``gbg eval``: keep the NL layer honest, in two halves.

CI cannot run Claude, so the eval splits:

* ``--check-goldens`` (runs in CI): every reference query still produces its
  golden. The goldens were established independently of the queries (see
  evals/nl_questions.yaml), so this fails when either the graph or a saved
  query drifts -- not merely when an output changes.
* ``--answers FILE`` (run by hand): score answers Claude gave, question by
  question. The hard failure is a HALLUCINATED id -- one that looks like
  ``sblgnt:n...`` but does not exist in the build -- because a fabricated
  citation is worse than no answer. Beyond that: precision/recall of cited
  ids against the golden, the golden number stated (in digits, or as a number
  word up to twenty -- compound phrases like "one hundred sixteen" are not
  parsed), or a proper refusal: a decline phrase plus the topic, with any
  cited ids real.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from . import cli, db as dbmod, ids, queries

#: A decline must say it cannot answer -- naming the topic alone is not enough
#: ("ἀγάπη is in domain 25.43" names the topic and answers anyway).
DECLINE_MARKERS = ("not in", "can't", "cannot", "can not", "does not contain",
                   "doesn't contain", "not available", "unable", "won't", "will not",
                   "no data", "not include", "doesn't include", "does not include")
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}

ID_RE = re.compile(r"\b(?:sblgnt:(?:n\d{11}|[1-4A-Z][A-Z0-9]{2}(?:\.\d+\.\d+)?)|lemma:[^\s,;)\]`'\"]+)")


def load(root: Path) -> list[dict]:
    data = yaml.safe_load((root / "evals" / "nl_questions.yaml").read_text(encoding="utf-8"))
    return data["questions"]


def db_scope(db: Path) -> str:
    con = dbmod.connect(db)
    try:
        return "nt" if con.execute("SELECT count(*) FROM book").fetchone()[0] == 27 else "fixture"
    finally:
        con.close()


def reference(root: Path, db: Path, q: dict):
    if "query" in q:
        return queries.run_saved(root, db, q["query"], {k: str(v) for k, v in
                                                        (q.get("params") or {}).items()},
                                 limit=dbmod.MAX_LIMIT)
    return dbmod.run_query(db, q["sql"], limit=dbmod.MAX_LIMIT)


def check_golden(res, golden: dict) -> str | None:
    """None if the reference result matches the golden, else a reason."""
    if "rows" in golden:
        return None if len(res.rows) == golden["rows"] else \
            f"{len(res.rows)} rows, golden {golden['rows']}"
    if "value" in golden:
        got = res.rows[0][0] if len(res.rows) == 1 and len(res.rows[0]) == 1 else res.rows
        return None if got == golden["value"] else f"value {got!r}, golden {golden['value']!r}"
    if "ids" in golden:
        found = {v for r in res.rows for v in r if isinstance(v, str) and ids.kind_of(v)}
        missing = set(golden["ids"]) - found
        return None if not missing else f"golden ids not returned: {sorted(missing)}"
    return f"unknown golden {golden}"


def check_goldens(root: Path, db: Path) -> list[cli.Violation]:
    scope = db_scope(db)
    out = []
    for q in load(root):
        if "refusal" in q["golden"] or q["scope"] not in (scope, "any"):
            continue
        why = check_golden(reference(root, db, q), q["golden"])
        if why:
            out.append(cli.Violation(f"evals/{q['id']}", "golden-drift", why))
    return out


def score(root: Path, db: Path, answers: dict[str, str]) -> tuple[list[dict], bool]:
    con = dbmod.connect(db)
    try:
        def exists(i: str) -> bool:
            kind = ids.kind_of(i)
            table = {"token": "token", "verse": "verse", "book": "book", "lemma": "lemma"}.get(kind)
            return bool(table) and bool(
                con.execute(f"SELECT 1 FROM {table} WHERE id = ?", [i]).fetchone())
        rows, hallucinated = [], False
        for q in load(root):
            text = answers.get(q["id"])
            if text is None:
                continue
            cited = sorted(set(ID_RE.findall(text)))
            fake = [c for c in cited if not exists(c)]
            hallucinated |= bool(fake)
            g = q["golden"]
            verdict = ""
            if "ids" in g:
                gold = set(g["ids"])
                hit = gold & set(cited)
                prec = len(hit) / len(cited) if cited else 0.0
                rec = len(hit) / len(gold)
                verdict = f"precision {prec:.2f} recall {rec:.2f}"
                ok = rec == 1.0 and not fake
            elif "rows" in g or "value" in g:
                want = str(g.get("rows", g.get("value")))
                # "1,307" and "1 307" state the same number as "1307"; "Four" states 4.
                # Number words stop at twenty (NUMBER_WORDS) by contract.
                plain = re.sub(r"(?<=\d)[,\u202f\u00a0 ](?=\d{3}\b)", "", text)
                plain = re.sub(r"\b[A-Za-z]+\b", lambda m: str(NUMBER_WORDS.get(
                    m.group(0).lower(), m.group(0))), plain)
                ok = re.search(rf"\b{re.escape(want)}\b", plain) is not None and not fake
                verdict = f"states {want}: {'yes' if ok else 'no'}"
            else:
                # Citing real context (the lemma, the neighbouring verses) while
                # declining is good practice; fabricated ids still fail above.
                low = text.lower()
                ok = (any(m in low for m in DECLINE_MARKERS)
                      and any(w.lower() in low for w in g["refusal"]) and not fake)
                verdict = "declines" if ok else "does not decline cleanly"
            rows.append({"id": q["id"], "ok": ok, "verdict": verdict, "fabricated_ids": fake})
        return rows, hallucinated
    finally:
        con.close()


def add_arguments(p) -> None:
    cli.add_db(p)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-goldens", action="store_true",
                      help="reference queries still produce their goldens")
    mode.add_argument("--answers", type=Path, help="YAML/JSON mapping question id -> answer text")


def run(args) -> int:
    root, db = cli.root_of(args), cli.db_of(args)
    if args.check_goldens:
        return cli.report(check_goldens(root, db), "gbg eval --check-goldens")
    answers = yaml.safe_load(args.answers.read_text(encoding="utf-8")) or {}
    rows, hallucinated = score(root, db, answers)
    for r in rows:
        mark = "ok  " if r["ok"] else "FAIL"
        extra = f"  FABRICATED: {', '.join(r['fabricated_ids'])}" if r["fabricated_ids"] else ""
        print(f"{mark} {r['id']}: {r['verdict']}{extra}")
    passed = sum(r["ok"] for r in rows)
    print(f"\n{passed}/{len(rows)} answered well", file=sys.stderr)
    return cli.EXIT_VIOLATION if hallucinated else cli.EXIT_OK
