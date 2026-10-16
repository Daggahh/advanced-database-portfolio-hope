-- q15 run against the monthly-partitioned copy post_like_by_month (03_partition_experiment.sql).
-- Partition pruning means only the October 2026 partition is read; the other twelve are skipped
-- from the plan entirely, with no index needed.
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS day_utc, count(*) AS likes
FROM post_like_by_month
WHERE created_at >= :'month_start' AND created_at < :'as_of'
GROUP BY 1
ORDER BY 1;
