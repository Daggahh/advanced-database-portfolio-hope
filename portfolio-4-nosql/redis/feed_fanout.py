"""Fan-out-on-write home feeds in Redis, built from the Portfolio 2 dataset.

When a user posts, the post id is pushed onto the list of every follower (LPUSH feed:<user>) and the
list is trimmed to its newest 500 ids (LTRIM). Reading a feed is then one LRANGE instead of a join.
This script replays all 300,000 posts in time order to build every feed, then:

1. checks that the Redis feed of the Portfolio 2 feed user returns exactly the ids SQL query q01 does;
2. times the read path (LRANGE, then fetch the 20 posts by primary key) against q01;
3. measures the celebrity problem: the cost of fanning out one post from the most-followed creator
   against a typical creator.

Writes portfolio-4-nosql/evidence/redis_feed_fanout.txt.
"""

import os
import statistics
import time
from collections import defaultdict
from pathlib import Path

import psycopg
import redis

FEED_LEN = 500
FEED_USER = 82114
AS_OF = "2026-10-15 00:00:00+00"
EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "redis_feed_fanout.txt"
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


def main():
    pg = psycopg.connect(os.environ["PG_URL"], options="-c search_path=fitscheck")
    r = redis.from_url(os.environ["REDIS_URL"])

    log("Fan-out-on-write home feeds (Redis lists), built from the Portfolio 2 dataset")
    log("=" * 78)

    followers = defaultdict(list)
    for follower, followed in pg.execute("SELECT follower_id, followed_id FROM follow"):
        followers[followed].append(follower)
    posts = pg.execute("SELECT id, author_id FROM post WHERE created_at < %s ORDER BY created_at, id",
                       (AS_OF,)).fetchall()
    log(f"loaded {sum(map(len, followers.values())):,} follows and {len(posts):,} posts")

    for key in r.scan_iter("feed:*", count=10_000):
        r.delete(key)
    start = time.perf_counter()
    pushes = 0
    pipe = r.pipeline(transaction=False)
    for post_id, author in posts:
        for follower in followers.get(author, ()):
            pipe.lpush(f"feed:{follower}", post_id)
            pipe.ltrim(f"feed:{follower}", 0, FEED_LEN - 1)
            pushes += 1
        if len(pipe) >= 20_000:
            pipe.execute()
    pipe.execute()
    elapsed = time.perf_counter() - start
    feeds = sum(1 for _ in r.scan_iter("feed:*", count=10_000))
    memory = r.info("memory")["used_memory_human"]
    log(f"fan-out: {pushes:,} pushes into {feeds:,} feeds in {elapsed:.1f}s "
        f"({pushes / elapsed:,.0f} pushes/s), each feed capped at {FEED_LEN}; Redis memory {memory}")

    log()
    log(f"Correctness: feed of user {FEED_USER}")
    redis_ids = [int(x) for x in r.lrange(f"feed:{FEED_USER}", 0, 19)]
    sql = ("SELECT p.id FROM follow f JOIN post p ON p.author_id = f.followed_id "
           "WHERE f.follower_id = %s AND p.created_at < %s ORDER BY p.created_at DESC, p.id DESC LIMIT 20")
    sql_ids = [row[0] for row in pg.execute(sql, (FEED_USER, AS_OF))]
    log(f"Redis LRANGE feed:{FEED_USER} 0 19 -> {redis_ids}")
    log(f"SQL q01 ids                      -> {sql_ids}")
    log(f"identical: {redis_ids == sql_ids}")

    log()
    log("Read path, median of 7 runs (warm)")
    detail = ("SELECT id, author_id, caption, likes_count, comments_count, created_at FROM post "
              "WHERE id = ANY(%s)")

    def redis_read():
        ids = [int(x) for x in r.lrange(f"feed:{FEED_USER}", 0, 19)]
        pg.execute(detail, (ids,)).fetchall()

    def sql_read():
        pg.execute(sql.replace("SELECT p.id", "SELECT p.id, p.author_id, p.caption, p.likes_count, "
                                              "p.comments_count, p.created_at"), (FEED_USER, AS_OF)).fetchall()

    lrange_only = median_ms(lambda: r.lrange(f"feed:{FEED_USER}", 0, 19))
    log(f"Redis LRANGE alone:                           {lrange_only:6.2f} ms")
    log(f"Redis LRANGE + fetch 20 posts by primary key: {median_ms(redis_read):6.2f} ms")
    log(f"SQL q01 with ix_post_author_created:          {median_ms(sql_read):6.2f} ms")
    log("(client-side round-trip times; P2 reported q01 server execution time as 6.8 ms)")

    log()
    log("The celebrity problem: fan-out cost of one new post")
    by_size = sorted(followers.items(), key=lambda kv: len(kv[1]))
    celebrity, celeb_followers = by_size[-1]
    typical, typical_followers = by_size[len(by_size) // 2]

    def fan_out(author_followers):
        pipe = r.pipeline(transaction=False)
        for follower in author_followers:
            pipe.lpush(f"feed:{follower}", 0)
            pipe.ltrim(f"feed:{follower}", 0, FEED_LEN - 1)
        pipe.execute()

    for label, author, flw in [("typical creator", typical, typical_followers),
                               ("most-followed creator", celebrity, celeb_followers)]:
        ms = median_ms(lambda: fan_out(flw), runs=3)
        log(f"{label:22} (user {author}): {len(flw):>6,} followers -> {len(flw):>6,} writes, {ms:8.1f} ms")
    for follower in celeb_followers + typical_followers:
        r.lrem(f"feed:{follower}", 0, 0)
    log("(the test pushes used post id 0 and were removed afterwards)")

    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
