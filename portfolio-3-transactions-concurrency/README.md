# Portfolio 3: Transactions and Concurrency

**Case study:** FitsCheck. **Status:** Complete.

**Brief requires:** transaction examples showing commit, rollback, isolation, concurrency issue or control mechanism, and screenshots/output evidence.

## 1. Objective

Show how FitsCheck keeps its data correct when many people act at once: liking the same fit,
double-tapping a vote, racing for the last challenge slot, or two admins closing the same challenge.
Each concurrency problem is reproduced on real concurrent PostgreSQL sessions, then fixed, and the
isolation matrix is built from what was observed rather than copied from the documentation. This
portfolio also enforces the three business rules that Portfolio 1 left to transactions: BR-07 (a post
has 1 to 10 images), BR-16 (entries only while a challenge is open and below its limit) and BR-17 (a
winner is set only once, after the challenge ends).

## 2. What I built

### 2.1 Scenarios

| # | FitsCheck situation | Concept | Evidence |
|---|---|---|---|
| T1 | Posting a fit: post, images, hashtags, counters | Atomic COMMIT | [t01](evidence/t01_post_fit_commit.txt) |
| T2 | A post fails partway; a post has no images | ROLLBACK, BR-07 | [t02](evidence/t02_post_fit_rollback.txt) |
| T3 | Closing a challenge while the winner's notification fails | SAVEPOINT, row lock, BR-17 | [t03](evidence/t03_close_challenge_savepoint.txt) |
| T4 | 50 people like the same fit at once | Lost update; atomic update; row locks | [t04](evidence/t04_lost_update.txt) |
| T5 | A double-tap sends the same vote twice | Unique constraint as concurrency control | [t05](evidence/t05_double_tap_vote.txt) |
| T6 | Two users take the last challenge slot at once | Write skew; SERIALIZABLE; BR-16 | [t06](evidence/t06_last_challenge_slot.txt) |
| T7 | A leaderboard is read twice while votes arrive | Non-repeatable read, phantom read | [t07](evidence/t07_non_repeatable_read.txt) |
| T8 | Two counter jobs lock the same posts in opposite order | Deadlock, ordered locking | [t08](evidence/t08_deadlock.txt) |
| T9 | An update blocks another, observed live | MVCC (`xmin`, `xmax`, `ctid`), `pg_locks` | [t09](evidence/t09_mvcc_and_locks.txt) |
| T10 | Two admins close the same challenge at once | Duplicate processing, `SELECT ... FOR UPDATE` | [t10](evidence/t10_double_close.txt) |

### 2.2 Components
- **[sql/00_post_fit.sql](sql/00_post_fit.sql)**: `post_fit()`, posting a fit as one unit of work. A
  function runs inside its caller's transaction, so any error undoes everything it wrote. It holds
  BR-07, and maintains hashtag counters with an upsert (`ON CONFLICT ... DO UPDATE SET posts_count =
  posts_count + 1`) so the increment is atomic.
- **T1-T3 ([sql/](sql/))**: single-session scripts run with `psql -a`, so the evidence shows every
  statement next to its output.
- **T4-T10 ([harness/concurrency.py](harness/concurrency.py))**: each session is a thread with its own
  connection. **Barriers force the interleaving** (for example, all 50 likers read the counter before
  any of them writes), so every anomaly happens on every run instead of by luck. Each scenario
  creates its own fresh rows and logs a timestamped line per session.
- **A separate database**, `fitscheck_p3`, built from the Portfolio 1 schema and the small seed by
  [setup_p3_db.sh](setup_p3_db.sh). The scenarios commit real changes, so they never touch the
  Portfolio 2 dataset, and rebuilding gives every run the same starting state.

## 3. How to run

From the repository root, with `.env` loaded (`set -a; . ./.env; set +a`) and the stack running:

```bash
portfolio-3-transactions-concurrency/run_all.sh
```

This rebuilds `fitscheck_p3`, runs T1-T3, runs T4-T10, writes every file in [evidence/](evidence/) and
generates [isolation_matrix.md](evidence/isolation_matrix.md). It takes about a minute, most of it T4's
deliberate deadlock variant. Single scenarios: `python portfolio-3-transactions-concurrency/harness/concurrency.py t06`.

## 4. How it was tested

- **Ground truth for every counter.** In T4 the `post_like` rows are counted independently of
  `likes_count`, and the Portfolio 1 view `v_counter_drift` is queried: it flags the post whose
  counter lost updates and reports no drift for every fixed variant.
- **Each anomaly is shown, then its fix**, in the same scenario with fresh rows, so the only difference
  between the two runs is the technique.
- **The isolation matrix is generated, not written.** The harness records "occurs" or "prevented" for
  each anomaly at each level it actually ran.
- **A clean end-to-end run** (`run_all.sh` from a freshly built database) completed with exit status 0
  and no thread errors. Exceptions raised inside threads are caught and logged, so a hidden failure
  cannot pass as success; this is how the T4 deadlock in section 5.2 was found.

## 5. Results and evidence

### 5.1 Commit, rollback and savepoint (T1-T3)

| Scenario | Before | After | Shows |
|---|---|---|---|
| T1 `post_fit` with 3 images and 2 hashtags | 6,000 posts; `#ootd` on 1,794 | 6,001 posts; new post has 3 images; `#ootd` on 1,795; new tag on 1; **0 counters out of step** | Every part committed together |
| T2a `post_fit` whose second hashtag breaks `ck_hashtag_name_format` | 6,001 posts, 11,247 images, `#ootd` on 1,795 | **Identical**; 0 posts with the failed caption | The post and images written before the error were rolled back too |
| T2a next statement in the failed transaction | | `current transaction is aborted, commands ignored until end of transaction block` | PostgreSQL refuses partial work after an error |
| T2b `post_fit` with no images | | Refused: `a post needs 1 to 10 images, got 0`; 0 posts without images | BR-07, enforced by the transaction |
| T3 close challenge 20, notification fails | Total style points 2,550; no winner | Winner set; points **2,600** (exactly the reward of 50); **0** notifications | `ROLLBACK TO SAVEPOINT` undid only the notification |
| T3 run the closing statement again | | `UPDATE 0` | BR-17's `WHERE winner_entry_id IS NULL` makes closing idempotent |

### 5.2 Concurrency (T4-T10)

**T4: 50 simultaneous likes on one post** (50 `post_like` rows stored in every variant)

| Variant | Level | `likes_count` | Lost | Notes |
|---|---|---:|---:|---|
| Read the counter, write back read + 1 | READ COMMITTED | **1** | **49** | `v_counter_drift` flags it: stored 1, actual 50 |
| Same | REPEATABLE READ | 50 | 0 | 633 serialization failures (40001), each retried |
| Same | SERIALIZABLE | 50 | 0 | 766 serialization failures, each retried |
| `UPDATE ... SET likes_count = likes_count + 1` | READ COMMITTED | 50 | 0 | One atomic statement; no retries |
| `SELECT ... FOR UPDATE`, then write | READ COMMITTED | 1 | 0 | **49 of 50 sessions deadlocked** (40P01); 43.9 s |
| `SELECT ... FOR NO KEY UPDATE`, then write | READ COMMITTED | 50 | 0 | No deadlocks |

Retry counts vary slightly between runs because they depend on thread timing; the outcomes do not.

**T5: double-tapped vote.** With a plain `INSERT`, the second tap waits for the first to commit, then
fails with `23505 uq_vote_user_post`. With `INSERT ... ON CONFLICT DO NOTHING`, both taps succeed
(1 row and 0 rows inserted). Either way exactly **1 vote** is stored.

**T6: last challenge slot** (`max_entries` 3, 2 already taken, two users enter together)

| Variant | Level | Entries | Outcome |
|---|---|---:|---|
| Count, then insert | READ COMMITTED | **4** | Both saw 2/3 and inserted: over the limit |
| Count, then insert | REPEATABLE READ | **4** | Both saw 2/3 and inserted: write skew |
| Count, then insert | SERIALIZABLE | 3 | One aborted with 40001 ("read/write dependencies among transactions"), retried, saw 3/3 and was refused |
| Lock the challenge row `FOR UPDATE`, then count | READ COMMITTED | 3 | The second waited, then saw 3/3 and was refused |

**T7: repeated read during a write.** The writer commits one like and one vote between the reader's two
reads. READ COMMITTED: counter 0 then 1, votes 0 then 1. REPEATABLE READ and SERIALIZABLE: 0 and 0
both times.

**T8: deadlock.** In opposite order, job B was aborted with `40P01 deadlock detected` after 1.0 s and
job A committed. When both jobs first lock the posts in id order, B waits for A, then both commit.

**T9: MVCC and locks.** Session A's uncommitted update leaves the old row version visible to readers at
every level, with A's transaction id in its `xmax`. Session B's update of the same row appears in
`pg_stat_activity` with `wait_event_type=Lock`, `wait_event=transactionid` and A's process as its
blocker; `pg_locks` shows B waiting (`granted=False`) for a `ShareLock` on A's transaction id while
holding the tuple lock. After both commit, the row has a new `xmin` and a new `ctid`: a new version,
not an overwrite.

**T10: double close.** With a plain read, both admins saw no winner, so the winner received 200
points instead of 100. With `SELECT ... FOR UPDATE`, the second admin waited, saw the winner already
set and did nothing: 100 points.

### 5.3 Isolation matrix (observed)

| Anomaly | READ COMMITTED | REPEATABLE READ | SERIALIZABLE | Scenario |
|---|---|---|---|---|
| Dirty read | prevented | prevented | prevented | T9 |
| Non-repeatable read | occurs | prevented | prevented | T7 |
| Phantom read | occurs | prevented | prevented | T7 |
| Lost update | occurs | prevented | prevented | T4 |
| Write skew | occurs | occurs | prevented | T6 |

Generated file: [isolation_matrix.md](evidence/isolation_matrix.md).

## 6. Analysis

**PostgreSQL's isolation levels are snapshot rules.** Under MVCC an update never overwrites a row in
place; it writes a new version and marks the old one with its transaction id in `xmax` (T9). Readers
choose a version by snapshot, which is why no reader at any level saw A's uncommitted caption (no dirty
reads, even though the standard allows them at READ UNCOMMITTED, a level PostgreSQL treats as READ
COMMITTED). READ COMMITTED takes a new snapshot for every statement, so a transaction can see other
transactions' commits between two of its own statements (T7). REPEATABLE READ and SERIALIZABLE keep one
snapshot for the whole transaction, so repeated reads agree, and PostgreSQL's REPEATABLE READ also
prevents phantoms, which the SQL standard does not require.

**A lost update is a read-modify-write race, and there are three ways out.** At READ COMMITTED, 49 of
50 likes vanished from the counter because every session wrote back a value it had read before the
others committed (T4). REPEATABLE READ and SERIALIZABLE refuse to update a row changed since the
snapshot and raise 40001, which is correct but costs hundreds of retries under contention. An atomic
`likes_count = likes_count + 1` avoids the race with no retries, because the row lock makes each
increment start from the latest committed value; it is the right choice for counters. Locking the row
first also works, but only with the right lock (below).

**The lock mode matters as much as the lock.** Locking the post `FOR UPDATE` after inserting a like
deadlocked 49 of 50 sessions. The like's foreign key check holds a `KEY SHARE` lock on the post, and
`FOR UPDATE` conflicts with `KEY SHARE`, so every session waited for locks the others held.
`FOR NO KEY UPDATE`, the mode an ordinary `UPDATE` takes when it changes no key columns, is compatible
with `KEY SHARE`, and stored all 50 likes in under a second. This came from a failed run, found only
because thread exceptions are logged rather than swallowed.

**Write skew is the anomaly REPEATABLE READ lets through.** In T6 each session checked the entry count
and inserted a different row, so no row was written by both and REPEATABLE READ saw no conflict:
the challenge ended with 4 entries for 3 places. SERIALIZABLE (PostgreSQL's Serializable Snapshot
Isolation) tracks read/write dependencies between transactions, detected that the two could not have
run one after the other, and aborted one; on retry it saw the full challenge. The alternative at READ
COMMITTED is to turn the hidden conflict into a real one by locking the challenge row first, which is
also what makes T10's double close safe. For FitsCheck, the entry rule uses the row lock, since it
serialises only entrants of the same challenge and needs no retry logic.

**Constraints are concurrency control too.** The double-tap vote (T5) needed no application logic:
`uq_vote_user_post` made the second insert wait for the first and then fail, so a race could not create
two votes. `ON CONFLICT DO NOTHING` turns that failure into a harmless no-op for the client.

**Deadlocks are prevented by order, not by timeouts.** PostgreSQL resolved T8's cycle by aborting one
job after `deadlock_timeout`, which is safe but wastes work. Locking rows in a fixed order (by id)
means two jobs can never each hold what the other needs.

**Choosing levels for FitsCheck.** READ COMMITTED with targeted techniques covers almost everything:
atomic increments for counters, unique constraints for one-per-user rules, row locks for the challenge
entry limit and for closing. SERIALIZABLE is the safety net for logic that is hard to lock correctly,
at the price of retry handling in the application.

## 7. Limitations and next steps

- **A row lock serialises everyone on that row.** The T4 fix keeps one hot post's likes correct, but
  every like on a viral post queues behind the same row lock. At scale the counter would be kept in
  Redis (`INCR`) and flushed to PostgreSQL in batches, the design Portfolio 4 builds, with T8's ordered
  locking in the flush job.
- **Interleavings are forced.** Barriers make each anomaly appear on every run; real traffic would hit
  them only sometimes, which is why they are dangerous and why they are demonstrated this way.
- **Retries are simple.** The harness retries serialization failures immediately and without limit; a
  production client would cap retries and back off.
- **The fixes are demonstrated, not wired into a running application.** `post_fit` is the only
  transaction packaged as a database function; the challenge entry and close logic lives in the
  scenarios.
- **The screenshots the brief mentions are replaced by text logs**, which show the same sequence with
  timestamps and can be searched and compared between runs.
