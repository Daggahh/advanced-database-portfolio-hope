# Portfolio 2: Query Processing and Optimisation

**Case study:** FitsCheck. **Marks:** 7. **Status:** Complete.

**Brief requires:** SQL queries, query results, execution plans, indexing/optimisation evidence, and brief performance analysis.

## 1. Objective

Make the queries FitsCheck runs on every app open fast on realistic volumes, and prove each
improvement with execution plans rather than claims. Every optimisation is measured before and
after on the same data and settings, its result rows are checked to be unchanged, and its cost
(write time, disk, build time, staleness) is measured alongside the speed-up.

## 2. What I built

### 2.1 A realistic dataset
The Portfolio 1 schema loaded with 9.6 million synthetic rows (1.05 GB) by the shared generator
([shared/seed/generate.py](../shared/seed/generate.py), `--scale large`): 100,000 users, 300,000 posts,
4.8 million likes, 1 million votes, 894,000 follows and 763,000 comments. Popularity is deliberately
skewed, because the planner chooses differently for popular and rare values:

| Value | Most popular | Typical |
|---|---|---|
| Likes on a post | 99,999 | median 3 |
| Posts carrying a hashtag | `#ootd`: 73,616 | rarest: 1 |

### 2.2 Twelve baseline queries
Each file in [sql/](sql/) is one FitsCheck feature with a one-line purpose. Parameters live in
[sql/params.sql](sql/params.sql) and were chosen from the data (for example, the feed user follows 15
accounts, 10 of whom post, with 8,333 posts between them). Time windows use the dataset's fixed as-of time, so every
result is repeatable.

| Query | Feature | Concept exercised |
|---|---|---|
| q01, q02 | Home feed, page 1 and page 101 | Join + top-N sort; OFFSET pagination |
| q03 | Trending in the last 24 hours | Time-window aggregation |
| q04 | People search by name fragment | Leading-wildcard `ILIKE` |
| q05 | Comment thread with nested replies | Recursive CTE |
| q06 | Challenge leaderboard | Window function `rank()` |
| q07 | People you may know | Self-join with anti-join (`NOT EXISTS`) |
| q08 | Likes per day this month | Range scan + grouping over the largest table |
| q09, q10 | A post's like count, counted vs stored | Cost of the P1 denormalisation |
| q11, q12 | Brands worn under a popular / rare hashtag | Five-way join, selectivity |

### 2.3 Optimisations
| Change | Script | For |
|---|---|---|
| 9 indexes: composite, partial, covering (`INCLUDE`) and trigram GIN (`pg_trgm`) | [01_indexes.sql](sql/optimise/01_indexes.sql) | q01-q06, q09, q11, q12 |
| Expression statistics on the day of a like | [02_statistics.sql](sql/optimise/02_statistics.sql) | q15 |
| Keyset pagination, then keyset inside `LATERAL` | [q13](sql/q13_home_feed_keyset.sql), [q14](sql/q14_home_feed_keyset_lateral.sql) | q02 |
| Group by the UTC day so the statistics apply | [q15](sql/q15_likes_this_month_utc.sql) | q08 |
| Resolve the hashtag id before joining | [q16](sql/q16_brands_for_popular_tag_by_id.sql), [q17](sql/q17_brands_for_rare_tag_by_id.sql) | q11, q12 |
| Monthly range partitioning (experiment on a copy) | [03_partition_experiment.sql](sql/optimise/03_partition_experiment.sql), [q18](sql/q18_likes_this_month_partitioned.sql) | q08 |
| Materialized view for trending | [05_trending_mv.sql](sql/optimise/05_trending_mv.sql), [q19](sql/q19_trending_from_mv.sql) | q03 |

## 3. How to run

From the repository root with `.env` loaded and the Portfolio 1 schema built (see the root README):

```bash
python shared/seed/generate.py --scale large --truncate                 # 9.6M rows, about 4 minutes
python portfolio-2-query-optimisation/run_plans.py --label before --only q0 q10 q11 q12 q13   # baseline
psql "$PG_URL" -f portfolio-2-query-optimisation/sql/optimise/01_indexes.sql
psql "$PG_URL" -f portfolio-2-query-optimisation/sql/optimise/02_statistics.sql
psql "$PG_URL" -f portfolio-2-query-optimisation/sql/optimise/03_partition_experiment.sql
psql "$PG_URL" -f portfolio-2-query-optimisation/sql/optimise/05_trending_mv.sql
python portfolio-2-query-optimisation/run_plans.py --label after         # every query, optimised
psql "$PG_URL" -f portfolio-2-query-optimisation/sql/optimise/04_retention_test.sql
for v in pk_only all_indexes pk_only all_indexes; do
  psql "$PG_URL" -X -q -At -v variant=$v -c "SET temp_buffers = '256MB'" -f portfolio-2-query-optimisation/sql/optimise/write_cost.sql
done
```

Any single query can be run by hand: `psql "$PG_URL" -f sql/params.sql -f sql/q05_comment_thread.sql`.

## 4. How it was tested

[run_plans.py](run_plans.py) applies the same method to every query:

1. **Results first.** The query runs once and its rows are saved to `evidence/results/`. In the
   "after" run the rows are compared with the "before" rows; an optimisation that changes the answer
   is a bug, not a speed-up. Rewritten queries (q13-q19) were diffed against the query they replace.
   **All 19 queries return the same rows as their baseline.**
2. **Three timed runs.** `EXPLAIN (ANALYZE, BUFFERS)` runs three times. The first may read from disk;
   the **median** is reported, all three are kept in the CSV, and the third (warm) plan is saved.
3. **Same conditions.** A snapshot of the server version, planner settings and table and index sizes
   is saved with each run (`work_mem` 4 MB, `random_page_cost` 4, 2 parallel workers, JIT on).

Costs were measured separately: index build time and size, and write cost by an A/B test that
inserts the same 531,225 likes into an identical temporary table with and without the two extra
indexes, alternating the variants so both see the same cache.

## 5. Results and evidence

### 5.1 Before and after (median of three runs, warm cache, same result rows)

| Query | Before | After | Change | What changed in the plan |
|---|---:|---:|---:|---|
| q05 comment thread | 567.8 ms | **1.0 ms** | 568x | Six full scans of 763k comments became index lookups per recursion level |
| q06 challenge leaderboard | 111.5 ms | **0.6 ms** | 186x | Full scan of 1M votes became an index-only scan of 491 votes |
| q12 / q17 brands, rare tag | 69.4 ms | **0.4 / 0.3 ms** | 174x | Scans became nested-loop index lookups for 5 posts |
| q04 people search | 42.6 ms | **1.4 ms** | 30x | Scan of 100k names became a trigram GIN index lookup |
| q09 like count, counted | 112.9 ms | **8.6 ms** | 13x | Full scan of 4.8M likes became an index-only scan of 99,999 entries |
| q03 / q19 trending 24h | 145.5 ms | **39.1 / 0.1 ms** | 4x / 1,455x | Index-only range scan; then a precomputed materialized view |
| q01 feed, page 1 | 20.7 ms | **6.8 ms** | 3x | Scan of 300k posts became index scans per followed author |
| q02 / q14 feed, page 101 | 20.9 ms | **7.7 / 5.8 ms** | 3.6x | OFFSET, then keyset pagination inside `LATERAL` |
| q08 / q15 / q18 likes per day | 331.1 ms | **361.5 / 153.8 / 131.9 ms** | 2.5x | Index alone did not help; expression statistics, then partition pruning did |
| q11 / q16 brands, popular tag | 295.5 ms | **521.0 / 160.4 ms** | regressed, then 1.8x | Misestimate after indexing; fixed by resolving the tag id first |
| q07 people you may know | 0.3 ms | 0.3 ms | none | Already served by the `follow` primary key |
| q10 like count, stored | 0.1 ms | 0.1 ms | none | Primary key lookup of one row |

Full figures: [timings_before.csv](evidence/timings_before.csv) and [timings_after.csv](evidence/timings_after.csv).
Every plan is in [plans/](plans/) as `qNN_<label>.txt`, with its query and all three timings at the top.

### 5.2 Costs

| Cost | Measurement | Evidence |
|---|---|---|
| Write time | Inserting 531,225 likes: **903.9 ms** with the primary key only, **1852.4 ms** with the two extra `post_like` indexes (2.05x) | [write_cost_post_like_indexes.txt](evidence/write_cost_post_like_indexes.txt) |
| Disk | 9 indexes add about 250 MB; the two on `post_like` alone are 182 MB | [index_build_times.txt](evidence/index_build_times.txt) |
| Build time | 38.0 s in total; `ix_post_like_created` alone 20.8 s | [index_build_times.txt](evidence/index_build_times.txt) |
| Staleness | Trending view refresh: 428 ms plain, 530 ms concurrent | [trending_mv_build_and_refresh.txt](evidence/trending_mv_build_and_refresh.txt) |

### 5.3 Partitioning experiment

| Finding | Measurement | Evidence |
|---|---|---|
| A unique key must include the partition column | PostgreSQL rejects `PRIMARY KEY (user_id, post_id)` on the partitioned table | [partition_experiment.txt](evidence/partition_experiment.txt) |
| Pruning | The monthly report reads only the October partition (1 of 13): 131.9 ms with no index | [q18 plan](plans/q18_likes_this_month_partitioned_after.txt) |
| Retention | Removing September's 1.2M likes: **31.4 s** by `DELETE`, **0.23 s** by dropping the partition | [retention_delete_vs_drop_partition.txt](evidence/retention_delete_vs_drop_partition.txt) |

## 6. Analysis

**The planner is only as good as its estimates.** Three of the most instructive results came from
estimation, not from missing indexes:

- **An index made a query slower.** After indexing, q11 rose from 295.5 ms to 521.0 ms. The planner
  estimated 149 posts for `#ootd` and got 73,616, so it chose nested-loop index lookups, which are
  ideal for a few rows and touched 774,872 buffers for this many. It cannot estimate better because it
  only learns which `hashtag_id` the name `'ootd'` maps to at run time, and per-table statistics cannot
  see through the join. Resolving the id first (as an application would, once, from a cache) lets it
  read that id's real frequency: it then chooses hash joins for the popular tag (160.4 ms, 12,674
  buffers) and index lookups for the rare one (0.3 ms, 87 buffers). The same query shape needs
  different plans for different selectivity, and the right plan depends on the estimate.
- **The planner assumed one group per row.** q08 spilled to disk because PostgreSQL keeps no
  statistics on expressions by default and guessed that grouping likes by day would produce
  1,093,563 groups. The index did not help (361.5 ms). Expression statistics on the UTC day told it
  there are about 361, so it switched to an in-memory parallel hash aggregate (153.8 ms). Expression
  statistics require an immutable expression, which is why the query groups by the UTC day.
- **The planner assumed an average creator.** In q14 each followed author's posts are fetched
  separately. The planner estimated 6 posts per author, from the average author (about 10 posts), and chose a
  bitmap scan; the authors people actually follow are prolific (8,333 posts across 10 posting
  authors, about 833 each), so the bitmap read hundreds of rows to keep 20. Forcing the ordered index scan, for diagnosis only, ran in 0.18 ms against
  5.8 ms ([diagnostic plan](plans/q14_home_feed_keyset_lateral_diagnostic_forced_index_scan.txt)). Skew
  that correlates with user behaviour is exactly what column statistics cannot capture.

**Indexes help reads and hurt writes.** The largest gains came from indexes that turned repeated full
scans into lookups: q05 (568x) because a recursive query scans once per level, and q06 (186x) because
a covering index answered the count without visiting the table. The cost was measured, not assumed:
the two read indexes on `post_like` double the time to insert likes, the busiest write in a social
app, and add 182 MB. For FitsCheck that is the right trade, since feeds and trending are read far more
often than any single post is liked, but it is why the index set stops at what a query needs.

**Pagination by OFFSET grows with depth; keyset does not, if the index can stop early.** Keyset alone
(q13) did not beat OFFSET, because the feed merged 15 authors and the plan still fetched and sorted
all of their posts. Only after rewriting it with `LATERAL`, so each author's next 20 posts come
straight from `ix_post_author_created`, did it improve, and only partly, because of the estimate above.

**Denormalisation measured.** Reading the stored counter (q10, 0.1 ms) is about 1,000 times faster
than counting likes without an index (q09 before, 112.9 ms) and still 86 times faster with one
(8.6 ms). This is the quantitative justification for `post.likes_count` in Portfolio 1.

**Partitioning is a schema decision, not only a performance one.** Monthly partitions made the
monthly report fastest without any index (131.9 ms) and made retention almost free (dropping a month
took 0.23 s against 31.4 s to delete it). But a partitioned table can only enforce uniqueness keys
that include the partition column, so "one like per user per post" (BR-10) could no longer be a
constraint. For FitsCheck that integrity rule matters more than the report, so `post_like` stays
unpartitioned and the experiment stays on a copy. A table without such a key, such as `notification`,
would be a better candidate.

**Not every query needed work.** q07 was already fast because the `follow` primary key
`(follower_id, followed_id)` serves both of its lookups. Adding an index there would only have added
write cost.

## 7. Limitations and next steps

- **Single machine, warm cache.** Timings are medians on one laptop (WSL2, 4 cores, 128 MB
  `shared_buffers`) with a warm cache; production numbers would differ, but the plan changes and
  relative differences are what the evidence shows.
- **One parameter set per query.** Each query was measured for one representative user, post or tag.
  q11 and q12 show how much the answer can change with the parameter; a fuller study would sweep
  parameters.
- **Planner workarounds were diagnosed, not deployed.** The faster q14 plan needed a disabled
  planner setting. In production it could be fixed with a plan hint extension (`pg_hint_plan`) or by
  storing a per-author post count the planner could use; neither was added.
- **The trending view uses a fixed window.** In production it would use `now()` and a scheduled
  refresh, and the staleness window would be a product decision.
- **One write-cost run was excluded** as warm-up, after a 642 s stall consistent with host I/O rather
  than index work. All runs are in the evidence file.
- **`pg_stat_statements` is enabled but not used** for this report; it would be the tool for finding
  which queries to optimise in a running system.
