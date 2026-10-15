-- Trending: the 20 posts with the most likes in the last 24 hours.
SELECT pl.post_id, count(*) AS likes_24h
FROM post_like pl
WHERE pl.created_at >= :'as_of'::timestamptz - interval '24 hours'
  AND pl.created_at < :'as_of'
GROUP BY pl.post_id
ORDER BY likes_24h DESC, pl.post_id
LIMIT 20;
