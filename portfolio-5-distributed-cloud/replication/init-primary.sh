#!/bin/bash
# Runs once when the primary's data directory is created: a role that may stream WAL, and permission
# for it to connect for replication from the compose network.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${REPLICATION_PASSWORD}'"
echo "host replication replicator all scram-sha-256" >> "$PGDATA/pg_hba.conf"
