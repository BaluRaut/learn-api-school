"""One client, six API shapes — watch how differently the same question travels. (Showcase)

    python3 api/api_types.py          # terminal 1
    python3 api/types_client.py       # terminal 2
"""
import base64, json, os, socket, struct, sys, threading, time, urllib.request

BASE = "http://127.0.0.1:8081"
def show(title): print(f"\n── {title}")

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r: return json.loads(r.read())

# 1 ── REST: a noun, a filter, a whole representation back
show("1 REST — GET /v1/students?class=3A")
rest = get("/v1/students?class=3A")
print("   →", json.dumps(rest)[:120])
print("   the shape: you asked for a RESOURCE; you got all of its fields, whether you wanted them or not")

# 2 ── JSON-RPC: a verb by name, with an id to match the answer
show("2 JSON-RPC — POST /jsonrpc  {method: 'students.list'}")
rpc = post("/jsonrpc", {"jsonrpc": "2.0", "id": 1, "method": "students.list", "params": {"class": "3B"}})
print("   →", json.dumps(rpc)[:120])
bad = post("/jsonrpc", {"jsonrpc": "2.0", "id": 2, "method": "students.teleport"})
print("   unknown method →", json.dumps(bad["error"]), " (an ERROR in a 200 — the RPC way)")

# 3 ── GraphQL: you write the shape of the answer
show("3 GraphQL — POST /graphql  { students { name grade } }")
gq = post("/graphql", {"query": "{ students { name grade } }"})
print("   →", json.dumps(gq)[:120])
gq2 = post("/graphql", {"query": "{ students { name } }"})
print("   ask for less →", json.dumps(gq2)[:90], " (no 'class', no 'id' — you chose)")

# 4 ── long polling: the clerk holds the question until there is news
show("4 Long polling — GET /poll?since=0  (the clerk holds it open)")
t0 = time.time(); box = {}
th = threading.Thread(target=lambda: box.update(get("/poll?since=0&wait=10")), daemon=True); th.start()
time.sleep(0.4)
post("/jsonrpc", {"jsonrpc": "2.0", "id": 3, "method": "students.enrol", "params": {"name": "Zoya", "class": "3B", "grade": "A"}})
th.join(timeout=12)
print(f"   → answered after {time.time()-t0:0.1f}s with {len(box.get('events', []))} event(s):", json.dumps(box.get("events"))[:110])
print("   the shape: ONE request that waits — no news means an empty answer and you ask again")

# 5 ── SSE: one connection, many messages, server → client only
show("5 SSE — GET /events  (a one-way stream; Last-Event-ID resumes it)")
def enrol_later():
    time.sleep(0.6); post("/jsonrpc", {"jsonrpc": "2.0", "id": 4, "method": "students.enrol", "params": {"name": "Yash", "class": "3A"}})
threading.Thread(target=enrol_later, daemon=True).start()
with urllib.request.urlopen(BASE + "/events", timeout=15) as r:      # no ?since → only NEW events
    lines, deadline = [], time.time() + 4
    while time.time() < deadline:
        line = r.readline().decode().rstrip("\n")
        if line: lines.append(line)
        if len([l for l in lines if l.startswith("data:")]) >= 1 and line == "": break
    for l in lines[:6]: print("   ", l if l else "(blank line = end of one message)")
print("   the shape: text/event-stream, id/event/data frames — and browsers resend Last-Event-ID to resume")
with urllib.request.urlopen(urllib.request.Request(BASE + "/events", headers={"Last-Event-ID": "0"}), timeout=15) as r:
    first = [r.readline().decode().rstrip() for _ in range(3)]
print("   resuming from id 0 replays history:", " | ".join(x for x in first if x))

# 6 ── WebSocket: one connection, both directions
show("6 WebSocket — GET /ws  (Upgrade: websocket)")
key = base64.b64encode(os.urandom(16)).decode()
s = socket.create_connection(("127.0.0.1", 8081), timeout=10)
s.sendall(("GET /ws HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
hs = b""
while b"\r\n\r\n" not in hs: hs += s.recv(1024)
print("   handshake:", hs.split(b"\r\n")[0].decode(), "·", [l.decode() for l in hs.split(b"\r\n") if b"Accept" in l][0])
def ws_send(sock, text):
    p = text.encode(); m = os.urandom(4)
    sock.sendall(bytes([0x81, 0x80 | len(p)]) + m + bytes(b ^ m[i % 4] for i, b in enumerate(p)))
def ws_recv(sock):
    h = sock.recv(2); n = h[1] & 0x7F
    if n == 126: n = struct.unpack(">H", sock.recv(2))[0]
    buf = b""
    while len(buf) < n: buf += sock.recv(n - len(buf))
    return buf.decode()
for msg in ("hello", "students"):
    ws_send(s, msg); print(f"   → {msg!r}   ← {ws_recv(s)[:90]}")
s.close()
print("   the shape: one socket, either side may speak at any time — chat, cursors, live dashboards")
print("\n✅ six shapes, one dataset — the difference is who starts, how often, and how much comes back")
