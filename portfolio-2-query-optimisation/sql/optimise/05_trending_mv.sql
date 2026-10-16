-- Materialized view for trending (q03). The 24-hour like counts are computed once per refresh and
-- stored, so reading trending becomes an index scan of a small table instead of aggregating every
-- like from the last day. The trade-off is staleness: results are as old as the last refresh.
-- The window is anchored to the dataset's as-of time for repeatability; in production it would use
-- now() and be refreshed on a schedule (for example every 5 minutes).
SET search_path = fitscheck;
\timing on

CREATE MATERIALIZED VIEW mv_trending_24h AS
SELECT post_id, count(*) AS likes_24h
FROM post_like
WHERE created_at >= timestamptz '2026-10-15 00:00:00+00' - interval '24 hours'
  AND created_at < timestamptz '2026-10-15 00:00:00+00'
GROUP BY post_id;

-- The unique index is required by REFRESH ... CONCURRENTLY; the ordered index serves the read.
CREATE UNIQUE INDEX uq_mv_trending_24h_post ON mv_trending_24h (post_id);
CREATE INDEX ix_mv_trending_24h_likes ON mv_trending_24h (likes_24h DESC, post_id);
ANALYZE mv_trending_24h;

SELECT count(*) AS posts_in_view, pg_size_pretty(pg_total_relation_size('mv_trending_24h')) AS size
FROM mv_trending_24h;

-- Refresh cost. A plain refresh locks the view against reads while it rebuilds; CONCURRENTLY lets
-- readers keep using the old contents but does more work (it diffs old and new rows).
REFRESH MATERIALIZED VIEW mv_trending_24h;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_trending_24h;
