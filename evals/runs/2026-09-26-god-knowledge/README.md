# End-to-end run: God's knowledge, and knowledge hidden from people

An independent Claude agent answered the question below with only
`skills/gbg-query/SKILL.md` and the `gbg` CLI. It had no access to `evals/`,
`tests/` or `docs/DESIGN.md`, and ran against the full-NT build
`a5bc19c489d1460e` (the first version of the thematic workflow, commit
`6930d06`).

> Find all passages in the NT that pertain to God's knowledge and what
> knowledge is hidden from humans. Then create a description of each using the
> following set taxonomy: S (God knows himself), A (all things actual),
> P (all things possible), D (the things God ordains), F (people's future free
> choices; F ⊆ A).

Files:

- `analysis.yaml`: the agent's analysis. It passed `gbg analysis --check` on
  that build. After the fixes below its retrieval row counts no longer match,
  so it is a record, not a live gate.
- `reply.md`: the reply it would give.
- `notes.md`: its friction log, the main output of the run.

It found 274 candidate verses in 8 retrieval steps and kept 145 (S 16, A 79,
P 10, D 18, F 8). It also used H 59, an added label for hidden knowledge,
marked as the agent's own. The other 129 were rejected, each with a reason.

## Scores (`gbg eval --answers`, question `god-knowledge`, Nave's golden)

| answer text scored | recall | result |
|---|---|---|
| the rendered analysis (`gbg analysis --render`) | 0.81 | ok (minimum 0.5) |
| `reply.md` alone | 0.03 | FAIL: the reply names passages but cites 1 id |

No ids were fabricated.

## Acted on in the same PR

- `predicate_participants`:
  - Voice now decides the role. A passive's subject is its patient, so 1 Pet
    1:20's "foreknown" Christ no longer shows as the knower.
  - "Passive" means Robinson voice letter P, so deponents such as ἀπεκρίθη
    stay active.
  - A new `by` signal reads the ὑπό agent (1 Cor 8:3, Gal 4:9).
  - `exception` now takes a lone-word subject (Rev 19:12).
  - A new `question` flag catches rhetorical "who has known ...?" (Rom 11:34).
  - A new `words` filter takes one sense of a lemma (ὁράω + know = εἰδώς).
- New saved query `verse_texts` with a `verses` parameter type, so a batch
  read never needs a direct database connection.
- `gbg analysis`:
  - `--template` prints the format.
  - The worked example is now unrelated to any eval; the old docstring example
    was this very question, which anchored the answer.
  - `taxonomy.added` marks analyst labels.
  - `related` ids can lie outside the passage.
  - The render shows SQL steps and evidence words.
- The skill now covers: divine titles missed by the `referents` filter, εἰδώς
  filed under ὁράω, Jesus as knower (decide and say), revealing vocabulary as
  the counterpart of hiding, coordinated genitives, knowledge of *when*,
  multi-verse rejections, and that **the reply must cite every passage's
  verse id**.

## Recorded, not changed

- **Rom 16:25-27 is absent; Rom 16:24 is present.** The absence is upstream
  and consistent. MACULA's SBLGNT TSV and trees have no doxology, and neither
  does the Logos SBLGNT XML that MACULA builds from
  (`sources/LogosBible/SBLGNT/data/sblgnt/xml/Rom.xml` at the pinned commit
  ends at 16:24). The agent recalled the printed edition differently. That
  would need checking against the printed text; the build faithfully
  reproduces its source.
- `contrary_to_fact` found 33 genuine conditionals, but deciding which are
  statements about God's knowledge of the non-actual (P) is interpretation.
- The triage burden is real: 274 hand entries. Multi-verse rejections now
  lighten it, but a rejection is still a judgement per verse.
