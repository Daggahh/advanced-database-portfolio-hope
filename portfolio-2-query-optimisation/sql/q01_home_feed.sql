-- Home feed: the newest 20 posts from the people a user follows.
SELECT p.id, p.author_id, p.caption, p.likes_count, p.comments_count, p.created_at
FROM follow f
JOIN post p ON p.author_id = f.followed_id
WHERE f.follower_id = :feed_user
  AND p.created_at < :'as_of'
ORDER BY p.created_at DESC, p.id DESC
LIMIT 20;
