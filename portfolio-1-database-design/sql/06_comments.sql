-- FitsCheck catalog documentation. Descriptions live in the database so the generated data
-- dictionary (07_data_dictionary.sql) always matches the real schema.

SET search_path = fitscheck;

COMMENT ON SCHEMA fitscheck IS 'FitsCheck: outfit posts, community likes and votes, and style challenges';

COMMENT ON TYPE device_platform IS 'Platforms that can receive push notifications';
COMMENT ON TYPE report_status IS 'Moderation lifecycle of a report';

COMMENT ON TABLE app_user IS 'A person with a FitsCheck account. Deactivated, never deleted, while they own content (BR-05)';
COMMENT ON COLUMN app_user.id IS 'Surrogate key';
COMMENT ON COLUMN app_user.username IS 'Public handle, 3 to 30 of letters, digits, underscore or dot; unique ignoring case (BR-01)';
COMMENT ON COLUMN app_user.email IS 'Login email; unique ignoring case (BR-01)';
COMMENT ON COLUMN app_user.password_hash IS 'Password hash produced by the application; never the raw password';
COMMENT ON COLUMN app_user.full_name IS 'Display name';
COMMENT ON COLUMN app_user.bio IS 'Optional profile text';
COMMENT ON COLUMN app_user.avatar_url IS 'Optional profile picture location';
COMMENT ON COLUMN app_user.style_points IS 'Running total of points from challenge wins; never negative (BR-17)';
COMMENT ON COLUMN app_user.is_active IS 'False once the account is deactivated';
COMMENT ON COLUMN app_user.is_admin IS 'Can run challenges and moderate reports';
COMMENT ON COLUMN app_user.created_at IS 'When the account was created';
COMMENT ON COLUMN app_user.updated_at IS 'Last profile change, stamped by trigger';

COMMENT ON TABLE user_device IS 'A device registered for push notifications';
COMMENT ON COLUMN user_device.id IS 'Surrogate key';
COMMENT ON COLUMN user_device.user_id IS 'Owner of the device';
COMMENT ON COLUMN user_device.push_token IS 'Push service token; belongs to exactly one device (BR-04)';
COMMENT ON COLUMN user_device.platform IS 'ios, android or web';
COMMENT ON COLUMN user_device.last_seen_at IS 'Last time the device contacted the service';
COMMENT ON COLUMN user_device.created_at IS 'When the device was registered';

COMMENT ON TABLE follow IS 'User A follows user B (M:N self relationship, BR-02)';
COMMENT ON COLUMN follow.follower_id IS 'The user who follows';
COMMENT ON COLUMN follow.followed_id IS 'The user being followed; never the follower';
COMMENT ON COLUMN follow.created_at IS 'When the follow started';

COMMENT ON TABLE block IS 'User A blocks user B; B can then not follow A (BR-03)';
COMMENT ON COLUMN block.blocker_id IS 'The user who blocks';
COMMENT ON COLUMN block.blocked_id IS 'The user being blocked; never the blocker';
COMMENT ON COLUMN block.created_at IS 'When the block was made';

COMMENT ON TABLE post IS 'A fit: one outfit post with 1 to 10 images (BR-06, BR-07)';
COMMENT ON COLUMN post.id IS 'Surrogate key';
COMMENT ON COLUMN post.author_id IS 'The user who posted it';
COMMENT ON COLUMN post.caption IS 'Optional caption, up to 2,200 characters';
COMMENT ON COLUMN post.likes_count IS 'Derived counter of post_like rows, kept in the same transaction (BR-20)';
COMMENT ON COLUMN post.comments_count IS 'Derived counter of comment rows, kept in the same transaction (BR-20)';
COMMENT ON COLUMN post.created_at IS 'When it was posted';
COMMENT ON COLUMN post.updated_at IS 'Last edit, stamped by trigger';

COMMENT ON TABLE post_image IS 'One outfit photo within a post, in display order';
COMMENT ON COLUMN post_image.id IS 'Surrogate key';
COMMENT ON COLUMN post_image.post_id IS 'The post it belongs to';
COMMENT ON COLUMN post_image.position IS 'Display order 1 to 10, unique within the post (BR-07)';
COMMENT ON COLUMN post_image.image_url IS 'Image location';
COMMENT ON COLUMN post_image.created_at IS 'When it was uploaded';

COMMENT ON TABLE brand IS 'A clothing brand that shop items can name';
COMMENT ON COLUMN brand.id IS 'Surrogate key';
COMMENT ON COLUMN brand.name IS 'Brand name, unique';
COMMENT ON COLUMN brand.website IS 'Optional brand website';

COMMENT ON TABLE shop_item IS 'A piece of clothing tagged on an image, with where to buy it (BR-08)';
COMMENT ON COLUMN shop_item.id IS 'Surrogate key';
COMMENT ON COLUMN shop_item.post_image_id IS 'The image the item appears in';
COMMENT ON COLUMN shop_item.brand_id IS 'Optional brand; cleared if the brand is deleted';
COMMENT ON COLUMN shop_item.item_name IS 'What the item is, e.g. Linen shirt';
COMMENT ON COLUMN shop_item.price IS 'Price in major units, zero or more';
COMMENT ON COLUMN shop_item.currency IS 'Three-letter ISO currency code, e.g. NGN';
COMMENT ON COLUMN shop_item.affiliate_url IS 'Optional link to buy the item';
COMMENT ON COLUMN shop_item.promo_code IS 'Optional discount code';

COMMENT ON TABLE hashtag IS 'A lowercase tag that groups posts (BR-09)';
COMMENT ON COLUMN hashtag.id IS 'Surrogate key';
COMMENT ON COLUMN hashtag.name IS 'Tag text without #, lowercase letters, digits and underscore, unique';
COMMENT ON COLUMN hashtag.posts_count IS 'Derived counter of post_hashtag rows (BR-20)';
COMMENT ON COLUMN hashtag.created_at IS 'When the tag was first used';

COMMENT ON TABLE post_hashtag IS 'Which hashtags a post carries (M:N junction)';
COMMENT ON COLUMN post_hashtag.post_id IS 'The tagged post';
COMMENT ON COLUMN post_hashtag.hashtag_id IS 'The tag';

COMMENT ON TABLE post_like IS 'A user likes a post, at most once (BR-10)';
COMMENT ON COLUMN post_like.user_id IS 'The user who liked';
COMMENT ON COLUMN post_like.post_id IS 'The liked post';
COMMENT ON COLUMN post_like.created_at IS 'When the like was given';

COMMENT ON TABLE vote IS 'A user picks the best look in a post: one vote per user per post, never on their own post (BR-11, BR-12)';
COMMENT ON COLUMN vote.id IS 'Surrogate key';
COMMENT ON COLUMN vote.user_id IS 'The voter';
COMMENT ON COLUMN vote.post_id IS 'The voted post; derivable from the image but kept so one vote per post is a UNIQUE constraint (3NF, not BCNF)';
COMMENT ON COLUMN vote.post_image_id IS 'The look the voter picked; must belong to the voted post';
COMMENT ON COLUMN vote.created_at IS 'When the vote was cast';

COMMENT ON TABLE comment IS 'A comment on a post, or a reply to another comment on the same post (BR-13)';
COMMENT ON COLUMN comment.id IS 'Surrogate key';
COMMENT ON COLUMN comment.post_id IS 'The post commented on; a reply must match its parent';
COMMENT ON COLUMN comment.author_id IS 'The user who wrote it';
COMMENT ON COLUMN comment.parent_id IS 'The comment being replied to; NULL for a top-level comment';
COMMENT ON COLUMN comment.body IS 'Comment text, 1 to 2,000 characters';
COMMENT ON COLUMN comment.created_at IS 'When it was written';
COMMENT ON COLUMN comment.updated_at IS 'Last edit, stamped by trigger';

COMMENT ON TABLE challenge IS 'A timed style challenge that users enter and the community votes on';
COMMENT ON COLUMN challenge.id IS 'Surrogate key';
COMMENT ON COLUMN challenge.slug IS 'URL name, lowercase words joined by hyphens, unique';
COMMENT ON COLUMN challenge.title IS 'Display title';
COMMENT ON COLUMN challenge.description IS 'Optional rules and theme';
COMMENT ON COLUMN challenge.starts_at IS 'When entries open; before ends_at (BR-14)';
COMMENT ON COLUMN challenge.ends_at IS 'When entries close';
COMMENT ON COLUMN challenge.max_entries IS 'Entry limit, greater than zero (BR-14, BR-16)';
COMMENT ON COLUMN challenge.reward_points IS 'Style points awarded to the winner';
COMMENT ON COLUMN challenge.entries_count IS 'Derived counter of challenge_entry rows (BR-20)';
COMMENT ON COLUMN challenge.winner_entry_id IS 'Winning entry of this challenge; NULL until closed (BR-17)';
COMMENT ON COLUMN challenge.created_at IS 'When the challenge was created';

COMMENT ON TABLE challenge_entry IS 'A user enters a challenge with one of their own posts, once per challenge (BR-15)';
COMMENT ON COLUMN challenge_entry.id IS 'Surrogate key';
COMMENT ON COLUMN challenge_entry.challenge_id IS 'The challenge entered';
COMMENT ON COLUMN challenge_entry.user_id IS 'The entrant; derivable from the post but kept so one entry per user is a UNIQUE constraint';
COMMENT ON COLUMN challenge_entry.post_id IS 'The entered post; must be written by the entrant';
COMMENT ON COLUMN challenge_entry.created_at IS 'When the entry was made';

COMMENT ON TABLE report IS 'A moderation report about exactly one user, post or comment (BR-18)';
COMMENT ON COLUMN report.id IS 'Surrogate key';
COMMENT ON COLUMN report.reporter_id IS 'The user who filed the report';
COMMENT ON COLUMN report.target_user_id IS 'Reported user, if the target is a user';
COMMENT ON COLUMN report.target_post_id IS 'Reported post, if the target is a post';
COMMENT ON COLUMN report.target_comment_id IS 'Reported comment, if the target is a comment';
COMMENT ON COLUMN report.reason IS 'Short reason category, e.g. spam';
COMMENT ON COLUMN report.details IS 'Optional free-text explanation';
COMMENT ON COLUMN report.status IS 'open, reviewing, actioned or dismissed; closed statuses need a review time';
COMMENT ON COLUMN report.reviewed_by IS 'Moderator who reviewed it; set together with reviewed_at';
COMMENT ON COLUMN report.reviewed_at IS 'When it was reviewed';
COMMENT ON COLUMN report.created_at IS 'When it was filed';

COMMENT ON TABLE notification IS 'A message shown to one user, starting unread (BR-19)';
COMMENT ON COLUMN notification.id IS 'Surrogate key';
COMMENT ON COLUMN notification.recipient_id IS 'The user it is for';
COMMENT ON COLUMN notification.type IS 'Kind of event, e.g. like, follow, challenge_won';
COMMENT ON COLUMN notification.title IS 'Headline text';
COMMENT ON COLUMN notification.body IS 'Optional detail text';
COMMENT ON COLUMN notification.is_read IS 'True once the user has seen it';
COMMENT ON COLUMN notification.created_at IS 'When it was created';

COMMENT ON VIEW v_post_card IS 'One feed card: post, author, cover image (position 1) and counts; hides deactivated authors';
COMMENT ON VIEW v_counter_drift IS 'Stored counters that differ from the rows they count; empty means no drift (BR-20)';
