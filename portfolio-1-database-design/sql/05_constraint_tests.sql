-- FitsCheck constraint tests: every declarative and trigger rule in business-rules.md is attacked
-- with data that breaks it, and the constraint that fired is recorded. Runs in one transaction
-- that is rolled back, so the database is unchanged afterwards.
-- Run: psql "$PG_URL" -X -q -v ON_ERROR_STOP=1 -f portfolio-1-database-design/sql/05_constraint_tests.sql
-- Only the final report tables are printed; the individual test calls write to /dev/null.

\o /dev/null
BEGIN;
SET LOCAL search_path = fitscheck;

CREATE TEMP TABLE result (
    n        serial,
    rule     text,
    test     text,
    expected text,
    got      text,
    outcome  text
) ON COMMIT DROP;

-- Runs one statement that must fail. Passes when the named constraint (or SQLSTATE, for errors that
-- carry no constraint name such as NOT NULL) is the one that rejected it. The inner BEGIN/EXCEPTION
-- block is a subtransaction, so a failed statement leaves nothing behind.
CREATE FUNCTION pg_temp.expect_error(p_rule text, p_test text, p_expect text, p_sql text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_state text;
    v_con   text;
    v_got   text := 'no error';
BEGIN
    BEGIN
        EXECUTE p_sql;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS v_state = RETURNED_SQLSTATE, v_con = CONSTRAINT_NAME;
        v_got := coalesce(nullif(v_con, '') || ' (' || v_state || ')', v_state);
    END;
    INSERT INTO pg_temp.result (rule, test, expected, got, outcome)
    VALUES (p_rule, p_test, p_expect, v_got,
            CASE WHEN v_con = p_expect OR v_state = p_expect THEN 'PASS' ELSE 'FAIL' END);
END;
$$;

-- Runs a query returning one boolean that must be true, for behaviour rather than rejection.
CREATE FUNCTION pg_temp.expect_true(p_rule text, p_test text, p_sql text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    v_ok boolean;
BEGIN
    EXECUTE p_sql INTO v_ok;
    INSERT INTO pg_temp.result (rule, test, expected, got, outcome)
    VALUES (p_rule, p_test, 'true', coalesce(v_ok::text, 'null'),
            CASE WHEN v_ok THEN 'PASS' ELSE 'FAIL' END);
END;
$$;

CREATE FUNCTION pg_temp.note(p_rule text, p_test text, p_where text)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO pg_temp.result (rule, test, expected, got, outcome)
    VALUES (p_rule, p_test, p_where, '-', 'P3');
$$;

CREATE FUNCTION pg_temp.uid(p_username text) RETURNS bigint LANGUAGE sql AS $$
    SELECT id FROM fitscheck.app_user WHERE username = p_username;
$$;

CREATE FUNCTION pg_temp.post_of(p_username text) RETURNS bigint LANGUAGE sql AS $$
    SELECT min(p.id) FROM fitscheck.post p
    JOIN fitscheck.app_user u ON u.id = p.author_id WHERE u.username = p_username;
$$;

CREATE FUNCTION pg_temp.img(p_username text, p_position int) RETURNS bigint LANGUAGE sql AS $$
    SELECT id FROM fitscheck.post_image
    WHERE post_id = pg_temp.post_of(p_username) AND position = p_position;
$$;

CREATE FUNCTION pg_temp.chal(p_slug text) RETURNS bigint LANGUAGE sql AS $$
    SELECT id FROM fitscheck.challenge WHERE slug = p_slug;
$$;

-- Fixture: a small valid world. If any of it were rejected, ON_ERROR_STOP would abort the run.
INSERT INTO app_user (username, email, password_hash, full_name, is_admin) VALUES
    ('t_hope', 't_hope@test.dev', 'x', 'Test Hope', false),
    ('t_ada',  't_ada@test.dev',  'x', 'Test Ada',  false),
    ('t_tolu', 't_tolu@test.dev', 'x', 'Test Tolu', false),
    ('t_solo', 't_solo@test.dev', 'x', 'Test Solo', false),
    ('t_mod',  't_mod@test.dev',  'x', 'Test Mod',  true);

INSERT INTO user_device (user_id, push_token, platform)
VALUES (pg_temp.uid('t_hope'), 'tok-hope-1', 'ios');

INSERT INTO post (author_id, caption) VALUES
    (pg_temp.uid('t_hope'), 'Sunday fit'),
    (pg_temp.uid('t_ada'),  'Office look'),
    (pg_temp.uid('t_tolu'), 'Throwaway fit'),
    (pg_temp.uid('t_solo'), 'Only post');

INSERT INTO post_image (post_id, position, image_url) VALUES
    (pg_temp.post_of('t_hope'), 1, 'hope-1.jpg'),
    (pg_temp.post_of('t_hope'), 2, 'hope-2.jpg'),
    (pg_temp.post_of('t_ada'),  1, 'ada-1.jpg'),
    (pg_temp.post_of('t_tolu'), 1, 'tolu-1.jpg'),
    (pg_temp.post_of('t_solo'), 1, 'solo-1.jpg');

INSERT INTO brand (name, website) VALUES ('Zara', 'https://zara.com');
INSERT INTO shop_item (post_image_id, brand_id, item_name, price, currency)
VALUES (pg_temp.img('t_hope', 1), (SELECT id FROM brand WHERE name = 'Zara'), 'Linen shirt', 30000, 'NGN');

INSERT INTO hashtag (name) VALUES ('ootd');
INSERT INTO post_hashtag VALUES (pg_temp.post_of('t_hope'), (SELECT id FROM hashtag WHERE name = 'ootd'));

INSERT INTO follow (follower_id, followed_id) VALUES
    (pg_temp.uid('t_tolu'), pg_temp.uid('t_hope')),
    (pg_temp.uid('t_ada'),  pg_temp.uid('t_hope'));

INSERT INTO post_like (user_id, post_id) VALUES
    (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope')),
    (pg_temp.uid('t_ada'),  pg_temp.post_of('t_tolu'));

INSERT INTO vote (user_id, post_id, post_image_id) VALUES
    (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'), pg_temp.img('t_hope', 2)),
    (pg_temp.uid('t_ada'),  pg_temp.post_of('t_tolu'), pg_temp.img('t_tolu', 1));

INSERT INTO comment (post_id, author_id, body) VALUES
    (pg_temp.post_of('t_hope'), pg_temp.uid('t_ada'), 'Love the shirt'),
    (pg_temp.post_of('t_tolu'), pg_temp.uid('t_ada'), 'Nice');
INSERT INTO comment (post_id, author_id, parent_id, body)
SELECT post_id, pg_temp.uid('t_hope'), id, 'Thank you'
FROM comment WHERE body = 'Love the shirt';

INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries) VALUES
    ('sunday-fits', 'Sunday Fits', now() - interval '1 day', now() + interval '6 days', 100),
    ('monday-fits', 'Monday Fits', now() - interval '1 day', now() + interval '6 days', 100);

INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES
    (pg_temp.chal('sunday-fits'), pg_temp.uid('t_hope'), pg_temp.post_of('t_hope')),
    (pg_temp.chal('monday-fits'), pg_temp.uid('t_ada'),  pg_temp.post_of('t_ada'));

UPDATE post p SET likes_count    = (SELECT count(*) FROM post_like WHERE post_id = p.id),
                  comments_count = (SELECT count(*) FROM comment WHERE post_id = p.id);
UPDATE hashtag h SET posts_count = (SELECT count(*) FROM post_hashtag WHERE hashtag_id = h.id);
UPDATE challenge c SET entries_count = (SELECT count(*) FROM challenge_entry WHERE challenge_id = c.id);

SELECT pg_temp.expect_true('fixture', 'valid fixture data is accepted',
    $q$SELECT (SELECT count(*) FROM app_user WHERE username LIKE 't\_%') = 5$q$);

SELECT pg_temp.expect_error('BR-01', 'username differing only in case', 'uq_app_user_username_ci',
    $q$INSERT INTO app_user (username, email, password_hash, full_name) VALUES ('T_HOPE', 'other@test.dev', 'x', 'Dup')$q$);
SELECT pg_temp.expect_error('BR-01', 'email differing only in case', 'uq_app_user_email_ci',
    $q$INSERT INTO app_user (username, email, password_hash, full_name) VALUES ('t_other', 'T_HOPE@TEST.DEV', 'x', 'Dup')$q$);
SELECT pg_temp.expect_error('BR-01', 'username with a space', 'ck_app_user_username_format',
    $q$INSERT INTO app_user (username, email, password_hash, full_name) VALUES ('bad name', 'bad@test.dev', 'x', 'Bad')$q$);
SELECT pg_temp.expect_error('BR-01', 'email without @', 'ck_app_user_email_format',
    $q$INSERT INTO app_user (username, email, password_hash, full_name) VALUES ('t_noat', 'noat.test.dev', 'x', 'Bad')$q$);

SELECT pg_temp.expect_error('BR-02', 'user follows themselves', 'ck_follow_not_self',
    $q$INSERT INTO follow (follower_id, followed_id) VALUES (pg_temp.uid('t_ada'), pg_temp.uid('t_ada'))$q$);
SELECT pg_temp.expect_error('BR-02', 'same follow twice', 'pk_follow',
    $q$INSERT INTO follow (follower_id, followed_id) VALUES (pg_temp.uid('t_ada'), pg_temp.uid('t_hope'))$q$);

INSERT INTO block (blocker_id, blocked_id) VALUES (pg_temp.uid('t_hope'), pg_temp.uid('t_tolu'));
SELECT pg_temp.expect_true('BR-03', 'blocking removes the blocked user''s existing follow',
    $q$SELECT NOT EXISTS (SELECT 1 FROM follow WHERE follower_id = pg_temp.uid('t_tolu') AND followed_id = pg_temp.uid('t_hope'))$q$);
SELECT pg_temp.expect_error('BR-03', 'blocked user follows the blocker', 'tg_follow_not_blocked',
    $q$INSERT INTO follow (follower_id, followed_id) VALUES (pg_temp.uid('t_tolu'), pg_temp.uid('t_hope'))$q$);
SELECT pg_temp.expect_error('BR-03', 'user blocks themselves', 'ck_block_not_self',
    $q$INSERT INTO block (blocker_id, blocked_id) VALUES (pg_temp.uid('t_ada'), pg_temp.uid('t_ada'))$q$);

SELECT pg_temp.expect_error('BR-04', 'push token reused by another device', 'uq_user_device_push_token',
    $q$INSERT INTO user_device (user_id, push_token, platform) VALUES (pg_temp.uid('t_ada'), 'tok-hope-1', 'android')$q$);
SELECT pg_temp.expect_error('BR-04', 'platform outside the enum', '22P02',
    $q$INSERT INTO user_device (user_id, push_token, platform) VALUES (pg_temp.uid('t_ada'), 'tok-ada-1', 'blackberry')$q$);

SELECT pg_temp.expect_error('BR-06', 'post without an author', '23502',
    $q$INSERT INTO post (author_id, caption) VALUES (NULL, 'orphan')$q$);

SELECT pg_temp.note('BR-07', 'post must have at least one image', 'posting transaction, P3 T1/T2');
SELECT pg_temp.expect_error('BR-07', 'image in position 11', 'ck_post_image_position_range',
    $q$INSERT INTO post_image (post_id, position, image_url) VALUES (pg_temp.post_of('t_hope'), 11, 'x.jpg')$q$);
SELECT pg_temp.expect_error('BR-07', 'two images in the same position', 'uq_post_image_post_position',
    $q$INSERT INTO post_image (post_id, position, image_url) VALUES (pg_temp.post_of('t_hope'), 1, 'x.jpg')$q$);

SELECT pg_temp.expect_error('BR-08', 'negative price', 'ck_shop_item_price_nonneg',
    $q$INSERT INTO shop_item (post_image_id, item_name, price, currency) VALUES (pg_temp.img('t_hope', 1), 'Belt', -1, 'NGN')$q$);
SELECT pg_temp.expect_error('BR-08', 'lowercase currency code', 'ck_shop_item_currency_iso',
    $q$INSERT INTO shop_item (post_image_id, item_name, price, currency) VALUES (pg_temp.img('t_hope', 1), 'Belt', 5000, 'ngn')$q$);

SELECT pg_temp.expect_error('BR-09', 'hashtag with capitals', 'ck_hashtag_name_format',
    $q$INSERT INTO hashtag (name) VALUES ('OOTD')$q$);
SELECT pg_temp.expect_error('BR-09', 'duplicate hashtag', 'uq_hashtag_name',
    $q$INSERT INTO hashtag (name) VALUES ('ootd')$q$);
SELECT pg_temp.expect_error('BR-09', 'same hashtag on a post twice', 'pk_post_hashtag',
    $q$INSERT INTO post_hashtag VALUES (pg_temp.post_of('t_hope'), (SELECT id FROM hashtag WHERE name = 'ootd'))$q$);

SELECT pg_temp.expect_error('BR-10', 'same user likes a post twice', 'pk_post_like',
    $q$INSERT INTO post_like (user_id, post_id) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'))$q$);

SELECT pg_temp.expect_error('BR-11', 'second vote on the same post', 'uq_vote_user_post',
    $q$INSERT INTO vote (user_id, post_id, post_image_id) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'), pg_temp.img('t_hope', 1))$q$);
SELECT pg_temp.expect_error('BR-11', 'vote picks an image from a different post', 'fk_vote_post_image',
    $q$INSERT INTO vote (user_id, post_id, post_image_id) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_ada'), pg_temp.img('t_hope', 1))$q$);

SELECT pg_temp.expect_error('BR-12', 'author votes on their own post', 'tg_vote_not_own_post',
    $q$INSERT INTO vote (user_id, post_id, post_image_id) VALUES (pg_temp.uid('t_hope'), pg_temp.post_of('t_hope'), pg_temp.img('t_hope', 1))$q$);

SELECT pg_temp.expect_error('BR-13', 'empty comment', 'ck_comment_body_length',
    $q$INSERT INTO comment (post_id, author_id, body) VALUES (pg_temp.post_of('t_hope'), pg_temp.uid('t_ada'), '')$q$);
SELECT pg_temp.expect_error('BR-13', 'reply on a different post from its parent', 'fk_comment_parent',
    $q$INSERT INTO comment (post_id, author_id, parent_id, body)
       SELECT pg_temp.post_of('t_ada'), pg_temp.uid('t_tolu'), id, 'wrong post' FROM comment WHERE body = 'Love the shirt'$q$);

SELECT pg_temp.expect_error('BR-14', 'duplicate challenge slug', 'uq_challenge_slug',
    $q$INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries) VALUES ('sunday-fits', 'Again', now(), now() + interval '1 day', 10)$q$);
SELECT pg_temp.expect_error('BR-14', 'challenge ends before it starts', 'ck_challenge_dates',
    $q$INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries) VALUES ('backwards', 'Backwards', now(), now() - interval '1 day', 10)$q$);
SELECT pg_temp.expect_error('BR-14', 'entry limit of zero', 'ck_challenge_max_entries_positive',
    $q$INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries) VALUES ('no-room', 'No room', now(), now() + interval '1 day', 0)$q$);

SELECT pg_temp.expect_error('BR-15', 'user enters the same challenge twice', 'uq_entry_challenge_user',
    $q$INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES (pg_temp.chal('sunday-fits'), pg_temp.uid('t_hope'), pg_temp.post_of('t_hope'))$q$);
SELECT pg_temp.expect_error('BR-15', 'user enters with someone else''s post', 'fk_entry_own_post',
    $q$INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES (pg_temp.chal('sunday-fits'), pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'))$q$);

SELECT pg_temp.note('BR-16', 'entries only while open and within the limit', 'entry transaction, P3 T6');

SELECT pg_temp.expect_error('BR-17', 'winner is an entry of another challenge', 'fk_challenge_winner',
    $q$UPDATE challenge SET winner_entry_id = (SELECT id FROM challenge_entry WHERE challenge_id = pg_temp.chal('monday-fits'))
       WHERE slug = 'sunday-fits'$q$);
SELECT pg_temp.expect_true('BR-17', 'winner from the same challenge is accepted',
    $q$WITH w AS (UPDATE challenge SET winner_entry_id = (SELECT id FROM challenge_entry WHERE challenge_id = pg_temp.chal('sunday-fits'))
                  WHERE slug = 'sunday-fits' RETURNING winner_entry_id)
       SELECT winner_entry_id IS NOT NULL FROM w$q$);
SELECT pg_temp.expect_error('BR-17', 'negative style points', 'ck_app_user_style_points_nonneg',
    $q$UPDATE app_user SET style_points = -1 WHERE username = 't_hope'$q$);
SELECT pg_temp.note('BR-17', 'winner set only after the challenge ends', 'close transaction, P3 T3');

SELECT pg_temp.expect_error('BR-18', 'report with two targets', 'ck_report_one_target',
    $q$INSERT INTO report (reporter_id, target_user_id, target_post_id, reason) VALUES (pg_temp.uid('t_tolu'), pg_temp.uid('t_hope'), pg_temp.post_of('t_hope'), 'spam')$q$);
SELECT pg_temp.expect_error('BR-18', 'report with no target', 'ck_report_one_target',
    $q$INSERT INTO report (reporter_id, reason) VALUES (pg_temp.uid('t_tolu'), 'spam')$q$);
SELECT pg_temp.expect_error('BR-18', 'reviewer recorded without a review time', 'ck_report_review_pair',
    $q$INSERT INTO report (reporter_id, target_post_id, reason, reviewed_by) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'), 'spam', pg_temp.uid('t_mod'))$q$);
SELECT pg_temp.expect_error('BR-18', 'report closed without being reviewed', 'ck_report_reviewed_when_closed',
    $q$INSERT INTO report (reporter_id, target_post_id, reason, status) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'), 'spam', 'actioned')$q$);
SELECT pg_temp.expect_error('BR-18', 'status outside the enum', '22P02',
    $q$INSERT INTO report (reporter_id, target_post_id, reason, status) VALUES (pg_temp.uid('t_tolu'), pg_temp.post_of('t_hope'), 'spam', 'deleted')$q$);

SELECT pg_temp.expect_error('BR-19', 'notification without a recipient', '23502',
    $q$INSERT INTO notification (recipient_id, type, title) VALUES (NULL, 'like', 'New like')$q$);
SELECT pg_temp.expect_true('BR-19', 'notification starts unread',
    $q$WITH n AS (INSERT INTO notification (recipient_id, type, title) VALUES (pg_temp.uid('t_hope'), 'like', 'New like') RETURNING is_read)
       SELECT NOT is_read FROM n$q$);

SELECT pg_temp.expect_true('BR-20', 'reconciled counters show no drift',
    $q$SELECT NOT EXISTS (SELECT 1 FROM v_counter_drift)$q$);
UPDATE post SET likes_count = likes_count + 5 WHERE id = pg_temp.post_of('t_hope');
SELECT pg_temp.expect_true('BR-20', 'a tampered counter is caught by v_counter_drift',
    $q$SELECT EXISTS (SELECT 1 FROM v_counter_drift WHERE counter = 'post.likes_count' AND row_id = pg_temp.post_of('t_hope'))$q$);
SELECT pg_temp.expect_error('BR-20', 'negative like counter', 'ck_post_likes_count_nonneg',
    $q$UPDATE post SET likes_count = -1 WHERE id = pg_temp.post_of('t_hope')$q$);

UPDATE post SET updated_at = '2000-01-01' WHERE id = pg_temp.post_of('t_ada');
UPDATE post SET caption = 'Edited' WHERE id = pg_temp.post_of('t_ada');
SELECT pg_temp.expect_true('trigger', 'editing a post stamps updated_at server side',
    $q$SELECT updated_at = now() FROM post WHERE id = pg_temp.post_of('t_ada')$q$);

SELECT pg_temp.expect_true('BR-08', 'deleting a brand keeps its items with no brand (SET NULL)',
    $q$WITH d AS (DELETE FROM brand WHERE name = 'Zara' RETURNING id)
       SELECT (SELECT count(*) FROM d) = 1$q$);
SELECT pg_temp.expect_true('BR-08', 'the shop item survived the brand delete',
    $q$SELECT brand_id IS NULL FROM shop_item WHERE item_name = 'Linen shirt'$q$);

CREATE TEMP TABLE tolu_post ON COMMIT DROP AS SELECT pg_temp.post_of('t_tolu') AS id;
DELETE FROM post WHERE id = (SELECT id FROM tolu_post);
SELECT pg_temp.expect_true('delete', 'deleting a post cascades to its images, likes, votes and comments',
    $q$SELECT NOT EXISTS (SELECT 1 FROM post_image WHERE post_id = (SELECT id FROM tolu_post))
          AND NOT EXISTS (SELECT 1 FROM post_like  WHERE post_id = (SELECT id FROM tolu_post))
          AND NOT EXISTS (SELECT 1 FROM vote       WHERE post_id = (SELECT id FROM tolu_post))
          AND NOT EXISTS (SELECT 1 FROM comment    WHERE post_id = (SELECT id FROM tolu_post))$q$);

SELECT pg_temp.expect_error('BR-05', 'deleting a user who has a post', 'fk_post_author',
    $q$DELETE FROM app_user WHERE username = 't_solo'$q$);
SELECT pg_temp.expect_error('BR-05', 'deleting a post that is a challenge entry', 'fk_entry_own_post',
    $q$DELETE FROM post WHERE id = pg_temp.post_of('t_ada')$q$);

\o
SELECT n, rule, test, expected, got, outcome FROM result ORDER BY n;

SELECT outcome, count(*) AS tests FROM result GROUP BY outcome ORDER BY outcome;

ROLLBACK;
