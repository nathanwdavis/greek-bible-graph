-- name: subject_lemma_subjref
-- description: Verbs whose subject, as resolved by MACULA's coreference annotation
-- description: (subjref), is a word of the lemma. The referent is often in another
-- description: verse: this finds "who does it", not "what is the grammatical subject".
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
