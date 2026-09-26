-- name: similar_lemmas
-- description: Lemmas semantically close to a lemma, from MACULA's Clear synonyms data
-- description: (lemma_proximity; Strong's-keyed, CC BY). Lower distance = closer. Upstream
-- description: lists each pair once, so both directions are read. A lemma whose forms carry
-- description: several Strong's numbers can be paired with itself; those rows are left out
-- description: here. top_glosses shows how each neighbour is usually glossed.
-- param: lemma lemma -- e.g. γινώσκω
-- param: max_distance float optional=0.8 -- keep neighbours at or below this distance
-- cites: lemma
WITH pairs AS (
    SELECT src AS a, dst AS b, distance, src_strong || '~' || dst_strong AS via
    FROM lemma_proximity
    UNION ALL
    SELECT dst, src, distance, dst_strong || '~' || src_strong FROM lemma_proximity
)
SELECT n.id AS lemma_id, n.lemma, min(p.distance) AS distance, n.n_tokens,
       list_sort(list_distinct(list(p.via))) AS strong_pairs,
       (SELECT string_agg(g, ', ' ORDER BY c DESC, g)
        FROM (SELECT lower(english) AS g, count(*) AS c FROM token
              WHERE lemma_id = n.id AND english IS NOT NULL
              GROUP BY 1 ORDER BY c DESC, g LIMIT 4)) AS top_glosses
FROM pairs p
JOIN lemma n ON n.id = p.b
WHERE p.a = 'lemma:' || $lemma AND p.b <> p.a AND p.distance <= $max_distance
GROUP BY n.id, n.lemma, n.n_tokens
ORDER BY distance, n.lemma
