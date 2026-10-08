# Portfolio 1: Database Design and Modelling

**Case study:** FitsCheck. **Marks:** 7. **Status:** Not started.

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
## 3. How to run
## 4. How it was tested
## 5. Results and evidence
## 6. Analysis
## 7. Limitations and next steps
