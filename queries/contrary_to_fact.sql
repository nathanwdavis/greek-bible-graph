-- name: contrary_to_fact
-- description: Contrary-to-fact ("second class") conditionals: "if X had happened, Y would have"
-- description: -- what could have happened but did not. The protasis is an adverbial clause
-- description: introduced by εἰ whose verb is an aorist, imperfect or pluperfect indicative; the
-- description: clause it modifies has ἄν outside the protasis. Known misses: an elided
-- description: protasis (Jn 14:2 εἰ δὲ μή, εἶπον ἄν), apodoses without ἄν, and mixed
-- description: conditionals with a present protasis (Lk 17:6). One row per
-- description: conditional, with the words that qualified it.
-- param: scope passage optional -- limit to a passage (applied to εἰ)
-- cites: token
WITH prot AS (
    SELECT a.id AS protasis, a.parent_wg AS apodosis, ei.id AS ei_id, ei.ord AS ei_ord
    FROM wg a
    JOIN token ei ON ei.parent_wg = a.id AND ei.lemma = 'εἰ'
    -- upstream leaves some protases without a role (Jn 4:10, Rom 9:29)
    WHERE (a.role = 'adv' OR a.role IS NULL)
      AND ei.ord BETWEEN $scope_first AND $scope_last
),
qualified AS (
    SELECT p.protasis, p.apodosis, p.ei_id, p.ei_ord,
           (SELECT arg_min(v.id, v.ord) FROM dominance d JOIN token v ON v.id = d.token_id
            WHERE d.wg_id = p.protasis AND v.mood = 'indicative'
              AND v.tense IN ('aorist', 'imperfect', 'pluperfect')) AS protasis_verb,
           (SELECT arg_min(an.id, an.ord) FROM dominance d JOIN token an ON an.id = d.token_id
            WHERE d.wg_id = p.apodosis AND an.lemma = 'ἄν'
              AND an.id NOT IN (SELECT token_id FROM dominance WHERE wg_id = p.protasis))
               AS an_id
    FROM prot p
)
SELECT q.ei_id, e.ref AS ei_ref, e.verse_id,
       q.protasis_verb AS protasis_verb_id, pv.surface AS protasis_verb, pv.morph AS protasis_morph,
       q.an_id, an.ref AS an_ref, s.text AS sentence
FROM qualified q
JOIN token e ON e.id = q.ei_id
JOIN token pv ON pv.id = q.protasis_verb
JOIN token an ON an.id = q.an_id
JOIN sentence s ON s.id = e.sentence_id
ORDER BY q.ei_ord
