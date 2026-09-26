# God's knowledge, and what is hidden from people, in the Greek NT

I searched the SBLGNT corpus graph (build `a5bc19c489d1460e`) and checked each candidate verse by hand. The full record is in `analysis.yaml`, which passes `gbg analysis --check` with no errors. `analysis.md` has the Greek text, a word-by-word English gloss, the evidence, what the rows show and my reading for each verse.

**An extra label.** Your taxonomy has no slot for "knowledge hidden from humans", so I added one: **H**. It is my label, not yours, and it says so in the taxonomy block. I copied your S, A, P, D and F exactly as you wrote them. F ⊆ A is enforced: every F passage also carries A. K = S ∪ A ∪ P needed no separate label.

## How the passages were found

- **Vocabulary.** I looked up English glosses (65 lemmas matched) and Clear's synonym distances. I kept 25 lemmas:
  - Knowing: οἶδα, γινώσκω, ἐπιγινώσκω, ἐπίσταμαι, προγινώσκω, πρόγνωσις, γνῶσις, ἐραυνάω, γνωστός, σοφία, and καρδιογνώστης.
  - Hiding: κρύπτω, ἀποκρύπτω, ἐγκρύπτω, παρακαλύπτομαι, κρυπτός, ἀπόκρυφος, κρυφαῖος, κρυφῇ, μυστήριον, ἀνεξιχνίαστος, ἀνεξεραύνητος, ἀφανής, ἄγνωστος.
  - ὁράω, but only where it is glossed "know". The database files the participle εἰδώς under ὁράω rather than οἶδα.
- **Lemmas I dropped:**
  - Revealing words (ἀποκαλύπτω, φανερόω, γνωρίζω). Revealing is the reverse of hiding.
  - Words mostly about human understanding (συνίημι, νοέω, ἐπίγνωσις, ἀγνοέω).
  - "Search" words with a low share of the gloss (ζητέω and related words).
- **Candidates: 274 verses from 8 retrieval steps:**
  - knowing verbs whose agent resolves to a divine word (104 verses)
  - an unfiltered pass over Revelation (15)
  - passive knowing verbs (16)
  - εἰδώς filed under ὁράω (22)
  - negated "know" near day/hour/time words (20)
  - hiding and mystery words (71)
  - contrary-to-fact conditionals (33)
  - 10 passages I already knew of, added in their own step
- **Result: 145 kept, 129 rejected, each rejection with a reason.**

The 10 passages I added from my own knowledge are flagged in their `basis`: Matt 10:29, 10:30, 26:34; Luke 10:22; John 13:19; Acts 15:18; Rom 11:34; 1 Cor 2:16; 1 Thess 2:4; Heb 4:12. Most use no knowing word, or have an agent the filters cannot reach (τίς, "who?").

## Passages by label

Every classification below is my interpretation. The citable evidence for each one, such as `sblgnt:n45008029003` (προέγνω, Rom 8:29), is in `analysis.md`.

- **S — God knows himself (16):**
  - Matt 11:27 and Luke 10:22: only the Father knows the Son, and only the Son knows the Father.
  - 1 Cor 2:10-11: the Spirit searches "the depths of God"; no one knows the things of God except the Spirit of God.
  - Rom 8:27; John 7:29, 8:55, 10:15, 17:25; Rev 19:12: a name "no one knows except himself".
  - Also John 5:32, 6:6, 8:14, 11:42, 12:50, 13:3.
- **A — God knows all things actual (79):**
  - Broad claims: 1 John 3:20 (γινώσκει πάντα, "knows all things"); Heb 4:13 (no creature ἀφανής, "hidden", before him); John 16:30 and 21:17 ("you know all things").
  - Hearts and thoughts: Luke 16:15; Acts 1:24 and 15:8 (καρδιογνώστης, "heart-knower"); Rom 8:27; 1 Cor 3:20; 1 Thess 2:4.
  - Needs before they are asked: Matt 6:8, 6:32; Luke 12:30. Secret acts: Matt 6:4, 6:6, 6:18.
  - Foreknowledge: Rom 8:29, 11:2; 1 Pet 1:2, 1:20; Acts 2:23.
  - Oaths ("God knows"): 2 Cor 11:11, 11:31, 12:2-3.
  - The risen Christ's "I know your works": Rev 2:2, 2:9, 2:13, 2:19, 3:1, 3:8, 3:15.
  - Many Gospel verses where Jesus knows people's thoughts: Mark 2:8, Luke 5:22, John 2:24-25, and others.
- **P — God knows things possible but never actual (10):**
  - Matt 11:21, 11:23 and Luke 10:13: Tyre, Sidon and Sodom would have repented or remained.
  - Matt 24:22 and Mark 13:20: had the days not been shortened, no one would be saved.
  - Rom 9:29 ("we would have become like Sodom"); 1 Cor 2:8 (the rulers would not have crucified him).
  - Matt 12:7, John 4:10 and John 18:36: what people would have done.
- **D — God ordains (18):**
  - Acts 2:23 (ὡρισμένῃ βουλῇ, "fixed plan"); Rom 8:29 (προώρισεν, "predestined"); 1 Cor 2:7; Eph 1:9 (προέθετο, "purposed beforehand").
  - Acts 1:7: times the Father "set" (ἔθετο).
  - Matt 11:25 and Luke 10:21: God's decision to hide and reveal.
  - Matt 13:11, Mark 4:11, Luke 8:10: δέδοται ("it has been given"), read as God's giving.
  - Also 1 Pet 1:2, 1:20; Rom 9:29; Matt 24:22; Mark 13:20; John 13:18; Col 1:27; Rev 10:7.
  - I left out passages where God only knows or permits something, as you specified.
- **F — people's future free choices (8), all also A:**
  - Matt 26:34 (Peter's denial).
  - John 6:64, 13:11, 13:18, 13:19 (the betrayer known beforehand).
  - John 6:15 and 18:4, where F is a weaker reading.
  - Acts 2:23: foreknowledge and a fixed plan, of an act done by lawless men.
  - John 13:18 and Acts 2:23 carry both F and D. The verses put the two side by side without saying how they relate, which is exactly the point in dispute.
- **H — knowledge hidden from humans (my addition, 59):**
  - The day and hour: Matt 24:36, 24:42, 25:13; Mark 13:32-35; Acts 1:7; Rev 3:3.
  - Things God hid: Matt 11:25; Luke 9:45, 18:34, 19:42.
  - Mysteries hidden for ages: 1 Cor 2:7; Eph 3:9; Col 1:26; Rom 11:25.
  - Beyond searching out: Rom 11:33-34 (ἀνεξεραύνητα, "unsearchable"); 1 Cor 2:11, 2:16; Eph 3:8.
  - Hidden now, disclosed later: Matt 10:26; Mark 4:22; Luke 8:17, 12:2; 1 Cor 4:5, 13:12.

## Rejected candidates

Three kinds of candidate came up often and were rejected:

- **The divine word did not mean God.** πατήρ was "your father" (Joseph, the official in John 4:53) or "our fathers". κύριοι were human masters (Eph 6:9, Col 4:1). πνεῦμα was an unclean spirit (Mark 1:24, Acts 19:15). In Rev 7:14, John's "my lord" is said to an elder.
- **The knower was an ordinary person.** Most εἰδώς participles have human subjects.
- **The word "hide" meant physical hiding.** Examples are the parables of treasure and leaven, and Jesus slipping away in John 8:59.

## What this analysis cannot see

- **No semantic domains.** Louw-Nida is not in this build, so a passage about God's knowledge that uses none of the searched words is found only if I added it myself. Predictions phrased without a knowing word are the main gap.
- **The analysis matches words, not persons.** The divine filter caught human "fathers" and "lords". It missed divine titles such as ὁ κρατῶν ("the one who holds") and ὁ Ἀμήν ("the Amen"): in Revelation I had to recover these by hand, and similar titles elsewhere may still be missing.
- **Some grammar is missed.** Contrary-to-fact detection misses elided or mixed conditionals, so the P list may be incomplete. Rhetorical "who has known…?" questions and "known by God" passives needed their own steps.
- **Jesus as God.** Treating Jesus' knowledge (and the risen Christ's in Rev 2–3) as God's knowledge is a theological step. Each such passage says so in its reading.
- **No Old Testament.** The Septuagint is not in this build, and your taxonomy leans on OT texts I could not check or quote:
  - P: 1 Sam 23:11-13 (David at Keilah)
  - A and S: Ps 139, Ps 147:5, Isa 40:28
  - D: Isa 46:9-10
  - H: Deut 29:29
- **Missing and variant text.** Rom 16:25-27 (the doxology about the mystery "kept secret for long ages") is not in this edition, and textual variants are not in this build.
