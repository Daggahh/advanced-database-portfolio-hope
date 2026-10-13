-- FitsCheck constraints: alternate keys, checks and foreign keys.
-- BR-xx refers to business-rules.md. Unique keys come first because the composite
-- foreign keys below need their target keys to exist.

SET search_path = fitscheck;

-- Case-insensitive uniqueness needs an expression index; a UNIQUE constraint cannot use lower() (BR-01)
CREATE UNIQUE INDEX uq_app_user_username_ci ON app_user (lower(username));
CREATE UNIQUE INDEX uq_app_user_email_ci ON app_user (lower(email));

ALTER TABLE user_device ADD CONSTRAINT uq_user_device_push_token UNIQUE (push_token);
ALTER TABLE brand ADD CONSTRAINT uq_brand_name UNIQUE (name);
ALTER TABLE hashtag ADD CONSTRAINT uq_hashtag_name UNIQUE (name);
ALTER TABLE challenge ADD CONSTRAINT uq_challenge_slug UNIQUE (slug);

ALTER TABLE post_image ADD CONSTRAINT uq_post_image_post_position UNIQUE (post_id, position);
ALTER TABLE vote ADD CONSTRAINT uq_vote_user_post UNIQUE (user_id, post_id);
ALTER TABLE challenge_entry ADD CONSTRAINT uq_entry_challenge_user UNIQUE (challenge_id, user_id);

-- Redundant as keys (id is already unique), but a composite foreign key can only reference a declared key
ALTER TABLE post ADD CONSTRAINT uq_post_id_author UNIQUE (id, author_id);
ALTER TABLE post_image ADD CONSTRAINT uq_post_image_id_post UNIQUE (id, post_id);
ALTER TABLE comment ADD CONSTRAINT uq_comment_id_post UNIQUE (id, post_id);
ALTER TABLE challenge_entry ADD CONSTRAINT uq_entry_id_challenge UNIQUE (id, challenge_id);

ALTER TABLE app_user
    ADD CONSTRAINT ck_app_user_username_format CHECK (username ~ '^[A-Za-z0-9_.]{3,30}$'),
    ADD CONSTRAINT ck_app_user_email_format CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    ADD CONSTRAINT ck_app_user_style_points_nonneg CHECK (style_points >= 0);

ALTER TABLE follow ADD CONSTRAINT ck_follow_not_self CHECK (follower_id <> followed_id);
ALTER TABLE block ADD CONSTRAINT ck_block_not_self CHECK (blocker_id <> blocked_id);

ALTER TABLE post
    ADD CONSTRAINT ck_post_likes_count_nonneg CHECK (likes_count >= 0),
    ADD CONSTRAINT ck_post_comments_count_nonneg CHECK (comments_count >= 0);

ALTER TABLE post_image ADD CONSTRAINT ck_post_image_position_range CHECK (position BETWEEN 1 AND 10);

ALTER TABLE shop_item
    ADD CONSTRAINT ck_shop_item_price_nonneg CHECK (price >= 0),
    ADD CONSTRAINT ck_shop_item_currency_iso CHECK (currency ~ '^[A-Z]{3}$');

ALTER TABLE hashtag
    ADD CONSTRAINT ck_hashtag_name_format CHECK (name ~ '^[a-z0-9_]{1,100}$'),
    ADD CONSTRAINT ck_hashtag_posts_count_nonneg CHECK (posts_count >= 0);

ALTER TABLE comment
    ADD CONSTRAINT ck_comment_body_length CHECK (char_length(body) BETWEEN 1 AND 2000),
    ADD CONSTRAINT ck_comment_not_own_parent CHECK (parent_id <> id);

ALTER TABLE challenge
    ADD CONSTRAINT ck_challenge_slug_format CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    ADD CONSTRAINT ck_challenge_dates CHECK (starts_at < ends_at),
    ADD CONSTRAINT ck_challenge_max_entries_positive CHECK (max_entries > 0),
    ADD CONSTRAINT ck_challenge_reward_nonneg CHECK (reward_points >= 0),
    ADD CONSTRAINT ck_challenge_entries_count_nonneg CHECK (entries_count >= 0);

ALTER TABLE report
    ADD CONSTRAINT ck_report_one_target
        CHECK (num_nonnulls(target_user_id, target_post_id, target_comment_id) = 1),
    ADD CONSTRAINT ck_report_review_pair CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL)),
    ADD CONSTRAINT ck_report_reviewed_when_closed
        CHECK (status IN ('open', 'reviewing') OR reviewed_at IS NOT NULL);

-- Accounts are deactivated, not deleted (BR-05), so references to app_user from content RESTRICT.
-- Deleting a post removes everything that only exists because of it.

ALTER TABLE user_device ADD CONSTRAINT fk_user_device_user
    FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE CASCADE;

ALTER TABLE follow
    ADD CONSTRAINT fk_follow_follower FOREIGN KEY (follower_id) REFERENCES app_user (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_follow_followed FOREIGN KEY (followed_id) REFERENCES app_user (id) ON DELETE CASCADE;

ALTER TABLE block
    ADD CONSTRAINT fk_block_blocker FOREIGN KEY (blocker_id) REFERENCES app_user (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_block_blocked FOREIGN KEY (blocked_id) REFERENCES app_user (id) ON DELETE CASCADE;

ALTER TABLE post ADD CONSTRAINT fk_post_author
    FOREIGN KEY (author_id) REFERENCES app_user (id) ON DELETE RESTRICT;

ALTER TABLE post_image ADD CONSTRAINT fk_post_image_post
    FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE;

ALTER TABLE shop_item
    ADD CONSTRAINT fk_shop_item_image FOREIGN KEY (post_image_id) REFERENCES post_image (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_shop_item_brand FOREIGN KEY (brand_id) REFERENCES brand (id) ON DELETE SET NULL;

ALTER TABLE post_hashtag
    ADD CONSTRAINT fk_post_hashtag_post FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_post_hashtag_hashtag FOREIGN KEY (hashtag_id) REFERENCES hashtag (id) ON DELETE RESTRICT;

ALTER TABLE post_like
    ADD CONSTRAINT fk_post_like_user FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_post_like_post FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE;

-- The chosen image must belong to the voted post (BR-11)
ALTER TABLE vote
    ADD CONSTRAINT fk_vote_user FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_vote_post_image FOREIGN KEY (post_image_id, post_id)
        REFERENCES post_image (id, post_id) ON DELETE CASCADE;

-- A reply must be on its parent's post (BR-13); a NULL parent_id skips the check (MATCH SIMPLE)
ALTER TABLE comment
    ADD CONSTRAINT fk_comment_post FOREIGN KEY (post_id) REFERENCES post (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_comment_author FOREIGN KEY (author_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_comment_parent FOREIGN KEY (parent_id, post_id)
        REFERENCES comment (id, post_id) ON DELETE CASCADE;

-- The entry's post must be written by the entrant (BR-15)
ALTER TABLE challenge_entry
    ADD CONSTRAINT fk_entry_challenge FOREIGN KEY (challenge_id) REFERENCES challenge (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_entry_user FOREIGN KEY (user_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_entry_own_post FOREIGN KEY (post_id, user_id)
        REFERENCES post (id, author_id) ON DELETE RESTRICT;

-- The winner must be an entry of this same challenge (BR-17)
ALTER TABLE challenge ADD CONSTRAINT fk_challenge_winner
    FOREIGN KEY (winner_entry_id, id) REFERENCES challenge_entry (id, challenge_id) ON DELETE RESTRICT;

ALTER TABLE report
    ADD CONSTRAINT fk_report_reporter FOREIGN KEY (reporter_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_report_target_user FOREIGN KEY (target_user_id) REFERENCES app_user (id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_report_target_post FOREIGN KEY (target_post_id) REFERENCES post (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_report_target_comment FOREIGN KEY (target_comment_id) REFERENCES comment (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_report_reviewer FOREIGN KEY (reviewed_by) REFERENCES app_user (id) ON DELETE RESTRICT;

ALTER TABLE notification ADD CONSTRAINT fk_notification_recipient
    FOREIGN KEY (recipient_id) REFERENCES app_user (id) ON DELETE CASCADE;
