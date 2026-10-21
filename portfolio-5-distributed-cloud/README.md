# Portfolio 5: Distributed and Cloud Database Exercise

**Case study:** FitsCheck. **Status:** Complete.

**Brief requires:** distributed/cloud database discussion or setup based on the same case study, including replication, sharding, availability, consistency, or deployment evidence.

## 1. Objective

Run FitsCheck's data on real multi-node clusters and observe what distribution costs and buys:
replication for read capacity and surviving a failed server, sharding for spreading data, and the
consistency and availability trade-offs each forces. Every cluster is built from scratch by one script,
loaded with the FitsCheck data from the earlier portfolios, and every distributed answer is checked
against the single-node database.

| Cluster | Software | Nodes | Shows |
|---|---|---|---|
| Streaming replication | PostgreSQL 16 | 1 primary, 2 hot standbys | Lag, read-only replicas, read-your-writes, synchronous commit, failover |
| Replica set | MongoDB 7 | 3 members | Write concern, causal reads, transactions, elections, quorum loss |
| Sharding | Citus 12.1 on PostgreSQL 16 | 1 coordinator, 2 workers | Shard key design, single-shard and all-shard queries, hot shards |

## 2. What I built

### 2.1 PostgreSQL streaming replication ([replication/](replication/))
- [docker-compose.yml](replication/docker-compose.yml): three official `postgres:16` containers. The
  primary runs with `wal_level=replica` and a replication role created by
  [init-primary.sh](replication/init-primary.sh).
- [start-replica.sh](replication/start-replica.sh): on first start a replica clones the primary with
  `pg_basebackup -R -C -S <name>`, which writes the standby configuration and creates a **replication
  slot** so the primary keeps WAL the replica has not received. `cluster_name` names each replica, so
  `synchronous_standby_names` can refer to it.
- [run.sh](replication/run.sh) rebuilds the cluster, loads FitsCheck (Portfolio 1 schema, the small seed
  and `post_fit` from Portfolio 3) **into the primary only**, and runs [demo.py](replication/demo.py).

### 2.2 MongoDB replica set ([mongo-replicaset/](mongo-replicaset/))
- Three `mongo:7` members in replica set `rs0`; [run.sh](mongo-replicaset/run.sh) initiates it, exports
  the FitsCheck fit documents from the Portfolio 3 database with the Portfolio 4 document query
  ([export_posts.py](mongo-replicaset/export_posts.py)), and runs [demo.py](mongo-replicaset/demo.py).
- The demo runs **inside the replica set's Docker network**, so the real driver discovers members,
  follows elections and retries writes, as an application server would. The host kills members
  between the demo's phases.

### 2.3 Citus sharding ([sharding/](sharding/))
FitsCheck is sharded **by creator**: [schema.sql](sharding/schema.sql) distributes `app_user` on `id`,
and `post`, `post_like` and `follow` on the creator's id, all in **one co-location group** of 16 shards
over two workers, so a creator's profile, posts and the likes on those posts share a shard and join
locally. `hashtag` is a **reference table** copied to every node. [load.py](sharding/load.py) streams
the 9.6 million row Portfolio 2 dataset in with `COPY`; [demo.py](sharding/demo.py) compares each query
with the single-node database.

Two schema consequences of the shard key:
- Each shard can only check uniqueness on its own rows, so Citus refuses a primary key that omits the
  shard column ([citus_schema.txt](evidence/citus_schema.txt)). `post`'s key became `(author_id, id)`,
  the same trade-off Portfolio 2 met when partitioning `post_like`.
- Each like stores its post's author (`post_author_id`) so it lands on the post's shard: denormalising
  the shard key into child tables is the price of co-located joins.

## 3. How to run

From the repository root with `.env` loaded. Each script removes and rebuilds its own cluster.

```bash
portfolio-5-distributed-cloud/replication/run.sh        # about 1 minute
portfolio-5-distributed-cloud/mongo-replicaset/run.sh   # about 2 minutes; needs fitscheck_p3 (Portfolio 3)
portfolio-5-distributed-cloud/sharding/run.sh           # about 5 minutes; needs the Portfolio 2 dataset
```

Stop a cluster afterwards with `docker compose down -v` in its folder. On this laptop the clusters were
run one at a time to stay within memory.

## 4. How it was tested

- **Data arrives only through the distributed mechanism.** In the replication cluster, data is loaded
  into the primary only; the replicas' identical row counts prove replication carried it.
- **Same answer as one node.** Every Citus query, the rewritten home feed and the MongoDB data counts are
  compared with the single-node results.
- **No acknowledged write may be lost.** During MongoDB failover, every write the driver reported as
  acknowledged is looked up on the new primary afterwards. In the PostgreSQL failover, the last
  committed post is checked on the promoted replica.
- **Failures are real.** Primaries are crashed with `docker kill` (no shutdown, no final flush), not
  stopped politely.

## 5. Results and evidence

### 5.1 PostgreSQL replication ([replication_demo.txt](evidence/replication_demo.txt))

| Measurement | Result |
|---|---|
| Data on each node | 2,000 users, 6,000 posts, 115,028 likes on the primary and on both replicas |
| Replication lag | Commit on the primary to visible on a replica: median 5.81 ms (min 0.66, max 34.02) over 20 posts |
| Writing to a replica | Refused: SQLSTATE 25006, `cannot execute INSERT in a read-only transaction` |
| Reading your own write from a paused replica | The new post is **missing** |
| Same read with LSN-aware routing | Replica behind the commit's WAL position, so the read goes to the primary: post found. After the replica catches up, the read goes to the replica: post found |
| Commit latency by `synchronous_commit` (median of 200) | off 0.10 ms, local 7.67 ms, remote_write 13.48 ms, on 18.89 ms, remote_apply 20.07 ms |
| Synchronous commit with both standbys down | Still waiting after 5 s; cancelled after 5.1 s with the warning `canceling wait for synchronous replication`; the row was **committed locally but never confirmed** by a standby |
| Failover after `docker kill` of the primary | Replica1 promoted in 720 ms on **timeline 2**; all 6,022 posts present, including the last one; new writes accepted; replica2 repointed and streaming from the new primary |
| Ids after failover | Post ids jumped from 6022 to 6034: sequences are logged ahead in batches, so ids stay unique but not gap-free |

### 5.2 MongoDB replica set ([mongo_replicaset_demo.txt](evidence/mongo_replicaset_demo.txt))

| Measurement | Result |
|---|---|
| Data | 6,039 fit documents written with `w:majority`, present on all three members |
| Write concern (median of 200) | `w:1` 0.54 ms; `w:majority` 12.04 ms |
| Read your own write from a secondary | Plain session, `w:1`: **missing 196 of 200** times. Causally consistent session with majority read and write concerns: **missing 0 of 200** |
| Multi-document transaction | Post and comment committed together; a failing transaction left neither behind |
| Failover under load (one `w:majority` write every 100 ms, primary killed) | 250 writes acknowledged, **0 failed**; the slowest waited 11.3 s for the election and was retried by the driver; **all 250 present** on the new primary |
| Two of three members down | The survivor stepped down to secondary; a `w:majority` write was refused |

### 5.3 Citus sharding ([citus_demo.txt](evidence/citus_demo.txt))

| Query | Same as single node | Shard tasks | Citus | Single node |
|---|---|---:|---:|---:|
| Profile: latest 20 posts by creator 72535 | Yes | 1 | 2.62 ms | 6.35 ms |
| Creator 72535's five most-liked posts (co-located join) | Yes | 1 | 16.75 ms | 131.77 ms |
| Trending, last 24 hours | Yes | 16 | 386.95 ms | 161.73 ms |
| Home feed of user 82114 as one join | Refused: `the query contains a join that requires repartitioning` | | | |
| Home feed in two steps | Yes, the same 20 posts as Portfolio 2's q01 | 13 | | |

Client-side medians of 5. The creator-likes gap comes mostly from the Citus key `(post_author_id, ...)`
being an index on the author; the single-node schema has no author column on likes and probes 8,309
posts one by one.

Shard sizes: 32 shards and 458 MB on worker1, 32 shards and 404 MB on worker2. Rows per shard for
`post`: smallest 16,985, median 18,248, largest 24,403 (1.34x the median); for `post_like`: smallest
206,796, median 291,266, largest 473,170 (**1.62x**). The creator with the most likes (146,116) sits on
a single shard.

## 6. Analysis

**CAP in practice: during a partition, choose consistency or availability.** Both clusters made the
choice visibly. PostgreSQL with synchronous replication chose consistency: with no standby to confirm,
the commit simply waited, and when cancelled the client was told the row was committed locally but not
replicated, so a failover at that moment could lose it. MongoDB with `w:majority` chose consistency
too: with two of three members gone, the survivor stepped down rather than accept writes a returning
majority might contradict. Asynchronous replication and `w:1` choose availability: writes keep
succeeding, at the risk of losing the most recent ones in a crash (a recovery point objective equal to
the replication lag, a few milliseconds here).

**PACELC: even without failures, the choice is latency or consistency.** With every node healthy,
waiting for a standby cost 18.89 ms per PostgreSQL commit against 7.67 ms locally (remote_apply, which
also makes the write visible on the standby, cost 20.07 ms), and `w:majority` cost 12.04 ms against
0.54 ms for `w:1`. Replicas give read capacity but can be behind: 196 of 200 immediate reads from a
MongoDB secondary missed the user's own post, and a paused PostgreSQL replica hid it entirely. Both
systems offer the same remedy, applied only where it matters: track the position of the user's last
write (the WAL LSN in PostgreSQL, the cluster time in a MongoDB causal session) and read from a replica
only once it has caught up.

**FitsCheck's choices.** Likes, follower counts, feeds and trending can be eventually consistent:
nobody notices 1,203 against 1,205 likes, so they are read from replicas and caches (Portfolio 4) and
written asynchronously. Challenge results, votes and style points cannot be: a winner shown on one
screen and not another, or points awarded twice, is visible and unfair, so those writes go to the
primary with synchronous replication, and a user's own reads after posting are routed by LSN.

**Failover works, but it is not free.** Promotion took under a second and lost nothing, because the
last post had replicated before the crash. In MongoDB the election stalled writes for about 11 seconds
(detection plus election), which the driver absorbed by retrying. A promoted PostgreSQL replica starts a
new timeline, so the old primary cannot simply rejoin; it needs `pg_rewind` or a fresh clone. Promotion
was manual here; production uses a failover manager (for example Patroni) to detect the failure and
promote automatically.

**The shard key decides which queries are cheap.** Sharding by creator made everything about one
creator a single-shard query: their profile, their posts and the likes on them, joined locally because
the tables are co-located. Anything spanning creators costs more: trending visits all 16 shards, and the
home feed, which joins a user's follows to many creators' posts, was refused outright because the two
tables are sharded on different keys. Split into two queries it still had to reach 13 of 16 shards.
This is the strongest argument for the Portfolio 4 design, where feeds are precomputed in Redis so that
reading one never fans out across shards.

**Sharding adds hardware, not speed, by itself.** On this laptop the all-shard trending query was
slower on Citus (386.95 ms) than on one node (161.73 ms): three nodes shared one machine's 4 cores and
memory, so coordinating 16 shard tasks added overhead without adding capacity. Sharding pays off when
each worker brings its own CPU, memory and disk, and when data outgrows one machine.

**Skew follows the data into the shards.** Hashing spreads creators evenly, but not their activity: the
largest `post_like` shard holds 1.62 times the median, and one creator's 146,116 likes all land on one
shard. A viral creator makes a hot shard, the sharded form of Portfolio 4's celebrity fan-out problem;
remedies are splitting a hot shard onto its own node or adding a finer key for the busiest creators.

## 7. Limitations and next steps

- **One machine.** All nodes ran on one laptop, so the timings show behaviour and relative costs, not
  the throughput separate servers would give.
- **No managed cloud deployment.** The same topologies map onto managed services (for example a managed
  PostgreSQL with read replicas, MongoDB Atlas, or Azure Cosmos DB for PostgreSQL, which runs Citus), but
  none was provisioned; that would need a cloud account and would show the same behaviours.
- **Manual failover.** Promotion and repointing were done by the demo script; automatic failover needs a
  manager such as Patroni with a consensus store.
- **The old primary is not rejoined.** Reintegrating it with `pg_rewind` is described, not demonstrated.
- **No resharding.** Adding a third Citus worker and rebalancing shards (`citus_rebalance_start`) was
  left out to stay within the laptop's memory.
- **Trust authentication** inside the private compose networks keeps the local clusters simple; a real
  deployment would use passwords or certificates between nodes.
