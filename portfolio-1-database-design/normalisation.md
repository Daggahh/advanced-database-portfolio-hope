# FitsCheck Normalisation

This document shows how the FitsCheck schema was derived by normalising one flat record up to 3NF and
BCNF, where the final design deliberately stops short of BCNF, and where it deliberately stores
redundant data.

## 1. Why normalise

Normalisation removes redundancy: the same fact stored in more than one place. Redundancy causes three
kinds of anomaly.

| Anomaly | Meaning | FitsCheck example in a flat table |
|---|---|---|
| Update | A fact is changed in one place but not the others | Zara's website is repeated on 5,000 shop items. Zara changes domain, 12 rows are missed, and Zara now has two websites. |
| Insert | A fact cannot be recorded without an unrelated fact | The hashtag `#owambe` cannot exist until someone posts with it. |
| Delete | Deleting one fact destroys another | Deleting the only post tagged `#agbada` also deletes the hashtag. |

## 2. Terms used

- **Functional dependency (FD), `X -> Y`**: knowing X fixes exactly one value of Y. `user_id -> username`
  holds; `username -> post_id` does not, because a user has many posts.
- **Candidate key**: a minimal set of columns that determines every other column. The chosen one is the
  primary key; the others are enforced with `UNIQUE`.
- **Prime attribute**: a column that is part of any candidate key.

| Normal form | Rule |
|---|---|
| 1NF | Every cell holds one indivisible value; no repeating groups. |
| 2NF | 1NF, and no non-key column depends on only part of a composite key. |
| 3NF | 2NF, and no non-key column depends on another non-key column. Formally: for every FD `X -> A`, X is a superkey or A is prime. |
| BCNF | For every FD `X -> A`, X is a superkey. The "or A is prime" exception is removed. |

## 3. Starting point (0NF)

The "post a fit" screen saved as one row, exactly as entered:

| post_id | username | email | caption | images | hashtags | items |
|---|---|---|---|---|---|---|
| 501 | hope | hope@x.com | Sunday fit | a.jpg, b.jpg | #ootd, #lagos | Nike AF1 (Nike, nike.com) N85000; Linen shirt (Zara, zara.com) N30000 |

Three cells contain lists. Finding "all posts tagged #lagos" or totalling item prices requires parsing
strings, and no index can help.

## 4. First normal form

Each list becomes its own relation, one row per element, carrying the key of the post it belongs to.

- `post(post_id, username, email, caption)`
- `post_image(post_id, position, image_url)`
- `post_hashtag(post_id, hashtag_name)`
- `shop_item(post_id, image_position, item_name, brand_name, brand_website, price, currency)`

The same reasoning applies to push notification tokens: a user with three phones would otherwise need
`token1, token2, token3` columns, a repeating group, so devices became `user_device`.

Prices also changed from the text `N85000` to `price NUMERIC(12,2) = 85000.00` and `currency = 'NGN'`.
Strictly this is a domain (data type) correction rather than a normal-form rule, but it is needed for
the same reason: a value hidden inside text cannot be compared, summed or constrained.

## 5. Second normal form

2NF only concerns relations with composite keys.

**Example 1.** Suppose the junction relation also stored the tag's name:
`post_hashtag(post_id, hashtag_id, hashtag_name)` with key `(post_id, hashtag_id)`.

- FD `hashtag_id -> hashtag_name` depends on only half of the key: a partial dependency.
- Effect: "lagos" is repeated in every row that uses the tag, and a tag cannot exist without a post.
- Decomposition: `hashtag(id, name)` and `post_hashtag(post_id, hashtag_id)`.

**Example 2.** `post_like(user_id, post_id, username)` with key `(user_id, post_id)` has the partial
dependency `user_id -> username`. The username is removed; it already lives in `app_user`.

## 6. Third normal form

**Example 1.** `shop_item(id, item_name, brand_name, brand_website, price, currency)`.

- `id -> brand_name` and `brand_name -> brand_website`, so the website depends on the item only through
  the brand: a transitive dependency.
- Effect: the Zara update anomaly in section 1.
- Decomposition: `brand(id, name, website)` and `shop_item(id, brand_id, item_name, price, currency)`.

**Example 2.** `post(post_id, author_id, author_username, author_email, caption)`.

- `author_id -> author_username, author_email`, a transitive dependency through the author.
- Decomposition: `post(id, author_id, caption)`; the user's details live only in `app_user`.

## 7. BCNF, and where the design stops at 3NF

Most final relations are in BCNF because their only determinants are their keys (see the table in
section 10). Two relations share a pattern that is in 3NF but not BCNF, and one relation has a
controlled redundancy. Each was kept on purpose.

### 7.1 vote

`vote(id, user_id, post_id, post_image_id)`

FDs:
- `id -> user_id, post_id, post_image_id`
- `(user_id, post_id) -> post_image_id`, because a user casts one vote per post
- `post_image_id -> post_id`, because every image belongs to exactly one post

Candidate keys: `{id}`, `{user_id, post_id}` and `{user_id, post_image_id}` (the image fixes the post,
so the pair determines everything).

- **3NF holds.** In `post_image_id -> post_id`, the left side is not a superkey, but `post_id` is prime
  (it is part of the key `{user_id, post_id}`), so the 3NF exception applies.
- **BCNF fails.** `post_image_id` determines `post_id` but is not a superkey of `vote`.

The BCNF decomposition would drop `post_id`, leaving `vote(user_id, post_image_id)`. That loses the
rule "one vote per user per post": `(user_id, post_id) -> post_image_id` can no longer be checked inside
one relation, so no `UNIQUE` constraint could enforce it and a trigger would be needed. This is a known
result: a 3NF decomposition can always preserve every dependency, but a BCNF decomposition sometimes
cannot.

**Decision:** keep `vote` in 3NF. `UNIQUE (user_id, post_id)` enforces the rule declaratively, and the
composite foreign key `(post_image_id, post_id) -> post_image (id, post_id)` makes it impossible for the
redundant `post_id` to disagree with the image. The redundancy exists, but it cannot cause an anomaly.

### 7.2 challenge_entry

`challenge_entry(id, challenge_id, user_id, post_id)`. A user enters a challenge with one of their own
posts (BR-15), so:

- `post_id -> user_id`, because a post has exactly one author
- `(challenge_id, user_id) -> post_id`, because a user enters each challenge once

Candidate keys: `{id}`, `{challenge_id, user_id}` and `{challenge_id, post_id}`.

The same pattern as `vote`: `post_id -> user_id` has a non-superkey on the left and a prime attribute
on the right, so the relation is in 3NF but not BCNF. Dropping `user_id` would lose
`UNIQUE (challenge_id, user_id)`, the "one entry per user" rule. `user_id` is therefore kept.

This analysis also improved the design. BR-15 was originally enforced by a trigger checking that the
post belongs to the entrant. Once `post_id -> user_id` is recognised as the same pattern as `vote`, the
same tool applies: a composite foreign key `(post_id, user_id) -> post (id, author_id)`, backed by
`UNIQUE (id, author_id)` on `post`, enforces it declaratively. The DDL uses the constraint instead of the
trigger.

### 7.3 comment

`comment(id, post_id, author_id, parent_id, body)`. A reply must be on the same post as its parent
(BR-13), so for replies `parent_id -> post_id`. Here `post_id` is not prime (the only candidate key is
`{id}`), so for reply rows this is a transitive dependency `id -> parent_id -> post_id`, and strictly
those rows break 3NF.

`post_id` is kept because:
- for top-level comments (`parent_id` is NULL) `post_id` is the only link to the post and cannot be
  derived at all;
- without it, listing a post's comments would need a recursive walk up every reply chain.

The composite foreign key `(parent_id, post_id) -> comment (id, post_id)` guarantees a reply's `post_id`
always equals its parent's, so the redundancy cannot drift.

## 8. Design decisions that are not normal-form issues

These are modelling choices, recorded here so they are not mistaken for normalisation.

- **Report targets.** `report` has three nullable foreign keys, `target_user_id`, `target_post_id` and
  `target_comment_id`, with `CHECK (num_nonnulls(...) = 1)`. The alternatives were one table per target
  type (three near-identical tables) or a generic `target_type` + `target_id` pair. The generic pair
  cannot carry a real foreign key, so the database could not stop a report pointing at a deleted or
  non-existent row. Three typed foreign keys keep referential integrity.
- **Statuses and platforms** are enum types (`report_status`, `device_platform`) rather than free
  text, so invalid values are rejected by the database.

## 9. Deliberate denormalisation

`post.likes_count`, `post.comments_count`, `hashtag.posts_count` and `challenge.entries_count` are
derived data: each can be computed with `COUNT(*)` over another table. Storing them is redundancy added
on purpose (BR-20).

- **Why.** Every feed card shows these counts. A 20-post feed would otherwise run 40 or more `COUNT(*)`
  queries over tables with millions of rows on every app open.
- **Risk.** The stored number can drift from the real count, which is an update anomaly.
- **Control.** The counter is changed in the same transaction as the row it counts, using an atomic
  `UPDATE ... SET likes_count = likes_count + 1`. A reconciliation query compares each stored counter
  with the real count. Portfolio 3 shows the counter going wrong under concurrency without this, and
  Portfolio 2 measures the speed difference between `COUNT(*)` and the stored counter.

`app_user.style_points` is a running total of points awarded for challenge wins. It is maintained by
the challenge-close transaction (BR-17).

## 10. Final relations

| Relation | Candidate keys | Non-trivial FDs beyond the keys | Highest NF |
|---|---|---|---|
| app_user | `{id}`, `{lower(username)}`, `{lower(email)}` | none | BCNF |
| user_device | `{id}`, `{push_token}` | none | BCNF |
| follow | `{follower_id, followed_id}` | none | BCNF |
| block | `{blocker_id, blocked_id}` | none | BCNF |
| post | `{id}` | none (counters are derived data, section 9) | BCNF |
| post_image | `{id}`, `{post_id, position}` | none | BCNF |
| brand | `{id}`, `{name}` | none | BCNF |
| shop_item | `{id}` | none | BCNF |
| hashtag | `{id}`, `{name}` | none | BCNF |
| post_hashtag | `{post_id, hashtag_id}` | none | BCNF |
| post_like | `{user_id, post_id}` | none | BCNF |
| vote | `{id}`, `{user_id, post_id}`, `{user_id, post_image_id}` | `post_image_id -> post_id` | 3NF (7.1) |
| comment | `{id}` | `parent_id -> post_id` for replies | 2NF; controlled (7.3) |
| challenge | `{id}`, `{slug}` | none | BCNF |
| challenge_entry | `{id}`, `{challenge_id, user_id}`, `{challenge_id, post_id}` | `post_id -> user_id` | 3NF (7.2) |
| report | `{id}` | none | BCNF |
| notification | `{id}` | none | BCNF |

Every relation is at least in 3NF except `comment`, whose single exception applies only to replies and
is held consistent by a composite foreign key. Where BCNF was not reached, the redundant column is kept
so a business rule can be enforced as a `UNIQUE` constraint, and a composite foreign key prevents it
from ever holding a wrong value.
