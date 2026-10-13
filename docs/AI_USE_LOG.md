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
