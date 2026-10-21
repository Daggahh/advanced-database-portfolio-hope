"""Sharding FitsCheck by creator with Citus: shard placement, single-shard against all-shard queries,
the home feed join that the shard key cannot serve, and hot shards from skewed creators.

Every query is run on the Citus cluster and on the single-node Portfolio 2 database, checked for the
same answer, and timed (client side, median of 5). EXPLAIN shows how many shard tasks Citus ran.
Writes portfolio-5-distributed-cloud/evidence/citus_demo.txt. Run schema.sql and load.py first.
"""

import os
import re
import statistics
import time
from pathlib import Path

import psycopg

CITUS = "postgresql://fitscheck:fitscheck_local@localhost:5451/fitscheck"
EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "citus_demo.txt"
CREATOR = 72535
FEED_USER = 82114
AS_OF = "2026-10-15 00:00:00+00"
lines = []


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def section(title):
    log()
    log(title)
    log("-" * len(title))


def median_ms(conn, sql, params, runs=5):
    conn.execute(sql, params).fetchall()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        conn.execute(sql, params).fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def task_count(conn, sql, params):
    plan = "\n".join(r[0] for r in conn.execute("EXPLAIN " + sql, params))
    counts = re.findall(r"Task Count: (\d+)", plan)
    router = "Router" in plan or "Single" in plan
    return (", ".join(counts) if counts else "?") + (" (router query)" if router else "")


def compare(label, citus, single, sql, params, single_sql=None):
    a = citus.execute(sql, params).fetchall()
    b = single.execute(single_sql or sql, params).fetchall()
    log(f"{label}")
    log(f"  same answer as single-node PostgreSQL: {a == b} ({len(a)} rows)")
    log(f"  Citus shard tasks: {task_count(citus, sql, params)}")
    log(f"  Citus {median_ms(citus, sql, params):.2f} ms, single node "
        f"{median_ms(single, single_sql or sql, params):.2f} ms (client side, median of 5)")


def main():
    citus = psycopg.connect(CITUS, autocommit=True)
    single = psycopg.connect(os.environ["PG_URL"], autocommit=True, options="-c search_path=fitscheck")

    log("Sharding FitsCheck by creator with Citus 12.1 (coordinator + 2 workers, 16 shards per table)")
    log("=" * 93)

    section("1. Where the data lives")
    for row in citus.execute("SELECT nodename, count(*) AS shards, pg_size_pretty(sum(shard_size)) "
                             "FROM citus_shards WHERE citus_table_type = 'distributed' GROUP BY nodename ORDER BY 1"):
        log(f"{row[0]}: {row[1]} shards, {row[2]}")
    shard = citus.execute("SELECT get_shard_id_for_distribution_column('post', %s)", (CREATOR,)).fetchone()[0]
    node = citus.execute("SELECT nodename FROM citus_shards WHERE shardid = %s", (shard,)).fetchone()[0]
    log(f"creator {CREATOR}'s posts are in shard {shard} on {node}, together with their profile and the likes "
        "on their posts (co-location)")

    section("2. Queries that use the shard key, and queries that cannot")
    compare(f"Profile page: latest 20 posts by creator {CREATOR}", citus, single,
            "SELECT id FROM post WHERE author_id = %s ORDER BY created_at DESC, id DESC LIMIT 20", (CREATOR,))
    compare(f"Creator {CREATOR}'s five most-liked posts (join of post and post_like on one shard)", citus, single,
            "SELECT p.id, count(*) FROM post p JOIN post_like pl ON pl.post_author_id = p.author_id "
            "AND pl.post_id = p.id WHERE p.author_id = %s GROUP BY p.id ORDER BY count(*) DESC, p.id LIMIT 5",
            (CREATOR,),
            single_sql="SELECT p.id, count(*) FROM post p JOIN post_like pl ON pl.post_id = p.id "
                       "WHERE p.author_id = %s GROUP BY p.id ORDER BY count(*) DESC, p.id LIMIT 5")
    compare("Trending: most-liked posts in the last 24 hours (every shard, merged on the coordinator)", citus, single,
            "SELECT post_id, count(*) FROM post_like WHERE created_at >= %s::timestamptz - interval '24 hours' "
            "AND created_at < %s GROUP BY post_id ORDER BY count(*) DESC, post_id LIMIT 20", (AS_OF, AS_OF))

    section("3. The home feed: follows are sharded by follower, posts by author")
    feed = ("SELECT p.id FROM follow f JOIN post p ON p.author_id = f.followed_id WHERE f.follower_id = %s "
            "AND p.created_at < %s ORDER BY p.created_at DESC, p.id DESC LIMIT 20")
    try:
        citus.execute(feed, (FEED_USER, AS_OF)).fetchall()
        log("the single-query join ran (unexpected)")
    except psycopg.Error as e:
        log(f"single-query join refused: {e.diag.message_primary}")
    log("rewritten in two steps: read the user's follows from their shard, then ask only the authors' shards")
    followed = [r[0] for r in citus.execute("SELECT followed_id FROM follow WHERE follower_id = %s", (FEED_USER,))]
    two_step = ("SELECT id FROM post WHERE author_id = ANY(%s) AND created_at < %s "
                "ORDER BY created_at DESC, id DESC LIMIT 20")
    a = [r[0] for r in citus.execute(two_step, (followed, AS_OF))]
    b = [r[0] for r in single.execute(feed, (FEED_USER, AS_OF))]
    shards = citus.execute("SELECT count(DISTINCT get_shard_id_for_distribution_column('post', a)) "
                           "FROM unnest(%s::bigint[]) a", (followed,)).fetchone()[0]
    log(f"  same 20 posts as the single-node feed (Portfolio 2 q01): {a == b}")
    log(f"  the user follows {len(followed)} accounts spread over {shards} of 16 shards; Citus tasks: "
        f"{task_count(citus, two_step, (followed, AS_OF))}")
    log("  (this cross-shard fan-in on every feed read is why feeds were precomputed in Redis in Portfolio 4)")

    section("4. Hot shards: skewed creators make uneven shards")
    for table in ("post", "post_like"):
        counts = sorted(r[1] for r in citus.execute(
            "SELECT shardid, result::bigint FROM run_command_on_shards(%s, 'SELECT count(*) FROM %%s')", (table,)))
        median = statistics.median(counts)
        log(f"{table:9} rows per shard: smallest {counts[0]:,}, median {median:,.0f}, largest {counts[-1]:,} "
            f"(largest is {counts[-1] / median:.2f}x the median)")
    top = citus.execute("SELECT post_author_id, count(*) FROM post_like GROUP BY 1 ORDER BY 2 DESC LIMIT 1").fetchone()
    log(f"the creator with the most likes on their posts (user {top[0]}, {top[1]:,} likes) sits on one shard: "
        "every like for them is written to that shard")

    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
