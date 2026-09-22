"""One client, six hall passes — watch the header each scheme puts on the wire, and every 401 and 403. (Showcase)

    python3 api/auth_demo.py          # terminal 1
    python3 api/auth_client.py        # terminal 2
"""
import base64, hashlib, hmac, json, time, urllib.request, urllib.error, http.cookiejar
BASE = "http://127.0.0.1:8082"
def call(method, path, headers=None, body=None, opener=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={**({"Content-Type": "application/json"} if data else {}), **(headers or {})}, method=method)
    try:
        with (opener.open if opener else urllib.request.urlopen)(req, timeout=5) as r: return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), e.read().decode()
def show(label, res):
    st, h, b = res; extra = f"   WWW-Authenticate: {h['WWW-Authenticate']}" if "WWW-Authenticate" in h else ""
    b = json.loads(b) if b else {}
    what = b.get("error", {}).get("message") if "error" in b else (f"as {b['as']} ({b['role']}) via {b['via']} · {len(b['grades'])} grades" if "grades" in b else "")
    print(f"   {label:<46} → {st}  {what}{extra}")
def sec(t): print(f"\n── {t}")

sec("1 Basic — the pass you re-show at every door (user:password, base64, on EVERY request)")
show("no header", call("GET", "/basic/grades"))
cred = base64.b64encode(b"teacher:chalk").decode()
show(f"Authorization: Basic {cred[:10]}…", call("GET", "/basic/grades", {"Authorization": f"Basic {cred}"}))
show("wrong password", call("GET", "/basic/grades", {"Authorization": "Basic " + base64.b64encode(b"teacher:pen").decode()}))
print("   base64 is NOT encryption — Basic is only ever acceptable over HTTPS")

sec("2 API key — a program's pass; no person behind it (the counter's X-API-Key, lesson 06)")
show("no key", call("GET", "/apikey/grades"))
show("X-API-Key: hall-pass-123", call("GET", "/apikey/grades", {"X-API-Key": "hall-pass-123"}))
show("X-API-Key: made-up", call("GET", "/apikey/grades", {"X-API-Key": "made-up"}))
print("   an unknown key = we cannot tell who you are = 401 (strict); the lesson-06 counter says 403 — both are seen in the wild")

sec("3 Bearer token (opaque) — log in once, get a wristband, show the wristband")
st, h, b = call("POST", "/login", body={"user": "teacher", "password": "chalk"}); tok = json.loads(b)["token"]
print(f"   POST /login teacher/chalk                      → {st}  token {tok[:10]}… expires_in {json.loads(b)['expires_in']}")
show("no token", call("GET", "/token/grades"))
show(f"Authorization: Bearer {tok[:10]}…", call("GET", "/token/grades", {"Authorization": f"Bearer {tok}"}))
st, h, b = call("POST", "/login", body={"user": "teacher", "password": "chalk", "ttl": 1}); short = json.loads(b)["token"]; time.sleep(1.2)
show("a token issued with ttl=1, 1.2 s later", call("GET", "/token/grades", {"Authorization": f"Bearer {short}"}))
st, h, b = call("POST", "/login", body={"user": "student", "password": "pencil"}); stu = json.loads(b)["token"]
show("DELETE as student (valid token)", call("DELETE", "/token/grades", {"Authorization": f"Bearer {stu}"}))
print("   401 = who are you? · 403 = I know exactly who you are, and no · the server LOOKS UP each opaque token")

sec("4 JWT — a SIGNED wristband: the server verifies, it does not look anything up")
st, h, b = call("POST", "/login", body={"user": "teacher", "password": "chalk"}); jwt = json.loads(b)["jwt"]
hdr, pay, sig = jwt.split(".")
print(f"   header  {json.loads(base64.urlsafe_b64decode(hdr + '=='))}")
print(f"   payload {json.loads(base64.urlsafe_b64decode(pay + '=='))}   ← readable by anyone; never put secrets in it")
show(f"Authorization: Bearer {jwt[:14]}…", call("GET", "/jwt/grades", {"Authorization": f"Bearer {jwt}"}))
forged = base64.urlsafe_b64encode(json.dumps({**json.loads(base64.urlsafe_b64decode(pay + '==')), "role": "headmaster"}).encode()).rstrip(b"=").decode()
show("payload edited to role=headmaster, same signature", call("GET", "/jwt/grades", {"Authorization": f"Bearer {hdr}.{forged}.{sig}"}))
print("   the signature pins the payload; expiry is inside it (exp) — and a stolen JWT is valid until then, so keep them short")

sec("5 HMAC request signing — you sign the request itself (webhooks, AWS SigV4 style)")
ts = str(int(time.time()))
def sign(method, path, ts): return hmac.new(b"shared-secret-for-key-1", f"{method}\n{path}\n{ts}\n{hashlib.sha256(b'').hexdigest()}".encode(), hashlib.sha256).hexdigest()
show("unsigned", call("GET", "/hmac/grades"))
show(f"X-Key-Id key-1 · X-Timestamp {ts} · X-Signature {sign('GET','/hmac/grades',ts)[:8]}…", call("GET", "/hmac/grades", {"X-Key-Id": "key-1", "X-Timestamp": ts, "X-Signature": sign("GET", "/hmac/grades", ts)}))
show("same signature, path changed by an attacker", call("GET", "/hmac/grades?x=1", {"X-Key-Id": "key-1", "X-Timestamp": ts, "X-Signature": sign("GET", "/hmac/other", ts)}))
old = str(int(time.time()) - 900)
show("valid signature, 15-minute-old timestamp (replay)", call("GET", "/hmac/grades", {"X-Key-Id": "key-1", "X-Timestamp": old, "X-Signature": sign("GET", "/hmac/grades", old)}))
print("   the secret never travels; the signature covers method + path + time + body, so nothing can be altered or replayed")

sec("6 Session cookie — the browser's way: log in, the server sets an HttpOnly cookie, the browser sends it back")
jar = http.cookiejar.CookieJar(); opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
show("no cookie", call("GET", "/session/grades"))
st, h, b = call("POST", "/login", body={"user": "teacher", "password": "chalk"}, opener=opener)
print(f"   POST /login                                    → {st}  Set-Cookie: {h['Set-Cookie'][:14]}…; HttpOnly; SameSite=Lax")
show("GET with the cookie jar", call("GET", "/session/grades", opener=opener))
print("   HttpOnly = JavaScript cannot read it (XSS cannot steal it) · SameSite = other sites cannot ride it (CSRF)")

print("\n✅ six hall passes, one set of grades — who is asking, how do we know, and for how long")
