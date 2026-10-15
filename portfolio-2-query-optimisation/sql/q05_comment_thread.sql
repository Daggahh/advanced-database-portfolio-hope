-- Comment thread: every comment on a post with its replies nested under it (recursive CTE).
WITH RECURSIVE thread AS (
    SELECT id, parent_id, author_id, body, 1 AS depth, ARRAY[id] AS path
    FROM comment
    WHERE post_id = :thread_post AND parent_id IS NULL
    UNION ALL
    SELECT c.id, c.parent_id, c.author_id, c.body, t.depth + 1, t.path || c.id
    FROM comment c
    JOIN thread t ON c.parent_id = t.id
)
SELECT id, parent_id, depth, author_id, left(body, 40) AS body
FROM thread
ORDER BY path
LIMIT 50;
