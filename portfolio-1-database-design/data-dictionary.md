# FitsCheck Data Dictionary

Generated from the PostgreSQL catalog by `sql/07_data_dictionary.sql`; descriptions come from `sql/06_comments.sql`. Do not edit by hand: change the schema or comments and regenerate.

FitsCheck: outfit posts, community likes and votes, and style challenges

## Enum types

| Type | Values | Description |
|---|---|---|
| `device_platform` | ios, android, web | Platforms that can receive push notifications |
| `report_status` | open, reviewing, actioned, dismissed | Moderation lifecycle of a report |

## Views

| View | Description |
|---|---|
| `v_counter_drift` | Stored counters that differ from the rows they count; empty means no drift (BR-20) |
| `v_post_card` | One feed card: post, author, cover image (position 1) and counts; hides deactivated authors |

## Tables (17)

### app_user

A person with a FitsCheck account. Deactivated, never deleted, while they own content (BR-05)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `username` | character varying(30) | NOT NULL |  |  | Public handle, 3 to 30 of letters, digits, underscore or dot; unique ignoring case (BR-01) |
| `email` | character varying(255) | NOT NULL |  |  | Login email; unique ignoring case (BR-01) |
| `password_hash` | text | NOT NULL |  |  | Password hash produced by the application; never the raw password |
| `full_name` | character varying(100) | NOT NULL |  |  | Display name |
| `bio` | character varying(300) | null |  |  | Optional profile text |
| `avatar_url` | text | null |  |  | Optional profile picture location |
| `style_points` | integer | NOT NULL | 0 |  | Running total of points from challenge wins; never negative (BR-17) |
| `is_active` | boolean | NOT NULL | true |  | False once the account is deactivated |
| `is_admin` | boolean | NOT NULL | false |  | Can run challenges and moderate reports |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the account was created |
| `updated_at` | timestamp with time zone | NOT NULL | now() |  | Last profile change, stamped by trigger |

**Constraints**

- `pk_app_user`: `PRIMARY KEY (id)`
- `ck_app_user_email_format`: `CHECK (((email)::text ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'::text))`
- `ck_app_user_style_points_nonneg`: `CHECK ((style_points >= 0))`
- `ck_app_user_username_format`: `CHECK (((username)::text ~ '^[A-Za-z0-9_.]{3,30}$'::text))`

**Other indexes**

- `uq_app_user_email_ci`: `CREATE UNIQUE INDEX uq_app_user_email_ci ON fitscheck.app_user USING btree (lower((email)::text))`
- `uq_app_user_username_ci`: `CREATE UNIQUE INDEX uq_app_user_username_ci ON fitscheck.app_user USING btree (lower((username)::text))`

**Triggers**

- `trg_app_user_updated_at`: CREATE TRIGGER trg_app_user_updated_at BEFORE UPDATE ON fitscheck.app_user FOR EACH ROW EXECUTE FUNCTION set_updated_at()

### user_device

A device registered for push notifications

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `user_id` | bigint | NOT NULL |  | FK to app_user | Owner of the device |
| `push_token` | text | NOT NULL |  |  | Push service token; belongs to exactly one device (BR-04) |
| `platform` | device_platform | NOT NULL |  |  | ios, android or web |
| `last_seen_at` | timestamp with time zone | null |  |  | Last time the device contacted the service |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the device was registered |

**Constraints**

- `pk_user_device`: `PRIMARY KEY (id)`
- `uq_user_device_push_token`: `UNIQUE (push_token)`
- `fk_user_device_user`: `FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE`

### follow

User A follows user B (M:N self relationship, BR-02)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `follower_id` | bigint | NOT NULL |  | FK to app_user, PK | The user who follows |
| `followed_id` | bigint | NOT NULL |  | FK to app_user, PK | The user being followed; never the follower |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the follow started |

**Constraints**

- `pk_follow`: `PRIMARY KEY (follower_id, followed_id)`
- `fk_follow_followed`: `FOREIGN KEY (followed_id) REFERENCES app_user(id) ON DELETE CASCADE`
- `fk_follow_follower`: `FOREIGN KEY (follower_id) REFERENCES app_user(id) ON DELETE CASCADE`
- `ck_follow_not_self`: `CHECK ((follower_id <> followed_id))`

**Triggers**

- `trg_follow_not_blocked`: CREATE TRIGGER trg_follow_not_blocked BEFORE INSERT OR UPDATE ON fitscheck.follow FOR EACH ROW EXECUTE FUNCTION follow_not_blocked()

### block

User A blocks user B; B can then not follow A (BR-03)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `blocker_id` | bigint | NOT NULL |  | FK to app_user, PK | The user who blocks |
| `blocked_id` | bigint | NOT NULL |  | FK to app_user, PK | The user being blocked; never the blocker |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the block was made |

**Constraints**

- `pk_block`: `PRIMARY KEY (blocker_id, blocked_id)`
- `fk_block_blocked`: `FOREIGN KEY (blocked_id) REFERENCES app_user(id) ON DELETE CASCADE`
- `fk_block_blocker`: `FOREIGN KEY (blocker_id) REFERENCES app_user(id) ON DELETE CASCADE`
- `ck_block_not_self`: `CHECK ((blocker_id <> blocked_id))`

**Triggers**

- `trg_block_removes_follow`: CREATE TRIGGER trg_block_removes_follow AFTER INSERT ON fitscheck.block FOR EACH ROW EXECUTE FUNCTION block_removes_follow()

### post

A fit: one outfit post with 1 to 10 images (BR-06, BR-07)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `author_id` | bigint | NOT NULL |  | FK to app_user | The user who posted it |
| `caption` | character varying(2200) | null |  |  | Optional caption, up to 2,200 characters |
| `likes_count` | integer | NOT NULL | 0 |  | Derived counter of post_like rows, kept in the same transaction (BR-20) |
| `comments_count` | integer | NOT NULL | 0 |  | Derived counter of comment rows, kept in the same transaction (BR-20) |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When it was posted |
| `updated_at` | timestamp with time zone | NOT NULL | now() |  | Last edit, stamped by trigger |

**Constraints**

- `pk_post`: `PRIMARY KEY (id)`
- `uq_post_id_author`: `UNIQUE (id, author_id)`
- `fk_post_author`: `FOREIGN KEY (author_id) REFERENCES app_user(id) ON DELETE RESTRICT`
- `ck_post_comments_count_nonneg`: `CHECK ((comments_count >= 0))`
- `ck_post_likes_count_nonneg`: `CHECK ((likes_count >= 0))`

**Triggers**

- `trg_post_updated_at`: CREATE TRIGGER trg_post_updated_at BEFORE UPDATE ON fitscheck.post FOR EACH ROW EXECUTE FUNCTION set_updated_at()

### post_image

One outfit photo within a post, in display order

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `post_id` | bigint | NOT NULL |  | FK to post | The post it belongs to |
| `position` | smallint | NOT NULL |  |  | Display order 1 to 10, unique within the post (BR-07) |
| `image_url` | text | NOT NULL |  |  | Image location |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When it was uploaded |

**Constraints**

- `pk_post_image`: `PRIMARY KEY (id)`
- `uq_post_image_id_post`: `UNIQUE (id, post_id)`
- `uq_post_image_post_position`: `UNIQUE (post_id, "position")`
- `fk_post_image_post`: `FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE`
- `ck_post_image_position_range`: `CHECK ((("position" >= 1) AND ("position" <= 10)))`

### brand

A clothing brand that shop items can name

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `name` | character varying(100) | NOT NULL |  |  | Brand name, unique |
| `website` | text | null |  |  | Optional brand website |

**Constraints**

- `pk_brand`: `PRIMARY KEY (id)`
- `uq_brand_name`: `UNIQUE (name)`

### shop_item

A piece of clothing tagged on an image, with where to buy it (BR-08)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `post_image_id` | bigint | NOT NULL |  | FK to post_image | The image the item appears in |
| `brand_id` | bigint | null |  | FK to brand | Optional brand; cleared if the brand is deleted |
| `item_name` | character varying(150) | NOT NULL |  |  | What the item is, e.g. Linen shirt |
| `price` | numeric(12,2) | NOT NULL |  |  | Price in major units, zero or more |
| `currency` | character(3) | NOT NULL |  |  | Three-letter ISO currency code, e.g. NGN |
| `affiliate_url` | text | null |  |  | Optional link to buy the item |
| `promo_code` | character varying(50) | null |  |  | Optional discount code |

**Constraints**

- `pk_shop_item`: `PRIMARY KEY (id)`
- `fk_shop_item_brand`: `FOREIGN KEY (brand_id) REFERENCES brand(id) ON DELETE SET NULL`
- `fk_shop_item_image`: `FOREIGN KEY (post_image_id) REFERENCES post_image(id) ON DELETE CASCADE`
- `ck_shop_item_currency_iso`: `CHECK ((currency ~ '^[A-Z]{3}$'::text))`
- `ck_shop_item_price_nonneg`: `CHECK ((price >= (0)::numeric))`

### hashtag

A lowercase tag that groups posts (BR-09)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `name` | character varying(100) | NOT NULL |  |  | Tag text without #, lowercase letters, digits and underscore, unique |
| `posts_count` | integer | NOT NULL | 0 |  | Derived counter of post_hashtag rows (BR-20) |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the tag was first used |

**Constraints**

- `pk_hashtag`: `PRIMARY KEY (id)`
- `uq_hashtag_name`: `UNIQUE (name)`
- `ck_hashtag_name_format`: `CHECK (((name)::text ~ '^[a-z0-9_]{1,100}$'::text))`
- `ck_hashtag_posts_count_nonneg`: `CHECK ((posts_count >= 0))`

### post_hashtag

Which hashtags a post carries (M:N junction)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `post_id` | bigint | NOT NULL |  | FK to post, PK | The tagged post |
| `hashtag_id` | bigint | NOT NULL |  | FK to hashtag, PK | The tag |

**Constraints**

- `pk_post_hashtag`: `PRIMARY KEY (post_id, hashtag_id)`
- `fk_post_hashtag_hashtag`: `FOREIGN KEY (hashtag_id) REFERENCES hashtag(id) ON DELETE RESTRICT`
- `fk_post_hashtag_post`: `FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE`

### post_like

A user likes a post, at most once (BR-10)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `user_id` | bigint | NOT NULL |  | FK to app_user, PK | The user who liked |
| `post_id` | bigint | NOT NULL |  | FK to post, PK | The liked post |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the like was given |

**Constraints**

- `pk_post_like`: `PRIMARY KEY (user_id, post_id)`
- `fk_post_like_post`: `FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE`
- `fk_post_like_user`: `FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE RESTRICT`

### vote

A user picks the best look in a post: one vote per user per post, never on their own post (BR-11, BR-12)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `user_id` | bigint | NOT NULL |  | FK to app_user | The voter |
| `post_id` | bigint | NOT NULL |  | FK to post_image | The voted post; derivable from the image but kept so one vote per post is a UNIQUE constraint (3NF, not BCNF) |
| `post_image_id` | bigint | NOT NULL |  | FK to post_image | The look the voter picked; must belong to the voted post |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the vote was cast |

**Constraints**

- `pk_vote`: `PRIMARY KEY (id)`
- `uq_vote_user_post`: `UNIQUE (user_id, post_id)`
- `fk_vote_post_image`: `FOREIGN KEY (post_image_id, post_id) REFERENCES post_image(id, post_id) ON DELETE CASCADE`
- `fk_vote_user`: `FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE RESTRICT`

**Triggers**

- `trg_vote_not_own_post`: CREATE TRIGGER trg_vote_not_own_post BEFORE INSERT OR UPDATE ON fitscheck.vote FOR EACH ROW EXECUTE FUNCTION vote_not_own_post()

### comment

A comment on a post, or a reply to another comment on the same post (BR-13)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `post_id` | bigint | NOT NULL |  | FK to comment, FK to post | The post commented on; a reply must match its parent |
| `author_id` | bigint | NOT NULL |  | FK to app_user | The user who wrote it |
| `parent_id` | bigint | null |  | FK to comment | The comment being replied to; NULL for a top-level comment |
| `body` | character varying(2000) | NOT NULL |  |  | Comment text, 1 to 2,000 characters |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When it was written |
| `updated_at` | timestamp with time zone | NOT NULL | now() |  | Last edit, stamped by trigger |

**Constraints**

- `pk_comment`: `PRIMARY KEY (id)`
- `uq_comment_id_post`: `UNIQUE (id, post_id)`
- `fk_comment_author`: `FOREIGN KEY (author_id) REFERENCES app_user(id) ON DELETE RESTRICT`
- `fk_comment_parent`: `FOREIGN KEY (parent_id, post_id) REFERENCES comment(id, post_id) ON DELETE CASCADE`
- `fk_comment_post`: `FOREIGN KEY (post_id) REFERENCES post(id) ON DELETE CASCADE`
- `ck_comment_body_length`: `CHECK (((char_length((body)::text) >= 1) AND (char_length((body)::text) <= 2000)))`
- `ck_comment_not_own_parent`: `CHECK ((parent_id <> id))`

**Triggers**

- `trg_comment_updated_at`: CREATE TRIGGER trg_comment_updated_at BEFORE UPDATE ON fitscheck.comment FOR EACH ROW EXECUTE FUNCTION set_updated_at()

### challenge

A timed style challenge that users enter and the community votes on

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | FK to challenge_entry, PK | Surrogate key |
| `slug` | character varying(120) | NOT NULL |  |  | URL name, lowercase words joined by hyphens, unique |
| `title` | character varying(200) | NOT NULL |  |  | Display title |
| `description` | text | null |  |  | Optional rules and theme |
| `starts_at` | timestamp with time zone | NOT NULL |  |  | When entries open; before ends_at (BR-14) |
| `ends_at` | timestamp with time zone | NOT NULL |  |  | When entries close |
| `max_entries` | integer | NOT NULL |  |  | Entry limit, greater than zero (BR-14, BR-16) |
| `reward_points` | integer | NOT NULL | 100 |  | Style points awarded to the winner |
| `entries_count` | integer | NOT NULL | 0 |  | Derived counter of challenge_entry rows (BR-20) |
| `winner_entry_id` | bigint | null |  | FK to challenge_entry | Winning entry of this challenge; NULL until closed (BR-17) |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the challenge was created |

**Constraints**

- `pk_challenge`: `PRIMARY KEY (id)`
- `uq_challenge_slug`: `UNIQUE (slug)`
- `fk_challenge_winner`: `FOREIGN KEY (winner_entry_id, id) REFERENCES challenge_entry(id, challenge_id) ON DELETE RESTRICT`
- `ck_challenge_dates`: `CHECK ((starts_at < ends_at))`
- `ck_challenge_entries_count_nonneg`: `CHECK ((entries_count >= 0))`
- `ck_challenge_max_entries_positive`: `CHECK ((max_entries > 0))`
- `ck_challenge_reward_nonneg`: `CHECK ((reward_points >= 0))`
- `ck_challenge_slug_format`: `CHECK (((slug)::text ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text))`

### challenge_entry

A user enters a challenge with one of their own posts, once per challenge (BR-15)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `challenge_id` | bigint | NOT NULL |  | FK to challenge | The challenge entered |
| `user_id` | bigint | NOT NULL |  | FK to app_user, FK to post | The entrant; derivable from the post but kept so one entry per user is a UNIQUE constraint |
| `post_id` | bigint | NOT NULL |  | FK to post | The entered post; must be written by the entrant |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When the entry was made |

**Constraints**

- `pk_challenge_entry`: `PRIMARY KEY (id)`
- `uq_entry_challenge_user`: `UNIQUE (challenge_id, user_id)`
- `uq_entry_id_challenge`: `UNIQUE (id, challenge_id)`
- `fk_entry_challenge`: `FOREIGN KEY (challenge_id) REFERENCES challenge(id) ON DELETE RESTRICT`
- `fk_entry_own_post`: `FOREIGN KEY (post_id, user_id) REFERENCES post(id, author_id) ON DELETE RESTRICT`
- `fk_entry_user`: `FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE RESTRICT`

### report

A moderation report about exactly one user, post or comment (BR-18)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `reporter_id` | bigint | NOT NULL |  | FK to app_user | The user who filed the report |
| `target_user_id` | bigint | null |  | FK to app_user | Reported user, if the target is a user |
| `target_post_id` | bigint | null |  | FK to post | Reported post, if the target is a post |
| `target_comment_id` | bigint | null |  | FK to comment | Reported comment, if the target is a comment |
| `reason` | character varying(50) | NOT NULL |  |  | Short reason category, e.g. spam |
| `details` | character varying(1000) | null |  |  | Optional free-text explanation |
| `status` | report_status | NOT NULL | 'open'::report_status |  | open, reviewing, actioned or dismissed; closed statuses need a review time |
| `reviewed_by` | bigint | null |  | FK to app_user | Moderator who reviewed it; set together with reviewed_at |
| `reviewed_at` | timestamp with time zone | null |  |  | When it was reviewed |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When it was filed |

**Constraints**

- `pk_report`: `PRIMARY KEY (id)`
- `fk_report_reporter`: `FOREIGN KEY (reporter_id) REFERENCES app_user(id) ON DELETE RESTRICT`
- `fk_report_reviewer`: `FOREIGN KEY (reviewed_by) REFERENCES app_user(id) ON DELETE RESTRICT`
- `fk_report_target_comment`: `FOREIGN KEY (target_comment_id) REFERENCES comment(id) ON DELETE CASCADE`
- `fk_report_target_post`: `FOREIGN KEY (target_post_id) REFERENCES post(id) ON DELETE CASCADE`
- `fk_report_target_user`: `FOREIGN KEY (target_user_id) REFERENCES app_user(id) ON DELETE RESTRICT`
- `ck_report_one_target`: `CHECK ((num_nonnulls(target_user_id, target_post_id, target_comment_id) = 1))`
- `ck_report_review_pair`: `CHECK (((reviewed_by IS NULL) = (reviewed_at IS NULL)))`
- `ck_report_reviewed_when_closed`: `CHECK (((status = ANY (ARRAY['open'::report_status, 'reviewing'::report_status])) OR (reviewed_at IS NOT NULL)))`

### notification

A message shown to one user, starting unread (BR-19)

| Column | Type | Null | Default | Key | Description |
|---|---|---|---|---|---|
| `id` | bigint | NOT NULL | identity | PK | Surrogate key |
| `recipient_id` | bigint | NOT NULL |  | FK to app_user | The user it is for |
| `type` | character varying(30) | NOT NULL |  |  | Kind of event, e.g. like, follow, challenge_won |
| `title` | character varying(150) | NOT NULL |  |  | Headline text |
| `body` | character varying(500) | null |  |  | Optional detail text |
| `is_read` | boolean | NOT NULL | false |  | True once the user has seen it |
| `created_at` | timestamp with time zone | NOT NULL | now() |  | When it was created |

**Constraints**

- `pk_notification`: `PRIMARY KEY (id)`
- `fk_notification_recipient`: `FOREIGN KEY (recipient_id) REFERENCES app_user(id) ON DELETE CASCADE`

