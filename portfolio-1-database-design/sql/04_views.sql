-- FitsCheck views.

SET search_path = fitscheck;

-- What the app shows on one feed card: the post, its author, its cover image and its counts
CREATE VIEW v_post_card AS
SELECT p.id AS post_id,
       p.author_id,
       u.username AS author_username,
       u.avatar_url AS author_avatar_url,
       p.caption,
       cover.image_url AS cover_image_url,
       p.likes_count,
       p.comments_count,
       p.created_at
FROM post p
JOIN app_user u ON u.id = p.author_id
LEFT JOIN post_image cover ON cover.post_id = p.id AND cover.position = 1
WHERE u.is_active;

-- BR-20: every stored counter must equal the rows it counts. An empty result proves no drift.
CREATE VIEW v_counter_drift AS
SELECT 'post.likes_count' AS counter, p.id AS row_id, p.likes_count AS stored, count(pl.post_id) AS actual
FROM post p
LEFT JOIN post_like pl ON pl.post_id = p.id
GROUP BY p.id
HAVING p.likes_count <> count(pl.post_id)
UNION ALL
SELECT 'post.comments_count', p.id, p.comments_count, count(c.id)
FROM post p
LEFT JOIN comment c ON c.post_id = p.id
GROUP BY p.id
HAVING p.comments_count <> count(c.id)
UNION ALL
SELECT 'hashtag.posts_count', h.id, h.posts_count, count(ph.post_id)
FROM hashtag h
LEFT JOIN post_hashtag ph ON ph.hashtag_id = h.id
GROUP BY h.id
HAVING h.posts_count <> count(ph.post_id)
UNION ALL
SELECT 'challenge.entries_count', ch.id, ch.entries_count, count(e.id)
FROM challenge ch
LEFT JOIN challenge_entry e ON e.challenge_id = ch.id
GROUP BY ch.id
HAVING ch.entries_count <> count(e.id);
