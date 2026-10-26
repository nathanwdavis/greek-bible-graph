-- name: lemmas_by_gloss
-- description: Every lemma with a word glossed (Cherith) by any of the given English words:
-- description: the recall step for a concept, in place of the semantic domains this build
-- description: lacks. Type plain English -- words are normalised like the stored terms
-- description: (knew/known/knowing -> know) -- and name derivations separately (know,
-- description: knowledge). share = matching / all tokens of the lemma in the edition, so a
-- description: low share flags a polysemous lemma (τίθημι: "appointed" in a few of 100).
-- description: n_negated counts glosses like "not know". Glosses are one translator's choices.
-- param: words english -- plain English, comma-separated, e.g. "know, knowledge, hide"
-- param: scope passage optional -- limit the matching tokens to a passage
-- cites: lemma
SELECT l.id AS lemma_id, l.lemma, count(*) AS n_matching, l.n_tokens,
       round(count(*) / l.n_tokens, 3) AS share,
       count(*) FILTER (WHERE t.english_negated) AS n_negated,
       list_sort(list_distinct(flatten(list(list_intersect(t.english_terms, $words)))))
           AS matched_terms,
       list_sort(list_distinct(list(lower(t.english))))[1:8] AS glosses
FROM token t
JOIN lemma l ON l.id = t.lemma_id
WHERE list_has_any(t.english_terms, $words)
  AND t.ord BETWEEN $scope_first AND $scope_last
GROUP BY l.id, l.lemma, l.n_tokens
ORDER BY n_matching DESC, l.lemma
