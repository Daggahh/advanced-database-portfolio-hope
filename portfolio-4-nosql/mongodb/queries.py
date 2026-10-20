"""MongoDB operations on the FitsCheck document model, each compared with its SQL equivalent.

For every operation: the MongoDB result is checked against the PostgreSQL result, both are timed
(median of 7 warm runs, client side), and explain("executionStats") shows whether an index was used
and how many keys and documents were examined.

Writes portfolio-4-nosql/evidence/mongo_queries.txt. Run migrate.py first.
"""

import os
import statistics
import time
from pathlib import Path

import psycopg
from pymongo import MongoClient
from pymongo.errors import WriteError

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "mongo_queries.txt"
CARD_POST = 1332
PROFILE_AUTHOR = 72535
lines = []


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def median_ms(fn, runs=7):
    fn()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def explain_find(collection, flt, sort=None, limit=0):
    cursor = collection.find(flt)
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    stats = cursor.explain()["executionStats"]
    return summarise(stats)


def explain_aggregate(db, pipeline):
    result = db.command({"explain": {"aggregate": "posts", "pipeline": pipeline, "cursor": {}},
                         "verbosity": "executionStats"})
    stats = result.get("executionStats") or result["stages"][0]["$cursor"]["executionStats"]
    return summarise(stats)


def summarise(stats):
    stages, node = [], stats["executionStages"]
    while node:
        stages.append(node["stage"] + (f"({node['indexName']})" if "indexName" in node else ""))
        node = node.get("inputStage")
    return (f"plan {' <- '.join(stages)}; keys examined {stats['totalKeysExamined']:,}, "
            f"documents examined {stats['totalDocsExamined']:,}, returned {stats['nReturned']:,}")


def section(title):
    log()
    log(title)
    log("-" * len(title))


def main():
    pg = psycopg.connect(os.environ["PG_URL"], options="-c search_path=fitscheck")
    db = MongoClient(os.environ["MONGO_URL"]).fitscheck

    log("MongoDB operations compared with PostgreSQL (median of 7 warm runs, client side)")
    log("=" * 80)

    section(f"1. Fit card for post {CARD_POST}: one document read against joins over five tables")
    doc = db.posts.find_one({"_id": CARD_POST})
    card_sql = ("SELECT p.id, u.username, "
                "(SELECT count(*) FROM post_image WHERE post_id = p.id), "
                "(SELECT count(*) FROM shop_item si JOIN post_image pi ON pi.id = si.post_image_id WHERE pi.post_id = p.id), "
                "(SELECT array_agg(h.name ORDER BY h.name) FROM post_hashtag ph JOIN hashtag h ON h.id = ph.hashtag_id "
                " WHERE ph.post_id = p.id), "
                "(SELECT array_agg(id ORDER BY created_at DESC) FROM (SELECT id, created_at FROM comment "
                " WHERE post_id = p.id AND parent_id IS NULL ORDER BY created_at DESC LIMIT 3) c) "
                "FROM post p JOIN app_user u ON u.id = p.author_id WHERE p.id = %s")
    row = pg.execute(card_sql, (CARD_POST,)).fetchone()
    mongo_view = (doc["_id"], doc["author"]["username"], len(doc["images"]),
                  sum(len(i["items"]) for i in doc["images"]), doc["hashtags"] or None,
                  [c["comment_id"] for c in doc["latest_comments"]] or None)
    log(f"MongoDB: post {mongo_view[0]} by {mongo_view[1]}, {mongo_view[2]} images, {mongo_view[3]} shop items, "
        f"hashtags {mongo_view[4]}, latest comments {mongo_view[5]}")
    log(f"SQL:     post {row[0]} by {row[1]}, {row[2]} images, {row[3]} shop items, hashtags {row[4]}, "
        f"latest comments {row[5]}")
    log(f"same card: {mongo_view == tuple(row)}")
    log(f"MongoDB find_one by _id: {median_ms(lambda: db.posts.find_one({'_id': CARD_POST})):.2f} ms")
    log(f"SQL joins for the card:  {median_ms(lambda: pg.execute(card_sql, (CARD_POST,)).fetchone()):.2f} ms")
    log(explain_find(db.posts, {"_id": CARD_POST}))

    for number, tag, sql_name in [(2, "ootd", "q16"), (3, "sneakers_2916", "q17")]:
        section(f"{number}. Brands worn in fits tagged #{tag} (aggregation pipeline against SQL {sql_name})")
        pipeline = [
            {"$match": {"hashtags": tag}},
            {"$unwind": "$images"},
            {"$unwind": "$images.items"},
            {"$match": {"images.items.brand": {"$ne": None}}},
            {"$group": {"_id": "$images.items.brand", "items": {"$sum": 1}}},
            {"$sort": {"items": -1, "_id": 1}},
            {"$limit": 10},
        ]
        mongo = [(d["_id"], d["items"]) for d in db.posts.aggregate(pipeline)]
        sql = ("SELECT b.name, count(*) FROM post_hashtag ph JOIN post_image pi ON pi.post_id = ph.post_id "
               "JOIN shop_item si ON si.post_image_id = pi.id JOIN brand b ON b.id = si.brand_id "
               "WHERE ph.hashtag_id = (SELECT id FROM hashtag WHERE name = %s) "
               "GROUP BY b.name ORDER BY count(*) DESC, b.name COLLATE \"C\" LIMIT 10")
        rows = [tuple(r) for r in pg.execute(sql, (tag,))]
        log(f"MongoDB: {mongo}")
        log(f"SQL:     {rows}")
        log(f"same result: {mongo == rows}")
        log(f"MongoDB aggregate: {median_ms(lambda: list(db.posts.aggregate(pipeline))):8.2f} ms")
        log(f"SQL join:          {median_ms(lambda: pg.execute(sql, (tag,)).fetchall()):8.2f} ms")
        log(explain_aggregate(db, pipeline))

    section(f"4. Profile page: latest 20 posts by creator {PROFILE_AUTHOR}")
    flt, sort = {"author.id": PROFILE_AUTHOR}, [("created_at", -1), ("_id", -1)]
    mongo = [d["_id"] for d in db.posts.find(flt, {"_id": 1}).sort(sort).limit(20)]
    sql = "SELECT id FROM post WHERE author_id = %s ORDER BY created_at DESC, id DESC LIMIT 20"
    rows = [r[0] for r in pg.execute(sql, (PROFILE_AUTHOR,))]
    log(f"same 20 posts in the same order: {mongo == rows}")
    log(f"MongoDB find + sort + limit: {median_ms(lambda: list(db.posts.find(flt).sort(sort).limit(20))):.2f} ms")
    log(f"SQL with ix_post_author_created: {median_ms(lambda: pg.execute(sql, (PROFILE_AUTHOR,)).fetchall()):.2f} ms")
    log(explain_find(db.posts, flt, sort, 20))

    section(f"5. Comments page for post {CARD_POST}: first 50 from the referenced collection")
    flt, sort = {"post_id": CARD_POST}, [("created_at", 1), ("_id", 1)]
    mongo = [d["_id"] for d in db.comments.find(flt, {"_id": 1}).sort(sort).limit(50)]
    sql = "SELECT id FROM comment WHERE post_id = %s ORDER BY created_at, id LIMIT 50"
    rows = [r[0] for r in pg.execute(sql, (CARD_POST,))]
    log(f"same 50 comments in the same order: {mongo == rows}")
    log(f"MongoDB: {median_ms(lambda: list(db.comments.find(flt).sort(sort).limit(50))):.2f} ms; "
        f"SQL: {median_ms(lambda: pg.execute(sql, (CARD_POST,)).fetchall()):.2f} ms")
    log(explain_find(db.comments, flt, sort, 50))

    section("6. The cost of the embedded author copy: one creator changes their username")
    author, posts = pg.execute("SELECT author_id, count(*) FROM post GROUP BY author_id "
                               "ORDER BY count(*) DESC LIMIT 1").fetchone()
    old = db.posts.find_one({"author.id": author})["author"]["username"]
    start = time.perf_counter()
    result = db.posts.update_many({"author.id": author}, {"$set": {"author.username": "renamed_for_test"}})
    mongo_ms = (time.perf_counter() - start) * 1000
    log(f"MongoDB: update_many touched {result.modified_count:,} post documents in {mongo_ms:.1f} ms")
    log("SQL: one row, UPDATE app_user SET username = ... WHERE id = ...; every query joins to it")
    db.posts.update_many({"author.id": author}, {"$set": {"author.username": old}})
    log(f"(creator {author} has {posts:,} posts; the username was restored afterwards)")

    section("7. The $jsonSchema validator rejects invalid documents")
    for label, bad in [("a fit with no images (BR-07)", {"images": []}),
                       ("a hashtag with capitals and a space", {"hashtags": ["Bad Tag"]})]:
        candidate = db.posts.find_one({"_id": CARD_POST})
        candidate.update({"_id": -1, **bad})
        try:
            db.posts.insert_one(candidate)
            log(f"{label}: accepted (unexpected)")
            db.posts.delete_one({"_id": -1})
        except WriteError as e:
            log(f"{label}: rejected, code {e.code} ({e.details.get('errmsg')})")

    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
