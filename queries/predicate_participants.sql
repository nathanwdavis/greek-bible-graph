-- name: predicate_participants
-- description: Who does it (agent) or undergoes it (patient) for every occurrence of the
-- description: given predicate lemmas, from every signal the graph has, each followed through
-- description: coreference (refers_to, first target, cycle-guarded) to the word it ends at.
-- description: signal: tree = nominative word of the clause's role-s constituent, or accusative
-- description: word of its role-o constituent; subjref = has_subject; frame = A0 / A1; by = a
-- description: passive's ὑπό + genitive phrase (1 Cor 8:3 ἔγνωσται ὑπ' αὐτοῦ). VOICE MATTERS: the
-- description: grammatical subject (tree-s, subjref) of an ACTIVE or middle verb is its agent, of a
-- description: PASSIVE verb its patient, and the rows are filed that way -- "known by God"
-- description: puts God under by/frame, the one known under role=patient. Passive means
-- description: voice = passive with Robinson voice letter P: deponents (ἀπεκρίθη) stay active.
-- description: genitive = a noun predicate's genitive dependent (πρόγνωσις θεοῦ) -- subjective
-- description: or objective, the grammar does not say which, so it is listed for both roles.
-- description: exception = the subject of an elided εἰ μή clause on the predicate's clause
-- description: ("no one knows ... except the Father"): it does what is denied of the rest.
-- description: Only where upstream attaches the εἰ μή clause to the predicate's own clause
-- description: (e.g. Luke 10:22 attaches it inside the object clause, so it is missed) -- read
-- description: the context of every negated predicate (gbg ref).
-- description: agree = how many signals reach the same referent. implicit rows (no argument)
-- description: are unexpressed participants, e.g. a divine passive. negated = a negator (οὐ,
-- description: μή, οὐδείς ...) within two levels of the predicate's clause -- a heuristic.
-- description: question = an interrogative (τίς, morph I-) within two levels of the clause: "who
-- description: has known the mind of the Lord?" is often a denial in question form (Rom 11:34).
-- description: The referent is a WORD, not a person: πνεῦμα can be an unclean spirit, πατήρ
-- description: "our fathers". Check each one in context before counting it.
-- param: lemmas lemmas -- predicate lemmas, comma-separated, e.g. "οἶδα, γινώσκω, προγινώσκω"
-- param: words english optional -- keep only predicates glossed with these words (one sense of a polysemous lemma: ὁράω + know)
-- param: role text optional=agent -- agent or patient
-- param: referents lemmas optional -- keep only these referent lemmas (and implicit rows), e.g. "θεός, πατήρ"
-- param: scope passage optional -- limit to a passage (applied to the predicate)
-- cites: token
WITH RECURSIVE
pred AS (
    -- The predicate's clause: a verb is a direct constituent (role v) or sits inside a
    -- role-v group; anything else (a noun) belongs to its parent group.
    -- Passive in meaning: MACULA's voice AND Robinson's voice letter P. Deponents
    -- (ἀπεκρίθη V-ADI, ἐφοβήθη V-AOI) are "passive" in voice but active in meaning.
    SELECT t.id, t.ord, t.pos, t.parent_wg,
           t.voice = 'passive' AND regexp_extract(t.morph, '^V-2?[A-Z]([A-Z])', 1) = 'P'
               AS passive,
           coalesce(CASE WHEN t.role = 'v' THEN t.parent_wg END,
                    (SELECT arg_min(w.parent_wg, d.dist) FROM dominance d
                     JOIN wg w ON w.id = d.wg_id WHERE d.token_id = t.id AND w.role = 'v'),
                    t.parent_wg) AS clause
    FROM token t
    WHERE list_contains($lemmas, t.lemma)
      AND ($words IS NULL OR list_has_any(t.english_terms, $words))
      AND t.ord BETWEEN $scope_first AND $scope_last
),
arg AS (
    -- the grammatical subject: the agent of an active verb, the patient of a passive one
    SELECT p.id AS pred, h.id AS arg, 'tree' AS signal, false AS implicit
    FROM pred p
    JOIN wg c ON c.parent_wg = p.clause AND c.role = 's'
    JOIN dominance d ON d.wg_id = c.id
    JOIN token h ON h.id = d.token_id
    WHERE h.pos <> 'det' AND h.gcase = 'nominative'
      AND (($role = 'agent' AND NOT p.passive) OR ($role = 'patient' AND p.passive))
    UNION ALL
    SELECT p.id, h.id, 'tree', false
    FROM pred p
    JOIN token h ON h.parent_wg = p.clause AND h.role = 's'
    WHERE ($role = 'agent' AND NOT p.passive) OR ($role = 'patient' AND p.passive)
    UNION ALL
    SELECT p.id, e.dst, 'subjref', e.implicit
    FROM pred p JOIN has_subject e ON e.src = p.id
    WHERE ($role = 'agent' AND NOT p.passive) OR ($role = 'patient' AND p.passive)
    UNION ALL
    -- the grammatical object: a patient
    SELECT p.id, h.id, 'tree', false
    FROM pred p
    JOIN wg c ON c.parent_wg = p.clause AND c.role = 'o'
    JOIN dominance d ON d.wg_id = c.id
    JOIN token h ON h.id = d.token_id
    WHERE $role = 'patient' AND h.pos <> 'det' AND h.gcase = 'accusative'
    UNION ALL
    SELECT p.id, h.id, 'tree', false
    FROM pred p
    JOIN token h ON h.parent_wg = p.clause AND h.role = 'o'
    WHERE $role = 'patient'
    UNION ALL
    -- a passive's agent phrase: ὑπό + genitive
    SELECT p.id, g.id, 'by', false
    FROM pred p
    JOIN wg pp ON pp.parent_wg = p.clause AND pp.role = 'adv'
    JOIN token hy ON hy.parent_wg = pp.id AND hy.lemma = 'ὑπό'
    JOIN dominance d ON d.wg_id = pp.id
    JOIN token g ON g.id = d.token_id
    WHERE $role = 'agent' AND p.passive AND g.gcase = 'genitive' AND g.pos IN ('noun', 'pron')
    UNION ALL
    SELECT p.id, f.dst, 'frame', f.implicit
    FROM pred p JOIN frame_arg f ON f.src = p.id
    WHERE f.arg_role = CASE $role WHEN 'agent' THEN 'A0' WHEN 'patient' THEN 'A1' END
    UNION ALL
    -- "no one knows ... except the Father" (εἰ μή with the predicate elided, which MACULA
    -- marks): the exception's subject does what the negated predicate denies of everyone else.
    SELECT p.id, h.id, 'exception', false
    FROM pred p
    JOIN wg a ON a.parent_wg = p.clause AND a.role = 'adv'
    JOIN token ei ON ei.parent_wg = a.id AND ei.lemma = 'εἰ'
    JOIN wg ic ON ic.parent_wg = a.id AND ic.predication = 'elided'
    JOIN token mh ON mh.parent_wg = ic.id AND mh.lemma = 'μή'
    JOIN wg sg ON sg.parent_wg = ic.id AND sg.role = 's'
    JOIN dominance d ON d.wg_id = sg.id
    JOIN token h ON h.id = d.token_id
    WHERE $role = 'agent' AND h.gcase = 'nominative' AND h.pos <> 'det'
    UNION ALL
    -- ... or a lone word as that subject (Rev 19:12 εἰ μὴ αὐτός)
    SELECT p.id, h.id, 'exception', false
    FROM pred p
    JOIN wg a ON a.parent_wg = p.clause AND a.role = 'adv'
    JOIN token ei ON ei.parent_wg = a.id AND ei.lemma = 'εἰ'
    JOIN wg ic ON ic.parent_wg = a.id AND ic.predication = 'elided'
    JOIN token mh ON mh.parent_wg = ic.id AND mh.lemma = 'μή'
    JOIN token h ON h.parent_wg = ic.id AND h.role = 's'
    WHERE $role = 'agent'
    UNION ALL
    SELECT p.id, g.id, 'genitive', false
    FROM pred p
    JOIN dominance d ON d.wg_id = p.parent_wg AND d.dist <= 2
    JOIN token g ON g.id = d.token_id
    WHERE p.pos = 'noun' AND g.id <> p.id AND g.gcase = 'genitive' AND g.pos IN ('noun', 'pron')
),
chain(pred, signal, implicit, arg, cur, path) AS (
    SELECT pred, signal, implicit, arg, arg, [arg] FROM arg WHERE arg IS NOT NULL
    UNION ALL
    SELECT c.pred, c.signal, c.implicit, c.arg, r.dst, list_append(c.path, r.dst)
    FROM chain c
    JOIN refers_to r ON r.src = c.cur AND r.ord = 1
    WHERE r.dst IS NOT NULL AND NOT list_contains(c.path, r.dst) AND len(c.path) < 50
),
found AS (
    SELECT DISTINCT pred, signal, implicit, arg, cur AS referent, len(path) - 1 AS hops
    FROM chain c
    WHERE NOT EXISTS (SELECT 1 FROM refers_to r WHERE r.src = c.cur AND r.ord = 1
                      AND r.dst IS NOT NULL AND NOT list_contains(c.path, r.dst))
    UNION ALL
    SELECT DISTINCT pred, signal, implicit, NULL, NULL, NULL FROM arg WHERE arg IS NULL
),
question AS (
    SELECT DISTINCT p.id
    FROM pred p
    JOIN dominance d ON d.wg_id = p.clause AND d.dist <= 2
    JOIN token q ON q.id = d.token_id
    WHERE q.morph LIKE 'I-%'
),
negated AS (
    SELECT DISTINCT p.id
    FROM pred p
    JOIN dominance d ON d.wg_id = p.clause AND d.dist <= 2
    JOIN token n ON n.id = d.token_id
    WHERE n.lemma IN ('οὐ', 'μή', 'οὐδέ', 'μηδέ', 'οὔτε', 'μήτε', 'οὔπω', 'μήπω', 'οὐδείς',
                      'μηδείς', 'οὐθείς', 'μηθείς', 'οὐκέτι', 'μηκέτι', 'οὐδέποτε', 'μηδέποτε')
)
SELECT p.id AS predicate_id, p.ref AS predicate_ref, p.surface AS predicate,
       p.lemma AS predicate_lemma, p.voice, p.mood,
       x.pred IN (SELECT id FROM negated) AS negated,
       x.pred IN (SELECT id FROM question) AS question,
       x.signal, x.implicit, x.arg AS argument_id, a.surface AS argument, x.hops,
       x.referent AS referent_id, r.ref AS referent_ref, r.surface AS referent,
       r.lemma AS referent_lemma,
       count(DISTINCT x.signal) OVER (PARTITION BY x.pred, x.referent) AS agree
FROM found x
JOIN token p ON p.id = x.pred
LEFT JOIN token a ON a.id = x.arg
LEFT JOIN token r ON r.id = x.referent
WHERE $referents IS NULL OR x.referent IS NULL OR list_contains($referents, r.lemma)
ORDER BY p.ord, x.signal, a.ord NULLS LAST, r.ord NULLS LAST
