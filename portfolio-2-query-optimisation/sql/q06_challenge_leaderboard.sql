-- Challenge leaderboard: entries ranked by the votes their post received.
SELECT e.id AS entry_id, e.user_id, e.post_id, count(v.id) AS votes,
       rank() OVER (ORDER BY count(v.id) DESC) AS place
FROM challenge_entry e
LEFT JOIN vote v ON v.post_id = e.post_id
WHERE e.challenge_id = :challenge
GROUP BY e.id
ORDER BY place, e.id
LIMIT 10;
