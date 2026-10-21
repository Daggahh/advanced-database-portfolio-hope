#!/usr/bin/env bash
# Rebuilds the three-member replica set, initiates rs0, exports fit documents from fitscheck_p3 and runs
# demo.py inside the replica set's network in three phases, killing members in between.
# Requires PG_URL (set -a; . ./.env; set +a), the fitscheck_p3 database and the repository's .venv.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$here/../.."
evidence="$here/../evidence"
cd "$here"

docker compose down -v --remove-orphans > /dev/null 2>&1 || true
docker compose up -d > /dev/null
until docker exec mongo1 mongosh --quiet --eval "db.adminCommand('ping').ok" > /dev/null 2>&1; do sleep 1; done
docker exec mongo1 mongosh --quiet --eval 'rs.initiate({_id: "rs0", members: [
    {_id: 0, host: "mongo1:27017"}, {_id: 1, host: "mongo2:27017"}, {_id: 2, host: "mongo3:27017"}]})' > /dev/null
until [ "$(docker exec mongo1 mongosh --quiet --eval 'db.hello().isWritablePrimary')" = "true" ]; do sleep 1; done

"$root/.venv/bin/python" "$here/export_posts.py"
docker build -q -t fitscheck-mongo-demo - > /dev/null <<'DOCKERFILE'
FROM python:3.12-slim
RUN pip install --no-cache-dir pymongo==4.19.0
DOCKERFILE

demo() {
    docker run --rm --user "$(id -u):$(id -g)" --network fitscheck-mongo-rs_default \
        -v "$here/demo.py:/demo.py:ro" -v "$here/.data:/data:ro" -v "$evidence:/evidence" \
        fitscheck-mongo-demo python /demo.py "$@"
}
primary() {
    for m in mongo1 mongo2 mongo3; do
        if [ "$(docker exec "$m" mongosh --quiet --eval 'db.hello().isWritablePrimary' 2>/dev/null)" = "true" ]; then
            echo "$m"; return; fi
    done
}

rm -f "$evidence/mongo_replicaset_demo.txt"
demo load
demo failover &
writer=$!
sleep 8
victim="$(primary)"
docker kill "$victim" > /dev/null
echo "host: killed the primary, $victim, at about 8 s into the failover phase" | tee -a "$evidence/mongo_replicaset_demo.txt"
wait "$writer"
second="$(primary)"
docker kill "$second" > /dev/null
echo "host: killed the new primary, $second; one member left" | tee -a "$evidence/mongo_replicaset_demo.txt"
sleep 12
demo quorum
