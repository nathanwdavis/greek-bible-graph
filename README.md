# greek-bible-graph

The Greek New Testament as a queryable corpus graph. The SBL Greek New
Testament and MACULA Greek's morphology, glosses, syntax trees, semantic frames,
coreference and synonym distances are built into DuckDB + Parquet. You query it with SQL, with
SQL/PGQ graph patterns, or in plain English through a Claude Code skill that
cites a verse or word id for every claim.

It is a sibling of [auto-zettel-skill](https://github.com/nathanwdavis/auto-zettel-skill).
That repo's citation-grounded notes are designed to cite this graph's ids.
**Why this is a separate substrate** — which of auto-zettel-skill's techniques
carry over and which had to be replaced — is in [`docs/DESIGN.md`](docs/DESIGN.md).

**Status:** prototype, New Testament only. The Septuagint is designed
(`docs/DESIGN.md` §8) but not built.

## Quickstart

```sh
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/gbg fetch        # pinned upstream, ~134 MB, sha256-verified, cached
.venv/bin/gbg build        # ~30 s: 137,741 words, 7,939 verses, 8,010 sentences
.venv/bin/gbg lint         # integrity gate, ~1 s
```

The rest of this README writes `gbg` for `.venv/bin/gbg`. If `gbg fetch` fails
with `CERTIFICATE_VERIFY_FAILED` (a python.org Python on macOS has no CA bundle),
run it as `SSL_CERT_FILE=/etc/ssl/cert.pem gbg fetch`.

```text
$ gbg ref "Phlm 2"
PHM 1:2  (sblgnt:PHM.1.2)
καὶ   Ἀπφίᾳ      τῇ     ἀδελφῇ  καὶ   Ἀρχίππῳ       τῷ     συστρατιώτῃ     ἡμῶν   καὶ
καί   Ἀπφία      ὁ      ἀδελφή  καί   Ἄρχιππος      ὁ      συστρατιώτης    ἐγώ    καί
CONJ  N-DSF      T-DSF  N-DSF   CONJ  N-DSM         T-DSM  N-DSM           P-1GP  CONJ
and   to Apphia  our    sister  and   to Archippus  the    fellow soldier  of us  and
...

$ gbg query referent_chain --param "token=PHM 1:12!4"
step  id                   ref         surface   lemma     gloss
0     sblgnt:n57001012004  PHM 1:12!4  αὐτόν     αὐτός     in person
1     sblgnt:n57001010012  PHM 1:10!12 Ὀνήσιμον  Ὀνήσιμος  Onesimus

$ gbg sql "SELECT gcase, count(*) FROM token WHERE lemma = 'θεός' GROUP BY 1 ORDER BY 2 DESC"

$ gbg sql --pgq "FROM GRAPH_TABLE (gbg_graph
    MATCH (v:token)-[f:frame_arg]->(a:token)
    WHERE v.lemma = 'ἀγαπάω' AND f.arg_role = 'A0'
    COLUMNS (v.ref, a.surface AS lover))"
```

## Commands

| command | what it does |
|---|---|
| `gbg fetch [--offline] [--update --source S]` | download or verify the pinned sources, or re-pin them |
| `gbg build [--check \| --record]` | build; `--check` rebuilds and diffs against the committed manifest (exit 2 on any change) |
| `gbg lint` | 20 integrity rules, `FILE\tRULE\tREASON`, exit 1 on findings |
| `gbg schema [--static \| --write \| --check]` | the schema doc, pitfalls first, with live enum values |
| `gbg ref PASSAGE [--tree \| --tsv \| --json]` | interlinear, syntax trees, or rows with ids |
| `gbg resolve REF [--json]` | reference ↔ ids; exit 0 found, 1 not in this edition, 2 malformed |
| `gbg sql "SELECT…" [--json] [--pgq]` | one read-only SELECT, sandboxed (no files, no writes, timeout, row cap) |
| `gbg query [--list] NAME --param k=v` | 10 saved queries with typed parameters; `--pgq` for SQL/PGQ twins |
| `gbg eval --check-goldens \| --answers F` | the natural-language eval harness |

## Asking in plain English

`skills/gbg-query/` is a Claude Code skill. Link it into your skills directory:

```sh
ln -s "$PWD/skills/gbg-query" ~/.claude/skills/gbg-query
```

Then ask questions like "In Philemon 12, who is αὐτόν?", "Which verbs in
Philemon have ἐγώ as their grammatical subject?" or "Which Greek words mean
knowing or hiding?" -- concept questions go through the open glosses
(`lemmas_by_gloss`) and Clear's synonym distances (`similar_lemmas`), since
the semantic domains are not openly licensed. The skill reads the schema,
prefers saved queries, cites a row id for every claim, and declines what the
build does not contain: Louw–Nida domains, textual variants, and the LXX.
`evals/runs/` records its first end-to-end run: 5/5 answered, with no fabricated ids.

## Development

```sh
.venv/bin/python -m pytest -q          # offline: builds a 798-word fixture
.venv/bin/python -m pytest -m network  # the full NT from pinned upstream
./smoke_test.sh                        # the acceptance checklist; exit 0 or it isn't done
```

Generated files are never edited by hand: `build-manifest.json`,
`tests/fixtures/`, `docs/SCHEMA.md`. Regenerate them with the tool that owns
them. See `.claude/CLAUDE.md`.

## Data and licenses

The code is MIT. The data is licensed by its owners and checked **per field**:
the SBLGNT text is CC BY 4.0, MACULA's annotations are CC BY 4.0, the Berean
glosses are public domain, the Cherith glosses are CC BY 4.0, and Clear's synonym
proximities (part of MACULA) are CC BY 4.0. MACULA's
Louw–Nida domains (UBS MARBLE, "used with permission") are excluded from the
build, the fixtures and every artifact. See [`NOTICE.md`](NOTICE.md).
