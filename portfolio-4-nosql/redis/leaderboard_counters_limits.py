"""Three more Redis patterns for FitsCheck, each compared with its SQL equivalent.

1. Challenge leaderboard as a sorted set: every vote is a ZINCRBY, the top 10 is one ZREVRANGE and a
   user's position is one ZREVRANK. Checked against Portfolio 2's SQL leaderboard q06 (challenge 92).
2. Like counters with INCR: the Portfolio 3 T4 race (50 simultaneous likes) replayed against Redis,
   then the deltas are flushed to PostgreSQL in post-id order (the T8 deadlock lesson) and checked
   with v_counter_drift. Writes go to the fitscheck_p3 database so the Portfolio 2 dataset is untouched.
3. Rate limiting with expiring keys: at most 5 likes per user per 3-second window.

Writes portfolio-4-nosql/evidence/redis_leaderboard_counters_limits.txt.
"""

import os
import statistics
import threading
import time
from pathlib import Path

import psycopg
import redis

CHALLENGE = 92
EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "redis_leaderboard_counters_limits.txt"
lines = []


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def median_ms(fn, runs=7):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def leaderboard(r, pg):
    log("1. Challenge leaderboard (sorted set)")
    log("-" * 40)
    key = f"leaderboard:challenge:{CHALLENGE}"
    r.delete(key)
    entries = pg.execute("SELECT id, post_id FROM challenge_entry WHERE challenge_id = %s", (CHALLENGE,)).fetchall()
    entry_of_post = {post: entry for entry, post in entries}
    pipe = r.pipeline(transaction=False)
    # Ties: ZREVRANGE orders equal scores by member, but the product ranks equal votes by earliest entry.
    # Starting each score at -entry_id * 1e-6 builds that tie-break into the score itself; whole votes
    # still dominate, and the vote count is recovered by rounding.
    for entry, _ in entries:
        pipe.zadd(key, {entry: -entry * 1e-6})
    votes = pg.execute("SELECT post_id FROM vote WHERE post_id = ANY(%s) ORDER BY created_at",
                       (list(entry_of_post),)).fetchall()
    for (post,) in votes:
        pipe.zincrby(key, 1, entry_of_post[post])
    pipe.execute()
    log(f"replayed {len(votes)} votes as ZINCRBY onto {len(entries)} entries")

    top = r.zrevrange(key, 0, 9, withscores=True)
    redis_top = [(int(m), round(s + int(m) * 1e-6)) for m, s in top]
    sql = ("SELECT e.id, count(v.id) FROM challenge_entry e LEFT JOIN vote v ON v.post_id = e.post_id "
           "WHERE e.challenge_id = %s GROUP BY e.id ORDER BY count(v.id) DESC, e.id LIMIT 10")
    sql_top = [tuple(row) for row in pg.execute(sql, (CHALLENGE,))]
    log(f"Redis ZREVRANGE top 10 (entry, votes): {redis_top}")
    log(f"SQL q06 top 10 (entry, votes):         {sql_top}")
    same_scores = [s for _, s in redis_top] == [s for _, s in sql_top]
    log(f"same vote counts in the same order: {same_scores}; same entries: {redis_top == sql_top}")
    log("(equal votes rank by lowest entry id in both, via the tie-break built into the Redis score)")
    leader = redis_top[0][0]
    log(f"ZREVRANK of entry {leader}: {r.zrevrank(key, leader)} (0 = first place)")
    log(f"read top 10: Redis {median_ms(lambda: r.zrevrange(key, 0, 9, withscores=True)):.2f} ms, "
        f"SQL {median_ms(lambda: pg.execute(sql, (CHALLENGE,)).fetchall()):.2f} ms (median of 7, client side)")
    log()


def counters(r, p3):
    log("2. Like counters with INCR, flushed to PostgreSQL")
    log("-" * 40)
    post = p3.execute("SELECT post_fit(1, 'P4 counter fixture', ARRAY['p4.jpg'])").fetchone()[0]
    p3.commit()
    key = f"likes:post:{post}"
    r.delete(key)
    barrier = threading.Barrier(50, timeout=30)

    def like(user):
        conn = psycopg.connect(P3_URL, autocommit=True, options="-c search_path=fitscheck")
        barrier.wait()
        conn.execute("INSERT INTO post_like (user_id, post_id) VALUES (%s, %s)", (user, post))
        redis.from_url(os.environ["REDIS_URL"]).incr(key)
        conn.close()

    threads = [threading.Thread(target=like, args=(u,)) for u in range(2, 52)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log(f"50 sessions each inserted a post_like row and ran INCR {key} at the same moment")
    log(f"Redis counter = {int(r.get(key))} (Redis runs commands one at a time, so INCR cannot lose an update)")

    def flush():
        """Move every pending delta into PostgreSQL. GETDEL reads and resets each counter in one atomic
        step, so likes arriving during the flush land in a fresh counter. Posts are updated in id order
        so two flush jobs can never deadlock (Portfolio 3, T8)."""
        deltas = {}
        for k in r.scan_iter("likes:post:*", count=1000):
            value = r.getdel(k)
            if value:
                deltas[int(k.decode().rsplit(":", 1)[1])] = int(value)
        with p3.transaction():
            for post_id in sorted(deltas):
                p3.execute("UPDATE post SET likes_count = likes_count + %s WHERE id = %s", (deltas[post_id], post_id))
        return deltas

    before = p3.execute("SELECT likes_count FROM post WHERE id = %s", (post,)).fetchone()[0]
    deltas = flush()
    after = p3.execute("SELECT likes_count FROM post WHERE id = %s", (post,)).fetchone()[0]
    rows = p3.execute("SELECT count(*) FROM post_like WHERE post_id = %s", (post,)).fetchone()[0]
    drift = p3.execute("SELECT count(*) FROM v_counter_drift WHERE counter = 'post.likes_count' AND row_id = %s",
                       (post,)).fetchone()[0]
    log(f"flush applied {deltas}: likes_count {before} -> {after}; post_like rows = {rows}; "
        f"v_counter_drift rows for this post = {drift}")
    log("compare Portfolio 3 T4: the same race at READ COMMITTED left likes_count at 1 (49 lost)")
    log()


def rate_limit(r):
    log("3. Rate limiting with expiring keys (at most 5 likes per user per 3 s window)")
    log("-" * 40)
    user, limit, window = 77, 5, 3

    def allowed():
        bucket = int(time.time() // window)
        key = f"ratelimit:like:{user}:{bucket}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window * 2)
        count, _ = pipe.execute()
        return count <= limit, count, key

    time.sleep(window - (time.time() % window) + 0.05)
    for attempt in range(1, 8):
        ok, count, key = allowed()
        log(f"like attempt {attempt}: count in window = {count} -> {'allowed' if ok else 'rejected'}")
    log(f"TTL {key} = {r.ttl(key)} s: the key deletes itself, so no cleanup job is needed")
    time.sleep(window)
    ok, count, _ = allowed()
    log(f"after the window passes: count = {count} -> {'allowed' if ok else 'rejected'}")
    log()


P3_URL = os.environ["PG_URL"].rsplit("/", 1)[0] + "/fitscheck_p3"


def main():
    r = redis.from_url(os.environ["REDIS_URL"])
    pg = psycopg.connect(os.environ["PG_URL"], options="-c search_path=fitscheck")
    p3 = psycopg.connect(P3_URL, options="-c search_path=fitscheck")
    log("Redis leaderboard, counters and rate limiting")
    log("=" * 46)
    log()
    leaderboard(r, pg)
    counters(r, p3)
    rate_limit(r)
    persistence = r.config_get("save") | r.config_get("appendonly")
    log(f"Durability settings of this Redis: {persistence}")
    log("(RDB snapshots only, no append-only file: a crash can lose writes since the last snapshot)")
    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
