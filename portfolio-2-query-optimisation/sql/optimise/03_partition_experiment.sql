-- Partitioning experiment: a copy of post_like range-partitioned by month (PostgreSQL declarative
-- partitioning). It is an experiment on a copy, not a migration: step 1 shows why the real table is
-- not partitioned. Run once; it builds post_like_by_month from post_like.
-- Run: psql "$PG_URL" -X -f portfolio-2-query-optimisation/sql/optimise/03_partition_experiment.sql

SET search_path = fitscheck;
\timing on

-- Step 1: the uniqueness trade-off. A unique key on a partitioned table must include the partition
-- column, because each partition enforces uniqueness only on its own rows. "One like per user per
-- post" (BR-10) is exactly (user_id, post_id), so this is expected to fail.
CREATE TABLE post_like_by_month (
    user_id    bigint      NOT NULL,
    post_id    bigint      NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_post_like_by_month PRIMARY KEY (user_id, post_id)
) PARTITION BY RANGE (created_at);

-- Step 2: the key that partitioning allows. It would accept the same user liking the same post twice
-- at different times, so BR-10 would be lost.
CREATE TABLE post_like_by_month (
    user_id    bigint      NOT NULL,
    post_id    bigint      NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT pk_post_like_by_month PRIMARY KEY (user_id, post_id, created_at)
) PARTITION BY RANGE (created_at);

-- One partition per month of data, plus a default partition for anything outside the range.
DO $$
DECLARE
    m date;
BEGIN
    FOR m IN SELECT generate_series(date '2025-10-01', date '2026-10-01', interval '1 month')::date LOOP
        EXECUTE format('CREATE TABLE post_like_%s PARTITION OF post_like_by_month
                        FOR VALUES FROM (%L) TO (%L)',
                       to_char(m, 'YYYY_MM'), m::timestamptz, (m + interval '1 month')::timestamptz);
    END LOOP;
END;
$$;
CREATE TABLE post_like_default PARTITION OF post_like_by_month DEFAULT;

INSERT INTO post_like_by_month SELECT user_id, post_id, created_at FROM post_like;
ANALYZE post_like_by_month;

SELECT tableoid::regclass AS partition, count(*) AS rows
FROM post_like_by_month GROUP BY 1 ORDER BY 1;

-- The same expression statistics as 02_statistics.sql, on the partitioned copy, so q18 gets the
-- same accurate estimate of distinct days as q15.
CREATE STATISTICS st_post_like_by_month_day ON (date_trunc('day', created_at AT TIME ZONE 'UTC')) FROM post_like_by_month;
ANALYZE post_like_by_month;
