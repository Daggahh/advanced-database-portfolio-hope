-- Like count read from the denormalised counter (BR-20).
SELECT likes_count AS likes
FROM post
WHERE id = :top_post;
