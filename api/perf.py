"""Lesson 17 — measure the counter like production does: latency percentiles, per route, and the three ways
monitoring tools receive the numbers (Prometheus /metrics, CloudWatch EMF, Datadog DogStatsD). Zero dependencies.

    python3 api/perf.py              # 400 requests, 8 at a time, against a fresh counter on a free port
    python3 api/perf.py 2000 16      # more requests, more parallel callers

The report endpoint has a SIMULATED slow path (1 call in 15 "misses the cache", ~150 ms) so the tail is visible.
"""
import os, sys, time, socket, threading, random, math, json, urllib.request
from concurrent.futures import ThreadPoolExecutor

N = int(sys.argv[1]) if len(sys.argv) > 1 else 400
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 8

# a pretend Datadog agent: the counter sends DogStatsD packets over UDP, we catch a few to show them
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); udp.bind(("127.0.0.1", 0)); udp.settimeout(0.2)
PACKETS = []
def agent():
    while True:
        try: PACKETS.append(udp.recv(512).decode())
        except socket.timeout: pass
        except OSError: return
threading.Thread(target=agent, daemon=True).start()

os.environ.update(RATE_LIMIT="1000000000", LOG_REQUESTS="0", DOGSTATSD=f"127.0.0.1:{udp.getsockname()[1]}")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import school_api as S
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{PORT}"

def percentile(values, p):
    """Linear interpolation between the two nearest ranks — the same as numpy's default and Excel PERCENTILE.INC."""
    v = sorted(values); k = (len(v) - 1) * p / 100; lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)

random.seed(17)
PLAN = [random.choices(["/v1/students/{}".format(random.randint(1, 5)), "/v1/students?limit=2", "/v1/reports/grades"],
                       weights=[50, 25, 25])[0] for _ in range(N)]
def call(path):
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as r: r.read(); status = r.status
    except Exception as e: status = getattr(e, "code", 599)
    return S.route_template(path), status, (time.perf_counter() - t) * 1000

t0 = time.perf_counter()
with ThreadPoolExecutor(WORKERS) as pool: results = list(pool.map(call, PLAN))
wall = time.perf_counter() - t0
P = (25, 50, 75, 90, 95, 99)
fmt = lambda v: f"{v:7.1f}"
allms = [ms for _, _, ms in results]; errors = sum(1 for _, st, _ in results if st >= 500)

print(f"🏢 counter on :{PORT} · {N} requests · {WORKERS} at a time · {wall:.2f} s → {N / wall:.0f} requests/s · errors {errors} ({100 * errors / N:.1f}%)\n")
print("── latency, ALL requests together (ms, measured by the caller)")
print("   " + "".join(f"   p{p:<4}" for p in P) + "    max    mean")
print("   " + "".join(fmt(percentile(allms, p)) + " " for p in P) + fmt(max(allms)) + fmt(sum(allms) / N))
print(f"   p95 over everything says {percentile(allms, 95):.1f} ms — healthy? The slow report hides among the fast student reads; only p99 ({percentile(allms, 99):.0f} ms) sees it.")

print("\n── the same, per ROUTE — the view that finds the slow one")
print(f"   {'route':<24}{'count':>6}" + "".join(f"{'p' + str(p):>8}" for p in P) + f"{'max':>8}{'mean':>8}")
routes = sorted({r for r, _, _ in results})
for r in routes:
    ms = [m for rr, _, m in results if rr == r]
    print(f"   {'GET ' + r:<24}{len(ms):>6}" + "".join(f"{percentile(ms, p):8.1f}" for p in P) + f"{max(ms):8.1f}{sum(ms) / len(ms):8.1f}")

rep = [m for rr, _, m in results if rr == "/v1/reports/grades"]
print("\n── GET /v1/reports/grades — where the time goes (each █ ≈ 2 requests)")
edges = [0, 5, 10, 25, 50, 100, 250, 1000]
for lo, hi in zip(edges, edges[1:]):
    n = sum(1 for m in rep if lo <= m < hi)
    print(f"   {lo:>4}–{hi:<4} ms {'█' * math.ceil(n / 2):<45} {n}")
p90, p95, mean = percentile(rep, 90), percentile(rep, 95), sum(rep) / len(rep)
print(f"   mean {mean:.1f} ms looks fine · p90 {p90:.1f} ms · p95 {p95:.1f} ms — about 1 caller in 15 waits ~150 ms.")
print("   The average hides them; the percentiles show them. Alert on p95/p99 per route, not on the mean.")

text = urllib.request.urlopen(BASE + "/metrics").read().decode()
print("\n── 1 · Prometheus scrapes GET /metrics (then Grafana draws it)")
lines = [l for l in text.splitlines() if 'route="/v1/reports/grades"' in l]
for l in lines[3:6] + lines[-3:]: print("   " + l)
# the server-side p95, the way Prometheus computes it: histogram_quantile over the bucket counts
b = {}
for l in lines:
    if "_bucket" in l:
        le = l.split('le="')[1].split('"')[0]; b[float("inf") if le == "+Inf" else float(le)] = b.get(float("inf") if le == "+Inf" else float(le), 0) + int(l.split()[-1])
tot = b[float("inf")]; want = 0.95 * tot; prev_e, prev_c = 0.0, 0
for e in sorted(b):
    if b[e] >= want:
        est = prev_e + (e - prev_e) * (want - prev_c) / max(b[e] - prev_c, 1) if e != float("inf") else prev_e; break
    prev_e, prev_c = e, b[e]
print(f"   histogram_quantile(0.95, …) ≈ {est * 1000:.0f} ms (server side, bucket estimate) vs {p95:.0f} ms measured by the caller —")
print("   close, not equal: buckets are coarse, and the caller also counts the network and its own queue.")

print("\n── 2 · Datadog: the counter sent DogStatsD packets over UDP to the agent (first 3 caught here)")
time.sleep(0.4)
for pk in [p for p in PACKETS if "reports" in p][:3]: print("   " + pk)
print(f"   ({len(PACKETS)} packets caught — one per request; 'd' = distribution, so Datadog computes p95 across all servers)")

print("\n── 3 · CloudWatch: with METRICS_EMF=1 each request prints one Embedded Metric Format line; CloudWatch turns it into a metric")
print("   " + S.emf_line("GET", "/v1/reports/grades", 200, percentile(rep, 50) / 1000, "a1b2c3d4"))

print("\n── the alarm: 'p95 of the report route above 100 ms for 15 minutes' — the same rule in each tool")
print("   CloudWatch  aws cloudwatch put-metric-alarm --alarm-name school-api-report-p95 --namespace SchoolAPI \\")
print("                 --metric-name Latency --dimensions Name=Route,Value='GET /v1/reports/grades' --extended-statistic p95 \\")
print("                 --period 300 --evaluation-periods 3 --threshold 100 --comparison-operator GreaterThanThreshold")
print("   Datadog     percentile(last_15m):p95:school_api.request.duration{route:/v1/reports/grades} > 100")
print("   Prometheus  histogram_quantile(0.95, sum by (le) (rate(school_api_request_duration_seconds_bucket{route=\"/v1/reports/grades\"}[5m]))) > 0.1")
srv.shutdown(); udp.close()
