-- T3: closing a challenge crowns the winner and awards style points in one transaction. Notifying the
-- winner is inside a SAVEPOINT, so a failed notification is undone on its own and the win still
-- commits. BR-17: a winner is set only once the challenge has ended and only if none is set yet.
SET search_path = fitscheck;
\set challenge 20

-- step 1: state before
SELECT id, ends_at, now() > ends_at AS has_ended, winner_entry_id, reward_points
FROM challenge WHERE id = :challenge;
SELECT sum(style_points) AS total_style_points_before FROM app_user;

BEGIN;
-- step 2: lock the challenge row so no other session can close it at the same time (see T10)
SELECT id FROM challenge WHERE id = :challenge FOR UPDATE;

-- step 3: the entry whose post has the most votes wins; the WHERE clause holds BR-17
WITH winner AS (
    SELECT e.id, e.user_id, count(v.id) AS votes
    FROM challenge_entry e LEFT JOIN vote v ON v.post_id = e.post_id
    WHERE e.challenge_id = :challenge
    GROUP BY e.id ORDER BY votes DESC, e.id LIMIT 1
)
UPDATE challenge c SET winner_entry_id = w.id
FROM winner w
WHERE c.id = :challenge AND c.winner_entry_id IS NULL AND now() > c.ends_at
RETURNING c.winner_entry_id, w.user_id AS winner_user, w.votes \gset

-- step 4: award the style points
UPDATE app_user SET style_points = style_points + (SELECT reward_points FROM challenge WHERE id = :challenge)
WHERE id = :winner_user RETURNING id, username, style_points;

-- step 5: notifying the winner fails (title is NOT NULL); the savepoint undoes only this part
SAVEPOINT notify_winner;
INSERT INTO notification (recipient_id, type, title) VALUES (:winner_user, 'challenge_won', NULL);
ROLLBACK TO SAVEPOINT notify_winner;

-- step 6: the transaction is usable again and commits the win
COMMIT;

-- step 7: the winner and the points were kept; the failed notification was not
SELECT id, winner_entry_id FROM challenge WHERE id = :challenge;
SELECT sum(style_points) AS total_style_points_after FROM app_user;
SELECT count(*) AS challenge_won_notifications_for_winner
FROM notification WHERE recipient_id = :winner_user AND type = 'challenge_won' AND created_at > now() - interval '1 minute';

-- step 8: running the same closing statement again changes nothing, because BR-17's WHERE clause
-- requires that no winner is set yet
WITH winner AS (
    SELECT e.id FROM challenge_entry e LEFT JOIN vote v ON v.post_id = e.post_id
    WHERE e.challenge_id = :challenge GROUP BY e.id ORDER BY count(v.id) DESC, e.id LIMIT 1
)
UPDATE challenge c SET winner_entry_id = w.id
FROM winner w
WHERE c.id = :challenge AND c.winner_entry_id IS NULL AND now() > c.ends_at;
