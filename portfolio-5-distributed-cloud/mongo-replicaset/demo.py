"""MongoDB replica set behaviour for FitsCheck. Runs inside the replica set's Docker network (see run.sh)
so the driver can reach every member by name, discover the primary and follow elections itself.

Phases, called by run.sh in order (the host kills members between them):
  load      load the fit documents, compare write concerns, read your own writes, transactions
  failover  write continuously while the host kills the primary; count acknowledged writes afterwards
  quorum    after the host kills a second member: majority writes can no longer succeed

Appends to /evidence/mongo_replicaset_demo.txt.
"""

import statistics
import sys
import time
from pathlib import Path

from bson import json_util
from pymongo import MongoClient, ReadPreference, WriteConcern
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern

URI = "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0&serverSelectionTimeoutMS=20000"
EVIDENCE = Path("/evidence/mongo_replicaset_demo.txt")


def log(text=""):
    print(text, flush=True)
    with EVIDENCE.open("a") as f:
        f.write(text + "\n")


def section(title):
    log()
    log(title)
    log("-" * len(title))


def members(client):
    status = client.admin.command("replSetGetStatus")
    return ", ".join(f"{m['name'].split(':')[0]}={m['stateStr']}" for m in status["members"])


def phase_load():
    client = MongoClient(URI)
    db = client.fitscheck
    log("MongoDB 7 replica set rs0: three members, FitsCheck fit documents")
    log("=" * 66)
    section("1. Members and data")
    log(f"members: {members(client)}")
    docs = [json_util.loads(line) for line in Path("/data/posts.jsonl").read_text().splitlines()]
    db.drop_collection("posts")
    db.drop_collection("comments")
    start = time.perf_counter()
    db.get_collection("posts", write_concern=WriteConcern(w="majority")).insert_many(docs)
    log(f"inserted {len(docs):,} fit documents with w:majority in {time.perf_counter() - start:.1f}s")
    for host in ("mongo1", "mongo2", "mongo3"):
        direct = MongoClient(f"mongodb://{host}:27017/?directConnection=true")
        role = "primary" if direct.admin.command("hello")["isWritablePrimary"] else "secondary"
        count = direct.fitscheck.posts.count_documents({})
        log(f"  {host} ({role}) holds {count:,} posts")

    section("2. Write concern: who must acknowledge before the write returns")
    for label, wc in [("w:1        (primary only)", WriteConcern(w=1)),
                      ("w:majority (2 of 3 members)", WriteConcern(w="majority"))]:
        coll = db.get_collection("probe", write_concern=wc)
        times = []
        for i in range(200):
            start = time.perf_counter()
            coll.insert_one({"i": i})
            times.append((time.perf_counter() - start) * 1000)
        log(f"{label}: median {statistics.median(times):.2f} ms over 200 inserts")
    log("a w:1 write can be lost if the primary fails before a secondary copies it; a w:majority write cannot")

    section("3. Reading your own write from a secondary")
    secondary = db.get_collection("posts", read_preference=ReadPreference.SECONDARY,
                                  write_concern=WriteConcern(w=1))
    misses = 0
    for i in range(200):
        post_id = 900_000 + i
        db.get_collection("posts", write_concern=WriteConcern(w=1)).insert_one(
            {**docs[0], "_id": post_id, "caption": "fresh post"})
        if secondary.find_one({"_id": post_id}) is None:
            misses += 1
    log(f"plain session, w:1, read from a secondary straight after writing: own post missing {misses} of 200 times")
    misses = 0
    with client.start_session(causal_consistency=True) as session:
        writer = db.get_collection("posts", write_concern=WriteConcern(w="majority"))
        reader = db.get_collection("posts", read_preference=ReadPreference.SECONDARY,
                                   read_concern=ReadConcern("majority"))
        for i in range(200):
            post_id = 910_000 + i
            writer.insert_one({**docs[0], "_id": post_id, "caption": "fresh post"}, session=session)
            if reader.find_one({"_id": post_id}, session=session) is None:
                misses += 1
    log(f"causally consistent session, w:majority + read concern majority, secondary read: missing {misses} of 200 times")
    log("(the session sends its last operation time, so the secondary waits until it has caught up)")

    section("4. Multi-document transaction: a post and its first comment together")
    comments = db.comments
    with client.start_session() as session:
        with session.start_transaction(write_concern=WriteConcern(w="majority")):
            db.posts.insert_one({**docs[0], "_id": 920_000, "caption": "post with comment"}, session=session)
            comments.insert_one({"_id": 1, "post_id": 920_000, "body": "first!"}, session=session)
    log(f"committed: post present={db.posts.count_documents({'_id': 920_000}) == 1}, "
        f"comment present={comments.count_documents({'_id': 1}) == 1}")
    try:
        with client.start_session() as session:
            with session.start_transaction():
                db.posts.insert_one({**docs[0], "_id": 920_001, "caption": "aborted post"}, session=session)
                comments.insert_one({"_id": 1, "post_id": 920_001, "body": "duplicate id"}, session=session)
    except PyMongoError as e:
        log(f"second transaction failed on its comment ({type(e).__name__}); the whole transaction aborted")
    log(f"aborted post present: {db.posts.count_documents({'_id': 920_001}) == 1} "
        "(single-node MongoDB in Portfolio 4 could not run multi-document transactions)")


def phase_failover():
    client = MongoClient(URI, retryWrites=True)
    coll = client.fitscheck.get_collection("heartbeat", write_concern=WriteConcern(w="majority"))
    coll.drop()
    section("5. Failover under load: one w:majority write every 100 ms while the primary is killed")
    log(f"before: {members(client)}")
    acknowledged, failed, slowest, t0 = [], 0, (0.0, 0), time.perf_counter()
    for i in range(250):
        start = time.perf_counter()
        try:
            coll.insert_one({"_id": i, "at": time.time()})
            acknowledged.append(i)
            took = time.perf_counter() - start
            if took > slowest[0]:
                slowest = (took, i)
        except PyMongoError as e:
            failed += 1
            log(f"  write {i} failed after {time.perf_counter() - start:.1f}s: {type(e).__name__}")
        time.sleep(0.1)
    log(f"ran {time.perf_counter() - t0:.1f}s: {len(acknowledged)} writes acknowledged, {failed} failed")
    log(f"slowest acknowledged write: #{slowest[1]} took {slowest[0]:.2f}s (the election, absorbed by the "
        "driver's automatic retry)")
    stored = set(d["_id"] for d in coll.find({}, {"_id": 1}))
    log(f"after: {members(client)}")
    log(f"every acknowledged write is stored on the new primary: {set(acknowledged) <= stored} "
        f"({len(stored)} stored)")


def phase_quorum():
    section("6. Losing the majority: two of three members down")
    client = MongoClient(URI, serverSelectionTimeoutMS=8000)
    try:
        log(f"members seen: {members(client)}")
    except PyMongoError as e:
        log(f"replica set status unavailable from a primary: {type(e).__name__}")
    direct = MongoClient("mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rs0"
                         "&serverSelectionTimeoutMS=8000")
    start = time.perf_counter()
    try:
        direct.fitscheck.get_collection("heartbeat", write_concern=WriteConcern(w="majority", wtimeout=3000)) \
              .insert_one({"_id": "after quorum loss"})
        log("write succeeded (unexpected)")
    except PyMongoError as e:
        log(f"w:majority write refused after {time.perf_counter() - start:.1f}s: {type(e).__name__}")
    survivors = []
    for host in ("mongo1", "mongo2", "mongo3"):
        try:
            hello = MongoClient(f"mongodb://{host}:27017/?directConnection=true&serverSelectionTimeoutMS=2000") \
                .admin.command("hello")
            survivors.append(f"{host} is {'primary' if hello['isWritablePrimary'] else 'secondary'}")
        except PyMongoError:
            survivors.append(f"{host} is down")
    log("; ".join(survivors))
    log("the surviving member steps down to secondary: without a majority no primary can be elected, so the")
    log("replica set stops accepting writes rather than risk two primaries accepting conflicting writes")


if __name__ == "__main__":
    {"load": phase_load, "failover": phase_failover, "quorum": phase_quorum}[sys.argv[1]]()
