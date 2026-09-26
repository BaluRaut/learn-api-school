"""The school's front office — a REAL HTTP/JSON API in pure Python. (Lessons 02–10, 17)

Zero dependencies: the standard library's http.server. Every idea in the course is a
few readable lines here: routes, status codes, validation, API keys, idempotency keys,
pagination, ETags, rate limits, versioning, request logs — and all seven REST methods
(GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE; see docs/rest-methods.html).
Lesson 17 adds measurement: GET /metrics (Prometheus), and optional CloudWatch EMF log
lines (METRICS_EMF=1) and Datadog DogStatsD packets (DOGSTATSD=127.0.0.1:8125).

    python3 api/school_api.py            # serves http://127.0.0.1:8080/v1/...
    bash api/smoke_test.sh               # the whole course, in curl
"""
import json, os, sys, time, hashlib, uuid, urllib.request, threading, socket, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

API_KEY = os.environ.get("SCHOOL_API_KEY", "hall-pass-123")   # lesson 06: the hall pass for WRITES
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "20"))         # lesson 10: requests per 10 s, per client
VERSION = "v1"
LOG_REQUESTS = os.environ.get("LOG_REQUESTS", "1") != "0"    # the one-line request log (lesson 12)
METRICS_EMF = os.environ.get("METRICS_EMF") == "1"            # lesson 17: CloudWatch Embedded Metric Format lines
DOGSTATSD = os.environ.get("DOGSTATSD")                       # lesson 17: "host:port" of a Datadog agent (UDP)

# ---- the record room (in memory — the Database school's job to make this durable) ----
STUDENTS = {
    1: {"id": 1, "name": "Aarav", "class": "3A", "grade": "A"},
    2: {"id": 2, "name": "Sita",  "class": "3A", "grade": "A+"},
    3: {"id": 3, "name": "Kabir", "class": "3A", "grade": "B+"},
    4: {"id": 4, "name": "Meera", "class": "3B", "grade": "A"},
    5: {"id": 5, "name": "Rohan", "class": "3B", "grade": "B"},
}
NEXT_ID = [6]
IDEMPOTENCY = {}          # lesson 07: Idempotency-Key → the response we already gave
WEBHOOKS = []             # lesson 11: URLs to call back when a student is created
BUCKETS = {}              # lesson 10: client → [count, window_start]
CLASSES = {"3A", "3B"}

# ---- lesson 17: the stopwatch at the counter ----------------------------------------
BUCKETS_S = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)   # histogram edges, in seconds (Prometheus style)
METRICS = {}                                                  # (method, route, status) → [count, sum_s, [bucket counts]]
METRICS_LOCK = threading.Lock()
REPORT_CALLS = [0]
REPORT_CACHE_MISS_EVERY = 15   # SIMULATED slow path: 1 report in 15 "misses the cache" and takes ~150 ms, so the tail is visible

def route_template(path):
    """/v1/students/7 → /v1/students/{id}: one metric per ROUTE, not per URL (unbounded label values sink monitoring bills)."""
    p = urlparse(path).path
    if not p.startswith(f"/{VERSION}/"): return "(unmatched)"
    return re.sub(r"/\d+(?=/|$)", "/{id}", p)

def record(method, route, status, seconds):
    with METRICS_LOCK:
        m = METRICS.setdefault((method, route, status), [0, 0.0, [0] * len(BUCKETS_S)])
        m[0] += 1; m[1] += seconds
        for i, edge in enumerate(BUCKETS_S):
            if seconds <= edge: m[2][i] += 1
    if METRICS_EMF: print(emf_line(method, route, status, seconds), flush=True)
    if DOGSTATSD:
        host, port = DOGSTATSD.rsplit(":", 1)
        try: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(dogstatsd_line(method, route, status, seconds).encode(), (host, int(port)))
        except OSError: pass                        # monitoring must never break the counter

def emf_line(method, route, status, seconds, request_id="-"):
    """CloudWatch Embedded Metric Format: a JSON log line that CloudWatch turns into a metric (Lambda, ECS, the agent)."""
    return json.dumps({"_aws": {"Timestamp": int(time.time() * 1000), "CloudWatchMetrics": [{"Namespace": "SchoolAPI",
            "Dimensions": [["Route"]], "Metrics": [{"Name": "Latency", "Unit": "Milliseconds"}]}]},
            "Route": f"{method} {route}", "StatusCode": status, "RequestId": request_id, "Latency": round(seconds * 1000, 2)})

def dogstatsd_line(method, route, status, seconds):
    """Datadog DogStatsD over UDP: a distribution ("d"), so Datadog can compute p50/p95/p99 across every server."""
    tag = route.replace("{", "").replace("}", "")
    return f"school_api.request.duration:{seconds * 1000:.2f}|d|#method:{method},route:{tag},status:{status}"

def prometheus_text():
    """GET /metrics — the Prometheus exposition format: counters + a latency histogram per route."""
    out = ["# HELP school_api_request_duration_seconds Time from the first byte of the request to the response.",
           "# TYPE school_api_request_duration_seconds histogram"]
    with METRICS_LOCK:
        for (method, route, status), (count, total, buckets) in sorted(METRICS.items()):
            labels = f'method="{method}",route="{route}",status="{status}"'
            for edge, n in zip(BUCKETS_S, buckets):
                out.append(f'school_api_request_duration_seconds_bucket{{{labels},le="{edge}"}} {n}')
            out.append(f'school_api_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}')
            out.append(f"school_api_request_duration_seconds_sum{{{labels}}} {total:.6f}")
            out.append(f"school_api_request_duration_seconds_count{{{labels}}} {count}")
    return "\n".join(out) + "\n"

def etag_of(obj):
    return '"' + hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16] + '"'

def validate_student(body):
    """Lesson 04: the standard form. Returns a list of problems (empty = valid)."""
    problems = []
    if not isinstance(body, dict):
        return [{"field": "(body)", "problem": "must be a JSON object"}]
    if not isinstance(body.get("name"), str) or not body.get("name", "").strip():
        problems.append({"field": "name", "problem": "required, non-empty string"})
    if body.get("class") not in CLASSES:
        problems.append({"field": "class", "problem": f"must be one of {sorted(CLASSES)}"})
    if "grade" in body and body["grade"] not in ("A+", "A", "B+", "B", "C"):
        problems.append({"field": "grade", "problem": "must be one of A+, A, B+, B, C"})
    return problems

class Handler(BaseHTTPRequestHandler):
    server_version = "school-api/1.0"

    # ---- the clerk's stamps (lesson 02) -------------------------------------------
    def send(self, status, body=None, headers=None):
        data = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("X-API-Version", VERSION)
        self.send_header("X-Request-Id", self.request_id)
        if body is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if data:
            if not getattr(self, "head_only", False): self.wfile.write(data)   # HEAD: headers only
        self.log_line(status)

    def error(self, status, code, message, hint=None, **extra):
        """Lesson 07: one error shape, always — code for machines, message for humans."""
        err = {"code": code, "message": message}
        if hint: err["hint"] = hint
        err.update(extra)
        self.send(status, {"error": err})

    def log_line(self, status):
        ms = int((time.time() - self.t0) * 1000)
        record(self.command, route_template(self.path), status, time.perf_counter() - self.t0p)   # lesson 17
        if LOG_REQUESTS:
            print(f"{self.command} {self.path} → {status} · {ms} ms · {self.request_id}", file=sys.stderr, flush=True)

    def log_message(self, *a):   # silence the default noisy log; we print our own line
        pass

    # ---- the queue at the counter (lesson 10) ----------------------------------------
    def rate_limited(self):
        who = self.client_address[0]
        count, start = BUCKETS.get(who, [0, time.time()])
        if time.time() - start > 10:
            count, start = 0, time.time()
        count += 1
        BUCKETS[who] = [count, start]
        if count > RATE_LIMIT:
            self.error(429, "rate_limited", "Too many requests — wait and retry.",
                       hint="respect Retry-After; add jittered backoff", retry_after_seconds=10)
            return True
        return False

    # ---- the hall pass (lesson 06) ---------------------------------------------------
    def authorized(self):
        key = self.headers.get("X-API-Key")
        if key is None:
            self.error(401, "unauthenticated", "Writes need an X-API-Key header.", hint="the hall pass is missing")
            return False
        if key != API_KEY:
            self.error(403, "forbidden", "This key may not write.", hint="a pass, but not the right one")
            return False
        return True

    def read_json(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.error(415, "unsupported_media_type", "Send application/json.")
            return None
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self.error(400, "invalid_json", "The body is not valid JSON.")
            return None

    # ---- routing: nouns and ids (lesson 03) ------------------------------------------
    def route(self):
        self.t0 = time.time(); self.t0p = time.perf_counter(); self.request_id = uuid.uuid4().hex[:8]
        u = urlparse(self.path); parts = [p for p in u.path.split("/") if p]
        self.q = parse_qs(u.query)
        if self.rate_limited():
            return None
        if not parts or parts[0] != VERSION:
            self.error(404, "not_found", f"Unknown path — this API lives under /{VERSION}/.", hint="try /v1/students")
            return None
        return parts[1:]

    def do_GET(self):
        if urlparse(self.path).path == "/metrics":             # lesson 17: scraped by Prometheus; not counted, not rate-limited
            data = prometheus_text().encode()
            self.send_response(200); self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
            return
        p = self.route()
        if p is None: return
        if p == ["health"]:
            return self.send(200, {"status": "ok", "students": len(STUDENTS)})
        if p == ["students"]:
            return self.list_students()
        if len(p) == 2 and p[0] == "students" and p[1].isdigit():
            s = STUDENTS.get(int(p[1]))
            if not s:
                return self.error(404, "not_found", f"No student with id {p[1]}.")
            tag = etag_of(s)                                  # lesson 10: the ETag receipt
            if self.headers.get("If-None-Match") == tag:
                return self.send(304, None, {"ETag": tag})
            return self.send(200, s, {"ETag": tag, "Cache-Control": "private, max-age=30"})
        if p == ["reports", "grades"]:                        # lesson 17: a heavier read, with a SIMULATED cache-miss tail
            REPORT_CALLS[0] += 1
            time.sleep(0.150 if REPORT_CALLS[0] % REPORT_CACHE_MISS_EVERY == 0 else 0.008)
            counts = {}
            for s in STUDENTS.values(): counts.setdefault(s["class"], {}).setdefault(s["grade"], 0); counts[s["class"]][s["grade"]] += 1
            return self.send(200, {"grades_by_class": counts})
        if len(p) == 3 and p[0] == "classes" and p[2] == "students":
            rows = [s for s in STUDENTS.values() if s["class"] == p[1]]
            return self.send(200, {"items": rows, "count": len(rows)})
        self.error(404, "not_found", "No such resource.")

    def list_students(self):
        """Lesson 08: filter → sort → paginate (cursor = the last id you saw)."""
        rows = list(STUDENTS.values())
        if "class" in self.q:
            rows = [s for s in rows if s["class"] == self.q["class"][0]]
        sort = self.q.get("sort", ["id"])[0]
        if sort not in ("id", "name", "grade"):
            return self.error(400, "bad_sort", "sort must be id, name or grade.")
        rows.sort(key=lambda s: s[sort])
        try:
            limit = min(int(self.q.get("limit", ["2"])[0]), 100)
            after = int(self.q.get("cursor", ["0"])[0])
        except ValueError:
            return self.error(400, "bad_pagination", "limit and cursor must be integers.")
        page = [s for s in rows if s["id"] > after][:limit] if sort == "id" else rows[after:after+limit]
        next_cursor = (page[-1]["id"] if sort == "id" else after + limit) if len(page) == limit and (sort != "id" or page[-1]["id"] < max([s["id"] for s in rows] or [0])) else None
        self.send(200, {"items": page, "next_cursor": next_cursor, "total": len(rows)},
                  {"Cache-Control": "private, max-age=5"})

    def do_POST(self):
        p = self.route()
        if p is None: return
        if p == ["webhooks"]:                                   # lesson 11: "call me back"
            body = self.read_json()
            if body is None: return
            if not isinstance(body.get("url"), str):
                return self.error(400, "validation_failed", "Need {\"url\": \"http://…\"}.")
            WEBHOOKS.append(body["url"])
            return self.send(201, {"registered": body["url"], "events": ["student.created"]})
        if p != ["students"]:
            return self.error(404, "not_found", "POST only creates students (or webhooks).")
        if not self.authorized(): return
        key = self.headers.get("Idempotency-Key")             # lesson 07: the receipt number
        if key and key in IDEMPOTENCY:
            status, body = IDEMPOTENCY[key]
            return self.send(status, body, {"Idempotent-Replay": "true"})
        body = self.read_json()
        if body is None: return
        problems = validate_student(body)
        if problems:
            return self.error(400, "validation_failed", "The form has problems.", problems=problems)
        sid = NEXT_ID[0]; NEXT_ID[0] += 1
        student = {"id": sid, "name": body["name"].strip(), "class": body["class"], "grade": body.get("grade", "C")}
        STUDENTS[sid] = student
        if key: IDEMPOTENCY[key] = (201, student)
        self.send(201, student, {"Location": f"/{VERSION}/students/{sid}"})
        self.notify({"event": "student.created", "student": student})

    def do_PUT(self):
        p = self.route()
        if p is None: return
        if len(p) != 2 or p[0] != "students" or not p[1].isdigit():
            return self.error(404, "not_found", "PUT replaces one student: /v1/students/{id}.")
        if not self.authorized(): return
        sid = int(p[1])
        if sid not in STUDENTS:
            return self.error(404, "not_found", f"No student with id {sid}.")
        body = self.read_json()
        if body is None: return
        problems = validate_student(body)
        if problems:
            return self.error(400, "validation_failed", "The form has problems.", problems=problems)
        STUDENTS[sid] = {"id": sid, "name": body["name"].strip(), "class": body["class"], "grade": body.get("grade", "C")}
        self.send(200, STUDENTS[sid], {"ETag": etag_of(STUDENTS[sid])})

    def do_PATCH(self):
        """Lesson 03: change PART of one student — send only the fields that change (PUT replaces the whole thing)."""
        p = self.route()
        if p is None: return
        if len(p) != 2 or p[0] != "students" or not p[1].isdigit():
            return self.error(404, "not_found", "PATCH changes part of one student: /v1/students/{id}.")
        if not self.authorized(): return
        sid = int(p[1])
        if sid not in STUDENTS:
            return self.error(404, "not_found", f"No student with id {sid}.")
        body = self.read_json()
        if body is None: return
        if not isinstance(body, dict) or not body:
            return self.error(400, "validation_failed", "Send a JSON object with the fields to change.")
        unknown = [k for k in body if k not in ("name", "class", "grade")]
        if unknown:
            return self.error(400, "validation_failed", "Unknown fields.", problems=[{"field": k, "problem": "not a student field"} for k in unknown])
        merged = {**STUDENTS[sid], **body}
        problems = validate_student(merged)
        if problems:
            return self.error(400, "validation_failed", "The form has problems.", problems=problems)
        STUDENTS[sid] = {"id": sid, "name": merged["name"].strip(), "class": merged["class"], "grade": merged.get("grade", "C")}
        self.send(200, STUDENTS[sid], {"ETag": etag_of(STUDENTS[sid])})

    def do_HEAD(self):
        """Lesson 02: GET's headers without the body — 'is it there, has it changed?' for the price of the envelope."""
        self.head_only = True
        self.do_GET()

    def do_OPTIONS(self):
        """Lesson 02: 'what may I do here?' — and the browser's CORS preflight before a cross-origin write (UI school, lesson 11)."""
        p = self.route()
        if p is None: return
        if p == ["students"]:                         allow = "GET, HEAD, POST, OPTIONS"
        elif len(p) == 2 and p[0] == "students":     allow = "GET, HEAD, PUT, PATCH, DELETE, OPTIONS"
        else:                                          allow = "GET, HEAD, OPTIONS"
        self.send(204, None, {"Allow": allow, "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": allow,
                              "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Idempotency-Key, If-None-Match",
                              "Access-Control-Max-Age": "600"})

    def do_DELETE(self):
        p = self.route()
        if p is None: return
        if len(p) != 2 or p[0] != "students" or not p[1].isdigit():
            return self.error(404, "not_found", "DELETE removes one student: /v1/students/{id}.")
        if not self.authorized(): return
        STUDENTS.pop(int(p[1]), None)        # deleting twice is fine: idempotent (lesson 03)
        self.send(204)

    def notify(self, event):
        for url in WEBHOOKS:
            try:
                req = urllib.request.Request(url, data=json.dumps(event).encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=2)
            except Exception as e:           # a dead webhook must never break the counter
                print(f"webhook {url} failed: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"🏢 school-api on http://127.0.0.1:{port}/{VERSION}/students  (writes need X-API-Key: {API_KEY})", file=sys.stderr, flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
