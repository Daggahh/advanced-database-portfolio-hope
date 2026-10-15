-- Like count computed by counting rows (what the feed would need without the stored counter).
SELECT count(*) AS likes
FROM post_like
WHERE post_id = :top_post;
