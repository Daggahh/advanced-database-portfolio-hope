-- q12 rewritten to filter by the rare tag's id, looked up first. With a literal id the
-- planner reads that id's real frequency from the post_hashtag statistics and picks a plan to match.
SELECT b.name, count(*) AS items
FROM post_hashtag ph
JOIN post_image pi ON pi.post_id = ph.post_id
JOIN shop_item si ON si.post_image_id = pi.id
JOIN brand b ON b.id = si.brand_id
WHERE ph.hashtag_id = :rare_tag_id
GROUP BY b.name
ORDER BY items DESC, b.name
LIMIT 10;
