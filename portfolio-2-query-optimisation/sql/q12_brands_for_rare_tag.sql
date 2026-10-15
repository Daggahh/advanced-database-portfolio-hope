-- Brands most often worn in posts carrying a rare hashtag (same query, different selectivity).
SELECT b.name, count(*) AS items
FROM hashtag h
JOIN post_hashtag ph ON ph.hashtag_id = h.id
JOIN post_image pi ON pi.post_id = ph.post_id
JOIN shop_item si ON si.post_image_id = pi.id
JOIN brand b ON b.id = si.brand_id
WHERE h.name = :'rare_tag'
GROUP BY b.name
ORDER BY items DESC, b.name
LIMIT 10;
