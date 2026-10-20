"""Migrates the Portfolio 2 dataset from PostgreSQL into a MongoDB document model.

posts: one document per fit, shaped by how the app reads it. Images and their shop items are
embedded (bounded at 10 images, always read together), hashtags are an embedded array, the author's
username and avatar are an embedded copy (extended reference), and the latest three top-level comments
are embedded as a preview (subset pattern). PostgreSQL builds each document with jsonb functions, so
the shapes come straight from the relational data.

comments: every comment, referenced by post_id, because a post can have hundreds and the document
would otherwise grow without bound.

A $jsonSchema validator enforces document rules, including BR-07 (1 to 10 images), which the relational
schema could not express as a CHECK constraint. Prices are Decimal128, never floating point.

Writes portfolio-4-nosql/evidence/mongo_migration.txt.
"""

import json
import os
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING, MongoClient

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "mongo_migration.txt"
lines = []

POST_DOCUMENTS = """
SELECT jsonb_build_object(
    '_id', p.id,
    'author', jsonb_build_object('id', u.id, 'username', u.username, 'avatar_url', u.avatar_url),
    'caption', p.caption,
    'created_at', p.created_at,
    'counts', jsonb_build_object('likes', p.likes_count, 'comments', p.comments_count),
    'hashtags', (SELECT coalesce(jsonb_agg(h.name ORDER BY h.name), '[]'::jsonb)
                 FROM post_hashtag ph JOIN hashtag h ON h.id = ph.hashtag_id WHERE ph.post_id = p.id),
    'images', (SELECT jsonb_agg(jsonb_build_object(
                   'position', pi.position,
                   'url', pi.image_url,
                   'items', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                 'name', si.item_name, 'brand', b.name,
                                 'price', si.price::text, 'currency', si.currency) ORDER BY si.id), '[]'::jsonb)
                             FROM shop_item si LEFT JOIN brand b ON b.id = si.brand_id
                             WHERE si.post_image_id = pi.id)) ORDER BY pi.position)
               FROM post_image pi WHERE pi.post_id = p.id),
    'latest_comments', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                            'comment_id', c.id, 'author_id', c.author_id, 'body', c.body,
                            'created_at', c.created_at) ORDER BY c.created_at DESC), '[]'::jsonb)
                        FROM (SELECT * FROM comment WHERE post_id = p.id AND parent_id IS NULL
                              ORDER BY created_at DESC LIMIT 3) c)
)
FROM post p JOIN app_user u ON u.id = p.author_id
ORDER BY p.id
"""

POST_SCHEMA = {
    "bsonType": "object",
    "required": ["_id", "author", "created_at", "counts", "hashtags", "images"],
    "properties": {
        "author": {"bsonType": "object", "required": ["id", "username"]},
        "created_at": {"bsonType": "date"},
        "counts": {"bsonType": "object", "properties": {
            "likes": {"bsonType": "int", "minimum": 0}, "comments": {"bsonType": "int", "minimum": 0}}},
        "hashtags": {"bsonType": "array", "items": {"bsonType": "string", "pattern": "^[a-z0-9_]+$"}},
        "images": {"bsonType": "array", "minItems": 1, "maxItems": 10, "items": {
            "bsonType": "object", "required": ["position", "url", "items"], "properties": {
                "position": {"bsonType": "int", "minimum": 1, "maximum": 10},
                "items": {"bsonType": "array", "items": {
                    "bsonType": "object", "required": ["name", "price", "currency"], "properties": {
                        "price": {"bsonType": "decimal"},
                        "currency": {"bsonType": "string", "pattern": "^[A-Z]{3}$"}}}}}}},
    },
}


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def to_document(doc):
    doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    for comment in doc["latest_comments"]:
        comment["created_at"] = datetime.fromisoformat(comment["created_at"])
    for image in doc["images"]:
        for item in image["items"]:
            item["price"] = Decimal128(Decimal(item["price"]))
    return doc


def main():
    pg = psycopg.connect(os.environ["PG_URL"], options="-c search_path=fitscheck")
    db = MongoClient(os.environ["MONGO_URL"]).fitscheck
    db.drop_collection("posts")
    db.drop_collection("comments")
    db.create_collection("posts", validator={"$jsonSchema": POST_SCHEMA}, validationAction="error")

    log("PostgreSQL -> MongoDB migration")
    log("=" * 31)
    start = time.perf_counter()
    batch, total = [], 0
    with pg.cursor(name="posts") as cur:
        cur.itersize = 5000
        cur.execute(POST_DOCUMENTS)
        for (doc,) in cur:
            batch.append(to_document(doc))
            if len(batch) == 5000:
                db.posts.insert_many(batch, ordered=False)
                total += len(batch)
                batch = []
    if batch:
        db.posts.insert_many(batch, ordered=False)
        total += len(batch)
    log(f"posts: {total:,} documents in {time.perf_counter() - start:.1f}s")

    start = time.perf_counter()
    batch, total = [], 0
    with pg.cursor(name="comments") as cur:
        cur.itersize = 20000
        cur.execute("SELECT id, post_id, author_id, parent_id, body, created_at FROM comment ORDER BY id")
        for cid, post_id, author_id, parent_id, body, created_at in cur:
            batch.append({"_id": cid, "post_id": post_id, "author_id": author_id, "parent_id": parent_id,
                          "body": body, "created_at": created_at})
            if len(batch) == 20000:
                db.comments.insert_many(batch, ordered=False)
                total += len(batch)
                batch = []
    if batch:
        db.comments.insert_many(batch, ordered=False)
        total += len(batch)
    log(f"comments: {total:,} documents in {time.perf_counter() - start:.1f}s")

    start = time.perf_counter()
    # The sort tie-break (_id) is part of each index, so sorted reads come straight from the index with
    # no in-memory SORT stage, as with ix_post_author_created in Portfolio 2
    db.posts.create_index([("author.id", ASCENDING), ("created_at", DESCENDING), ("_id", DESCENDING)],
                          name="ix_posts_author_created")
    db.posts.create_index([("hashtags", ASCENDING), ("created_at", DESCENDING)], name="ix_posts_hashtags_created")
    db.comments.create_index([("post_id", ASCENDING), ("created_at", ASCENDING), ("_id", ASCENDING)],
                             name="ix_comments_post_created")
    log(f"indexes built in {time.perf_counter() - start:.1f}s")

    for name in ("posts", "comments"):
        stats = db.command("collStats", name)
        log(f"{name}: {stats['count']:,} documents, average {stats['avgObjSize']:,} bytes, "
            f"data {stats['size'] / 2**20:.1f} MB, storage {stats['storageSize'] / 2**20:.1f} MB, "
            f"indexes {stats['totalIndexSize'] / 2**20:.1f} MB")

    sample = db.posts.find_one({"counts.comments": {"$gte": 3}, "images.1": {"$exists": True},
                                "images.items.0": {"$exists": True}}, sort=[("_id", ASCENDING)])
    log()
    log("Sample document (a fit with several images, shop items and comments):")
    log(json.dumps(sample, default=str, indent=2))
    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
