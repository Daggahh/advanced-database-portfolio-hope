-- People you may know: accounts followed by the people I follow, that I do not follow yet.
SELECT f2.followed_id AS suggestion, count(*) AS mutual_follows
FROM follow f1
JOIN follow f2 ON f2.follower_id = f1.followed_id
WHERE f1.follower_id = :feed_user
  AND f2.followed_id <> :feed_user
  AND NOT EXISTS (SELECT 1 FROM follow x
                  WHERE x.follower_id = :feed_user AND x.followed_id = f2.followed_id)
GROUP BY f2.followed_id
ORDER BY mutual_follows DESC, suggestion
LIMIT 10;
