-- T2: a post that fails partway leaves nothing behind, and a post with no images is refused (BR-07).
SET search_path = fitscheck;
\set author 7

-- step 1: state before
SELECT (SELECT count(*) FROM post) AS posts, (SELECT count(*) FROM post_image) AS images,
       (SELECT posts_count FROM hashtag WHERE name = 'ootd') AS ootd_posts;

-- step 2 (T2a): the post and its images are inserted, then the second hashtag breaks the hashtag
-- format check, so the whole transaction fails
BEGIN;
SELECT post_fit(:author, 'T2 fit that fails', ARRAY['t2-a.jpg', 't2-b.jpg'], ARRAY['ootd', 'Bad Tag!']);
-- step 3: after an error PostgreSQL refuses further work in this transaction until it ends
SELECT 1 AS still_usable;
ROLLBACK;

-- step 4: nothing from the failed transaction survived, not even the rows written before the error
SELECT (SELECT count(*) FROM post) AS posts, (SELECT count(*) FROM post_image) AS images,
       (SELECT posts_count FROM hashtag WHERE name = 'ootd') AS ootd_posts;
SELECT count(*) AS posts_with_t2_caption FROM post WHERE caption = 'T2 fit that fails';

-- step 5 (T2b): BR-07, a post with no images, is refused by the posting transaction
SELECT post_fit(:author, 'T2 fit with no images', ARRAY[]::text[]);
SELECT count(*) AS posts_with_no_images
FROM post p WHERE NOT EXISTS (SELECT 1 FROM post_image WHERE post_id = p.id);
