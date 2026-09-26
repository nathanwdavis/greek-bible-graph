-- name: topic_verses
-- description: The verses of this edition that the given topics cite, in canonical order, with
-- description: the reference as upstream wrote it and, for OpenBible, its vote score (weigh
-- description: low-vote verses before counting them). Nave's is keyed to the KJV: a verse can
-- description: be cited for wording the SBLGNT lacks. A topic id that matches nothing returns no
-- description: rows -- check the ids against topics_matching.
-- param: topics text -- topic ids, comma-separated, e.g. topic:naves:god/115
-- cites: verse
WITH wanted AS (SELECT trim(unnest(string_split($topics, ','))) AS id),
hits AS (
    SELECT e.dst, 'naves' AS source, t.id AS topic_id, t.path AS topic, e.ref,
           NULL::INTEGER AS votes
    FROM naves_topic_verse e JOIN naves_topic t ON t.id = e.src
    WHERE e.src IN (SELECT id FROM wanted)
    UNION ALL
    SELECT e.dst, 'openbible', t.id, t.title, e.ref, e.votes
    FROM openbible_topic_verse e JOIN openbible_topic t ON t.id = e.src
    WHERE e.src IN (SELECT id FROM wanted)
)
SELECT h.dst AS verse_id, h.source, h.topic_id, h.topic, h.ref, h.votes
FROM hits h JOIN verse v ON v.id = h.dst
ORDER BY v.ord, h.source, h.topic_id
