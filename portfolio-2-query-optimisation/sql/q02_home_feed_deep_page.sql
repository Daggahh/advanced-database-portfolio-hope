-- Home feed page 101 (posts 2,001 to 2,020) using OFFSET pagination.
SELECT p.id, p.author_id, p.caption, p.likes_count, p.comments_count, p.created_at
FROM follow f
JOIN post p ON p.author_id = f.followed_id
WHERE f.follower_id = :feed_user
  AND p.created_at < :'as_of'
ORDER BY p.created_at DESC, p.id DESC
OFFSET 2000
LIMIT 20;
