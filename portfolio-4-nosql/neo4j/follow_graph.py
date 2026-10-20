"""The FitsCheck follow network in Neo4j, compared with the same questions in SQL.

Loads every user as a (:User) node and every follow as a [:FOLLOWS] relationship from the Portfolio 2
dataset, then answers two graph questions both ways and checks the answers agree:

1. People you may know: accounts followed by the people a user follows (Portfolio 2 query q07).
2. Shortest follow path between two users: one shortestPath() call in Cypher against a recursive CTE
   that has to enumerate paths in SQL.

PROFILE reports database hits for each Cypher query. Writes portfolio-4-nosql/evidence/neo4j_follow_graph.txt.
"""

import os
import statistics
import time
from pathlib import Path

import psycopg
from neo4j import GraphDatabase

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "neo4j_follow_graph.txt"
ME = 82114
MAX_DEPTH = 4
lines = []

PYMK_CYPHER = """
MATCH (me:User {id: $me})-[:FOLLOWS]->(:User)-[:FOLLOWS]->(s:User)
WHERE s <> me AND NOT (me)-[:FOLLOWS]->(s)
RETURN s.id AS suggestion, count(*) AS mutual
ORDER BY mutual DESC, suggestion
LIMIT 10
"""

PYMK_SQL = """
SELECT f2.followed_id, count(*) FROM follow f1 JOIN follow f2 ON f2.follower_id = f1.followed_id
WHERE f1.follower_id = %(me)s AND f2.followed_id <> %(me)s
  AND NOT EXISTS (SELECT 1 FROM follow x WHERE x.follower_id = %(me)s AND x.followed_id = f2.followed_id)
GROUP BY f2.followed_id ORDER BY count(*) DESC, f2.followed_id LIMIT 10
"""

PATH_CYPHER = f"""
MATCH (a:User {{id: $a}}), (b:User {{id: $b}})
MATCH p = shortestPath((a)-[:FOLLOWS*..{MAX_DEPTH}]->(b))
RETURN [n IN nodes(p) | n.id] AS path
"""

PATH_SQL = f"""
WITH RECURSIVE walk(node, depth, path) AS (
    SELECT %(a)s::bigint, 0, ARRAY[%(a)s::bigint]
    UNION ALL
    SELECT f.followed_id, w.depth + 1, w.path || f.followed_id
    FROM walk w JOIN follow f ON f.follower_id = w.node
    WHERE w.depth < {MAX_DEPTH} AND w.node <> %(b)s AND NOT f.followed_id = ANY(w.path)
)
SELECT path FROM walk WHERE node = %(b)s ORDER BY depth, path LIMIT 1
"""


def log(text=""):
    print(text, flush=True)
    lines.append(text)


def median_ms(fn, runs=5):
    fn()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def db_hits(plan):
    return plan.get("dbHits", 0) + sum(db_hits(child) for child in plan.get("children", []))


def main():
    pg = psycopg.connect(os.environ["PG_URL"], options="-c search_path=fitscheck")
    driver = GraphDatabase.driver(os.environ["NEO4J_URL"], auth=("neo4j", os.environ["NEO4J_PASSWORD"]))

    log("FitsCheck follow graph: Neo4j against PostgreSQL")
    log("=" * 48)

    with driver.session() as s:
        s.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 50000 ROWS").consume()
        s.run("CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE").consume()
        start = time.perf_counter()
        users = pg.execute("SELECT id, username FROM app_user ORDER BY id").fetchall()
        for i in range(0, len(users), 20000):
            s.run("UNWIND $rows AS r CREATE (:User {id: r[0], username: r[1]})",
                  rows=[list(u) for u in users[i:i + 20000]]).consume()
        follows = pg.execute("SELECT follower_id, followed_id FROM follow").fetchall()
        for i in range(0, len(follows), 50000):
            s.run("UNWIND $rows AS r MATCH (a:User {id: r[0]}), (b:User {id: r[1]}) CREATE (a)-[:FOLLOWS]->(b)",
                  rows=[list(f) for f in follows[i:i + 50000]]).consume()
        nodes = s.run("MATCH (u:User) RETURN count(u)").single()[0]
        rels = s.run("MATCH ()-[f:FOLLOWS]->() RETURN count(f)").single()[0]
        log(f"loaded {nodes:,} User nodes and {rels:,} FOLLOWS relationships in {time.perf_counter() - start:.1f}s")

        log()
        log(f"1. People you may know for user {ME} (Portfolio 2 query q07)")
        log("-" * 56)
        graph = [(r["suggestion"], r["mutual"]) for r in s.run(PYMK_CYPHER, me=ME)]
        sql = [tuple(r) for r in pg.execute(PYMK_SQL, {"me": ME})]
        log(f"Cypher: {graph}")
        log(f"SQL:    {sql}")
        log(f"same suggestions: {graph == sql}")
        log(f"Neo4j {median_ms(lambda: s.run(PYMK_CYPHER, me=ME).consume()):.2f} ms, "
            f"PostgreSQL {median_ms(lambda: pg.execute(PYMK_SQL, {'me': ME}).fetchall()):.2f} ms (median of 5)")
        profile = s.run("PROFILE " + PYMK_CYPHER, me=ME).consume().profile
        log(f"Neo4j database hits: {db_hits(profile):,}")

        target = s.run(f"MATCH (a:User {{id: $me}})-[:FOLLOWS*{MAX_DEPTH - 1}]->(t:User) "
                       f"WHERE NOT exists {{ MATCH p = shortestPath((a)-[:FOLLOWS*..{MAX_DEPTH - 2}]->(t)) RETURN p }} "
                       "RETURN t.id ORDER BY t.id LIMIT 1", me=ME).single()[0]
        log()
        log(f"2. Shortest follow path from user {ME} to user {target} (at most {MAX_DEPTH} hops)")
        log("-" * 60)
        graph_path = s.run(PATH_CYPHER, a=ME, b=target).single()["path"]
        sql_path = pg.execute(PATH_SQL, {"a": ME, "b": target}).fetchone()[0]
        log(f"Cypher shortestPath: {graph_path} ({len(graph_path) - 1} hops)")
        log(f"SQL recursive CTE:   {sql_path} ({len(sql_path) - 1} hops)")
        log(f"same length: {len(graph_path) == len(sql_path)} (several equally short paths may exist)")
        log(f"Neo4j {median_ms(lambda: s.run(PATH_CYPHER, a=ME, b=target).consume()):.2f} ms, "
            f"PostgreSQL {median_ms(lambda: pg.execute(PATH_SQL, {'a': ME, 'b': target}).fetchone(), runs=3):.2f} ms")
        explored = pg.execute(PATH_SQL.replace("SELECT path FROM walk WHERE node = %(b)s ORDER BY depth, path LIMIT 1",
                                               "SELECT count(*) FROM walk"), {"a": ME, "b": target}).fetchone()[0]
        profile = s.run("PROFILE " + PATH_CYPHER, a=ME, b=target).consume().profile
        log(f"the recursive CTE built {explored:,} partial paths; Neo4j used {db_hits(profile):,} database hits")

        log()
        log("3. How the work grows with the search depth (same pair of users)")
        log("-" * 64)
        log("max hops | SQL partial paths | SQL ms    | Neo4j db hits | Neo4j ms")
        for depth in (3, 4, 5, 6):
            sql_d = PATH_SQL.replace(f"w.depth < {MAX_DEPTH}", f"w.depth < {depth}")
            count_d = sql_d.replace("SELECT path FROM walk WHERE node = %(b)s ORDER BY depth, path LIMIT 1",
                                    "SELECT count(*) FROM walk")
            paths = pg.execute(count_d, {"a": ME, "b": target}).fetchone()[0]
            sql_ms = median_ms(lambda: pg.execute(sql_d, {"a": ME, "b": target}).fetchone(), runs=1)
            cypher_d = PATH_CYPHER.replace(f"*..{MAX_DEPTH}", f"*..{depth}")
            hits = db_hits(s.run("PROFILE " + cypher_d, a=ME, b=target).consume().profile)
            neo_ms = median_ms(lambda: s.run(cypher_d, a=ME, b=target).consume(), runs=3)
            log(f"{depth:8} | {paths:17,} | {sql_ms:9.1f} | {hits:13,} | {neo_ms:8.1f}")
        log("The recursive CTE enumerates every path up to the depth limit, so its work multiplies by roughly")
        log("the average out-degree (about 9 follows) per extra hop. shortestPath() runs a bidirectional")
        log("breadth-first search that stops at the first meeting point, so its work barely changes.")

    driver.close()
    EVIDENCE.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
