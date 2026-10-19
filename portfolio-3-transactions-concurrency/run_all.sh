#!/usr/bin/env bash
# Regenerates every Portfolio 3 evidence file from a freshly built fitscheck_p3 database:
# T1-T3 as psql scripts (every statement echoed with its output), then T4-T10 and the isolation matrix
# from the concurrency harness. Requires PG_URL (set -a; . ./.env; set +a) and the repository's .venv.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PG_URL:?PG_URL is not set}"
P3_URL="${PG_URL%/*}/fitscheck_p3"
DIR=portfolio-3-transactions-concurrency

"$DIR/setup_p3_db.sh"
for t in t01_post_fit_commit t02_post_fit_rollback t03_close_challenge_savepoint; do
    psql "$P3_URL" -X -a -f "$DIR/sql/$t.sql" > "$DIR/evidence/$t.txt" 2>&1
    echo "wrote $DIR/evidence/$t.txt"
done
P3_URL="$P3_URL" .venv/bin/python "$DIR/harness/concurrency.py"
