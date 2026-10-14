-- Generates data-dictionary.md from the PostgreSQL catalog, so the dictionary cannot drift from the
-- schema. Descriptions come from 06_comments.sql.
-- Run: psql "$PG_URL" -X -q -At -f portfolio-1-database-design/sql/07_data_dictionary.sql \
--        > portfolio-1-database-design/data-dictionary.md

SET search_path = fitscheck;

WITH tbl AS (
    SELECT c.oid, c.relname, obj_description(c.oid, 'pg_class') AS descr
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'fitscheck' AND c.relkind = 'r'
),
col AS (
    SELECT t.oid, a.attnum,
           format('| `%s` | %s | %s | %s | %s | %s |',
                  a.attname,
                  format_type(a.atttypid, a.atttypmod),
                  CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE 'null' END,
                  CASE WHEN a.attidentity <> '' THEN 'identity'
                       ELSE coalesce(replace(pg_get_expr(d.adbin, d.adrelid), '|', '\|'), '') END,
                  coalesce((SELECT string_agg(DISTINCT
                                       CASE k.contype WHEN 'p' THEN 'PK'
                                                      ELSE 'FK to ' || k.confrelid::regclass END, ', ')
                            FROM pg_constraint k
                            WHERE k.conrelid = t.oid AND k.contype IN ('p', 'f')
                              AND a.attnum = ANY (k.conkey)), ''),
                  coalesce(replace(col_description(t.oid, a.attnum), '|', '\|'), '')) AS line
    FROM tbl t
    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum > 0 AND NOT a.attisdropped
    LEFT JOIN pg_attrdef d ON d.adrelid = t.oid AND d.adnum = a.attnum
),
con AS (
    SELECT t.oid,
           string_agg(format('- `%s`: `%s`', k.conname, replace(pg_get_constraintdef(k.oid), '|', '\|')),
                      E'\n' ORDER BY position(k.contype::text IN 'pufc'), k.conname) AS lines
    FROM tbl t
    JOIN pg_constraint k ON k.conrelid = t.oid
    GROUP BY t.oid
),
idx AS (
    SELECT t.oid,
           string_agg(format('- `%s`: `%s`', i.relname, pg_get_indexdef(i.oid)), E'\n' ORDER BY i.relname) AS lines
    FROM tbl t
    JOIN pg_index x ON x.indrelid = t.oid
    JOIN pg_class i ON i.oid = x.indexrelid
    WHERE NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.oid)
    GROUP BY t.oid
),
trg AS (
    SELECT t.oid,
           string_agg(format('- `%s`: %s', g.tgname, pg_get_triggerdef(g.oid)), E'\n' ORDER BY g.tgname) AS lines
    FROM tbl t
    JOIN pg_trigger g ON g.tgrelid = t.oid AND NOT g.tgisinternal
    GROUP BY t.oid
),
table_section AS (
    SELECT t.oid,
           format(E'### %s\n\n%s\n\n| Column | Type | Null | Default | Key | Description |\n|---|---|---|---|---|---|\n%s\n\n**Constraints**\n\n%s%s%s',
                  t.relname, coalesce(t.descr, ''),
                  (SELECT string_agg(line, E'\n' ORDER BY attnum) FROM col WHERE col.oid = t.oid),
                  coalesce(c.lines, '- none'),
                  coalesce(E'\n\n**Other indexes**\n\n' || i.lines, ''),
                  coalesce(E'\n\n**Triggers**\n\n' || g.lines, '')) AS body
    FROM tbl t
    LEFT JOIN con c ON c.oid = t.oid
    LEFT JOIN idx i ON i.oid = t.oid
    LEFT JOIN trg g ON g.oid = t.oid
),
enum_section AS (
    SELECT string_agg(format('| `%s` | %s | %s |', ty.typname,
                             (SELECT string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder)
                              FROM pg_enum e WHERE e.enumtypid = ty.oid),
                             coalesce(obj_description(ty.oid, 'pg_type'), '')),
                      E'\n' ORDER BY ty.typname) AS body
    FROM pg_type ty
    JOIN pg_namespace n ON n.oid = ty.typnamespace
    WHERE n.nspname = 'fitscheck' AND ty.typtype = 'e'
),
view_section AS (
    SELECT string_agg(format('| `%s` | %s |', c.relname, coalesce(obj_description(c.oid, 'pg_class'), '')),
                      E'\n' ORDER BY c.relname) AS body
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'fitscheck' AND c.relkind = 'v'
)
SELECT format(E'# FitsCheck Data Dictionary\n\n'
              'Generated from the PostgreSQL catalog by `sql/07_data_dictionary.sql`; descriptions come from '
              '`sql/06_comments.sql`. Do not edit by hand: change the schema or comments and regenerate.\n\n'
              '%s\n\n'
              '## Enum types\n\n| Type | Values | Description |\n|---|---|---|\n%s\n\n'
              '## Views\n\n| View | Description |\n|---|---|\n%s\n\n'
              '## Tables (%s)\n\n%s\n',
              obj_description('fitscheck'::regnamespace, 'pg_namespace'),
              (SELECT body FROM enum_section),
              (SELECT body FROM view_section),
              (SELECT count(*) FROM tbl),
              (SELECT string_agg(body, E'\n\n' ORDER BY oid) FROM table_section));
