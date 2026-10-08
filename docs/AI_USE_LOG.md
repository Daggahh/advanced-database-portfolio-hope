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
