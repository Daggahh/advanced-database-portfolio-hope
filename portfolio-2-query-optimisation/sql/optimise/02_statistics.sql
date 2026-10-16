-- q15: PostgreSQL keeps no statistics on expressions by default, so it guessed that grouping likes by
-- day would produce one group per row (1,093,563) and chose a sort that spilled to disk. Expression
-- statistics give it the real number of distinct days. The expression must be immutable, so the day
-- is taken explicitly in UTC (date_trunc on timestamptz alone depends on the session time zone).
SET search_path = fitscheck;
CREATE STATISTICS IF NOT EXISTS st_post_like_day ON (date_trunc('day', created_at AT TIME ZONE 'UTC')) FROM post_like;
ANALYZE post_like;
