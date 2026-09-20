"""A polite client: timeouts, retries with jittered backoff, ETag caching. (Lesson 10)

    python3 api/client.py          # with the API running on :8080
"""
import json, random, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8080/v1"
CACHE = {}                                   # url → (etag, body)

def get(path, retries=4):
    url = BASE + path
    for attempt in range(retries + 1):
        req = urllib.request.Request(url)
        if url in CACHE:
            req.add_header("If-None-Match", CACHE[url][0])   # "only if it changed, please"
        try:
            with urllib.request.urlopen(req, timeout=3) as r:  # never wait forever
                body = json.loads(r.read() or b"{}")
                tag = r.headers.get("ETag")
                if tag: CACHE[url] = (tag, body)
                return r.status, body
        except urllib.error.HTTPError as e:
            if e.code == 304:                                    # our copy is still good
                return 304, CACHE[url][1]
            if e.code in (429, 503) and attempt < retries:       # the counter is busy: back off
                wait = float(e.headers.get("Retry-After", 2 ** attempt)) + random.random()
                print(f"   {e.code} → sleeping {wait:.1f}s (attempt {attempt + 1})")
                time.sleep(min(wait, 5))
                continue
            return e.code, json.loads(e.read() or b"{}")
    return 599, {"error": {"code": "gave_up"}}

if __name__ == "__main__":
    print(get("/students/2"))          # 200 + cached
    print(get("/students/2"))          # 304 — served from our cache
    for _ in range(3):
        print(get("/health")[0], end=" ")
    print()
