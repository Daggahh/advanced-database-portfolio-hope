#!/usr/bin/env bash
# Rebuilds the replication cluster from nothing, loads FitsCheck into the primary only (Portfolio 1
# schema, small seed, post_fit) and runs demo.py. The demo ends in a failover, so every run starts by
# removing the old cluster and its volumes. Uses the repository's .venv.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
primary="postgresql://fitscheck:fitscheck_local@localhost:5441/fitscheck"

cd "$here"
docker compose down -v --remove-orphans > /dev/null 2>&1 || true
docker compose up -d > /dev/null
echo "waiting for both replicas to stream..."
until [ "$(psql "$primary" -X -At -c "SELECT count(*) FROM pg_stat_replication WHERE state = 'streaming'" 2>/dev/null)" = "2" ]; do
    sleep 1
done

cd "$root"
for f in 01_schema 02_constraints 03_triggers 04_views 06_comments; do
    psql "$primary" -X -q -v ON_ERROR_STOP=1 -f "portfolio-1-database-design/sql/$f.sql"
done
PG_URL="$primary" .venv/bin/python shared/seed/generate.py --scale small > /dev/null
psql "$primary" -X -q -v ON_ERROR_STOP=1 -f portfolio-3-transactions-concurrency/sql/00_post_fit.sql
.venv/bin/python "$here/demo.py"
