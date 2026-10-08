# MIT 8103 Advanced Database Systems: Practical Portfolio

**Student:** Odidi Hope | **Matric No:** 2026/A/MIT/0574 | **Cohort:** September 2026, First Semester
**Repository:** [advanced-database-portfolio-hope](https://github.com/Daggahh/advanced-database-portfolio-hope.git)

This repository is my individual practical portfolio for MIT 8103. All five portfolio activities use
one case study, **FitsCheck**. Every claim made here is backed by a script you can run and by
evidence (outputs, execution plans, screenshots) that the script produced.

---

## 1. Case study statement

| Item | Detail |
|---|---|
| **Organisation / system** | FitsCheck, a fashion social platform where people post outfits ("fits") and the community rates them. |
| **Nature of the system** | A user posts a fit made of one or more outfit photos, tagged with hashtags and with the clothing items they wear (brand, price, shop link). Followers see it in their feed and can like it, comment, and vote for the best look in it. Style challenges run for a fixed period: users enter a fit, the community votes, and when the challenge closes a winner is crowned and earns style points. |
| **Database users** | Creators (post fits, enter challenges), viewers (browse, follow, like, vote, comment), moderators (review reports, block abuse), and administrators (run challenges, manage users). |
| **Major data stored** | Users and profiles, follows and blocks, posts, post images, shop items and brands, hashtags, likes, votes, comments and replies, challenges and entries, notifications, and moderation reports. |
| **Key operations** | Post a fit, follow a creator, build a user's home feed, like/vote/comment, search by hashtag, list trending fits, enter a challenge, close a challenge and crown the winner, rank creators by style points, and report content. |

**Why FitsCheck.** A social platform built around outfit voting is simple to describe, yet it
raises a real database problem in every area this course covers:

- **Design:** users, follows, posts, images and votes are strongly relational, and the rules that
  govern them can be enforced as constraints, for example one vote per user per fit.
- **Query performance:** feeds, hashtag search and trending lists run on every app open, over tables
  that grow by millions of rows, so indexing and query shape decide whether the app feels instant.
- **Concurrency:** many people liking or voting on the same fit at the same moment, and several users
  competing for the last challenge slot, produce lost updates, write skew and deadlocks.
- **Alternative data models:** feeds and leaderboards suit a key-value store, a fit with its images and
  shop items suits a document store, and the follow network is naturally a graph.
- **Distribution:** a read-heavy social workload is the textbook case for read replicas and sharding
  by user, and it shows clearly where eventual consistency is acceptable (like counts) and where it is
  not (challenge results).

FitsCheck is an app I am building. The schema, SQL, data and analysis in this repository were
written fresh for this course; no application code is reused. Every row is synthetic and comes from
`shared/seed/`.

---

## 2. Portfolio index

| # | Activity | Marks | Folder | Status |
|---|---|---|---|---|
| 1 | Database Design and Modelling | 7 | [portfolio-1-database-design](portfolio-1-database-design/) | Not started |
| 2 | Query Processing and Optimisation | 7 | [portfolio-2-query-optimisation](portfolio-2-query-optimisation/) | Not started |
| 3 | Transactions and Concurrency | 7 | [portfolio-3-transactions-concurrency](portfolio-3-transactions-concurrency/) | Not started |
| 4 | NoSQL and Advanced Data Models | 7 | [portfolio-4-nosql](portfolio-4-nosql/) | Not started |
| 5 | Distributed and Cloud Database Exercise | 6 | [portfolio-5-distributed-cloud](portfolio-5-distributed-cloud/) | Not started |
| - | Final Documentation and Reflection | 6 | [docs](docs/) | Not started |

Each portfolio folder has its own README covering what was built, how to run it, how it was tested,
the evidence it produced, and what I learned.

---

## 3. Technology

| Concern | Choice | Used in |
|---|---|---|
| Relational DBMS | PostgreSQL 16 | P1, P2, P3, P5 |
| Document store | MongoDB 7 | P4, P5 |
| Key-value store | Redis 7 | P4 |
| Graph store | Neo4j 5 Community | P4 |
| Distributed SQL | PostgreSQL streaming replication; Citus for sharding | P5 |
| Data generation and test harness | Python 3.12, psycopg 3, Faker, pymongo, redis-py | All |
| Diagrams | dbdiagram.io / draw.io, with exported PNG and source committed | P1 |
| Environment | Docker Compose; each service starts with one command | All |

---

## 4. Repository structure

```
.
├── README.md                              this file
├── docker-compose.yml                     Postgres, MongoDB, Redis, Neo4j for local work
├── .env.example                           connection settings (copy to .env)
├── shared/
│   ├── seed/                              synthetic data generator (deterministic seed)
│   └── requirements.txt
├── portfolio-1-database-design/
│   ├── README.md
│   ├── diagrams/                          ERD source + PNG export
│   ├── sql/                               01_schema.sql, 02_constraints.sql, 03_sample_data.sql
│   └── evidence/
├── portfolio-2-query-optimisation/
│   ├── README.md
│   ├── sql/                               queries, indexes, partitioning
│   ├── plans/                             EXPLAIN (ANALYZE, BUFFERS) before and after
│   └── evidence/
├── portfolio-3-transactions-concurrency/
│   ├── README.md
│   ├── sql/                               transaction scripts per scenario
│   ├── harness/                           Python scripts that run sessions concurrently
│   └── evidence/
├── portfolio-4-nosql/
│   ├── README.md
│   ├── mongodb/  redis/  neo4j/
│   └── evidence/
├── portfolio-5-distributed-cloud/
│   ├── README.md
│   ├── replication/  sharding/  mongo-replicaset/  cloud/
│   └── evidence/
└── docs/
    ├── final-documentation.md             2-3 page LMS summary (exported to PDF)
    ├── reflection.md                      individual technical reflection
    ├── AI_USE_DECLARATION.md
    ├── AI_USE_LOG.md                      dated log of AI-assisted work
    └── references.md
```

---

## 5. Running it

Prerequisites: Docker with Compose v2, Python 3.12, and `psql`.

```bash
cp .env.example .env
docker compose up -d postgres                 # add mongo redis neo4j when you reach P4
python3 -m venv .venv && source .venv/bin/activate
pip install -r shared/requirements.txt

psql "$PG_URL" -f portfolio-1-database-design/sql/01_schema.sql
psql "$PG_URL" -f portfolio-1-database-design/sql/02_constraints.sql
python shared/seed/generate.py --scale small   # small = about 2k users; large = about 100k users for P2
```

Each portfolio README lists the exact commands that reproduce its evidence.

---

## 6. Academic integrity and AI use

This is individual work. External sources, libraries and documentation are listed in
[docs/references.md](docs/references.md). AI tools were used as learning and productivity aids. Which
tools, what they were used for, and how I verified their output are recorded in
[docs/AI_USE_DECLARATION.md](docs/AI_USE_DECLARATION.md), with a per-session log in
[docs/AI_USE_LOG.md](docs/AI_USE_LOG.md). I have run, tested and can explain everything in this
repository.
