"""Streams the Portfolio 2 dataset into the Citus cluster with COPY, coordinator to workers.
Each like carries its post's author (post_author_id) so it is stored on the same shard as the post."""

import os
import time

import psycopg

CITUS = "postgresql://fitscheck:fitscheck_local@localhost:5451/fitscheck"
COPIES = [
    ("app_user", "SELECT id, username, created_at FROM fitscheck.app_user"),
    ("post", "SELECT id, author_id, caption, likes_count, created_at FROM fitscheck.post"),
    ("post_like", "SELECT p.author_id, pl.post_id, pl.user_id, pl.created_at "
                  "FROM fitscheck.post_like pl JOIN fitscheck.post p ON p.id = pl.post_id"),
    ("follow", "SELECT follower_id, followed_id, created_at FROM fitscheck.follow"),
    ("hashtag", "SELECT id, name, posts_count FROM fitscheck.hashtag"),
]

with psycopg.connect(os.environ["PG_URL"]) as src, psycopg.connect(CITUS) as dst:
    for table, query in COPIES:
        start = time.perf_counter()
        with src.cursor().copy(f"COPY ({query}) TO STDOUT") as out, \
                dst.cursor().copy(f"COPY {table} FROM STDIN") as inp:
            for chunk in out:
                inp.write(chunk)
        dst.commit()
        rows = dst.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"{table}: {rows:,} rows in {time.perf_counter() - start:.1f}s", flush=True)
    dst.execute("ANALYZE")
