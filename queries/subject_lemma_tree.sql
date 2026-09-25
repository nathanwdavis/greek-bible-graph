-- name: subject_lemma_tree
-- description: Verbs whose SYNTACTIC subject (the clause constituent with role 's')
-- description: contains the lemma in the nominative. Compare subject_lemma_subjref,
-- description: which follows coreference instead and answers a different question.
-- param: lemma lemma -- e.g. θεός, ἐγώ
-- param: scope passage optional -- limit to a passage
-- cites: token
WITH subj AS (
    -- a word group with role 's', and each nominative word of the lemma inside it
    SELECT w.parent_wg AS clause, h.id AS subject_id
    FROM wg w
    JOIN dominance d ON d.wg_id = w.id
    JOIN token h ON h.id = d.token_id
    WHERE w.role = 's' AND h.lemma = $lemma AND h.gcase = 'nominative'
    UNION ALL
    -- or a lone word standing as the subject
    SELECT t.parent_wg, t.id
    FROM token t
    WHERE t.role = 's' AND t.lemma = $lemma AND t.gcase = 'nominative'
),
verbs AS (
    -- the clause's verb: a word with role 'v', or a verb inside a role-'v' group
    SELECT t.parent_wg AS clause, t.id AS verb_id
    FROM token t WHERE t.role = 'v' AND t.pos = 'verb'
    UNION ALL
    SELECT w.parent_wg, t.id
    FROM wg w JOIN dominance d ON d.wg_id = w.id JOIN token t ON t.id = d.token_id
    WHERE w.role = 'v' AND t.pos = 'verb'
)
SELECT v.verb_id, vt.ref AS verb_ref, vt.surface AS verb, vt.lemma AS verb_lemma,
       vt.morph AS verb_morph, s.subject_id, st.surface AS subject
FROM subj s
JOIN verbs v ON v.clause = s.clause
JOIN token vt ON vt.id = v.verb_id
JOIN token st ON st.id = s.subject_id
WHERE vt.ord BETWEEN $scope_first AND $scope_last
ORDER BY vt.ord, st.ord
