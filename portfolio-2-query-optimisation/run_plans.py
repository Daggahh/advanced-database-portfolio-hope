"""Runs every Portfolio 2 query and records its results, execution plan and timings.

For each sql/qNN_*.sql file:
1. Runs the query and saves its result rows to evidence/results/qNN_<label>.txt. For any label other
   than "before", the rows are compared with the "before" rows: an optimisation must not change the
   answer.
2. Runs EXPLAIN (ANALYZE, BUFFERS) three times. The first run may read from disk; the median of the
   three is reported, and the third plan (warm cache) is saved to plans/qNN_<label>.txt.
3. Writes evidence/timings_<label>.csv and a snapshot of the planner settings and table sizes.

Queries are run through psql so that the same files work by hand with psql variables (sql/params.sql).

Usage:
    python portfolio-2-query-optimisation/run_plans.py --label before
    python portfolio-2-query-optimisation/run_plans.py --label after --only q05 q06
"""

import argparse
import csv
import os
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SQL = HERE / "sql"
PLANS = HERE / "plans"
EVIDENCE = HERE / "evidence"
RESULTS = EVIDENCE / "results"
RUNS = 3

SETTINGS_SQL = """
SELECT version();
SELECT name, setting, unit FROM pg_settings
WHERE name IN ('work_mem', 'shared_buffers', 'effective_cache_size', 'random_page_cost', 'jit',
               'max_parallel_workers_per_gather', 'default_statistics_target')
ORDER BY name;
SELECT relname AS table_name, n_live_tup AS rows, pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables WHERE schemaname = 'fitscheck' ORDER BY n_live_tup DESC;
SELECT indexrelname AS index_name, relname AS table_name, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes WHERE schemaname = 'fitscheck' ORDER BY relname, indexrelname;
"""


def psql(url, script):
    proc = subprocess.run(["psql", url, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-P", "pager=off"],
                          input=script, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"psql failed:\n{proc.stderr}")
    return proc.stdout


def parse_ms(pattern, text):
    match = re.search(pattern + r":\s+([\d.]+) ms", text)
    return float(match.group(1)) if match else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--label", required=True, help="e.g. before, after")
    parser.add_argument("--only", nargs="*", help="query prefixes to run, e.g. q01 q05")
    args = parser.parse_args()

    url = os.environ.get("PG_URL")
    if not url:
        sys.exit("PG_URL is not set; run: set -a; . ./.env; set +a")

    for folder in (PLANS, RESULTS):
        folder.mkdir(parents=True, exist_ok=True)

    params = (SQL / "params.sql").read_text()
    queries = sorted(SQL.glob("q[0-9][0-9]_*.sql"))
    if args.only:
        queries = [q for q in queries if any(q.name.startswith(prefix) for prefix in args.only)]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (EVIDENCE / f"settings_{args.label}.txt").write_text(
        f"Captured {stamp}\n\n" + psql(url, SETTINGS_SQL))

    rows = []
    for query_file in queries:
        name = query_file.stem
        query = query_file.read_text()

        result = psql(url, params + query)
        (RESULTS / f"{name}_{args.label}.txt").write_text(result)
        same = ""
        before = RESULTS / f"{name}_before.txt"
        if args.label != "before" and before.exists():
            same = "yes" if before.read_text() == result else "NO"

        times, planning, plan = [], [], ""
        for _ in range(RUNS):
            plan = psql(url, params + "EXPLAIN (ANALYZE, BUFFERS)\n" + query)
            times.append(parse_ms("Execution Time", plan))
            planning.append(parse_ms("Planning Time", plan))
        median = statistics.median(times)
        buffers = next((line.strip() for line in plan.splitlines() if "Buffers:" in line), "")

        header = (f"-- {name} [{args.label}] captured {stamp}\n"
                  f"-- execution times (ms): {', '.join(f'{t:.1f}' for t in times)}; median {median:.1f}\n\n")
        (PLANS / f"{name}_{args.label}.txt").write_text(header + query + "\n" + plan)

        rows.append(dict(query=name, run1_ms=f"{times[0]:.1f}", run2_ms=f"{times[1]:.1f}",
                         run3_ms=f"{times[2]:.1f}", median_ms=f"{median:.1f}",
                         planning_ms=f"{statistics.median(planning):.1f}", top_buffers=buffers,
                         same_result_as_before=same))
        print(f"{name:32} median {median:10.1f} ms   {buffers}"
              + (f"   same result: {same}" if same else ""), flush=True)

    out = EVIDENCE / f"timings_{args.label}.csv"
    existing = {}
    if args.only and out.exists():
        with out.open() as f:
            existing = {r["query"]: r for r in csv.DictReader(f)}
    existing.update({r["query"]: r for r in rows})
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(existing[k] for k in sorted(existing))


if __name__ == "__main__":
    main()
