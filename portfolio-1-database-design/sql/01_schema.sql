-- FitsCheck schema: types and tables with primary keys and column defaults.
-- Keys beyond the primary key, checks and foreign keys are in 02_constraints.sql.
-- Re-run from scratch with: DROP SCHEMA fitscheck CASCADE;

CREATE SCHEMA fitscheck;
SET search_path = fitscheck;

CREATE TYPE device_platform AS ENUM ('ios', 'android', 'web');
CREATE TYPE report_status AS ENUM ('open', 'reviewing', 'actioned', 'dismissed');

CREATE TABLE app_user (
    id            bigint GENERATED ALWAYS AS IDENTITY,
    username      varchar(30)  NOT NULL,
    email         varchar(255) NOT NULL,
    password_hash text         NOT NULL,
    full_name     varchar(100) NOT NULL,
    bio           varchar(300),
    avatar_url    text,
    style_points  integer      NOT NULL DEFAULT 0,
    is_active     boolean      NOT NULL DEFAULT true,
    is_admin      boolean      NOT NULL DEFAULT false,
    created_at    timestamptz  NOT NULL DEFAULT now(),
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_app_user PRIMARY KEY (id)
);

CREATE TABLE user_device (
    id           bigint GENERATED ALWAYS AS IDENTITY,
    user_id      bigint          NOT NULL,
    push_token   text            NOT NULL,
    platform     device_platform NOT NULL,
    last_seen_at timestamptz,
    created_at   timestamptz     NOT NULL DEFAULT now(),
    CONSTRAINT pk_user_device PRIMARY KEY (id)
);

CREATE TABLE follow (
    follower_id bigint      NOT NULL,
    followed_id bigint      NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_follow PRIMARY KEY (follower_id, followed_id)
);

CREATE TABLE block (
    blocker_id bigint      NOT NULL,
    blocked_id bigint      NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_block PRIMARY KEY (blocker_id, blocked_id)
);

CREATE TABLE post (
    id             bigint GENERATED ALWAYS AS IDENTITY,
    author_id      bigint        NOT NULL,
    caption        varchar(2200),
    likes_count    integer       NOT NULL DEFAULT 0,
    comments_count integer       NOT NULL DEFAULT 0,
    created_at     timestamptz   NOT NULL DEFAULT now(),
    updated_at     timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_post PRIMARY KEY (id)
);

CREATE TABLE post_image (
    id         bigint GENERATED ALWAYS AS IDENTITY,
    post_id    bigint      NOT NULL,
    position   smallint    NOT NULL,
    image_url  text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_post_image PRIMARY KEY (id)
);

CREATE TABLE brand (
    id      bigint GENERATED ALWAYS AS IDENTITY,
    name    varchar(100) NOT NULL,
    website text,
    CONSTRAINT pk_brand PRIMARY KEY (id)
);

CREATE TABLE shop_item (
    id            bigint GENERATED ALWAYS AS IDENTITY,
    post_image_id bigint        NOT NULL,
    brand_id      bigint,
    item_name     varchar(150)  NOT NULL,
    price         numeric(12,2) NOT NULL,
    currency      char(3)       NOT NULL,
    affiliate_url text,
    promo_code    varchar(50),
    CONSTRAINT pk_shop_item PRIMARY KEY (id)
);

CREATE TABLE hashtag (
    id          bigint GENERATED ALWAYS AS IDENTITY,
    name        varchar(100) NOT NULL,
    posts_count integer      NOT NULL DEFAULT 0,
    created_at  timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_hashtag PRIMARY KEY (id)
);

CREATE TABLE post_hashtag (
    post_id    bigint NOT NULL,
    hashtag_id bigint NOT NULL,
    CONSTRAINT pk_post_hashtag PRIMARY KEY (post_id, hashtag_id)
);

CREATE TABLE post_like (
    user_id    bigint      NOT NULL,
    post_id    bigint      NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_post_like PRIMARY KEY (user_id, post_id)
);

CREATE TABLE vote (
    id            bigint GENERATED ALWAYS AS IDENTITY,
    user_id       bigint      NOT NULL,
    post_id       bigint      NOT NULL,
    post_image_id bigint      NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_vote PRIMARY KEY (id)
);

CREATE TABLE comment (
    id         bigint GENERATED ALWAYS AS IDENTITY,
    post_id    bigint        NOT NULL,
    author_id  bigint        NOT NULL,
    parent_id  bigint,
    body       varchar(2000) NOT NULL,
    created_at timestamptz   NOT NULL DEFAULT now(),
    updated_at timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_comment PRIMARY KEY (id)
);

CREATE TABLE challenge (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    slug            varchar(120) NOT NULL,
    title           varchar(200) NOT NULL,
    description     text,
    starts_at       timestamptz  NOT NULL,
    ends_at         timestamptz  NOT NULL,
    max_entries     integer      NOT NULL,
    reward_points   integer      NOT NULL DEFAULT 100,
    entries_count   integer      NOT NULL DEFAULT 0,
    winner_entry_id bigint,
    created_at      timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_challenge PRIMARY KEY (id)
);

CREATE TABLE challenge_entry (
    id           bigint GENERATED ALWAYS AS IDENTITY,
    challenge_id bigint      NOT NULL,
    user_id      bigint      NOT NULL,
    post_id      bigint      NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_challenge_entry PRIMARY KEY (id)
);

CREATE TABLE report (
    id                bigint GENERATED ALWAYS AS IDENTITY,
    reporter_id       bigint        NOT NULL,
    target_user_id    bigint,
    target_post_id    bigint,
    target_comment_id bigint,
    reason            varchar(50)   NOT NULL,
    details           varchar(1000),
    status            report_status NOT NULL DEFAULT 'open',
    reviewed_by       bigint,
    reviewed_at       timestamptz,
    created_at        timestamptz   NOT NULL DEFAULT now(),
    CONSTRAINT pk_report PRIMARY KEY (id)
);

CREATE TABLE notification (
    id           bigint GENERATED ALWAYS AS IDENTITY,
    recipient_id bigint       NOT NULL,
    type         varchar(30)  NOT NULL,
    title        varchar(150) NOT NULL,
    body         varchar(500),
    is_read      boolean      NOT NULL DEFAULT false,
    created_at   timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT pk_notification PRIMARY KEY (id)
);
