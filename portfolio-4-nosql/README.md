# Portfolio 4: NoSQL and Advanced Data Models

**Case study:** FitsCheck. **Status:** Complete.

**Brief requires:** NoSQL model based on the same case study, document/key-value/column/graph example, implementation evidence, and explanation of suitability.

## 1. Objective

Model the parts of FitsCheck that fit a relational schema least well in three NoSQL stores, using the
same data as Portfolios 1 to 3, and decide with evidence what each store should own. Every NoSQL
operation is checked against its SQL equivalent for **the same answer** before speed or cost is
compared, so a faster wrong answer cannot pass.

| Store | Model | FitsCheck use |
|---|---|---|
| Redis 7.4 | Key-value (lists, sorted sets, counters, expiring keys) | Home feeds, challenge leaderboard, like counters, rate limits |
| MongoDB 7.0 | Document | One document per fit with its images, shop items, hashtags and comment preview |
| Neo4j 5.26 | Graph | The follow network: suggestions and follow paths |

## 2. What I built

### 2.1 Redis: feeds, leaderboards, counters and limits
- **Fan-out-on-write feeds** ([redis/feed_fanout.py](redis/feed_fanout.py)), the design in FitsCheck's
  own system notes. When a user posts, the post id is pushed onto each follower's list
  (`LPUSH feed:<user>`) and the list is trimmed to its newest 500 (`LTRIM`). Reading a feed is one
  `LRANGE`. The script replays all 300,000 posts in time order to build every feed.
- **Challenge leaderboard** as a sorted set: each vote is a `ZINCRBY`, the top 10 is `ZREVRANGE`, a
  position is `ZREVRANK`. Each entry's score starts at `-entry_id * 1e-6`, so equal vote counts rank by
  the earliest entry, as in SQL.
- **Like counters** with `INCR`, flushed to PostgreSQL by a job that reads and resets each counter in
  one step (`GETDEL`) and applies the deltas **in post-id order**, the deadlock lesson from
  Portfolio 3 (T8). Writes go to the `fitscheck_p3` database so the Portfolio 2 data stays unchanged.
- **Rate limiting**: at most 5 likes per user per window, with `INCR` on a key that `EXPIRE`s itself.

All in [redis/leaderboard_counters_limits.py](redis/leaderboard_counters_limits.py).

### 2.2 MongoDB: one document per fit
[mongodb/migrate.py](mongodb/migrate.py) builds each document in PostgreSQL with `jsonb` functions and
loads it into MongoDB. Each part of a fit is embedded or referenced according to how the app reads it:

| Part of a fit | Decision | Reason |
|---|---|---|
| Images (1 to 10) and their shop items | Embedded | Bounded, always shown together: one read returns the whole card |
| Hashtags | Embedded array, multikey index | Small; a multikey index indexes each tag separately |
| Author's username and avatar | Embedded copy (extended reference) | Shown on every card; the cost is updating copies when a username changes (measured) |
| Latest 3 top-level comments | Embedded (subset pattern) | The card shows a preview |
| All comments (up to 400 per post) | Referenced, own collection | Unbounded growth would bloat every read of the post |

```json
{ "_id": 20,
  "author": { "id": 76658, "username": "sijuadeobasanjo.76658", "avatar_url": null },
  "caption": null, "created_at": "2026-09-25 22:47:08.972",
  "counts": { "likes": 29, "comments": 6 },
  "hashtags": ["asoebi_110", "fitcheck", "fitcheck_71", "womenswear"],
  "images": [
    { "position": 1, "url": "https://img.fitscheck.example/20/1.jpg",
      "items": [ { "name": "Kaftan", "brand": "Label 305", "price": "90321.00", "currency": "NGN" },
                 { "name": "Jacket", "brand": null, "price": "21.00", "currency": "USD" } ] },
    { "position": 2, "url": "https://img.fitscheck.example/20/2.jpg", "items": [] } ],
  "latest_comments": [ { "comment_id": 32, "author_id": 55112, "body": "Clean!", "created_at": "2026-10-10 02:19:21.914" }, "..." ] }
```
Post 20 as stored, abridged from [mongo_migration.txt](evidence/mongo_migration.txt); prices are
`Decimal128` in MongoDB and print as strings.

A **`$jsonSchema` validator** enforces the shape: 1 to 10 images (BR-07, which the relational schema
could not express as a CHECK), lowercase hashtags, non-negative counts and three-letter currencies.
Prices are `Decimal128`, never floating point, as in Portfolio 1. Indexes:
`(author.id, created_at desc, _id desc)`, `(hashtags, created_at desc)` and `(post_id, created_at, _id)`
on comments. [mongodb/queries.py](mongodb/queries.py) runs the comparisons.

### 2.3 Neo4j: the follow graph
[neo4j/follow_graph.py](neo4j/follow_graph.py) loads every user as a `(:User)` node and every follow as
a `[:FOLLOWS]` relationship, with a uniqueness constraint on the user id, then answers "people you may
know" and "shortest follow path" in Cypher and in SQL.

## 3. How to run

Requires the Portfolio 2 dataset (`generate.py --scale large`) and the Portfolio 3 database
(`setup_p3_db.sh`). From the repository root with `.env` loaded:

```bash
docker compose --profile nosql up -d
python portfolio-4-nosql/redis/feed_fanout.py                  # about 40 s
python portfolio-4-nosql/redis/leaderboard_counters_limits.py
python portfolio-4-nosql/mongodb/migrate.py                    # about 40 s
python portfolio-4-nosql/mongodb/queries.py
python portfolio-4-nosql/neo4j/follow_graph.py                 # about 2 minutes
```

Each script writes its evidence file to [evidence/](evidence/).

## 4. How it was tested

- **Same answer first.** The Redis feed is compared id by id with SQL query q01, the leaderboard with
  q06, each MongoDB query with its SQL equivalent (Portfolio 2's q16 and q17 for the hashtag
  aggregations), and both Cypher queries with SQL (q07 and a recursive CTE). All comparisons agree.
- **Counters against ground truth.** The 50 concurrent likes are checked against the `post_like` rows
  and Portfolio 1's `v_counter_drift`.
- **Plans, not only timings.** MongoDB `explain("executionStats")` and Neo4j `PROFILE` show index use
  and the work done (keys and documents examined, database hits), which is steadier than
  sub-millisecond client timings.
- **Validation tested by failure.** Documents breaking the schema are inserted and must be rejected.

## 5. Results and evidence

### 5.1 Redis ([redis_feed_fanout.txt](evidence/redis_feed_fanout.txt), [redis_leaderboard_counters_limits.txt](evidence/redis_leaderboard_counters_limits.txt))

| Measurement | Result |
|---|---|
| Building every feed | 2,224,561 pushes into 100,000 feeds in 36.4 s; 19.2 MB of memory |
| Feed of user 82114 | **The same 20 post ids, in the same order, as SQL q01** |
| Reading a feed (client side, median of 7) | `LRANGE` 0.50 ms; with the 20 posts fetched by primary key **1.84 ms**; SQL join **9.57 ms** |
| Fan-out of one new post | Typical creator: 2 followers, 2 writes, 0.2 ms. Most-followed creator: **99,999 writes, 1,679.9 ms** |
| Leaderboard of challenge 92 | **Same top 10 as SQL q06**, ties included; 0.35 ms against 0.99 ms |
| 50 simultaneous likes | Redis counter **50**; flushed to PostgreSQL: `likes_count` 0 to 50, 50 rows, no drift. Portfolio 3's naive counter lost 49 |
| Rate limit | Likes 1 to 5 allowed, 6 and 7 rejected; the key expires by itself; the next window allows again |
| Durability | RDB snapshots only (`save 3600 1 300 100 60 10000`, `appendonly no`) |

### 5.2 MongoDB ([mongo_migration.txt](evidence/mongo_migration.txt), [mongo_queries.txt](evidence/mongo_queries.txt))

| Operation | Same as SQL | MongoDB plan | MongoDB | SQL |
|---|---|---|---:|---:|
| Fit card by id | Yes | `IDHACK`: 1 key, 1 document | 0.96 ms | 0.90 ms (joins over 5 tables) |
| Brands under `#ootd` | Yes | `IXSCAN(hashtags)`: 73,616 keys and documents | 340.6 ms | 495.6 ms |
| Brands under a rare tag | Yes | `IXSCAN(hashtags)`: 5 keys, 5 documents | 2.15 ms | 0.25 ms |
| Profile, latest 20 posts | Yes | `IXSCAN`: 20 keys, 20 documents, no sort | 2.07 ms | 0.73 ms |
| Comments page, first 50 | Yes | `IXSCAN`: 50 keys, 50 documents, no sort | 1.69 ms | 0.37 ms |
| A prolific creator renames | n/a | `update_many` | **8,309 documents**, 344.0 ms | 1 row |
| Fit with no images; bad hashtag | n/a | validator | Both rejected (code 121) | |

The migration loaded 300,000 posts (average 627 bytes; 179.6 MB of data stored in 63.7 MB thanks to
compression) and 763,273 comments, and **every post passed the validator**. Before the `_id` tie-break
was added to the indexes, `explain` showed an in-memory `SORT` stage: the comments page examined 400
keys to return 50. With it, 50.

### 5.3 Neo4j ([neo4j_follow_graph.txt](evidence/neo4j_follow_graph.txt))

| Question | Same as SQL | Neo4j | PostgreSQL |
|---|---|---:|---:|
| People you may know (user 82114) | **Same 10 suggestions** | 6.64 ms, 445 db hits | **0.74 ms** |
| Shortest path to user 235, up to 4 hops | Same length (3 hops) | **6.54 ms**, 49 db hits | 9.23 ms, 8,685 partial paths |

How the shortest-path work grows with the depth limit:

| Max hops | SQL partial paths | SQL | Neo4j db hits | Neo4j |
|---:|---:|---:|---:|---:|
| 3 | 1,084 | 1.5 ms | 49 | 5.9 ms |
| 4 | 8,685 | 10.7 ms | 49 | 6.1 ms |
| 5 | 70,146 | 70.1 ms | 49 | 5.2 ms |
| 6 | **563,077** | **3,724.5 ms** | **49** | **30.7 ms** |

## 6. Analysis: which store should own what

| Property | PostgreSQL | Redis | MongoDB | Neo4j |
|---|---|---|---|---|
| Consistency | ACID, constraints across tables | Single commands atomic; no constraints | Single-document atomic; multi-document transactions need a replica set (Portfolio 5) | ACID transactions |
| Schema | Fixed, enforced | None | Flexible, optionally validated | Flexible properties |
| Best query shape | Joins, aggregates, ad-hoc questions | Lookup by key; ordered lists and sets | Read a whole entity in one go | Traverse relationships to any depth |
| Weakness shown here | Path enumeration explodes with depth | Fan-out cost grows with followers; memory-bound; snapshot durability | Copies must be updated everywhere | Slower than SQL for shallow, indexed lookups |

**Redis owns feeds, leaderboards and counters, all rebuildable from PostgreSQL.** Its data structures
are the access pattern: a feed is a list read with one command, a leaderboard is a sorted set that is
always in order, and `INCR` is atomic because Redis runs commands one at a time, which is why 50
simultaneous likes counted to exactly 50 with no locks or retries. The cost is skew: one post from the
most-followed creator is 99,999 writes. The standard answer, and the one FitsCheck should use, is a
**hybrid**: push for ordinary creators, pull for the few creators with huge followings, merging their
latest posts into the feed when it is read. Redis keeps data in memory with periodic snapshots, so it
holds only what can be rebuilt from PostgreSQL. The counter flush is the bridge: the likes stay
recorded as rows in PostgreSQL, and only the counter increments go through Redis.

**MongoDB suits the fit as a unit, but SQL stays the source of truth.** One document holds what a
fit card shows, its validator enforced BR-07 where a CHECK could not, and its shape came straight from
the relational data. For single-entity reads both systems answer within a millisecond, so speed is not
the reason to choose it; the reasons are shape and schema flexibility (shop items can gain fields
without a migration). The price of embedding showed up clearly: copying the author's username into
every post means one rename touches 8,309 documents, where SQL changes one row. MongoDB is a good
read model for fit cards; ownership of users, follows, votes and challenge results, where constraints
and multi-entity transactions matter (Portfolios 1 and 3), stays in PostgreSQL.

**Neo4j wins when depth is unknown or large, not for every graph question.** "People you may know" is
two hops from one user, and PostgreSQL answered it faster because both hops are primary key lookups.
Shortest path is different: SQL has to enumerate paths, and the number of paths multiplies by about 8
per extra hop (the average number of follows), reaching 563,077 and 3.7 seconds at six hops.
`shortestPath()` searches from both ends and stops at the first meeting point, so its work stayed at 49
database hits at every depth. Graph databases store each relationship as a direct pointer, so a
traversal follows pointers instead of joining tables.

**Indexes and plans transfer across models.** The same lesson as Portfolio 2 appeared in MongoDB: an
index has to cover the sort, including the tie-break column, or the database sorts in memory.

## 7. Limitations and next steps

- **Single-node stores.** Each runs as one container, so MongoDB here cannot run multi-document
  transactions and nothing is replicated; Portfolio 5 adds replication.
- **The hybrid feed is described, not built.** The celebrity cost is measured; the pull path for large
  creators is left as the design.
- **The NoSQL copies are loaded once.** A production system would keep them in step with PostgreSQL
  with change data capture or an outbox; the counter flush is the only continuous path built here.
- **Client-side timings.** Sub-millisecond comparisons are dominated by network round trips and vary
  between runs; plan statistics (keys, documents and database hits examined) are the steadier evidence.
- **Neo4j holds only the follow graph.** Blocks, likes and co-entry in challenges could be added as
  relationships for richer suggestions.
