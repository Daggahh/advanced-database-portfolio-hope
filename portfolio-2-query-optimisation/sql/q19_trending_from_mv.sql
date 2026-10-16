-- Trending read from the materialized view mv_trending_24h (05_trending_mv.sql): same answer as q03,
-- as of the last refresh.
SELECT post_id, likes_24h
FROM mv_trending_24h
ORDER BY likes_24h DESC, post_id
LIMIT 20;
