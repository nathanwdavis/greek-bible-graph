---
name: gbg-query
description: Answers questions about the Greek New Testament (SBLGNT) from the greek-bible-graph corpus graph - word occurrences and distributions, morphology, grammatical subjects and objects, who a pronoun refers to, semantic-frame agents and patients, shared wording between passages, and interlinear views - by writing read-only SQL against the built DuckDB graph and citing verse and token ids for every claim. Use when the user asks what the Greek text says or where a Greek word occurs, how often, in what forms, who does what in a passage, what a pronoun refers to, or wants an interlinear. Do not use for theological interpretation beyond what the rows show, for Louw-Nida semantic domains, textual variants or the Septuagint, which this build does not contain.
license: MIT
allowed-tools: Bash, Read
metadata:
  version: 0.1.0
  repo: https://github.com/nathanwdavis/greek-bible-graph
---

# Ask the Greek New Testament

`$ARGUMENTS` is the question. Answer it from the corpus graph and only the
graph: every factual sentence in the answer must rest on rows a query
returned, and cite the ids those rows carry.

Run commands from the greek-bible-graph checkout. `gbg` is its CLI
(`pip install -e .`); if the database is missing, `gbg fetch && gbg build`
(about a minute; downloads ~134 MB once).

## Step 1 -- read the schema, once per session

```sh
gbg schema
```

Read **"Read this first"** before writing any SQL. Two traps catch almost
every first query:

- `has_subject` is **coreference** (who the subject refers to, often in
  another verse), not the grammatical subject. The grammatical subject is the
  clause constituent with `role = 's'`.
- Lemmas match **exactly**, accents included. For accent-free input use
  `lemma_key = gbg_key('...')` and report every lemma that matches.

## Step 2 -- prefer a saved query

```sh
gbg query --list
gbg query lemma_occurrences --param lemma=θεός --param scope="Phlm" --json
```

Saved queries are tested against independently computed answers; a
hand-written query is not. Use one whenever it fits the question.

## Step 3 -- otherwise, write ONE SELECT

```sh
gbg sql --json "SELECT t.id, t.ref, t.surface, ... FROM token t WHERE ..."
```

- Always select `id` (and `ref`, `surface`) for word-level answers, so every
  row is citable. The JSON envelope says whether it is (`citable`).
- The sandbox allows one SELECT only; no files, no writes. A refusal is not a
  bug to work around -- rewrite the query.
- For counts, also keep the SQL: a count is citable as "this query, on build
  `<build_id>`".
- For graph patterns and paths, `gbg sql --pgq` accepts SQL/PGQ
  (`FROM GRAPH_TABLE (gbg_graph MATCH ...)`); plain SQL is always enough.

`gbg resolve "Rom 3:21-26"` turns a reference into verse ids;
`gbg resolve lemma:θεός` gives a lemma's total count in the edition; `gbg ref
"Phlm 2"` shows an interlinear (`--tree` for the syntax).

A word can have more than one referent: `referent_chain` follows the first
at each step, so check `SELECT * FROM refers_to WHERE src = '<id>'` when the
answer depends on the others.

## Step 4 -- answer from the rows

- Cite as `sblgnt:n57001010012` (PHM 1:10!12, Ὀνήσιμον) or `sblgnt:PHM.1.20`.
  Never cite `sblgnt:s:` or `sblgnt:wg:` ids: they are build-local.
- If `truncated` is true, say so and how many rows you saw -- or raise
  `--limit`.
- **Zero rows is a finding.** Say the graph has no such case; do not soften
  it into "rarely".
- Never fill a gap from memory. If the question needs Louw-Nida domains,
  textual variants, the Septuagint, or a passage `gbg resolve` reports as not
  in this edition (exit 1, e.g. Acts 8:37), say that plainly and stop.
- Keep interpretation separate from data: "the rows show X" first, then any
  reading of it, labelled as yours.
