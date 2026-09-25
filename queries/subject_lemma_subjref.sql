-- name: subject_lemma_subjref
-- description: Verbs whose UNEXPRESSED subject, as resolved by MACULA's coreference
-- description: annotation (subjref), is a word of the lemma. The referent is often in
-- description: another verse. Verbs whose subject is written out (e.g. ἐγώ) are not
-- description: here: add subject_lemma_tree, and follow refers_to from pronoun subjects.
-- param: lemma lemma -- e.g. Παῦλος, θεός
-- param: scope passage optional -- limit to a passage (applied to the verb)
-- cites: token
SELECT v.id AS verb_id, v.ref AS verb_ref, v.surface AS verb, v.lemma AS verb_lemma,
       s.id AS subject_id, s.ref AS subject_ref, s.surface AS subject
FROM has_subject h
JOIN token v ON v.id = h.src
JOIN token s ON s.id = h.dst
WHERE s.lemma = $lemma
  AND v.ord BETWEEN $scope_first AND $scope_last
ORDER BY v.ord, h.ord
