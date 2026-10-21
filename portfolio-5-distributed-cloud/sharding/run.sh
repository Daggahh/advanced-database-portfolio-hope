#!/usr/bin/env bash
# Rebuilds the Citus cluster, creates and distributes the schema, loads the Portfolio 2 dataset
# (about 4 minutes) and runs demo.py. Requires PG_URL (set -a; . ./.env; set +a) pointing at the
# Portfolio 2 database, and the repository's .venv.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
citus="postgresql://fitscheck:fitscheck_local@localhost:5451/fitscheck"
cd "$here"
docker compose down -v --remove-orphans > /dev/null 2>&1 || true
docker compose up -d > /dev/null
until psql "$citus" -X -At -c "SELECT citus_version()" > /dev/null 2>&1; do sleep 2; done
sleep 5
psql "$citus" -X -f schema.sql > "$here/../evidence/citus_schema.txt" 2>&1
"$root/.venv/bin/python" load.py
"$root/.venv/bin/python" demo.py
