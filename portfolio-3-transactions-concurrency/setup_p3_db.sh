#!/usr/bin/env bash
# Builds the Portfolio 3 database fitscheck_p3 from scratch: the Portfolio 1 schema, the small
# deterministic seed and post_fit. Scenarios commit real changes, so they get their own database and
# the Portfolio 2 dataset is never touched. Rebuilding it makes every P3 run start from the same state.
# Requires PG_URL (set -a; . ./.env; set +a) and the repository's .venv.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PG_URL:?PG_URL is not set}"
P3_URL="${PG_URL%/*}/fitscheck_p3"

psql "$PG_URL" -X -q -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS fitscheck_p3" -c "CREATE DATABASE fitscheck_p3"
for f in 01_schema 02_constraints 03_triggers 04_views 06_comments; do
    psql "$P3_URL" -X -q -v ON_ERROR_STOP=1 -f "portfolio-1-database-design/sql/$f.sql"
done
PG_URL="$P3_URL" .venv/bin/python shared/seed/generate.py --scale small > /dev/null
psql "$P3_URL" -X -q -v ON_ERROR_STOP=1 -f portfolio-3-transactions-concurrency/sql/00_post_fit.sql
echo "fitscheck_p3 ready: $P3_URL"
