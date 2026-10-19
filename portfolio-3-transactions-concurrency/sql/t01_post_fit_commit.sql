-- T1: posting a fit commits the post, its images, its hashtags and the hashtag counters together.
SET search_path = fitscheck;
\set author 7

-- step 1: state before
SELECT count(*) AS posts_before FROM post;
SELECT name, posts_count FROM hashtag WHERE name IN ('ootd', 't1_sunday') ORDER BY name;

-- step 2: one transaction does all the writes
BEGIN;
SELECT post_fit(:author, 'T1 Sunday fit', ARRAY['t1-front.jpg', 't1-side.jpg', 't1-back.jpg'],
                ARRAY['ootd', 't1_sunday']) AS new_post \gset
COMMIT;

-- step 3: every part is there, and the counters match the rows they count
SELECT p.id, p.caption, count(pi.id) AS images
FROM post p JOIN post_image pi ON pi.post_id = p.id
WHERE p.id = :new_post GROUP BY p.id;
SELECT h.name, h.posts_count FROM post_hashtag ph JOIN hashtag h ON h.id = ph.hashtag_id
WHERE ph.post_id = :new_post ORDER BY h.name;
SELECT count(*) AS posts_after FROM post;
SELECT count(*) AS counters_out_of_step FROM v_counter_drift;
