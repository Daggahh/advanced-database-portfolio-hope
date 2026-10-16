-- q08 rewritten to group by the UTC day, an immutable expression that st_post_like_day describes,
-- so the planner knows there are about 365 days rather than one group per row.
SELECT date_trunc('day', created_at AT TIME ZONE 'UTC') AS day_utc, count(*) AS likes
FROM post_like
WHERE created_at >= :'month_start' AND created_at < :'as_of'
GROUP BY 1
ORDER BY 1;
