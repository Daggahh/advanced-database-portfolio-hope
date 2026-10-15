-- People search: users whose name contains a fragment anywhere, case-insensitively.
SELECT id, username, full_name
FROM app_user
WHERE full_name ILIKE '%' || :'name_search' || '%'
ORDER BY full_name, id
LIMIT 20;
