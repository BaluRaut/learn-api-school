#!/usr/bin/env bash
# The whole course in curl — run with the API up: python3 api/school_api.py
B=http://127.0.0.1:8080/v1; K="X-API-Key: hall-pass-123"
say() { printf '\n── %s\n' "$1"; }
say "L02 · GET a student (200 + ETag)";        curl -si $B/students/2 | sed -n '1p;/ETag/p;$p'
say "L02 · unknown id (404, one error shape)"; curl -s $B/students/99
say "L03 · the collection";                    curl -s "$B/students?limit=3"
say "L06 · write without a hall pass (401)";   curl -s -X POST $B/students -H 'Content-Type: application/json' -d '{"name":"Zoya","class":"3B"}'
say "L04 · bad form (400 with field problems)"; curl -s -X POST $B/students -H "$K" -H 'Content-Type: application/json' -d '{"name":"","class":"9Z"}'
say "L07 · create with an Idempotency-Key (201)"; curl -si -X POST $B/students -H "$K" -H 'Content-Type: application/json' -H 'Idempotency-Key: enrol-zoya-1' -d '{"name":"Zoya","class":"3B","grade":"A"}' | sed -n '1p;/Location/p;$p'
say "L07 · same key again → same answer, no double-file"; curl -si -X POST $B/students -H "$K" -H 'Content-Type: application/json' -H 'Idempotency-Key: enrol-zoya-1' -d '{"name":"Zoya","class":"3B","grade":"A"}' | sed -n '1p;/Idempotent-Replay/p'
say "L08 · page 1 then page 2 (cursor)";       curl -s "$B/students?limit=2"; echo; curl -s "$B/students?limit=2&cursor=2"
say "L08 · filter + sort";                     curl -s "$B/students?class=3A&sort=name&limit=10"
say "L10 · conditional GET with If-None-Match (304)"; T=$(curl -si $B/students/2 | tr -d '\r' | awk -F': ' '/^ETag/{print $2}'); curl -si $B/students/2 -H "If-None-Match: $T" | sed -n '1p'
say "L03 · DELETE twice — idempotent (204, 204)"; curl -s -o /dev/null -w '%{http_code} ' -X DELETE $B/students/5 -H "$K"; curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $B/students/5 -H "$K"
say "L10 · 40 quick requests → the queue says 429"; for i in $(seq 1 40); do curl -s -o /dev/null -w '%{http_code} ' $B/health; done; echo
