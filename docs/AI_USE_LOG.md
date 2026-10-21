# AI Use Log

A dated record of AI-assisted work on the portfolio. Summarised in `AI_USE_DECLARATION.md` for submission.

## 2026-10-08 - Portfolio 1 / ER diagram rendering
- Tool: Claude Code
- Used for: converting the ERD into a Mermaid source file (`fitscheck-erd.mmd`) and rendering it
  locally to PNG with the Mermaid CLI and ELK layout, after dbdiagram.io's free tier blocked the
  export I needed.
- Files touched: portfolio-1-database-design/diagrams/fitscheck-erd.mmd,
  portfolio-1-database-design/diagrams/fitscheck-erd.png, portfolio-1-database-design/README.md
  (ERD section)
- My verification: I rejected the first auto-rendered layout as unreadable and asked for a cleaner
  tool. I then checked the final diagram against business-rules.md: all 17 tables, every
  relationship and its cardinality, and the composite keys on vote, comment and challenge.

## 2026-10-13 - Portfolio 1 / normalisation
- Tool: Claude Code
- Used for: drafting normalisation.md from my business rules and ERD, including the functional
  dependency and candidate key analysis for every relation.
- Files touched: portfolio-1-database-design/normalisation.md, business-rules.md (BR-15),
  diagrams/fitscheck-erd.mmd and .png, portfolio-1-database-design/README.md
- My verification: I reviewed the FD analysis, in particular the 3NF versus BCNF reasoning for vote
  and challenge_entry, and reworded it.

## 2026-10-13 - Portfolio 1 / DDL
- Tool: Claude Code
- Used for: writing the four DDL scripts (01_schema, 02_constraints, 03_triggers, 04_views) from my
  ERD and business rules.
- Files touched: portfolio-1-database-design/sql/01_schema.sql to 04_views.sql,
  portfolio-1-database-design/README.md (How to run)
- My verification: I reviewed the constraints and ran the scripts against a fresh database.

## 2026-10-14 - Portfolio 1 / constraint tests
- Tool: Claude Code
- Used for: writing 05_constraint_tests.sql, which attacks every schema rule and records which
  constraint rejected it.
- Files touched: portfolio-1-database-design/sql/05_constraint_tests.sql,
  portfolio-1-database-design/evidence/p1_constraint_tests_all_rules_enforced.txt,
  portfolio-1-database-design/README.md (How it was tested, Results and evidence)
- My verification: I ran it, checked all 50 tests pass for the intended constraint, and reviewed the
  evidence file.

## 2026-10-14 - Portfolio 1 / data dictionary and README completion
- Tool: Claude Code
- Used for: writing the COMMENT ON descriptions and the catalog query that generates the data
  dictionary, and drafting the Objective, Analysis and Limitations sections of the Portfolio 1 README.
- Files touched: portfolio-1-database-design/sql/06_comments.sql, sql/07_data_dictionary.sql,
  data-dictionary.md, portfolio-1-database-design/README.md, README.md
- My verification: I reviewed the generated dictionary and reworded the analysis.

## 2026-10-15 - Seed generator and Portfolio 2 baseline
- Tool: Claude Code
- Used for: writing the synthetic data generator (shared/seed/generate.py), fixing two constraint-test
  bugs that appeared at scale, writing the 12 Portfolio 2 queries, params.sql and run_plans.py.
- Files touched: shared/seed/generate.py, portfolio-1-database-design/sql/05_constraint_tests.sql,
  docker-compose.yml, README.md, portfolio-2-query-optimisation/ (sql, run_plans.py, plans, evidence)
- My verification: I ran the small and large loads, checked determinism by checksum, re-ran the
  Portfolio 1 tests on the seeded data, ran the baseline and reviewed the plans.

## 2026-10-16 - Portfolio 2 / indexes, statistics and rewrites
- Tool: Claude Code
- Used for: writing the nine indexes, the expression statistics, the keyset, LATERAL and id-lookup
  query rewrites, and the write-cost A/B test; diagnosing the three plans that did not improve as
  expected (q08 spill, q11 regression, q13 keyset).
- Files touched: portfolio-2-query-optimisation/sql/optimise/, sql/q13 to q17, sql/params.sql,
  plans/*_after.txt, evidence/ (timings, results, index build times, write cost)
- My verification: I reviewed the before and after plans, checked every rewrite returns the same
  rows as the query it replaces, and reviewed the A/B write-cost method and its excluded warm-up run.

## 2026-10-16 - Portfolio 2 / partitioning experiment
- Tool: Claude Code
- Used for: writing the monthly range-partitioning experiment on a copy of post_like, the retention
  test (DELETE versus DROP partition) and q18.
- Files touched: portfolio-2-query-optimisation/sql/optimise/03_partition_experiment.sql,
  04_retention_test.sql, sql/q18_likes_this_month_partitioned.sql, evidence/, plans/
- My verification: I reviewed the uniqueness error, the partition row counts, the pruned plan and
  the retention timings, and checked q18 returns the same rows as q15.

## 2026-10-16 - Portfolio 2 / trending materialized view
- Tool: Claude Code
- Used for: writing the trending materialized view, its refresh-cost measurement and q19.
- Files touched: portfolio-2-query-optimisation/sql/optimise/05_trending_mv.sql,
  sql/q19_trending_from_mv.sql, evidence/trending_mv_build_and_refresh.txt, plans/, evidence/
- My verification: I checked q19 returns the same rows as q03 and reviewed the refresh timings.

## 2026-10-16 - Portfolio 2 / README write-up
- Tool: Claude Code
- Used for: drafting the Portfolio 2 README (objective, method, before/after table, costs,
  partitioning findings, analysis and limitations) from the measured evidence.
- Files touched: portfolio-2-query-optimisation/README.md, sql/params.sql (comment),
  plans/q14 diagnostic header, README.md (status)
- My verification: I checked every figure in the README against the timings CSVs and evidence files;
  three wrong figures (index disk total, posts per followed author, a run command) were corrected.

## 2026-10-19 - Portfolio 3 / transaction scenarios and concurrency harness
- Tool: Claude Code
- Used for: writing post_fit, the P3 database setup and run scripts, the T1-T3 transaction scripts,
  and the concurrency harness for T4-T10 that generates the isolation matrix; diagnosing the
  FOR UPDATE deadlock in T4.
- Files touched: portfolio-3-transactions-concurrency/ (sql, harness, setup_p3_db.sh, run_all.sh,
  evidence)
- My verification: I ran run_all.sh from a freshly built database, checked there were no thread
  errors, and reviewed every scenario's evidence and the generated matrix.

## 2026-10-19 - Portfolio 3 / README write-up
- Tool: Claude Code
- Used for: drafting the Portfolio 3 README (scenarios, method, results, isolation matrix, analysis
  and limitations) from the regenerated evidence.
- Files touched: portfolio-3-transactions-concurrency/README.md, README.md (status)
- My verification: I checked the figures in the README against the evidence files from the final
  clean run.

## 2026-10-20 - Portfolio 4 / Redis
- Tool: Claude Code
- Used for: writing the Redis fan-out feed builder, the leaderboard, counter-flush and rate-limit
  demonstrations, and the tie-break encoding that makes the leaderboard match SQL exactly.
- Files touched: portfolio-4-nosql/redis/, portfolio-4-nosql/evidence/redis_*.txt,
  docker-compose.yml, .env.example, shared/requirements.txt
- My verification: I checked the Redis feed and leaderboard return the same rows as P2's q01 and
  q06, that the 50 concurrent INCRs flushed to exactly 50 with no counter drift, and reviewed the
  celebrity fan-out measurement.

## 2026-10-20 - Portfolio 4 / MongoDB
- Tool: Claude Code
- Used for: designing the document model, writing the PostgreSQL to MongoDB migration with its
  $jsonSchema validator, and the query comparisons with explain output; adding the sort tie-break to
  the MongoDB indexes after explain showed blocking SORT stages.
- Files touched: portfolio-4-nosql/mongodb/, portfolio-4-nosql/evidence/mongo_*.txt
- My verification: I checked every MongoDB result matches its SQL equivalent, reviewed the explain
  plans before and after the index change, and reviewed the embed versus reference decisions.

## 2026-10-20 - Portfolio 4 / Neo4j
- Tool: Claude Code
- Used for: writing the follow-graph loader and the Cypher versus SQL comparisons for people you may
  know and shortest path, including the search-depth growth measurement.
- Files touched: portfolio-4-nosql/neo4j/follow_graph.py, portfolio-4-nosql/evidence/neo4j_follow_graph.txt
- My verification: I checked both queries return the same answers as SQL and reviewed the growth
  table and the database-hit counts.

## 2026-10-20 - Portfolio 4 / README write-up
- Tool: Claude Code
- Used for: drafting the Portfolio 4 README (design per store, results, suitability analysis and
  limitations) from the evidence files.
- Files touched: portfolio-4-nosql/README.md, README.md (status)
- My verification: I checked the figures against the evidence files and replaced an illustrative
  JSON example with the real stored document.

## 2026-10-21 - Portfolio 5 / PostgreSQL streaming replication
- Tool: Claude Code
- Used for: writing the three-node replication cluster (compose file, primary init, replica clone
  script), run.sh and the demonstration of lag, read-only replicas, read-your-writes routing,
  synchronous commit costs and failover.
- Files touched: portfolio-5-distributed-cloud/replication/, portfolio-5-distributed-cloud/evidence/replication_demo.txt
- My verification: I ran the cluster from scratch, checked the replicas held identical data, and
  reviewed each section of the evidence, including the corrected crash and timeline readings.

## 2026-10-21 - Portfolio 5 / MongoDB replica set
- Tool: Claude Code
- Used for: writing the three-member replica set, the fit-document export, run.sh and the
  demonstration of write concerns, causal reads, transactions, failover under load and quorum loss.
- Files touched: portfolio-5-distributed-cloud/mongo-replicaset/, portfolio-5-distributed-cloud/evidence/mongo_replicaset_demo.txt
- My verification: I ran it end to end from a fresh replica set and reviewed every phase, including
  the check that all acknowledged writes survived the failover.

## 2026-10-21 - Portfolio 5 / Citus sharding
- Tool: Claude Code
- Used for: writing the Citus cluster, the creator-sharded schema, the loader and the demonstration
  of shard placement, single-shard and all-shard queries, the home feed rewrite and hot shards;
  diagnosing the slow single-node comparison as a visibility map cleared by P2's retention test.
- Files touched: portfolio-5-distributed-cloud/sharding/, portfolio-5-distributed-cloud/evidence/citus_*.txt
- My verification: I checked every Citus query returns the same answer as the single-node database,
  reviewed the shard task counts, and re-ran the comparison after the VACUUM fix.

## 2026-10-21 - Portfolio 5 / README write-up
- Tool: Claude Code
- Used for: drafting the Portfolio 5 README (cluster designs, results, CAP and PACELC analysis applied
  to FitsCheck, limitations) from the evidence files.
- Files touched: portfolio-5-distributed-cloud/README.md, README.md (status)
- My verification: I checked every figure against the final evidence files; MongoDB figures quoted
  from an earlier run were corrected to the final run.
