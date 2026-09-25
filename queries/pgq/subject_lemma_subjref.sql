-- name: subject_lemma_subjref
-- description: SQL/PGQ twin of queries/subject_lemma_subjref.sql.
-- param: lemma lemma -- e.g. Παῦλος, θεός
-- param: scope passage optional -- limit to a passage (applied to the verb)
-- cites: token
SELECT verb_id, verb_ref, verb, verb_lemma, subject_id, subject_ref, subject
FROM GRAPH_TABLE (gbg_graph
    MATCH (v:token)-[h:has_subject]->(s:token)
    WHERE s.lemma = $lemma AND v.ord BETWEEN $scope_first AND $scope_last
    COLUMNS (v.id AS verb_id, v.ref AS verb_ref, v.surface AS verb, v.lemma AS verb_lemma,
             s.id AS subject_id, s.ref AS subject_ref, s.surface AS subject,
             v.ord AS v_ord, h.ord AS h_ord))
ORDER BY v_ord, h_ord
