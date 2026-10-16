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
