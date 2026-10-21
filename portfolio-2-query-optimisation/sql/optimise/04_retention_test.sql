-- Retention: removing a whole month of likes (September 2026, about 1.2 million rows).
-- DELETE has to find and remove every row, write WAL for each, and leaves dead rows for VACUUM.
-- Dropping the month's partition removes its files in one catalog operation.
-- Both run inside transactions that are rolled back, so nothing is lost. Requires 03_partition_experiment.sql.
SET search_path = fitscheck;
\timing on
BEGIN;
DELETE FROM post_like WHERE created_at >= '2026-09-01' AND created_at < '2026-10-01';
ROLLBACK;
BEGIN;
DROP TABLE post_like_2026_09;
ROLLBACK;

-- The rolled-back DELETE still marked every row it touched, which clears the "all-visible" bits in the
-- visibility map for those pages. Index-only scans then have to visit the table again (trending went
-- from 527 to 103,067 buffers), and because an aborted delete leaves no dead rows, autovacuum is never
-- triggered to repair it. VACUUM rebuilds the visibility map.
VACUUM (ANALYZE) post_like;
