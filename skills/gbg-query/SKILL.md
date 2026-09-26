---
name: gbg-query
description: Answers questions about the Greek New Testament (SBLGNT) from the greek-bible-graph corpus graph - word occurrences and distributions, morphology, grammatical subjects and objects, who a pronoun refers to, semantic-frame agents and patients, shared wording between passages, which Greek words express an English concept, interlinear views, and thematic questions (every passage about a topic, optionally classified against a taxonomy the user supplies, recorded and checked with gbg analysis) - by writing read-only SQL against the built DuckDB graph and citing verse and token ids for every claim. Use when the user asks what the Greek text says, where or how often a word occurs, who does what in a passage, what a pronoun refers to, which passages concern a theme, or wants an interlinear. Interpretation is allowed only labelled and kept apart from what the rows show. Not for Louw-Nida semantic domains, textual variants or the Septuagint, which this build does not contain.
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

- `has_subject` is **coreference, mostly for unexpressed subjects** (who an
  implied subject refers to, often in another verse), not the grammatical
  subject. It is rarely present when the subject is written out (ἐγώ,
  Παῦλος), but not never -- keep every row it returns. The grammatical subject
  is the clause constituent with `role = 's'`; follow `refers_to` from it when
  it is a pronoun. "Every verb whose subject is X" needs both.
- Lemmas match **exactly**, accents included. For accent-free input use
  `lemma_key = gbg_key('...')` and report every lemma that matches.

## Step 2 -- prefer a saved query

```sh
gbg query --list
gbg query lemma_occurrences --param lemma=θεός --param scope="Phlm" --json
```

Saved queries are tested against independently computed answers; a
hand-written query is not. Use one whenever it fits the question.

**Which Greek words express a concept?** There are no semantic domains, so use
both open meaning layers and say which one found each word:

```sh
gbg query lemmas_by_gloss --param words="know, knowledge, hide"   # translator glosses
gbg query similar_lemmas --param lemma=γινώσκω                     # Clear synonym distance
```

Type plain English (knew/known/knowing all match `know`); name derivations
separately (`knowledge`). A low `share` means the lemma only sometimes carries
the concept -- check its occurrences before counting all of them. Glosses miss
what a translator worded differently (ἀγαπητός is "beloved", not "love");
proximity catches some of that. Neither finds a passage that is about a concept
without using a word for it -- say so.

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

## Thematic questions -- find, filter, classify

"Find every passage about X (and classify each against my taxonomy)" is a
funnel, not one query. Each step is a recorded retrieval, so the answer's
recall can be rerun and checked. Work through it in order:

1. **Vocabulary.** `lemmas_by_gloss` with the concept's English words,
   derivations and near-synonyms (know, knowledge, foreknow; hide, hidden,
   secret, mystery, reveal), then `similar_lemmas` on the central lemmas. Keep
   a lemma only after looking at its `glosses` and `share`; note why you
   dropped the rest.
2. **Participants.** When the theme has a subject ("God knows", "hidden from
   people"), run `predicate_participants` with those lemmas and a `referents`
   filter (θεός, πατήρ, κύριος, πνεῦμα, υἱός, Ἰησοῦς, Χριστός as the
   question needs). Read every signal. `exception` finds "no one knows ...
   except the Father". `negated` finds "no one knows". `implicit` rows are
   unexpressed agents, often divine passives. `genitive` catches nouns
   (πρόγνωσις θεοῦ). Use `role=patient` for "hidden from whom".
3. **Constructions.** Some categories are grammar, not words: things that
   could have happened but did not are `contrary_to_fact`.
4. **Plain occurrences** (`lemma_occurrences`) for nouns and adjectives where
   the agent is not the point (μυστήριον, ἀνεξιχνίαστος).
5. **Context.** `hits_in_context --param tokens=...` with the candidate ids,
   and `gbg ref` for anything unclear. A referent is a **word**, not a person:
   πνεῦμα may be an unclean spirit (Acts 19:15), πατήρ "our fathers" (Acts
   7:40), κύριοι human masters (Eph 6:9). Upstream bracketing can hide a
   participant (Luke 10:22), so read the context of every negated predicate.
6. **Passages you already know** that the funnel missed may be added, but only
   through their own retrieval step (an SQL selecting those verse ids, with
   `id: known-passages`), and say so in `basis`. That keeps the funnel's recall
   honest.

**Record the answer as an analysis file** and check it until it is clean. The
format is in `gbg analysis --help` and in `gbg/analysis.py`.

- Copy the user's taxonomy verbatim into `taxonomy.labels`, criteria included
  ("knowing or allowing is not enough for D"). Turn subset statements (F ⊆ A)
  into `implies: {F: [A]}`. A union (K = S ∪ A ∪ P) needs no rule.
- Record each step in `retrieval`, with its `rows`. For steps whose hits must
  all be triaged, add `candidates: <id column>`.
- Every candidate verse is either a **passage**, with `labels`, `evidence`
  (token ids from the rows), `basis` (what the rows show) and `reading` (your
  interpretation), or a **rejected** entry with a `reason`. Write `ids` with
  `gbg resolve`.

```sh
gbg analysis answer.yaml --check                 # exit 0 or it is not done
gbg analysis answer.yaml --render --out answer.md
```

In the reply, give the funnel counts (lemmas, candidates, kept, rejected), the
passages by label, and **what the analysis cannot see**: no semantic domains;
passages about the theme that use none of its words; referents are words, not
entities; and the Septuagint is absent. Name the Old Testament texts the
question needs (for "possible but not actual", 1 Sam 23:11-13) instead of
quoting them. Classifying is interpretation: give the rows first, then the
reading, labelled as yours.
