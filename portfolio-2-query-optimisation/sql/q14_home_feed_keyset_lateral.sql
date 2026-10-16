-- Home feed page 101 with keyset pagination rewritten with LATERAL: for each followed author, read only
-- their next 20 posts after the cursor straight from ix_post_author_created, then take the newest 20
-- of those (at most 15 x 20 rows) instead of fetching and sorting every post by every followed author.
SELECT p.id, p.author_id, p.caption, p.likes_count, p.comments_count, p.created_at
FROM follow f
CROSS JOIN LATERAL (
    SELECT p.id, p.author_id, p.caption, p.likes_count, p.comments_count, p.created_at
    FROM post p
    WHERE p.author_id = f.followed_id
      AND p.created_at < :'as_of'
      AND (p.created_at, p.id) < (:'cursor_created'::timestamptz, :cursor_id)
    ORDER BY p.created_at DESC, p.id DESC
    LIMIT 20
) p
WHERE f.follower_id = :feed_user
ORDER BY p.created_at DESC, p.id DESC
LIMIT 20;
