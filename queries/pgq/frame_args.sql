-- name: frame_args
-- description: SQL/PGQ twin of queries/frame_args.sql (explicit arguments only: a
-- description: property-graph edge needs a target, so implicit arguments do not appear).
-- param: verb_lemma lemma -- e.g. ἀγαπάω
-- param: role text optional=A0 -- A0, A1, A2 or AA2
-- param: scope passage optional -- limit to a passage
-- cites: token
SELECT predicate_id, predicate_ref, predicate, arg_role, argument_id, argument_ref,
       argument, argument_lemma, false AS implicit
FROM GRAPH_TABLE (gbg_graph
    MATCH (p:token)-[f:frame_arg]->(a:token)
    WHERE p.lemma = $verb_lemma AND f.arg_role = $role
      AND p.ord BETWEEN $scope_first AND $scope_last
    COLUMNS (p.id AS predicate_id, p.ref AS predicate_ref, p.surface AS predicate,
             f.arg_role, a.id AS argument_id, a.ref AS argument_ref, a.surface AS argument,
             a.lemma AS argument_lemma, p.ord AS p_ord, f.ord AS f_ord))
ORDER BY p_ord, f_ord
