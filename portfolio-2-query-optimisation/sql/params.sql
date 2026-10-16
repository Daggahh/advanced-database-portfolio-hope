-- Query parameters, chosen from the seeded data (seed 8103). Loaded before every query:
--   psql "$PG_URL" -f sql/params.sql -f sql/q01_home_feed.sql
-- as_of is the generator's anchor, so time windows are repeatable instead of moving with now().
\set as_of '2026-10-15 00:00:00+00'
\set month_start '2026-10-01 00:00:00+00'
-- follows 15 accounts, 10 of whom post, with 8,333 posts between them: a heavy home feed
\set feed_user 82114
-- 400 comments, the longest thread
\set thread_post 1332
-- closed challenge with 120 entries
\set challenge 92
-- 99,999 likes, the most liked post
\set top_post 160949
-- matches 398 of 100,000 users
\set name_search 'tunde'
-- tags 73,616 posts versus 5 posts
\set popular_tag 'ootd'
\set rare_tag 'sneakers_2916'
-- last post on feed page 100 (row 2,000): the keyset cursor for q13
\set cursor_created '2026-07-18 09:36:13.873242+00'
\set cursor_id 133930
-- the same two tags resolved to their ids, as an application would after one cached lookup
\set popular_tag_id 1
\set rare_tag_id 2917
SET search_path = fitscheck;
