# Portfolio 1: Database Design and Modelling

**Case study:** FitsCheck. **Marks:** 7. **Status:** In progress.

**Brief requires:** chosen case study description, ER diagram, relational schema, keys, constraints, and normalisation explanation.

## 1. Objective
## 2. What I built

### 2.1 Business rules
Twenty rules define what the database must guarantee, each tagged with where it is enforced:
declarative constraint, trigger, or transaction. See [business-rules.md](business-rules.md).

### 2.2 Entity relationship diagram

![FitsCheck ERD](diagrams/fitscheck-erd.png)

Source: [diagrams/fitscheck-erd.mmd](diagrams/fitscheck-erd.mmd), written in Mermaid and rendered locally
with the Mermaid CLI using the ELK layout engine. GitHub also renders the source file directly. To
re-render after a change:

```bash
npx -y -p @mermaid-js/mermaid-cli mmdc -i diagrams/fitscheck-erd.mmd -o diagrams/fitscheck-erd.png --size 5000 -s 2
```

17 tables in five areas: **social** (users, devices, follows, blocks), **content** (posts, images,
shop items, brands, hashtags), **engagement** (likes, votes, comments), **challenges** (challenges,
entries) and **moderation** (reports, notifications).

How to read it (crow's foot notation): the symbol at each end of a line shows how many rows can be
on that side. `||` means exactly one, `o|` zero or one, `o{` zero or many and `|{` one or many. The
line from `post` (`||`) to `post_image` (`|{`) reads "one post contains one or more images". Every many-to-many relationship (follows, likes, votes, post hashtags) is resolved into a
junction table, so no line is many-to-many.

Design points visible in the diagram:
- **Composite foreign keys** keep related rows consistent. A vote's `(post_image_id, post_id)` must
  match an image of that same post (BR-11). A reply's `(parent_id, post_id)` must match a comment on
  the same post (BR-13). A challenge's `(winner_entry_id, id)` must match an entry of that same
  challenge (BR-17).
- **Self-relationships**: `follow` and `block` link users to users; `comment.parent_id` links
  replies to comments.
- **Circular reference** between `challenge` and `challenge_entry`: entries belong to a challenge,
  and the challenge points back at its winning entry. The winner is nullable because no entry exists
  when a challenge is created.
- **Delete behaviour** is deliberate: deleting a post cascades to its images, likes, votes and
  comments, but user references restrict, because accounts are deactivated rather than deleted
  (BR-05).
### 2.3 Normalisation
[normalisation.md](normalisation.md) derives the schema from one flat "post a fit" record through
1NF, 2NF and 3NF, then tests every relation against BCNF. Three relations deliberately keep a
redundant column so a business rule can be a `UNIQUE` constraint: `vote` and `challenge_entry` are in
3NF but not BCNF, and `comment` keeps `post_id` for replies. In each case a composite foreign key
stops the redundant value from ever being wrong. The analysis also replaced a planned trigger (BR-15)
with a declarative composite foreign key. Stored counters are deliberate denormalisation, justified
and controlled.

## 3. How to run

From the repository root, with the stack running (`docker compose up -d postgres`) and `.env` loaded
(`set -a; . ./.env; set +a`):

```bash
psql "$PG_URL" -v ON_ERROR_STOP=1 -f portfolio-1-database-design/sql/01_schema.sql
psql "$PG_URL" -v ON_ERROR_STOP=1 -f portfolio-1-database-design/sql/02_constraints.sql
psql "$PG_URL" -v ON_ERROR_STOP=1 -f portfolio-1-database-design/sql/03_triggers.sql
psql "$PG_URL" -v ON_ERROR_STOP=1 -f portfolio-1-database-design/sql/04_views.sql
```

| Script | Contents |
|---|---|
| [01_schema.sql](sql/01_schema.sql) | Schema `fitscheck`, enum types, 17 tables with primary keys and defaults |
| [02_constraints.sql](sql/02_constraints.sql) | Alternate keys, checks and foreign keys, all named |
| [03_triggers.sql](sql/03_triggers.sql) | Cross-table rules (BR-03, BR-12) and `updated_at` stamping |
| [04_views.sql](sql/04_views.sql) | `v_post_card` (feed card) and `v_counter_drift` (counter reconciliation, BR-20) |

To start again from empty: `psql "$PG_URL" -c "DROP SCHEMA fitscheck CASCADE"`.
## 4. How it was tested
## 5. Results and evidence
## 6. Analysis
## 7. Limitations and next steps
