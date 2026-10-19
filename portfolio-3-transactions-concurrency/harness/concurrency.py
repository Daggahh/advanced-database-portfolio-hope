"""Concurrency scenarios T4 to T10 for Portfolio 3, run against the fitscheck_p3 database.

Every session is a thread with its own connection. Barriers force the dangerous interleaving (for
example, all readers read before any writer writes), so each anomaly happens on every run rather than
by chance. Each scenario creates its own fresh rows, logs a timestamped step per session to
evidence/tNN_*.txt, and records what it observed. The isolation matrix (evidence/isolation_matrix.md)
is generated from those observations, not written by hand.

Usage (after setup_p3_db.sh):
    python portfolio-3-transactions-concurrency/harness/concurrency.py            # all scenarios
    python portfolio-3-transactions-concurrency/harness/concurrency.py t04 t06    # some
"""

import os
import sys
import threading
import time
import uuid
from pathlib import Path

import psycopg
from psycopg import IsolationLevel, errors

EVIDENCE = Path(__file__).resolve().parent.parent / "evidence"
RC, RR, SER = IsolationLevel.READ_COMMITTED, IsolationLevel.REPEATABLE_READ, IsolationLevel.SERIALIZABLE
LEVEL_NAME = {RC: "READ COMMITTED", RR: "REPEATABLE READ", SER: "SERIALIZABLE"}

MATRIX = {}


def db_url():
    url = os.environ.get("P3_URL")
    if url:
        return url
    base = os.environ.get("PG_URL")
    if not base:
        sys.exit("PG_URL is not set; run: set -a; . ./.env; set +a")
    return base.rsplit("/", 1)[0] + "/fitscheck_p3"


URL = db_url()


def connect(level=RC, autocommit=False):
    conn = psycopg.connect(URL, autocommit=autocommit, options="-c search_path=fitscheck")
    if not autocommit:
        conn.isolation_level = level
    return conn


def observe(anomaly, level, observed):
    MATRIX.setdefault(anomaly, {})[LEVEL_NAME[level]] = "occurs" if observed else "prevented"


class Log:
    """Timestamped, thread-safe scenario log written to stdout and to the evidence file."""

    def __init__(self, name, title, explanation):
        self.path = EVIDENCE / f"{name}.txt"
        self.lock = threading.Lock()
        self.lines = [title, "=" * len(title), "", explanation, ""]
        self.t0 = time.perf_counter()

    def __call__(self, who, message):
        line = f"{time.perf_counter() - self.t0:8.3f}s  [{who}] {message}"
        with self.lock:
            self.lines.append(line)
        print(line, flush=True)

    def section(self, text):
        with self.lock:
            self.lines += ["", f"-- {text}"]
        print(f"\n-- {text}", flush=True)
        self.t0 = time.perf_counter()

    def save(self):
        self.path.write_text("\n".join(self.lines) + "\n")


def run_threads(targets):
    threads = [threading.Thread(target=t, args=a) for t, a in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def admin_sql(sql, params=()):
    with connect(autocommit=True) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else None


def new_post(author, images=2):
    """A fresh post by `author` through post_fit, so every scenario starts from known rows."""
    tag = uuid.uuid4().hex[:8]
    urls = [f"p3-{tag}-{i}.jpg" for i in range(1, images + 1)]
    post_id = admin_sql("SELECT post_fit(%s, %s, %s)", (author, f"P3 fixture {tag}", urls))[0][0]
    image_ids = [r[0] for r in admin_sql("SELECT id FROM post_image WHERE post_id = %s ORDER BY position", (post_id,))]
    return post_id, image_ids


def counter_state(post_id):
    return admin_sql("SELECT p.likes_count, (SELECT count(*) FROM post_like WHERE post_id = p.id) "
                     "FROM post p WHERE p.id = %s", (post_id,))[0]


def t04_lost_update():
    log = Log("t04_lost_update", "T4: 50 people like the same fit at the same moment",
              "Each like inserts a post_like row and then maintains post.likes_count (BR-20). The naive\n"
              "version reads the counter, then writes back read + 1. A barrier makes all 50 sessions read\n"
              "before any of them writes. The post_like rows are the ground truth: 50 per run.")
    likers = list(range(2, 52))

    def naive(user, post, barrier, level, stats):
        conn = connect(level)
        attempt = 0
        while True:
            attempt += 1
            try:
                with conn.transaction():
                    conn.execute("INSERT INTO post_like (user_id, post_id) VALUES (%s, %s)", (user, post))
                    read = conn.execute("SELECT likes_count FROM post WHERE id = %s", (post,)).fetchone()[0]
                    if attempt == 1:
                        barrier.wait()
                    conn.execute("UPDATE post SET likes_count = %s WHERE id = %s", (read + 1, post))
                if user in (2, 3, 51):
                    log(f"user {user}", f"read likes_count={read}, wrote {read + 1}, committed (attempt {attempt})")
                break
            except errors.SerializationFailure:
                stats["retries"] += 1
                if attempt == 1 and user in (2, 3):
                    log(f"user {user}", "40001 could not serialize access due to concurrent update; retrying")
        conn.close()

    def atomic(user, post, barrier, level, stats):
        conn = connect(level)
        barrier.wait()
        with conn.transaction():
            conn.execute("INSERT INTO post_like (user_id, post_id) VALUES (%s, %s)", (user, post))
            conn.execute("UPDATE post SET likes_count = likes_count + 1 WHERE id = %s", (post,))
        conn.close()

    def locked(user, post, barrier, level, stats, mode):
        # The post_like insert's foreign key check takes a KEY SHARE lock on the post row. FOR UPDATE
        # conflicts with KEY SHARE, so concurrent likers deadlock; FOR NO KEY UPDATE (the lock an UPDATE
        # of non-key columns takes) is compatible with it.
        conn = connect(level)
        barrier.wait()
        try:
            with conn.transaction():
                conn.execute("INSERT INTO post_like (user_id, post_id) VALUES (%s, %s)", (user, post))
                read = conn.execute(f"SELECT likes_count FROM post WHERE id = %s {mode}", (post,)).fetchone()[0]
                conn.execute("UPDATE post SET likes_count = %s WHERE id = %s", (read + 1, post))
        except errors.DeadlockDetected:
            stats["deadlocks"] += 1
        conn.close()

    def lock_for_update(user, post, barrier, level, stats):
        locked(user, post, barrier, level, stats, "FOR UPDATE")

    def lock_for_no_key_update(user, post, barrier, level, stats):
        locked(user, post, barrier, level, stats, "FOR NO KEY UPDATE")

    variants = [
        ("naive read-then-write", naive, RC, True),
        ("naive read-then-write", naive, RR, True),
        ("naive read-then-write", naive, SER, True),
        ("atomic UPDATE likes_count = likes_count + 1", atomic, RC, False),
        ("SELECT ... FOR UPDATE, then write", lock_for_update, RC, False),
        ("SELECT ... FOR NO KEY UPDATE, then write", lock_for_no_key_update, RC, False),
    ]
    for label, fn, level, is_naive in variants:
        post, _ = new_post(author=1)
        log.section(f"{label} at {LEVEL_NAME[level]} (post {post})")
        barrier = threading.Barrier(len(likers), timeout=60)
        stats = {"retries": 0, "deadlocks": 0}
        run_threads([(fn, (u, post, barrier, level, stats)) for u in likers])
        stored, actual = counter_state(post)
        lost = actual - stored
        log("result", f"post_like rows = {actual}, likes_count = {stored}, likes lost = {lost}, "
                      f"serialization retries = {stats['retries']}, deadlocks = {stats['deadlocks']}")
        drift = admin_sql("SELECT stored, actual FROM v_counter_drift WHERE counter = 'post.likes_count' "
                          "AND row_id = %s", (post,))
        log("result", "v_counter_drift (P1 BR-20 check): "
                      + (f"flags this post, stored {drift[0][0]} vs actual {drift[0][1]}" if drift else "no drift"))
        if is_naive:
            observe("Lost update", level, lost > 0)
    log.save()


def t05_double_tap_vote():
    log = Log("t05_double_tap_vote", "T5: a double-tap sends the same vote twice at the same moment",
              "Two sessions insert the same (user, post) vote together. uq_vote_user_post (BR-11) is the\n"
              "concurrency control: the second insert waits for the first to commit, then is rejected.")
    voter = 9
    for label, on_conflict in [("plain INSERT", ""), ("INSERT ... ON CONFLICT DO NOTHING", " ON CONFLICT DO NOTHING")]:
        post, images = new_post(author=8)
        log.section(f"{label} (post {post})")
        barrier = threading.Barrier(2, timeout=30)

        def tap(who):
            conn = connect()
            barrier.wait()
            start = time.perf_counter()
            try:
                with conn.transaction():
                    cur = conn.execute("INSERT INTO vote (user_id, post_id, post_image_id) VALUES (%s, %s, %s)"
                                       + on_conflict, (voter, post, images[0]))
                    rows = cur.rowcount
                log(who, f"committed, rows inserted = {rows} (waited {time.perf_counter() - start:.3f}s)")
            except errors.UniqueViolation as e:
                log(who, f"rejected after {time.perf_counter() - start:.3f}s: 23505 {e.diag.constraint_name}")
            conn.close()

        run_threads([(tap, ("tap 1",)), (tap, ("tap 2",))])
        count = admin_sql("SELECT count(*) FROM vote WHERE user_id = %s AND post_id = %s", (voter, post))[0][0]
        log("result", f"votes stored for this user and post = {count}")
    log.save()


def t06_write_skew():
    log = Log("t06_last_challenge_slot", "T6: two users take the last challenge slot at the same moment",
              "BR-16: a challenge accepts entries only while open and below max_entries. Each session counts\n"
              "the entries, checks the limit, then inserts its own entry. The two inserts are different rows,\n"
              "so no row conflict exists: this is write skew. The shared entries_count counter is updated\n"
              "after the race (and reconciled) so that it does not itself serialize the two sessions.")

    def fixture():
        slug = f"p3-slot-{uuid.uuid4().hex[:8]}"
        challenge = admin_sql("INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries) "
                              "VALUES (%s, 'Last slot', now() - interval '1 day', now() + interval '1 day', 3) "
                              "RETURNING id", (slug,))[0][0]
        for user in (21, 22):
            post, _ = new_post(user)
            admin_sql("INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES (%s, %s, %s)",
                      (challenge, user, post))
        candidates = [(user, new_post(user)[0]) for user in (23, 24)]
        return challenge, candidates

    def enter(who, user, post, challenge, level, barrier, lock_first):
        conn = connect(level)
        attempt = 0
        while True:
            attempt += 1
            try:
                with conn.transaction():
                    if lock_first:
                        if attempt == 1:
                            barrier.wait()
                        conn.execute("SELECT id FROM challenge WHERE id = %s FOR UPDATE", (challenge,))
                    taken, limit, is_open = conn.execute(
                        "SELECT (SELECT count(*) FROM challenge_entry WHERE challenge_id = c.id), c.max_entries, "
                        "now() BETWEEN c.starts_at AND c.ends_at FROM challenge c WHERE c.id = %s",
                        (challenge,)).fetchone()
                    if not lock_first and attempt == 1:
                        barrier.wait()
                    if not is_open or taken >= limit:
                        log(who, f"saw {taken}/{limit} entries: refused (attempt {attempt})")
                        break
                    conn.execute("INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES (%s, %s, %s)",
                                 (challenge, user, post))
                log(who, f"saw {taken}/{limit} entries: inserted and committed (attempt {attempt})")
                break
            except errors.SerializationFailure as e:
                log(who, f"40001 {e.diag.message_primary}; retrying")
        conn.close()

    for label, level, lock_first in [("count then insert", RC, False), ("count then insert", RR, False),
                                     ("count then insert", SER, False),
                                     ("lock the challenge row FOR UPDATE, then count", RC, True)]:
        challenge, candidates = fixture()
        log.section(f"{label} at {LEVEL_NAME[level]} (challenge {challenge}, max_entries 3, 2 taken)")
        barrier = threading.Barrier(2, timeout=30)
        run_threads([(enter, (f"user {u}", u, p, challenge, level, barrier, lock_first)) for u, p in candidates])
        admin_sql("UPDATE challenge c SET entries_count = (SELECT count(*) FROM challenge_entry "
                  "WHERE challenge_id = c.id) WHERE c.id = %s", (challenge,))
        final = admin_sql("SELECT entries_count, max_entries FROM challenge WHERE id = %s", (challenge,))[0]
        log("result", f"entries = {final[0]} for max_entries = {final[1]}"
                      + ("  <-- over the limit" if final[0] > final[1] else ""))
        if not lock_first:
            observe("Write skew", level, final[0] > final[1])
    log.save()


def t07_non_repeatable_read():
    log = Log("t07_non_repeatable_read", "T7: a leaderboard is read twice while a vote and a like arrive",
              "The reader reads a post's like counter (a row value) and counts its votes (a set of rows),\n"
              "then a writer commits one new like and one new vote, then the reader repeats both reads in\n"
              "the same transaction. A changed counter is a non-repeatable read; a changed count is a phantom.")
    for level in (RC, RR, SER):
        post, images = new_post(author=31)
        log.section(f"reader at {LEVEL_NAME[level]} (post {post})")
        first_read, writer_done = threading.Event(), threading.Event()

        def reader():
            conn = connect(level)
            with conn.transaction():
                q = ("SELECT likes_count, (SELECT count(*) FROM vote WHERE post_id = p.id) FROM post p WHERE p.id = %s")
                likes1, votes1 = conn.execute(q, (post,)).fetchone()
                log("reader", f"first read:  likes_count={likes1}, votes={votes1}")
                first_read.set()
                writer_done.wait(30)
                likes2, votes2 = conn.execute(q, (post,)).fetchone()
                log("reader", f"second read: likes_count={likes2}, votes={votes2}")
            observe("Non-repeatable read", level, likes1 != likes2)
            observe("Phantom read", level, votes1 != votes2)
            conn.close()

        def writer():
            first_read.wait(30)
            conn = connect()
            with conn.transaction():
                conn.execute("INSERT INTO post_like (user_id, post_id) VALUES (32, %s)", (post,))
                conn.execute("UPDATE post SET likes_count = likes_count + 1 WHERE id = %s", (post,))
                conn.execute("INSERT INTO vote (user_id, post_id, post_image_id) VALUES (32, %s, %s)", (post, images[0]))
            log("writer", "committed one like (counter +1) and one vote")
            writer_done.set()
            conn.close()

        run_threads([(reader, ()), (writer, ())])
    log.save()


def t08_deadlock():
    log = Log("t08_deadlock", "T8: two counter jobs lock the same two posts in opposite order",
              "Each job recomputes likes_count for posts X and Y (for example, flushing counters from a\n"
              "cache). Job A updates X then Y; job B updates Y then X. Each ends up waiting for a lock the\n"
              "other holds. PostgreSQL detects the cycle after deadlock_timeout (1s) and aborts one job.")
    recount = "UPDATE post SET likes_count = (SELECT count(*) FROM post_like WHERE post_id = %s) WHERE id = %s"

    for label, ordered in [("opposite order", False), ("both lock in id order first", True)]:
        x, _ = new_post(author=41)
        y, _ = new_post(author=42)
        log.section(f"{label} (post X = {x}, post Y = {y})")
        barrier = threading.Barrier(2, timeout=30)

        def job(who, first, second):
            conn = connect()
            start = time.perf_counter()
            try:
                with conn.transaction():
                    if ordered:
                        barrier.wait()
                        conn.execute("SELECT id FROM post WHERE id = ANY(%s) ORDER BY id FOR UPDATE", ([x, y],))
                        log(who, "locked both posts in id order")
                    conn.execute(recount, (first, first))
                    log(who, f"updated post {first}")
                    if not ordered:
                        barrier.wait()
                    conn.execute(recount, (second, second))
                    log(who, f"updated post {second}")
                log(who, f"committed after {time.perf_counter() - start:.3f}s")
            except errors.DeadlockDetected as e:
                log(who, f"40P01 deadlock detected after {time.perf_counter() - start:.3f}s: "
                         f"{e.diag.message_primary}; rolled back")
            conn.close()

        run_threads([(job, ("job A", x, y)), (job, ("job B", y, x))])
    log.save()


def t09_mvcc_and_locks():
    log = Log("t09_mvcc_and_locks", "T9: inside MVCC and row locking during a blocked update",
              "Session A updates a post and keeps its transaction open. An observer reads the row and the\n"
              "system views; session B tries to update the same row and blocks until A commits.")
    post, _ = new_post(author=51)
    row = ("SELECT xmin, xmax, ctid, caption FROM post WHERE id = %s")
    observer = connect(autocommit=True)

    def show(label):
        xmin, xmax, ctid, caption = observer.execute(row, (post,)).fetchone()
        log("observer", f"{label}: xmin={xmin} xmax={xmax} ctid={ctid} caption={caption!r}")

    show("before any update")
    a = connect()
    a_xid = a.execute("SELECT txid_current()").fetchone()[0]
    a.execute("UPDATE post SET caption = 'edited by A' WHERE id = %s", (post,))
    log("session A", f"txid {a_xid} updated the caption, not committed yet")
    show("while A is open (old version still visible, its xmax is A's txid)")
    for level in (RC, RR, SER):
        reader = connect(level)
        seen = reader.execute("SELECT caption FROM post WHERE id = %s", (post,)).fetchone()[0]
        reader.rollback()
        reader.close()
        log("observer", f"a {LEVEL_NAME[level]} reader sees caption={seen!r}")
        observe("Dirty read", level, seen == "edited by A")

    b_pid = {}

    def session_b():
        b = connect()
        b_pid["pid"] = b.execute("SELECT pg_backend_pid()").fetchone()[0]
        start = time.perf_counter()
        log("session B", "UPDATE the same row (will block on A's row lock)")
        b.execute("UPDATE post SET caption = 'edited by B' WHERE id = %s", (post,))
        log("session B", f"unblocked after {time.perf_counter() - start:.3f}s, updated, committing")
        b.commit()
        b.close()

    tb = threading.Thread(target=session_b)
    tb.start()
    time.sleep(1.0)
    waiting = observer.execute(
        "SELECT pid, wait_event_type, wait_event, pg_blocking_pids(pid), left(query, 50) "
        "FROM pg_stat_activity WHERE pid = %s", (b_pid["pid"],)).fetchone()
    log("observer", f"pg_stat_activity for B: pid={waiting[0]} wait_event_type={waiting[1]} "
                    f"wait_event={waiting[2]} blocked_by={waiting[3]} query={waiting[4]!r}")
    for lk in observer.execute("SELECT locktype, mode, granted, transactionid FROM pg_locks "
                               "WHERE pid = %s AND locktype IN ('transactionid', 'tuple') ORDER BY granted",
                               (b_pid["pid"],)).fetchall():
        log("observer", f"pg_locks for B: locktype={lk[0]} mode={lk[1]} granted={lk[2]} transactionid={lk[3]}")
    time.sleep(0.5)
    a.commit()
    log("session A", "committed")
    tb.join()
    show("after A and B committed (a new row version: new xmin and ctid)")
    a.close()
    observer.close()
    log.save()


def t10_double_close():
    log = Log("t10_double_close", "T10: two admins press 'close challenge' at the same moment",
              "Closing a challenge sets the winner and awards style points (BR-17). The naive version checks\n"
              "'no winner yet' with a plain read; the locked version reads the row FOR UPDATE, so the second\n"
              "admin waits, then sees the winner already set and does nothing.")

    def fixture():
        slug = f"p3-close-{uuid.uuid4().hex[:8]}"
        challenge = admin_sql("INSERT INTO challenge (slug, title, starts_at, ends_at, max_entries, reward_points) "
                              "VALUES (%s, 'Double close', now() - interval '8 days', now() - interval '1 hour', "
                              "10, 100) RETURNING id", (slug,))[0][0]
        for user in (61, 62):
            post, images = new_post(user)
            admin_sql("INSERT INTO challenge_entry (challenge_id, user_id, post_id) VALUES (%s, %s, %s)",
                      (challenge, user, post))
            if user == 61:
                admin_sql("INSERT INTO vote (user_id, post_id, post_image_id) VALUES (63, %s, %s)", (post, images[0]))
        admin_sql("UPDATE challenge SET entries_count = 2 WHERE id = %s", (challenge,))
        return challenge

    def close(who, challenge, lock, barrier):
        with connect() as conn, conn.transaction():
            barrier.wait()
            winner = conn.execute("SELECT winner_entry_id FROM challenge WHERE id = %s" + (" FOR UPDATE" if lock else ""),
                                  (challenge,)).fetchone()[0]
            if not lock:
                time.sleep(0.2)
            if winner is not None:
                log(who, f"winner already set ({winner}): nothing to do")
                return
            entry, user = conn.execute(
                "SELECT e.id, e.user_id FROM challenge_entry e LEFT JOIN vote v ON v.post_id = e.post_id "
                "WHERE e.challenge_id = %s GROUP BY e.id ORDER BY count(v.id) DESC, e.id LIMIT 1",
                (challenge,)).fetchone()
            conn.execute("UPDATE challenge SET winner_entry_id = %s WHERE id = %s", (entry, challenge))
            conn.execute("UPDATE app_user SET style_points = style_points + "
                         "(SELECT reward_points FROM challenge WHERE id = %s) WHERE id = %s", (challenge, user))
            log(who, f"set winner entry {entry} and awarded 100 points to user {user}")

    for label, lock in [("naive check with a plain SELECT", False), ("check with SELECT ... FOR UPDATE", True)]:
        challenge = fixture()
        before = admin_sql("SELECT style_points FROM app_user WHERE id = 61")[0][0]
        log.section(f"{label} (challenge {challenge}, reward 100)")
        barrier = threading.Barrier(2, timeout=30)
        run_threads([(close, ("admin 1", challenge, lock, barrier)), (close, ("admin 2", challenge, lock, barrier))])
        after = admin_sql("SELECT style_points FROM app_user WHERE id = 61")[0][0]
        log("result", f"winner's style points {before} -> {after} (awarded {after - before}, should be 100)")
    log.save()


def write_matrix():
    anomalies = ["Dirty read", "Non-repeatable read", "Phantom read", "Lost update", "Write skew"]
    levels = [LEVEL_NAME[lv] for lv in (RC, RR, SER)]
    source = {"Dirty read": "T9", "Non-repeatable read": "T7", "Phantom read": "T7", "Lost update": "T4",
              "Write skew": "T6"}
    lines = ["# Isolation matrix (observed)", "",
             "Generated by harness/concurrency.py from what each scenario actually observed on PostgreSQL 16.",
             "\"not run\" means the scenario did not exercise that level.", "",
             "| Anomaly | " + " | ".join(levels) + " | Scenario |", "|---|" + "---|" * len(levels) + "---|"]
    for anomaly in anomalies:
        cells = [MATRIX.get(anomaly, {}).get(lv, "not run") for lv in levels]
        lines.append(f"| {anomaly} | " + " | ".join(cells) + f" | {source[anomaly]} |")
    (EVIDENCE / "isolation_matrix.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


SCENARIOS = {"t04": t04_lost_update, "t05": t05_double_tap_vote, "t06": t06_write_skew,
             "t07": t07_non_repeatable_read, "t08": t08_deadlock, "t09": t09_mvcc_and_locks,
             "t10": t10_double_close}

if __name__ == "__main__":
    chosen = sys.argv[1:] or list(SCENARIOS)
    for key in chosen:
        print(f"\n===== {key} =====", flush=True)
        SCENARIOS[key]()
    if set(SCENARIOS) <= set(chosen):
        write_matrix()
