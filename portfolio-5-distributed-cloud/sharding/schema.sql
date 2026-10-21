-- Citus schema for FitsCheck, sharded by creator. Run on the coordinator.
-- Every table a creator owns is distributed on that creator's id and co-located, so a creator's
-- profile, posts and the likes on those posts live on the same shard and join without moving data.
\set ON_ERROR_STOP 0

SELECT citus_set_coordinator_host('coordinator', 5432);
SELECT citus_add_node('worker1', 5432);
SELECT citus_add_node('worker2', 5432);
SET citus.shard_count = 16;

-- Step 1: the uniqueness trade-off. Each shard can only check uniqueness on its own rows, so a unique
-- key must include the distribution column. A primary key on post.id alone is refused.
CREATE TABLE post_try (id bigint PRIMARY KEY, author_id bigint NOT NULL);
SELECT create_distributed_table('post_try', 'author_id');
DROP TABLE post_try;

\set ON_ERROR_STOP 1

CREATE TABLE app_user (
    id         bigint      NOT NULL,
    username   varchar(30) NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (id)
);

-- The primary key includes author_id (the distribution column); id alone stays unique in practice
-- because it is generated centrally, but no constraint can check that across shards.
CREATE TABLE post (
    id             bigint      NOT NULL,
    author_id      bigint      NOT NULL,
    caption        varchar(2200),
    likes_count    integer     NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL,
    PRIMARY KEY (author_id, id)
);

-- post_author_id is copied from the post so a like lives on the same shard as the post it is for.
CREATE TABLE post_like (
    post_author_id bigint      NOT NULL,
    post_id        bigint      NOT NULL,
    user_id        bigint      NOT NULL,
    created_at     timestamptz NOT NULL,
    PRIMARY KEY (post_author_id, post_id, user_id)
);

CREATE TABLE follow (
    follower_id bigint      NOT NULL,
    followed_id bigint      NOT NULL,
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (follower_id, followed_id)
);

CREATE TABLE hashtag (
    id          bigint       PRIMARY KEY,
    name        varchar(100) NOT NULL UNIQUE,
    posts_count integer      NOT NULL
);

SELECT create_distributed_table('app_user', 'id');
SELECT create_distributed_table('post', 'author_id', colocate_with => 'app_user');
SELECT create_distributed_table('post_like', 'post_author_id', colocate_with => 'app_user');
SELECT create_distributed_table('follow', 'follower_id', colocate_with => 'app_user');
SELECT create_reference_table('hashtag');

-- A foreign key between co-located tables is allowed because both rows are always on the same shard
ALTER TABLE post ADD CONSTRAINT fk_post_author FOREIGN KEY (author_id) REFERENCES app_user (id);
ALTER TABLE post_like ADD CONSTRAINT fk_like_post FOREIGN KEY (post_author_id, post_id) REFERENCES post (author_id, id);

CREATE INDEX ix_post_author_created ON post (author_id, created_at DESC, id DESC);
CREATE INDEX ix_post_like_created ON post_like (created_at) INCLUDE (post_id);

SELECT logicalrelid::regclass AS table_name, partmethod, colocationid,
       (SELECT count(*) FROM pg_dist_shard s WHERE s.logicalrelid = p.logicalrelid) AS shards
FROM pg_dist_partition p ORDER BY colocationid, 1;
