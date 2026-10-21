#!/bin/bash
# First start: clone the primary with pg_basebackup. -R writes standby.signal and primary_conninfo so
# the copy starts as a streaming replica; -C -S creates a replication slot named after this replica, so
# the primary keeps any WAL this replica has not received yet. Later starts reuse the existing copy.
set -e
until pg_isready -h "$PRIMARY_HOST" -U "$POSTGRES_USER" -q; do sleep 1; done
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA" && chown postgres:postgres "$PGDATA" && chmod 700 "$PGDATA"
    PGPASSWORD="$REPLICATION_PASSWORD" gosu postgres pg_basebackup -h "$PRIMARY_HOST" -U replicator \
        -D "$PGDATA" -R -X stream -C -S "$SLOT_NAME"
fi
# cluster_name becomes the replica's application_name on the primary, which synchronous_standby_names uses
exec gosu postgres postgres -c hot_standby=on -c primary_slot_name="$SLOT_NAME" -c cluster_name="$SLOT_NAME"
