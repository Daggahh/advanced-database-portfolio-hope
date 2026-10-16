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
