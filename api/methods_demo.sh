#!/usr/bin/env bash
# Every REST method against the counter, with the headers that prove each rule. (Showcase: REST methods)
#   python3 api/school_api.py &      then:      bash api/methods_demo.sh
B=${B:-http://127.0.0.1:8080/v1}; J='Content-Type: application/json'; K='X-API-Key: hall-pass-123'
say(){ printf '\n── %s\n' "$*"; }
code(){ curl -s -o /dev/null -w '%{http_code}' "$@"; }
hdr(){ grep -iE "$1" | sed 's/^/   /'; }

say "GET — read it · safe · idempotent · cacheable"
curl -s -i $B/students/2 | hdr '^HTTP|^ETag|^Cache-Control|^\{'
say "HEAD — GET's headers without the body: same ETag and Content-Length, zero bytes of body"
curl -s -I $B/students/2 | hdr '^HTTP|^ETag|^Content-Length'
say "OPTIONS — what may I do here? (also the browser's CORS preflight)"
curl -s -i -X OPTIONS $B/students/2 | hdr '^HTTP|^Allow|^Access-Control-Allow-Methods'
say "POST — create a NEW one · NOT idempotent: the same form twice = two students (unless Idempotency-Key, lesson 07)"
curl -s -i -X POST $B/students -H "$K" -H "$J" -d '{"name":"Zoya","class":"3B"}' | hdr '^HTTP|^Location'
curl -s -i -X POST $B/students -H "$K" -H "$J" -d '{"name":"Zoya","class":"3B"}' | hdr '^HTTP|^Location'
say "PUT — REPLACE the whole student · idempotent: twice = the same student"
curl -s -X PUT $B/students/2 -H "$K" -H "$J" -d '{"name":"Sita","class":"3B","grade":"A+"}'; echo
curl -s -X PUT $B/students/2 -H "$K" -H "$J" -d '{"name":"Sita","class":"3B","grade":"A+"}'; echo
say "PUT with only one field — a replace means ALL the fields, so this is a 400 with problems"
curl -s -X PUT $B/students/2 -H "$K" -H "$J" -d '{"grade":"A"}'; echo
say "PATCH — change PART of the student: send only what changes"
curl -s -X PATCH $B/students/2 -H "$K" -H "$J" -d '{"grade":"A"}'; echo
say "PATCH with a field that does not exist — 400, never a silent ignore"
curl -s -X PATCH $B/students/2 -H "$K" -H "$J" -d '{"nickname":"Situ"}'; echo
say "DELETE — remove it · idempotent: the second DELETE is still 204, because the state is the same (gone)"
echo "   first:  $(code -X DELETE $B/students/5 -H "$K")   second: $(code -X DELETE $B/students/5 -H "$K")   GET afterwards: $(code $B/students/5)"
say "the unsafe methods need the hall pass (lesson 06); the safe ones never do"
echo "   DELETE without a key: $(code -X DELETE $B/students/4)   GET without a key: $(code $B/students/4)"
say "and one that is NOT a method: /students/5/delete as a GET is a smell — GET must never change anything"
echo "   $(code "$B/students/5/delete")  ← 404: no such noun, and no verb hidden in the URL"
echo
echo "✅ seven methods, one counter — safe · idempotent · body · cacheable decide which one you reach for"
