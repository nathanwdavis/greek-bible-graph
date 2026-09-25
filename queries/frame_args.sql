-- name: frame_args
-- description: Semantic-frame arguments of a predicate lemma: A0 = agent/causer,
-- description: A1 = patient/theme, A2/AA2 = further arguments. Implicit (unexpressed)
-- description: arguments are listed with an empty argument id.
-- param: verb_lemma lemma -- e.g. ἀγαπάω
-- param: role text optional=A0 -- A0, A1, A2 or AA2
-- param: scope passage optional -- limit to a passage
-- cites: token
SELECT p.id AS predicate_id, p.ref AS predicate_ref, p.surface AS predicate,
       f.arg_role, a.id AS argument_id, a.ref AS argument_ref, a.surface AS argument,
       a.lemma AS argument_lemma, f.implicit
FROM frame_arg f
JOIN token p ON p.id = f.src
LEFT JOIN token a ON a.id = f.dst
WHERE p.lemma = $verb_lemma AND f.arg_role = $role
  AND p.ord BETWEEN $scope_first AND $scope_last
ORDER BY p.ord, f.ord
