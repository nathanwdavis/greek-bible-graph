# Friction log: e2e run on "God's knowledge / knowledge hidden from humans"

Build `a5bc19c489d1460e`. Final `gbg analysis e2e/analysis.yaml --check` returned `clean` (exit 0). The funnel had 274 candidate verses: 145 kept, 129 rejected. Labels: S 16, A 79, P 10, D 18, F 8, H 59 (H is my added label).

Most important items are first.

## Recall holes in `predicate_participants` (the skill's main tool for "God knows")

1. **The `referents` filter works on lemmas, so divine titles are invisible to it.**
   - Command: `predicate_participants lemmas="οἶδα, …" referents="θεός, πατήρ, κύριος, πνεῦμα, υἱός, Ἰησοῦς, Χριστός"`.
   - It returned only Rev 2:19 of the seven "Οἶδά σου τὰ ἔργα" ("I know your works") verses in Rev 2-3.
   - The other six resolve to ὁ κρατῶν (2:1), ὁ πρῶτος (2:8), ὁ ἔχων (2:12, 3:1), ὁ ἅγιος (3:7) and ὁ Ἀμήν (3:14). These are title words, not divine lemmas. `referent_chain` on `sblgnt:n66002001011` stops at κρατῶν.
   - Workaround: an extra unfiltered step, scoped to Rev.
   - The skill's warning says referents over-include (human πατήρ). It says nothing about under-inclusion, which is the more dangerous direction for recall. Titles elsewhere, like "the one who sent me", are probably missed the same way.
2. **The participle εἰδώς is lemmatized under ὁράω, not οἶδα** (they share Strong's G1492).
   - Querying οἶδα therefore misses John 13:1, 13:3, 18:4 ("knowing all that was coming upon him"), 19:28, 6:61, Matt 12:25, Mark 12:15, Luke 9:47 and 11:17. These are some of the central "Jesus knew" texts.
   - I found them only because `lemmas_by_gloss` listed ὁράω at share 0.046 for "know", and I followed the skill's advice to "check its occurrences".
   - There is no saved query for "occurrences of lemma X glossed Y". I hand-wrote `list_has_any(t.english_terms, ['know'])`, which types a stem by hand, the thing the schema says never to do.
   - Suggestions: a `gloss` param on `lemma_occurrences`, or a `gloss_occurrences` query. Also document the εἰδώς/ὁράω split in "Read this first".
   - Related: `similar_lemmas γινώσκω` ranks ὁράω at distance 0.26, as close as οἶδα, purely because of G1492. It looks like a strong synonym ("see ≈ know") but it is an artefact of the Strong's key.
3. **Passive "known by God" is not reached.**
   - Gal 4:9 γνωσθέντες ὑπὸ θεοῦ ("known by God"), 1 Cor 8:3 ἔγνωσται ὑπ᾽ αὐτοῦ ("known by him") and 1 Cor 13:12 ἐπεγνώσθην ("I have been fully known") produce no divine-agent row.
   - The frame on these passives has only A1. There is no signal for a ὑπό + genitive agent.
   - Workaround: a hand-written "all passive knowing verbs" step (16 rows), triaged by eye.
   - Suggestion: an `agent-pp` signal.
4. **`subjref` on passives gives the patient, but the query labels it "agent".**
   - 1 Pet 1:20 προεγνωσμένου: the `subjref` row resolves to Χριστοῦ, the one foreknown, and appears under role=agent.
   - The same happens with Luke 24:35 ἐγνώσθη → Ἰησοῦς.
   - A reader who trusts the column would conclude "Christ foreknew". The query should skip `subjref` for passive-voice predicates when role=agent, or flag voice in the signal.
5. **The `exception` signal missed Rev 19:12** ("ὃ οὐδεὶς οἶδεν εἰ μὴ αὐτός", "which no one knows except himself").
   - The query found the negated οἶδεν (agent οὐδείς) but no exception row.
   - The skill documents only the Luke 10:22 miss. This is a second case, so the note should say "e.g." rather than imply a single known miss.
   - Luke 10:22 itself was missed as the skill predicted. I added it as a known passage.
6. **Rhetorical "who knows?" questions have no signal.**
   - Rom 11:34 and 1 Cor 2:16 (τίς ἔγνω νοῦν κυρίου; "who has known the mind of the Lord?") are strong H texts.
   - The agent is τίς, so the referent filter drops them, and `negated` is false because there is no negator.
   - Added as known passages. A `rhetorical` signal (interrogative τίς as subject) would catch this class.
7. **The genitive signal misses coordinated genitives.**
   - Rom 11:33 (πλούτου καὶ σοφίας καὶ γνώσεως θεοῦ) returns 0 rows for γνῶσις/σοφία even with no referent filter. Eph 3:10 (ἡ πολυποίκιλος σοφία τοῦ θεοῦ) also returns 0.
   - Rom 11:33 was only rescued by the ἀνεξεραύνητος occurrence step.
   - The dist ≤ 2 window is too tight for coordinated noun phrases.
8. **`role=patient` with `referents="ἡμέρα, ὥρα, καιρός, χρόνος"` missed the main "you do not know the day" texts.**
   - It found Matt 25:13 and Acts 1:7, but missed Matt 24:42 (ποίᾳ ἡμέρᾳ) and Mark 13:33 and 13:35 (πότε…), because the object is an indirect-question clause, not a noun.
   - I replaced it with a hand-written proximity SQL (negator within 3 tokens, time word in the verse). That query is cruder but found 20 rows including all of these.
   - This is a whole category (knowledge of *when*) that the participant model cannot express.

## Misleading rows

9. **"Divine" referents that were not God:**
   - Luke 2:49 (πατήρ = Joseph, via 2:48)
   - John 4:53 (the official)
   - Acts 7:40, 1 John 2:13-14 (πατέρες)
   - Eph 6:9, Col 4:1 (κύριοι = human masters)
   - Mark 1:24, Acts 19:15 (unclean spirits)
   - Rev 7:14 (Κύριέ μου said to an elder)
   - Luke 24:18 and John 19:10: σύ/οἶδας addressed to Jesus inside someone else's question, so the "agent" is the addressee of a human question.

   The skill warns about this ("a referent is a word"), and the warning was accurate. Of the 104 divine-knower verses, 13 were referent false positives like these. About 12 more were `implicit` rows whose unexpressed agent was plainly human, such as Rom 7:1 and 2 John 1.
10. **The `negated` flag is loose.**
    - John 8:55 has both negated and affirmed οἶδα rows for the same verse.
    - Matt 11:27!21 is not flagged negated even though its clause is "οὐδὲ … τις ἐπιγινώσκει" ("nor does anyone know").
    - It is a heuristic, as documented, but it cannot be relied on as a filter.

## Analysis format and CLI

11. **`gbg analysis --help` does not contain the format.** It says "format: see the module docstring", so I had to read `gbg/analysis.py`. The format should be in `--help` (the skill says it is "in `gbg analysis --help`").
12. **The docstring example is this very question.** It uses "Which NT passages concern God's knowledge", Rom 8:29 with `labels: [A, F, D]`, and Acts 19:15 rejected. For an evaluation this is an anchoring leak: the reader is shown a model answer, including a contested F on Rom 8:29 (I did not give Rom 8:29 F; the verse has no free-choice language). Use a neutral example.
13. **No structured way to mark an analyst-added label.** I put "[ANALYST'S ADDITION…]" into the label text. A per-label `source: analyst` field, rendered visibly, would help, since the skill tells you to copy the user's taxonomy verbatim.
14. **Evidence must lie inside `ids`, so a referent in a neighbouring verse cannot be cited.** Examples: Rom 8:29 → θεόν at 8:28, Rev 2:2 → κρατῶν at 2:1. I cited the predicate only and named the referent ref in `basis`. The alternative is to widen `cite` (Rom 8:28-29), which blurs which verse is the hit.
15. **Heavy triage burden.**
    - 274 candidates each need a hand entry. Many rejections share a reason ("εἰδώς with a human subject", 12 verses).
    - `rejected` entries are one per verse because `ids` must equal the cite's resolution. Multi-verse cites like "2 Tim 2:23; 2 Tim 3:14" may not be allowed.
    - I generated the YAML from a Python dict. Doing this by hand-editing YAML would be error-prone.
16. **`--check` cannot catch misclassification, and says so.** It found nothing to fix on the first run (my file was generated), so it verified ids and coverage but gave no signal on label quality. A sanity test with a fabricated id did fail correctly (`id-fabricated`).
17. **Render issues:**
    - The retrieval table shows hand-written steps only as "SQL", so a reader of `analysis.md` cannot see what `unknown-times` or `eidos-under-horao` actually did.
    - Evidence renders as bare ids (`sblgnt:n…`) without the surface word.
    - An empty `params` (`contrary_to_fact`) renders with a double space before "(candidates".
    - My own `basis` begins "Rows: …", which reads awkwardly after the renderer's "The rows show:". That one is my doing, not the tool's.
18. **`scope` accepts one passage only.** `--param scope="Rom 11:33; Eph 3:10; 1 Cor 2:7"` gave `Error: scope: cannot read 'Eph3:10'`. That is acceptable, but the message is a confusing way to say "one passage only".
19. **`lemmas_by_gloss` does not report input words that matched nothing.** "omniscient" matched no lemma, and the output does not say so. A "no match: omniscient" line would make the recall step auditable.
20. **Truncation in my own helper script.** I needed verse text for about 270 verse ids. `hits_in_context` gives sentences, not verses, so I wrote `gbg sql` calls. One unfiltered `SELECT … FROM verse` silently hit my `--limit 5000` (7,939 verses) and produced a KeyError later. The JSON did carry `truncated: true`; I did not check it.
    - A saved `verses` query taking a list of ids would help.
    - I first opened the DuckDB file directly (read-only) from a helper script. The project CLAUDE.md says to route every query through `gbg/db.py`, so I switched to `gbg sql`. The skill offers no batch "verse text for these ids" path, which is what pushed me toward the direct connection.

## Data observations

21. **Rom 16:25-27 is not in this build, but Rom 16:24 is.** `gbg resolve "Rom 16:25-27"` exits 1 ("ROM 16:25 is not in this edition"), and `ROM.16.24` exists with "Ἡ χάρις τοῦ κυρίου…". From memory (flagged as such, not from rows): the printed SBLGNT includes 16:25-27 and omits 16:24. That is the reverse of what the build shows. This is worth checking against the pinned upstream, because the doxology ("mystery kept secret for long ages") is a core H passage and cannot be analysed here.
22. The `contrary_to_fact` query worked well: 33 rows, all genuine second-class conditionals. It cannot say whose knowledge a counterfactual belongs to. Only about 10 of 33 are statements a divine speaker makes about non-actual events (P). The rest are human arguments or rebukes, and deciding which is which is pure interpretation.

## Skill guidance gaps

23. **The skill does not say whether Jesus as knower counts as "God knows".** Its referent list includes Ἰησοῦς and Χριστός, which nudges toward including them. I included them and flagged each one ("Treating Jesus' knowledge as God's knowledge is a theological step the rows do not take"). A one-line instruction would make runs comparable.
24. **Step 1 of the funnel gives no guidance on converse vocabulary** (reveal / make known) for an H-type question. I dropped ἀποκαλύπτω, φανερόω and γνωρίζω (about 70 tokens) as "the converse of hiding". Another analyst could reasonably keep them and get a very different H count.
