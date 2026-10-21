"""PostgreSQL streaming replication for FitsCheck: lag, read-your-writes, commit modes and failover.

Expects a fresh cluster from run.sh (primary on 5441, replicas on 5442 and 5443) with the FitsCheck
schema and the small seed loaded on the primary only; everything on the replicas arrived through
replication. Writes portfolio-5-distributed-cloud/evidence/replication_demo.txt. Leaves the cluster
failed over to replica1, so run.sh rebuilds it before every run.
"""

import statistics
import subprocess
import threading
import time
from pathlib import Path

import psycopg
from psycopg import errors

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "replication_demo.txt"
URLS = {name: f"postgresql://fitscheck:fitscheck_local@localhost:{port}/fitscheck"
        for name, port in (("primary", 5441), ("replica1", 5442), ("replica2", 5443))}
lines = []


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def section(title):
    log()
    log(title)
    log("-" * len(title))


def connect(node, autocommit=True):
    return psycopg.connect(URLS[node], autocommit=autocommit, options="-c search_path=fitscheck")


def post_fit(conn, caption):
    return conn.execute("SELECT post_fit(7, %s, ARRAY['rep.jpg'])", (caption,)).fetchone()[0]


def wait_visible(conn, post_id, timeout=10.0):
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        if conn.execute("SELECT 1 FROM post WHERE id = %s", (post_id,)).fetchone():
            return (time.perf_counter() - start) * 1000
        time.sleep(0.0005)
    return None


def topology(primary):
    section("1. Topology: one primary streaming WAL to two hot standbys")
    for row in primary.execute("SELECT application_name, state, sync_state FROM pg_stat_replication ORDER BY 1"):
        log(f"pg_stat_replication: {row[0]} state={row[1]} sync_state={row[2]}")
    for row in primary.execute("SELECT slot_name, slot_type, active FROM pg_replication_slots ORDER BY 1"):
        log(f"pg_replication_slots: {row[0]} type={row[1]} active={row[2]}")
    for node in URLS:
        with connect(node) as c:
            counts = c.execute("SELECT (SELECT count(*) FROM app_user), (SELECT count(*) FROM post), "
                               "(SELECT count(*) FROM post_like), pg_is_in_recovery()").fetchone()
        log(f"{node:8}: {counts[0]:,} users, {counts[1]:,} posts, {counts[2]:,} likes, "
            f"in recovery (read-only standby) = {counts[3]}")


def lag(primary):
    section("2. Replication lag: time from commit on the primary until the post is visible on a replica")
    replica = connect("replica1")
    lags = []
    for i in range(20):
        post = post_fit(primary, f"lag probe {i}")
        lags.append(wait_visible(replica, post))
    log(f"20 posts: median {statistics.median(lags):.2f} ms, min {min(lags):.2f} ms, max {max(lags):.2f} ms")
    for row in primary.execute("SELECT application_name, write_lag, flush_lag, replay_lag FROM pg_stat_replication ORDER BY 1"):
        log(f"{row[0]}: write_lag={row[1]} flush_lag={row[2]} replay_lag={row[3]} (last reported)")
    replica.close()


def read_only():
    section("3. Replicas are read-only")
    with connect("replica1") as replica:
        try:
            post_fit(replica, "written on a replica")
        except errors.ReadOnlySqlTransaction as e:
            log(f"post_fit on replica1 -> SQLSTATE {e.sqlstate}: {e.diag.message_primary}")


def read_your_writes(primary):
    section("4. 'Where is my post?': reading your own write from a lagging replica")
    replica = connect("replica1")
    replica.execute("SELECT pg_wal_replay_pause()")
    log("replica1: WAL replay paused (simulating a replica that has fallen behind)")
    post = post_fit(primary, "posted while the replica lags")
    commit_lsn = primary.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
    log(f"primary: user 7 posted fit {post}; commit WAL position {commit_lsn}")
    seen = replica.execute("SELECT count(*) FROM post WHERE id = %s", (post,)).fetchone()[0]
    log(f"user 7 reloads their profile from replica1: the new post is {'there' if seen else 'MISSING'}")

    def route_read():
        """Read-your-writes routing: after a user writes, remember the commit's WAL position and only
        read from a replica once it has replayed at least that far; otherwise read from the primary."""
        replayed = replica.execute("SELECT pg_last_wal_replay_lsn() >= %s::pg_lsn", (commit_lsn,)).fetchone()[0]
        source = replica if replayed else primary
        found = source.execute("SELECT count(*) FROM post WHERE id = %s", (post,)).fetchone()[0]
        return ("replica1" if replayed else "primary"), found

    source, found = route_read()
    log(f"with LSN-aware routing: replica1 has not replayed {commit_lsn}, so the read goes to the {source}; "
        f"post found = {bool(found)}")
    replica.execute("SELECT pg_wal_replay_resume()")
    log("replica1: WAL replay resumed")
    wait_visible(replica, post)
    source, found = route_read()
    log(f"after catching up: the read goes to {source}; post found = {bool(found)}")
    replica.close()


def commit_modes(primary):
    section("5. Synchronous against asynchronous commit")
    primary.execute("ALTER SYSTEM SET synchronous_standby_names = 'FIRST 1 (replica1, replica2)'")
    primary.execute("SELECT pg_reload_conf()")
    time.sleep(1)
    for row in primary.execute("SELECT application_name, sync_state FROM pg_stat_replication ORDER BY 1"):
        log(f"synchronous_standby_names = 'FIRST 1 (replica1, replica2)': {row[0]} is {row[1]}")
    log()
    log("median commit latency of 200 single-row inserts, by synchronous_commit level:")
    meaning = {"off": "commit returns before the WAL is flushed locally",
               "local": "flushed on the primary only",
               "remote_write": "the standby has received and written the WAL",
               "on": "the standby has flushed the WAL to disk",
               "remote_apply": "the standby has replayed it, so it is visible there"}
    for level in ("off", "local", "remote_write", "on", "remote_apply"):
        primary.execute(f"SET synchronous_commit = {level}")
        times = []
        for i in range(200):
            start = time.perf_counter()
            primary.execute("INSERT INTO notification (recipient_id, type, title) VALUES (7, 'probe', %s)",
                            (f"{level} {i}",))
            times.append((time.perf_counter() - start) * 1000)
        log(f"  {level:13} {statistics.median(times):6.2f} ms  ({meaning[level]})")
    primary.execute("RESET synchronous_commit")

    log()
    log("Availability cost: both standbys stopped while synchronous replication is required")
    subprocess.run(["docker", "stop", "rep_replica1", "rep_replica2"], capture_output=True, check=True)
    writer = connect("primary")
    pid = writer.execute("SELECT pg_backend_pid()").fetchone()[0]
    outcome = {}

    def try_commit():
        start = time.perf_counter()
        try:
            writer.execute("INSERT INTO notification (recipient_id, type, title) VALUES (7, 'probe', 'no standby')")
            outcome["result"] = "committed"
        except psycopg.Error as e:
            outcome["result"] = f"error: {e.diag.message_primary}"
        outcome["seconds"] = time.perf_counter() - start

    def capture(notice):
        outcome["notice"] = notice.message_primary

    writer.add_notice_handler(capture)
    t = threading.Thread(target=try_commit)
    t.start()
    t.join(5)
    log(f"after 5 s the commit is still waiting: {t.is_alive()}")
    primary.execute("SELECT pg_cancel_backend(%s)", (pid,))
    t.join()
    log(f"cancelled after {outcome['seconds']:.1f} s; result: {outcome['result']}")
    log(f"server warning: {outcome.get('notice')}")
    landed = primary.execute("SELECT count(*) FROM notification WHERE title = 'no standby'").fetchone()[0]
    log(f"rows with that title on the primary: {landed} (committed locally, never confirmed by a standby)")
    writer.close()

    primary.execute("ALTER SYSTEM RESET synchronous_standby_names")
    primary.execute("SELECT pg_reload_conf()")
    subprocess.run(["docker", "start", "rep_replica1", "rep_replica2"], capture_output=True, check=True)
    for node in ("replica1", "replica2"):
        for _ in range(60):
            try:
                with connect(node) as c:
                    c.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                time.sleep(0.5)
    time.sleep(2)
    log("synchronous replication switched off again and both standbys restarted")


def failover():
    section("6. Failover: the primary goes down and replica1 is promoted")
    with connect("primary") as p:
        before = p.execute("SELECT count(*) FROM post").fetchone()[0]
        last = post_fit(p, "last post before the failure")
    log(f"primary: {before + 1:,} posts, last post id {last}")
    with connect("replica1") as r1:
        wait_visible(r1, last)
    subprocess.run(["docker", "kill", "rep_primary"], capture_output=True, check=True)
    log("primary crashed: docker kill (SIGKILL, no shutdown, no final WAL flush to the standbys)")

    r1 = connect("replica1")
    start = time.perf_counter()
    r1.execute("SELECT pg_promote(wait => true)")
    log(f"pg_promote() on replica1 returned after {(time.perf_counter() - start) * 1000:.0f} ms; "
        f"in recovery = {r1.execute('SELECT pg_is_in_recovery()').fetchone()[0]}")
    count = r1.execute("SELECT count(*) FROM post").fetchone()[0]
    log(f"replica1 (new primary) holds {count:,} posts; last post present = "
        f"{bool(r1.execute('SELECT 1 FROM post WHERE id = %s', (last,)).fetchone())}")
    new_post = post_fit(r1, "first post after failover")
    log(f"writes work on the new primary: post {new_post} committed")

    r1.execute("SELECT pg_create_physical_replication_slot('replica2')")
    r2 = connect("replica2")
    r2.execute("ALTER SYSTEM SET primary_conninfo = 'host=replica1 port=5432 user=replicator "
               "password=replicator_local application_name=replica2'")
    r2.execute("SELECT pg_reload_conf()")
    log("replica2: primary_conninfo pointed at replica1 and reloaded (it follows the new timeline)")
    seen = wait_visible(r2, new_post, timeout=30)
    log(f"replica2 sees post {new_post} written on the new primary: {seen is not None}")
    for row in r1.execute("SELECT application_name, state FROM pg_stat_replication"):
        log(f"new primary pg_stat_replication: {row[0]} state={row[1]}")
    timeline = int(r1.execute("SELECT substr(pg_walfile_name(pg_current_wal_lsn()), 1, 8)").fetchone()[0], 16)
    log(f"new primary writes WAL on timeline {timeline} (promotion starts a new timeline); the old primary "
        "would need pg_rewind or a fresh clone to rejoin")
    log(f"post ids jumped from {last} to {new_post}: sequences are logged ahead in batches, so a promoted "
        "replica skips the unused values (ids stay unique, not gap-free)")
    r1.close()
    r2.close()


def main():
    log("PostgreSQL 16 streaming replication: FitsCheck primary with two hot standbys")
    log("=" * 75)
    primary = connect("primary")
    topology(primary)
    lag(primary)
    read_only()
    read_your_writes(primary)
    commit_modes(primary)
    primary.close()
    failover()
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
