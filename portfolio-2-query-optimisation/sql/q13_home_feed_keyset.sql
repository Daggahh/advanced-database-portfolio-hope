-- Home feed page 101 using keyset pagination: the same rows as q02, found by continuing after the
-- last post of page 100 (its created_at and id) instead of counting past 2,000 rows with OFFSET.
SELECT p.id, p.author_id, p.caption, p.likes_count, p.comments_count, p.created_at
FROM follow f
JOIN post p ON p.author_id = f.followed_id
WHERE f.follower_id = :feed_user
  AND p.created_at < :'as_of'
  AND (p.created_at, p.id) < (:'cursor_created'::timestamptz, :cursor_id)
ORDER BY p.created_at DESC, p.id DESC
LIMIT 20;
