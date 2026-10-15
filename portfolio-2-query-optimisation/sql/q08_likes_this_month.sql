-- Likes per day so far this month: a time-range report over the largest table.
SELECT date_trunc('day', created_at) AS day, count(*) AS likes
FROM post_like
WHERE created_at >= :'month_start' AND created_at < :'as_of'
GROUP BY 1
ORDER BY 1;
