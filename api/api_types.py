"""The same five students, served through SIX different API shapes. (Showcase: API types)

Zero dependencies — one stdlib HTTP server. Every shape answers about the SAME data, so you
can compare the wire, not the domain:

    REST          GET  /v1/students?class=3A      → the counter with labelled cabinets
    JSON-RPC      POST /jsonrpc                   → "do this thing", called by name
    GraphQL-lite  POST /graphql                   → you write the exact shape you want back
    Long polling  GET  /poll?since=N              → the clerk holds your question until there is news
    SSE           GET  /events                    → the loudspeaker: a one-way stream of events
    WebSocket     GET  /ws  (Upgrade)             → the open phone line, both directions

    python3 api/api_types.py          # serves http://127.0.0.1:8081
    python3 api/types_client.py       # exercises all six and prints every byte
"""
import base64, hashlib, json, os, struct, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STUDENTS = [
    {"id": 1, "name": "Aarav", "class": "3A", "grade": "A"},
    {"id": 2, "name": "Sita",  "class": "3A", "grade": "A+"},
    {"id": 3, "name": "Kabir", "class": "3A", "grade": "B+"},
    {"id": 4, "name": "Meera", "class": "3B", "grade": "A"},
    {"id": 5, "name": "Rohan", "class": "3B", "grade": "B"},
]
EVENTS = []                       # append-only log: every enrolment, for polling / SSE / WS
NEW = threading.Condition()       # long polling waits on this instead of sleeping in a loop
WS_MAGIC = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"   # RFC 6455's handshake constant

def enrol(name, cls, grade="C"):
    s = {"id": len(STUDENTS) + 1, "name": name, "class": cls, "grade": grade}
    STUDENTS.append(s)
    with NEW:
        EVENTS.append({"seq": len(EVENTS) + 1, "event": "student.created", "student": s})
        NEW.notify_all()                                   # wake every long-poll and stream
    return s

def pick(obj, fields):
    """GraphQL-lite: return only the fields that were asked for (the whole point of GraphQL)."""
    return {f: obj[f] for f in fields if f in obj}

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): print(f"   · {self.command} {self.path}", file=sys.stderr, flush=True)

    def send_json(self, status, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)

    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except json.JSONDecodeError: return None

    # ── request/response shapes ────────────────────────────────────────────────
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/v1/students":                                   # 1 REST
            rows = [s for s in STUDENTS if s["class"] == q["class"][0]] if "class" in q else STUDENTS
            return self.send_json(200, {"items": rows, "count": len(rows)})
        if u.path == "/poll":                                          # 4 long polling
            since = int(q.get("since", ["0"])[0]); wait = min(float(q.get("wait", ["10"])[0]), 25)
            deadline = time.time() + wait
            with NEW:
                while len(EVENTS) <= since and time.time() < deadline:
                    NEW.wait(timeout=max(0.05, deadline - time.time()))
                fresh = EVENTS[since:]
            # no news before the deadline → an honest empty answer, and the client asks again
            return self.send_json(200, {"events": fresh, "cursor": since + len(fresh)})
        if u.path == "/events":                                        # 5 server-sent events
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive"); self.end_headers()
            # where to resume from: the browser sends Last-Event-ID automatically on reconnect
            resume = self.headers.get("Last-Event-ID") or q.get("since", [None])[0]
            sent = int(resume) if resume is not None else len(EVENTS)   # default: only what happens NEXT
            try:
                for _ in range(40):                                     # demo: ~8 s of stream
                    with NEW:
                        NEW.wait(timeout=0.2); fresh = EVENTS[sent:]; sent = len(EVENTS)
                    for e in fresh:                                     # the SSE frame: id/event/data
                        self.wfile.write(f"id: {e['seq']}\nevent: {e['event']}\ndata: {json.dumps(e['student'])}\n\n".encode())
                        self.wfile.flush()
                    else:
                        self.wfile.write(b": keep-alive\n\n"); self.wfile.flush()   # a comment keeps proxies happy
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if u.path == "/ws":                                            # 6 websocket upgrade
            return self.websocket()
        self.send_json(404, {"error": "no such shape — try /v1/students, /jsonrpc, /graphql, /poll, /events, /ws"})

    def do_POST(self):
        u = urlparse(self.path); b = self.body()
        if b is None: return self.send_json(400, {"error": "invalid JSON"})
        if u.path == "/jsonrpc":                                       # 2 JSON-RPC 2.0
            mid, method, params = b.get("id"), b.get("method"), b.get("params", {})
            if method == "students.list":
                rows = [s for s in STUDENTS if s["class"] == params["class"]] if "class" in params else STUDENTS
                return self.send_json(200, {"jsonrpc": "2.0", "id": mid, "result": rows})
            if method == "students.enrol":
                return self.send_json(200, {"jsonrpc": "2.0", "id": mid, "result": enrol(params["name"], params["class"], params.get("grade", "C"))})
            return self.send_json(200, {"jsonrpc": "2.0", "id": mid,     # errors are DATA, not a 500
                                        "error": {"code": -32601, "message": f"Method not found: {method}"}})
        if u.path == "/graphql":                                        # 3 GraphQL-lite
            query = (b.get("query") or "").replace("\n", " ")
            if "students" not in query:
                return self.send_json(200, {"errors": [{"message": "only the 'students' field exists here"}]})
            inside = query[query.find("{", query.find("students")) + 1: query.rfind("}")]
            fields = [w for w in inside.replace(",", " ").split() if w]     # exactly the fields asked for
            return self.send_json(200, {"data": {"students": [pick(s, fields) for s in STUDENTS]}})
        self.send_json(404, {"error": "no such shape"})

    # ── the websocket handshake and one frame each way (RFC 6455, the short version) ──
    def websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key: return self.send_json(400, {"error": "not a WebSocket upgrade"})
        accept = base64.b64encode(hashlib.sha1(key.encode() + WS_MAGIC).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept); self.end_headers()
        try:
            while True:
                msg = self.ws_recv()
                if msg is None: break
                if msg == "students":
                    self.ws_send(json.dumps({"students": [s["name"] for s in STUDENTS]}))
                else:
                    self.ws_send(json.dumps({"echo": msg, "at": round(time.time(), 3)}))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def ws_recv(self):
        hdr = self.rfile.read(2)
        if len(hdr) < 2: return None
        opcode, masked, length = hdr[0] & 0x0F, hdr[1] & 0x80, hdr[1] & 0x7F
        if opcode == 0x8: return None                                   # close frame
        if length == 126: length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127: length = struct.unpack(">Q", self.rfile.read(8))[0]
        mask = self.rfile.read(4) if masked else b"\0\0\0\0"            # clients MUST mask
        data = bytearray(self.rfile.read(length))
        for i in range(len(data)): data[i] ^= mask[i % 4]
        return data.decode("utf-8", "replace")

    def ws_send(self, text):
        payload = text.encode()
        frame = bytearray([0x81])                                       # FIN + text frame
        n = len(payload)
        if n < 126: frame.append(n)
        elif n < 1 << 16: frame.append(126); frame += struct.pack(">H", n)
        else: frame.append(127); frame += struct.pack(">Q", n)
        self.wfile.write(bytes(frame) + payload); self.wfile.flush()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    print(f"🔀 six API shapes on http://127.0.0.1:{port} — REST /v1/students · JSON-RPC /jsonrpc · "
          f"GraphQL /graphql · long poll /poll · SSE /events · WebSocket /ws", file=sys.stderr, flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
