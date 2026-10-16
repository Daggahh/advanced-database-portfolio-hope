-- Portfolio 2 indexes. Each one answers a problem seen in a baseline plan (plans/*_before.txt).
-- Write cost is measured separately with write_cost.sql.

SET search_path = fitscheck;

-- q01, q02, q13: the feed reads one author's newest posts. Matching the ORDER BY lets the planner
-- walk each followed author's posts newest-first and stop after 20, instead of sorting all of them.
CREATE INDEX ix_post_author_created ON post (author_id, created_at DESC, id DESC);

-- q05: the thread starts from a post's top-level comments, then repeatedly finds replies by parent.
-- The parent index is partial: top-level comments (70% of rows) have no parent and are never looked
-- up this way, so leaving them out makes the index smaller and cheaper to maintain.
CREATE INDEX ix_comment_post ON comment (post_id);
CREATE INDEX ix_comment_parent ON comment (parent_id) WHERE parent_id IS NOT NULL;

-- q06: votes are counted per post. INCLUDE (id) stores the counted column in the index itself, so
-- the count is answered by an index-only scan without visiting the table.
CREATE INDEX ix_vote_post ON vote (post_id) INCLUDE (id);

-- q03, q08: time-window reports over likes. INCLUDE (post_id) lets trending be index-only.
CREATE INDEX ix_post_like_created ON post_like (created_at) INCLUDE (post_id);

-- q09: counting one post's likes. The primary key (user_id, post_id) leads with user_id, so it
-- cannot find a post's likes; this index can.
CREATE INDEX ix_post_like_post ON post_like (post_id);

-- q04: ILIKE '%tunde%' has a leading wildcard, which a B-tree cannot use. A trigram GIN index
-- (PostgreSQL extension pg_trgm) indexes every three-letter fragment, so any substring can be found.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX ix_app_user_full_name_trgm ON app_user USING gin (full_name gin_trgm_ops);

-- q11, q12: find a hashtag's posts, then each image's shop items. The post_hashtag primary key
-- leads with post_id and shop_item has no index on its image, so both joins needed full scans.
CREATE INDEX ix_post_hashtag_hashtag ON post_hashtag (hashtag_id);
CREATE INDEX ix_shop_item_image ON shop_item (post_image_id);

ANALYZE;
