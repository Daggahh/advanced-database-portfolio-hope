# FitsCheck Business Rules

These rules define what the database must guarantee. Each one is enforced at one of three levels,
and the level is a design decision:

| Level | Mechanism | Used when |
|---|---|---|
| **D** Declarative | `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, `NOT NULL` | The rule can be checked by looking at one row, or at one key across a table |
| **T** Trigger | A function run by the database on insert/update | The rule needs to look at *another* table, and must hold whatever application writes the data |
| **X** Transaction | Logic inside a transaction at a chosen isolation level (Portfolio 3) | The rule depends on time ("while the challenge is open") or on counting other rows ("max 100 entries") under concurrency |

## Users and the social graph

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-01 | Every user has a username and an email, each unique regardless of letter case. | D | `UNIQUE` index on `lower(username)` and `lower(email)` |
| BR-02 | A user can follow many users and be followed by many. A user cannot follow themselves, or follow the same person twice. | D | `follow` PK `(follower_id, followed_id)`; `CHECK (follower_id <> followed_id)` |
| BR-03 | A user can block another user. A blocked user cannot follow the person who blocked them. | T | Trigger on `follow` insert checks `block` |
| BR-04 | A user may have several devices for push notifications. A push token belongs to exactly one device. | D | `user_device` table; `UNIQUE (push_token)` |
| BR-05 | A user account is deactivated, never deleted, while it has posts, votes or challenge wins, because those records must stay meaningful. | D | `ON DELETE RESTRICT` from content to `app_user`; `is_active` flag |

## Posts and what they contain

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-06 | A post (a "fit") belongs to exactly one author. | D | `post.author_id NOT NULL` FK |
| BR-07 | A post has 1 to 10 images, each in a distinct position from 1 to 10. | D + X | `UNIQUE (post_id, position)`, `CHECK (position BETWEEN 1 AND 10)`. "At least one image" spans several rows, so the posting transaction enforces it. |
| BR-08 | An image can tag any number of shop items. An item has a name, an optional brand, and a price of zero or more in a three-letter currency. | D | `CHECK (price >= 0)`, `CHECK (currency ~ '^[A-Z]{3}$')`, `NUMERIC(12,2)` |
| BR-09 | A post can carry many hashtags and a hashtag can appear on many posts. Hashtags are stored lowercase and are unique. | D | `post_hashtag` PK `(post_id, hashtag_id)`; `CHECK (name = lower(name))`; `UNIQUE (name)` |

## Engagement

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-10 | A user can like a post at most once. | D | `post_like` PK `(user_id, post_id)` |
| BR-11 | A user casts at most one vote per post, and the vote must be for one of that post's own images. | D | `UNIQUE (user_id, post_id)`; composite FK `(post_image_id, post_id) -> post_image (id, post_id)` |
| BR-12 | A user cannot vote on their own post. | T | Trigger on `vote` insert compares the voter with the post's author |
| BR-13 | A comment belongs to one post and one user and has 1 to 2,000 characters. A reply's parent comment must be on the same post. | D | `CHECK (char_length(body) BETWEEN 1 AND 2000)`; composite FK `(parent_id, post_id) -> comment (id, post_id)` |

## Challenges

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-14 | A challenge has a unique slug, a start before its end, and a positive entry limit. | D | `UNIQUE (slug)`, `CHECK (starts_at < ends_at)`, `CHECK (max_entries > 0)` |
| BR-15 | A user enters a challenge at most once, using one of their own posts. | D + T | `UNIQUE (challenge_id, user_id)`; trigger checks the post's author is the entrant |
| BR-16 | Entries are accepted only while the challenge is open, and never beyond its entry limit. | X | Entry transaction (Portfolio 3, scenario T6) |
| BR-17 | A challenge's winner must be one of that challenge's own entries, and is set only once the challenge has ended. Winning awards style points, and style points are never negative. | D + X | Composite FK `(winner_entry_id, id) -> challenge_entry (id, challenge_id)`; `CHECK (style_points >= 0)`; close transaction (T3) |

## Moderation and notifications

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-18 | A report targets exactly one thing: a user, a post or a comment. Its status is one of open, reviewing, actioned or dismissed. A reviewer and a review time are recorded together or not at all. | D | `CHECK (num_nonnulls(target_user_id, target_post_id, target_comment_id) = 1)`; status `CHECK ... IN`; `CHECK ((reviewed_by IS NULL) = (reviewed_at IS NULL))` |
| BR-19 | A notification belongs to one recipient and starts unread. | D | `recipient_id NOT NULL` FK; `is_read DEFAULT false` |

## Derived values

| ID | Rule | Level | Enforcement |
|---|---|---|---|
| BR-20 | Stored counters always equal the rows they count: `post.likes_count`, `post.comments_count`, `hashtag.posts_count`, `challenge.entries_count`. | T + X | Kept in the same transaction as the change; a reconciliation query proves they match (Portfolio 3) |

## Entities and relationships

| Relationship | Cardinality | Implemented as |
|---|---|---|
| app_user follows app_user | M:N (self) | `follow` |
| app_user blocks app_user | M:N (self) | `block` |
| app_user has user_device | 1:N | FK on `user_device` |
| app_user authors post | 1:N | FK on `post` |
| post has post_image | 1:N (1 to 10) | FK on `post_image` |
| post_image tags shop_item | 1:N | FK on `shop_item` |
| brand makes shop_item | 1:N (optional) | nullable FK on `shop_item` |
| post tagged with hashtag | M:N | `post_hashtag` |
| app_user likes post | M:N | `post_like` |
| app_user votes on post, choosing a post_image | M:N with attribute | `vote` |
| app_user comments on post; comment replies to comment | 1:N; 1:N (self) | FKs on `comment` |
| challenge has challenge_entry; app_user enters with post | 1:N; 1:N; 1:N | FKs on `challenge_entry` |
| challenge won by challenge_entry | 1:0..1 | `challenge.winner_entry_id` |
| app_user files report about user / post / comment | 1:N, exactly one target | `report` |
| app_user receives notification | 1:N | FK on `notification` |

Naming note: the tables are `app_user` and `post_like`, not `user` and `like`, because `USER` and
`LIKE` are reserved words in PostgreSQL.
