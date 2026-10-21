"""Exports FitsCheck fit documents from the fitscheck_p3 database for the replica set demo, using the
same document query as the Portfolio 4 migration so the shape is identical. Writes .data/posts.jsonl
in MongoDB Extended JSON, which keeps dates and Decimal128 prices exact."""

import os
import sys
from pathlib import Path

import psycopg
from bson import json_util

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "portfolio-4-nosql" / "mongodb"))
from migrate import POST_DOCUMENTS, to_document  # noqa: E402

out = Path(__file__).resolve().parent / ".data" / "posts.jsonl"
out.parent.mkdir(exist_ok=True)
url = os.environ["PG_URL"].rsplit("/", 1)[0] + "/fitscheck_p3"
with psycopg.connect(url, options="-c search_path=fitscheck") as pg, out.open("w") as f:
    count = 0
    for (doc,) in pg.execute(POST_DOCUMENTS):
        f.write(json_util.dumps(to_document(doc)) + "\n")
        count += 1
print(f"exported {count:,} fit documents to {out}")
