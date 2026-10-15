"""Synthetic FitsCheck data generator.

Fills the fitscheck schema (Portfolio 1 scripts 01-04 must already be loaded) with deterministic,
realistically skewed data: a few creators, posts and hashtags attract most of the activity, as on
a real social platform. That skew matters for Portfolio 2, because the planner chooses different
plans for popular and rare values.

Design decisions:
- Ids are assigned here (1..n) and written with COPY, which stores identity values as given, so
  foreign keys can be built without reading anything back. Identity sequences are reset at the end.
- Derived counters (likes_count, comments_count, posts_count, entries_count) and style_points are
  planned before the parent rows are written, so every row is written once and never updated.
  v_counter_drift is checked at the end and must be empty.
- Every rule from business-rules.md holds: no self-follows, blocked users never follow their
  blocker, one like and one vote per user per post, no votes on your own post, the voted image
  belongs to the voted post, replies stay on their parent's post, entries use the entrant's own
  post, and winners are entries of their own challenge.
- Time is anchored to AS_OF rather than now(), so the data and every query result are repeatable.
  Portfolio 2 queries use the same anchor.
- The whole load is one transaction: a failure leaves the schema empty.

Usage:
    python shared/seed/generate.py --scale small
    python shared/seed/generate.py --scale large --truncate
"""

import argparse
import bisect
import itertools
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg
from faker import Faker

AS_OF = datetime(2026, 10, 15, tzinfo=timezone.utc)
DEFAULT_SEED = 8103

SCALES = {
    "small": dict(users=2_000, posts=6_000, follows=40_000, likes=120_000, votes=30_000,
                  comments=30_000, hashtags=300, brands=60, challenges=20, notifications=6_000),
    "large": dict(users=100_000, posts=300_000, follows=1_000_000, likes=5_000_000, votes=1_000_000,
                  comments=1_000_000, hashtags=5_000, brands=400, challenges=200, notifications=300_000),
}

TABLES = ["notification", "report", "challenge_entry", "challenge", "comment", "vote", "post_like",
          "post_hashtag", "shop_item", "post_image", "post", "hashtag", "brand", "follow", "block",
          "user_device", "app_user"]

FASHION_TAGS = [
    "ootd", "fitcheck", "lagosfashion", "streetwear", "agbada", "asoebi", "owambe", "ankara",
    "naijastyle", "menswear", "womenswear", "sneakers", "thrifted", "vintage", "minimalist",
    "officelook", "weekendvibes", "churchfit", "aboutlastnight", "kaftan", "senator", "gele",
    "denim", "monochrome", "summerfit", "rainyday", "campusstyle", "wedding", "traditional",
    "accessories", "luxury", "budgetstyle", "styleinspo", "fashionweek", "abujastyle",
]

BRANDS = [
    "Zara", "Nike", "Adidas", "H&M", "Gucci", "Mango", "Puma", "Uniqlo", "Levi's", "Shein",
    "Orange Culture", "Lisa Folawiyo", "Maki Oh", "Kenneth Ize", "Andrea Iyamah", "Tokyo James",
    "Jermaine Bleu", "Lagos Space Programme", "Ugo Monye", "Mai Atafo",
]

CAPTIONS = [
    "Sunday best", "Office ready", "Weekend mood", "Which look wins?", "Rate this fit",
    "Thrifted everything", "Owambe ready", "Campus vibes", "Date night", "Simple but clean",
    "Monochrome moment", "Trying something new", "Lagos heat fit", "Rainy day layers",
    "First day at work", "Wedding guest look", "Back to basics", "Matching set",
]

REPORT_REASONS = ["spam", "harassment", "nudity", "impersonation", "hate", "other"]
NOTIFICATION_TYPES = ["like", "follow", "comment", "vote", "challenge_won", "mention"]


class Timer:
    def __init__(self):
        self.start = time.perf_counter()

    def log(self, message):
        print(f"[{time.perf_counter() - self.start:7.1f}s] {message}", flush=True)


def heavy_tail_weights(rng, n, alpha):
    """Pareto weights: most items small, a few very large. Lower alpha means a heavier tail."""
    return [rng.paretovariate(alpha) for _ in range(n)]


def allocate(rng, weights, total, cap):
    """Split a total across items in proportion to their weights, capping each item."""
    scale = total / sum(weights)
    return [min(cap, int(w * scale + rng.random())) for w in weights]


def rand_time(rng, start, end):
    return start + (end - start) * rng.random()


def username_from(name, i):
    base = re.sub(r"[^a-z0-9]", "", name.lower())[:20] or "user"
    return f"{base}.{i}"


def plan(rng, fake, n):
    """Build every value that a later table depends on, before anything is written."""
    p = {}
    users = n["users"]

    p["user_created"] = [None] + [rand_time(rng, AS_OF - timedelta(days=730), AS_OF - timedelta(days=30))
                                  for _ in range(users)]
    p["user_popularity"] = [0.0] + heavy_tail_weights(rng, users, 1.1)
    activity = heavy_tail_weights(rng, users, 1.3)
    cum_activity = list(itertools.accumulate(activity))

    authors = rng.choices(range(1, users + 1), cum_weights=cum_activity, k=n["posts"])
    p["post_author"] = [None] + authors
    p["post_created"] = [None]
    for a in authors:
        start = max(p["user_created"][a], AS_OF - timedelta(days=365))
        p["post_created"].append(rand_time(rng, start, AS_OF))
    p["post_images"] = [None] + rng.choices([1, 2, 3, 4], weights=[45, 30, 15, 10], k=n["posts"])

    post_weight = [p["user_popularity"][a] * rng.paretovariate(1.5) for a in authors]
    p["likes"] = [None] + allocate(rng, post_weight, n["likes"], users - 1)
    p["votes"] = [None] + allocate(rng, post_weight, n["votes"], users - 1)
    p["comments"] = [None] + allocate(rng, post_weight, n["comments"], 400)

    tag_weight = [1.0 / (rank + 1) ** 1.1 for rank in range(n["hashtags"])]
    cum_tags = list(itertools.accumulate(tag_weight))
    p["post_tags"] = [None]
    p["tag_posts"] = [0] * (n["hashtags"] + 1)
    for _ in range(n["posts"]):
        k = rng.choices([0, 1, 2, 3, 4], weights=[15, 30, 30, 15, 10])[0]
        tags = sorted({1 + bisect.bisect_left(cum_tags, rng.random() * cum_tags[-1]) for _ in range(k)})
        p["post_tags"].append(tags)
        for t in tags:
            p["tag_posts"][t] += 1

    names = []
    for rank in range(n["hashtags"]):
        names.append(FASHION_TAGS[rank] if rank < len(FASHION_TAGS)
                     else f"{FASHION_TAGS[rank % len(FASHION_TAGS)]}_{rank}")
    p["tag_names"] = [None] + names

    challenges = []
    weeks = n["challenges"]
    for c in range(1, weeks + 1):
        ends = AS_OF - timedelta(days=7 * (weeks - c)) + timedelta(days=3)
        starts = ends - timedelta(days=7)
        max_entries = rng.choice([50, 100, 250, 500])
        entrants, used = [], set()
        target = min(max_entries, rng.randint(10, 120))
        while len(entrants) < target:
            post_id = rng.randint(1, n["posts"])
            author = authors[post_id - 1]
            if author not in used:
                used.add(author)
                entrants.append((author, post_id))
        challenges.append(dict(id=c, starts=starts, ends=ends, max_entries=max_entries,
                               reward=rng.choice([50, 100, 200]), entrants=entrants))
    p["challenges"] = challenges

    p["style_points"] = [0] * (users + 1)
    entry_id = 0
    for ch in challenges:
        best = None
        for author, post_id in ch["entrants"]:
            entry_id += 1
            score = p["votes"][post_id]
            if best is None or score > best[0]:
                best = (score, entry_id, author)
        ch["first_entry_id"] = entry_id - len(ch["entrants"]) + 1
        ch["winner"] = None
        if ch["ends"] < AS_OF and best is not None:
            ch["winner"] = best[1]
            p["style_points"][best[2]] += ch["reward"]

    blocks = set()
    while len(blocks) < max(1, users // 200):
        a, b = rng.randint(1, users), rng.randint(1, users)
        if a != b:
            blocks.add((a, b))
    p["blocks"] = blocks
    return p


def copy_rows(cur, table, columns, rows):
    count = 0
    with cur.copy(f"COPY fitscheck.{table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            count += 1
    return count


def gen_users(rng, fake, n, p):
    admins = 10
    for i in range(1, n["users"] + 1):
        first, last = fake.first_name(), fake.last_name()
        username = username_from(first + last, i)
        bio = fake.sentence(nb_words=8)[:300] if rng.random() < 0.4 else None
        yield (i, username, f"{username}@example.com", "$argon2id$v=19$synthetic", f"{first} {last}",
               bio, None if rng.random() < 0.3 else f"https://img.fitscheck.example/avatar/{i}.jpg",
               p["style_points"][i], rng.random() > 0.01, i <= admins,
               p["user_created"][i], p["user_created"][i])


def gen_devices(rng, n, p):
    device_id = 0
    for u in range(1, n["users"] + 1):
        if rng.random() < 0.7:
            for k in range(rng.choice([1, 1, 2])):
                device_id += 1
                yield (device_id, u, f"tok-{u}-{k}-{rng.getrandbits(48):012x}",
                       rng.choice(["ios", "android", "android", "web"]),
                       rand_time(rng, p["user_created"][u], AS_OF), p["user_created"][u])


def gen_follows(rng, n, p):
    users = n["users"]
    counts = allocate(rng, p["user_popularity"][1:], n["follows"], users - 1)
    for followed, k in enumerate(counts, start=1):
        if k == 0:
            continue
        for follower in rng.sample(range(1, users + 1), min(k + 1, users)):
            if follower == followed or (followed, follower) in p["blocks"]:
                continue
            k -= 1
            if k < 0:
                break
            start = max(p["user_created"][followed], p["user_created"][follower])
            yield (follower, followed, rand_time(rng, start, AS_OF))


def gen_posts(rng, n, p):
    for post_id in range(1, n["posts"] + 1):
        caption = rng.choice(CAPTIONS) if rng.random() < 0.85 else None
        created = p["post_created"][post_id]
        yield (post_id, p["post_author"][post_id], caption, p["likes"][post_id], p["comments"][post_id],
               created, created)


def gen_images(n, p):
    image_id = 0
    for post_id in range(1, n["posts"] + 1):
        for position in range(1, p["post_images"][post_id] + 1):
            image_id += 1
            yield (image_id, post_id, position, f"https://img.fitscheck.example/{post_id}/{position}.jpg",
                   p["post_created"][post_id])


def image_id_of(p, post_id, position):
    return p["image_offset"][post_id] + position


def gen_shop_items(rng, n, p):
    item_id = 0
    for post_id in range(1, n["posts"] + 1):
        for position in range(1, p["post_images"][post_id] + 1):
            if rng.random() < 0.4:
                for _ in range(rng.choice([1, 1, 2])):
                    item_id += 1
                    currency = rng.choices(["NGN", "USD", "GBP"], weights=[85, 10, 5])[0]
                    price = rng.randint(3_000, 150_000) if currency == "NGN" else rng.randint(10, 400)
                    yield (item_id, image_id_of(p, post_id, position),
                           rng.randint(1, n["brands"]) if rng.random() < 0.8 else None,
                           rng.choice(["Shirt", "Trousers", "Sneakers", "Dress", "Agbada", "Cap",
                                       "Bag", "Watch", "Jacket", "Skirt", "Loafers", "Kaftan"]),
                           price, currency, None, None)


def gen_likes(rng, n, p):
    users = n["users"]
    for post_id in range(1, n["posts"] + 1):
        k = p["likes"][post_id]
        if k == 0:
            continue
        created = p["post_created"][post_id]
        for user_id in rng.sample(range(1, users + 1), k):
            yield (user_id, post_id, rand_time(rng, created, AS_OF))


def gen_votes(rng, n, p):
    users = n["users"]
    vote_id = 0
    for post_id in range(1, n["posts"] + 1):
        k = p["votes"][post_id]
        if k == 0:
            continue
        author = p["post_author"][post_id]
        created = p["post_created"][post_id]
        voters = [u for u in rng.sample(range(1, users + 1), min(k + 1, users)) if u != author][:k]
        for user_id in voters:
            vote_id += 1
            position = rng.randint(1, p["post_images"][post_id])
            yield (vote_id, user_id, post_id, image_id_of(p, post_id, position),
                   rand_time(rng, created, AS_OF))


def gen_comments(rng, fake, n, p):
    users = n["users"]
    comment_id = 0
    bodies = ["Clean!", "This is fire", "Where did you get the shoes?", "Love this", "Second look wins",
              "Colours are perfect", "Need this jacket", "Too sharp", "Fit check passed", "Iconic"]
    for post_id in range(1, n["posts"] + 1):
        k = p["comments"][post_id]
        if k == 0:
            continue
        created = p["post_created"][post_id]
        times = sorted(rand_time(rng, created, AS_OF) for _ in range(k))
        earlier = []
        for t in times:
            comment_id += 1
            parent = rng.choice(earlier) if earlier and rng.random() < 0.3 else None
            body = rng.choice(bodies) if rng.random() < 0.7 else fake.sentence(nb_words=10)
            yield (comment_id, post_id, rng.randint(1, users), parent, body, t, t)
            earlier.append(comment_id)


def gen_post_hashtags(n, p):
    for post_id in range(1, n["posts"] + 1):
        for tag in p["post_tags"][post_id]:
            yield (post_id, tag)


def gen_challenges(p):
    for ch in p["challenges"]:
        yield (ch["id"], f"week-{ch['id']}-fits", f"Week {ch['id']} Fit Challenge", None,
               ch["starts"], ch["ends"], ch["max_entries"], ch["reward"], len(ch["entrants"]),
               ch["starts"] - timedelta(days=2))


def gen_entries(rng, p):
    entry_id = 0
    for ch in p["challenges"]:
        for author, post_id in ch["entrants"]:
            entry_id += 1
            yield (entry_id, ch["id"], author, post_id, rand_time(rng, ch["starts"], min(ch["ends"], AS_OF)))


def gen_reports(rng, n, p):
    report_id = 0
    admins = list(range(1, 11))
    for _ in range(max(10, n["posts"] // 500)):
        report_id += 1
        reporter = rng.randint(11, n["users"])
        kind = rng.choices(["post", "user", "comment"], weights=[70, 20, 10])[0]
        target_post = rng.randint(1, n["posts"]) if kind == "post" else None
        target_user = rng.randint(1, n["users"]) if kind == "user" else None
        target_comment = rng.randint(1, max(1, sum(p["comments"][1:]))) if kind == "comment" else None
        status = rng.choices(["open", "reviewing", "actioned", "dismissed"], weights=[30, 10, 25, 35])[0]
        created = rand_time(rng, AS_OF - timedelta(days=180), AS_OF)
        reviewed = status in ("actioned", "dismissed") or (status == "reviewing" and rng.random() < 0.5)
        yield (report_id, reporter, target_user, target_post, target_comment, rng.choice(REPORT_REASONS),
               None, status, rng.choice(admins) if reviewed else None,
               rand_time(rng, created, AS_OF) if reviewed else None, created)


def gen_notifications(rng, n, p):
    cum_pop = list(itertools.accumulate(p["user_popularity"][1:]))
    recipients = rng.choices(range(1, n["users"] + 1), cum_weights=cum_pop, k=n["notifications"])
    for notification_id, recipient in enumerate(recipients, start=1):
        kind = rng.choice(NOTIFICATION_TYPES)
        created = rand_time(rng, AS_OF - timedelta(days=90), AS_OF)
        yield (notification_id, recipient, kind, f"New {kind.replace('_', ' ')}", None,
               created < AS_OF - timedelta(days=7) or rng.random() < 0.5, created)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scale", choices=SCALES, default="small")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--truncate", action="store_true",
                        help="empty every fitscheck table first (destructive)")
    args = parser.parse_args()

    url = os.environ.get("PG_URL")
    if not url:
        sys.exit("PG_URL is not set; run: set -a; . ./.env; set +a")

    n = SCALES[args.scale]
    rng = random.Random(args.seed)
    fake = Faker(["yo_NG", "ig_NG", "ha_NG", "en_NG"])
    fake.seed_instance(args.seed)
    timer = Timer()

    p = plan(rng, fake, n)
    p["image_offset"] = [0] * (n["posts"] + 2)
    for post_id in range(1, n["posts"] + 1):
        p["image_offset"][post_id + 1] = p["image_offset"][post_id] + p["post_images"][post_id]
    timer.log(f"planned scale={args.scale} seed={args.seed}")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM fitscheck.app_user")
            if cur.fetchone()[0] and not args.truncate:
                sys.exit("fitscheck already has data; rerun with --truncate to replace it")
            if args.truncate:
                cur.execute("TRUNCATE " + ", ".join(f"fitscheck.{t}" for t in TABLES) + " RESTART IDENTITY")
                timer.log("truncated existing data")

            loads = [
                ("app_user", ["id", "username", "email", "password_hash", "full_name", "bio", "avatar_url",
                              "style_points", "is_active", "is_admin", "created_at", "updated_at"],
                 gen_users(rng, fake, n, p)),
                ("user_device", ["id", "user_id", "push_token", "platform", "last_seen_at", "created_at"],
                 gen_devices(rng, n, p)),
                ("block", ["blocker_id", "blocked_id", "created_at"],
                 ((a, b, AS_OF - timedelta(days=rng.randint(1, 300))) for a, b in sorted(p["blocks"]))),
                ("follow", ["follower_id", "followed_id", "created_at"], gen_follows(rng, n, p)),
                ("brand", ["id", "name", "website"],
                 ((i, BRANDS[i - 1] if i <= len(BRANDS) else f"Label {i}", None) for i in range(1, n["brands"] + 1))),
                ("hashtag", ["id", "name", "posts_count", "created_at"],
                 ((t, p["tag_names"][t], p["tag_posts"][t], AS_OF - timedelta(days=400))
                  for t in range(1, n["hashtags"] + 1))),
                ("post", ["id", "author_id", "caption", "likes_count", "comments_count", "created_at", "updated_at"],
                 gen_posts(rng, n, p)),
                ("post_image", ["id", "post_id", "position", "image_url", "created_at"], gen_images(n, p)),
                ("shop_item", ["id", "post_image_id", "brand_id", "item_name", "price", "currency",
                               "affiliate_url", "promo_code"], gen_shop_items(rng, n, p)),
                ("post_hashtag", ["post_id", "hashtag_id"], gen_post_hashtags(n, p)),
                ("post_like", ["user_id", "post_id", "created_at"], gen_likes(rng, n, p)),
                ("vote", ["id", "user_id", "post_id", "post_image_id", "created_at"], gen_votes(rng, n, p)),
                ("comment", ["id", "post_id", "author_id", "parent_id", "body", "created_at", "updated_at"],
                 gen_comments(rng, fake, n, p)),
                ("challenge", ["id", "slug", "title", "description", "starts_at", "ends_at", "max_entries",
                               "reward_points", "entries_count", "created_at"], gen_challenges(p)),
                ("challenge_entry", ["id", "challenge_id", "user_id", "post_id", "created_at"], gen_entries(rng, p)),
                ("report", ["id", "reporter_id", "target_user_id", "target_post_id", "target_comment_id",
                            "reason", "details", "status", "reviewed_by", "reviewed_at", "created_at"],
                 gen_reports(rng, n, p)),
                ("notification", ["id", "recipient_id", "type", "title", "body", "is_read", "created_at"],
                 gen_notifications(rng, n, p)),
            ]
            for table, columns, rows in loads:
                timer.log(f"{table}: {copy_rows(cur, table, columns, rows):,} rows")

            for ch in p["challenges"]:
                if ch["winner"]:
                    cur.execute("UPDATE fitscheck.challenge SET winner_entry_id = %s WHERE id = %s",
                                (ch["winner"], ch["id"]))
            timer.log("challenge winners set")

            for table in ["app_user", "user_device", "post", "post_image", "brand", "shop_item", "hashtag",
                          "vote", "comment", "challenge", "challenge_entry", "report", "notification"]:
                cur.execute(f"SELECT setval(pg_get_serial_sequence('fitscheck.{table}', 'id'), "
                            f"(SELECT coalesce(max(id), 0) + 1 FROM fitscheck.{table}), false)")

            cur.execute("SELECT count(*) FROM fitscheck.v_counter_drift")
            drift = cur.fetchone()[0]
            if drift:
                raise RuntimeError(f"{drift} counters do not match their rows; rolling back")
            timer.log("counters verified: v_counter_drift is empty")

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("VACUUM ANALYZE")
    timer.log("VACUUM ANALYZE done; load committed")


if __name__ == "__main__":
    main()
