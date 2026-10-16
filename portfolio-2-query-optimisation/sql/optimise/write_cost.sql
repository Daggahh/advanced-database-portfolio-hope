-- Write cost of the Portfolio 2 indexes on post_like, isolated from everything else.
-- Copies the same ~480,000 real likes into a temporary table shaped like post_like, either with only
-- its primary key (-v variant=pk_only) or with the primary key plus the two Portfolio 2 indexes
-- (-v variant=all_indexes). A temporary table writes no WAL and has no foreign keys, so the only
-- difference between the two variants is index maintenance. Alternate the variants back to back.
SET search_path = fitscheck;
CREATE TEMP TABLE like_bench (
    user_id    bigint      NOT NULL,
    post_id    bigint      NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, post_id)
);
SELECT :'variant' = 'all_indexes' AS add_extra \gset
\if :add_extra
CREATE INDEX ON like_bench (created_at) INCLUDE (post_id);
CREATE INDEX ON like_bench (post_id);
\endif
SELECT clock_timestamp() AS t0 \gset
INSERT INTO like_bench SELECT user_id, post_id, created_at FROM post_like WHERE post_id % 10 = 0;
SELECT :'variant' AS variant,
       (SELECT count(*) FROM like_bench) AS rows_inserted,
       round(extract(epoch FROM clock_timestamp() - :'t0'::timestamptz) * 1000, 1) AS insert_ms;
