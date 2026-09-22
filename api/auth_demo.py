"""Six ways to show a hall pass — the same grades behind six authentication schemes. (Showcase: auth methods)

Zero dependencies. One resource, /<scheme>/grades, guarded six ways:

    /basic/grades     Authorization: Basic base64(user:password)      the pass you re-show at every door
    /apikey/grades    X-API-Key: hall-pass-123                        a program's pass, no person behind it
    /token/grades     Authorization: Bearer <opaque token>            a wristband from /login, looked up each time
    /jwt/grades       Authorization: Bearer <header.payload.sig>      a SIGNED wristband — nothing to look up
    /hmac/grades      X-Key-Id · X-Timestamp · X-Signature            you sign the request itself (webhooks, AWS)
    /session/grades   Cookie: sid=…  (HttpOnly)                       the browser's way
    /oauth/grades     Authorization: Bearer <token from POST /token>  OAuth 2.0 client_credentials — a program's own door

401 always carries a WWW-Authenticate challenge ("who are you?"); 403 is "I know you, and no" — try DELETE as a student.

    python3 api/auth_demo.py          # :8082
    python3 api/auth_client.py        # every header on the wire, every 401 and 403
"""
import base64, hashlib, hmac, json, secrets, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

USERS = {"teacher": {"password": "chalk", "role": "teacher"}, "student": {"password": "pencil", "role": "student"}}
API_KEYS = {"hall-pass-123": ("counter-bot", "teacher")}          # key → (who, role)
HMAC_SECRETS = {"key-1": b"shared-secret-for-key-1"}
JWT_SECRET = b"the-school-signing-secret"
TOKENS, SESSIONS = {}, {}                                          # opaque token → (user, role, exp) · sid → (user, role)
CLIENTS = {"report-bot": {"secret": "s3cr3t-bot", "scopes": {"grades:read"}}}   # OAuth clients: a PROGRAM's id + secret
OAUTH, REFRESH = {}, {}                                            # access token → (client, scope, exp) · refresh token → client
GRADES = [{"student": "Aarav", "subject": "maths", "grade": "A"}, {"student": "Sita", "subject": "maths", "grade": "A+"}]

def b64u(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def unb64u(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def jwt_encode(payload):
    h, p = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()), b64u(json.dumps(payload).encode())
    return f"{h}.{p}." + b64u(hmac.new(JWT_SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
def jwt_decode(tok):
    try:
        h, p, sig = tok.split(".")
    except ValueError: return None, "malformed token"
    good = b64u(hmac.new(JWT_SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(good, sig): return None, "bad signature"
    payload = json.loads(unb64u(p))
    if payload.get("exp", 0) < time.time(): return None, "expired"
    return payload, None

class Deny(Exception):
    def __init__(self, challenge, why): self.challenge, self.why = challenge, why

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def send(self, status, body=None, headers=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        if body is not None: self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)
    def body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except json.JSONDecodeError: return {}

    # ── one function per scheme: return (user, role) or raise Deny(challenge, why) ──
    def who_basic(self):
        a = self.headers.get("Authorization", "")
        if not a.startswith("Basic "): raise Deny('Basic realm="school"', "send Authorization: Basic base64(user:password)")
        try: user, pw = base64.b64decode(a[6:]).decode().split(":", 1)
        except Exception: raise Deny('Basic realm="school"', "malformed Basic credentials")
        u = USERS.get(user)
        if not u or not hmac.compare_digest(u["password"], pw): raise Deny('Basic realm="school"', "wrong user or password")
        return user, u["role"]
    def who_apikey(self):
        k = self.headers.get("X-API-Key")
        if k is None: raise Deny('ApiKey realm="school", header="X-API-Key"', "no X-API-Key header")
        if k not in API_KEYS: raise Deny('ApiKey realm="school", header="X-API-Key"', "unknown key — we cannot tell who you are")
        return API_KEYS[k]
    def bearer(self):
        a = self.headers.get("Authorization", "")
        if not a.startswith("Bearer "): raise Deny('Bearer realm="school"', "send Authorization: Bearer <token>")
        return a[7:]
    def who_token(self):
        t = self.bearer(); rec = TOKENS.get(t)
        if not rec: raise Deny('Bearer realm="school", error="invalid_token"', "unknown token")
        user, role, exp = rec
        if exp < time.time(): raise Deny('Bearer realm="school", error="invalid_token", error_description="expired"', "token expired")
        return user, role
    def who_jwt(self):
        payload, err = jwt_decode(self.bearer())
        if err: raise Deny(f'Bearer realm="school", error="invalid_token", error_description="{err}"', f"JWT {err}")
        return payload["sub"], payload["role"]
    def who_hmac(self):
        kid, ts, sig = (self.headers.get(h) for h in ("X-Key-Id", "X-Timestamp", "X-Signature"))
        ch = 'HMAC-SHA256 realm="school", headers="X-Key-Id X-Timestamp X-Signature"'
        if not (kid and ts and sig): raise Deny(ch, "sign the request: X-Key-Id, X-Timestamp, X-Signature")
        if kid not in HMAC_SECRETS: raise Deny(ch, "unknown key id")
        if abs(time.time() - float(ts)) > 300: raise Deny(ch, "timestamp outside the 5-minute replay window")
        canon = f"{self.command}\n{urlparse(self.path).path}\n{ts}\n{hashlib.sha256(b'').hexdigest()}"
        good = hmac.new(HMAC_SECRETS[kid], canon.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig): raise Deny(ch, "signature does not match — the request was altered or the secret is wrong")
        return f"key {kid}", "teacher"
    def who_oauth(self):
        t = self.bearer(); rec = OAUTH.get(t)
        if not rec: raise Deny('Bearer realm="school", error="invalid_token"', "unknown or expired access token — POST /token first")
        client, scope, exp = rec
        if exp < time.time(): raise Deny('Bearer realm="school", error="invalid_token", error_description="expired"', "access token expired")
        self.scope = scope
        return client, "client:" + scope
    def who_session(self):
        cookies = dict(c.strip().split("=", 1) for c in self.headers.get("Cookie", "").split(";") if "=" in c)
        rec = SESSIONS.get(cookies.get("sid", ""))
        if not rec: raise Deny('Cookie realm="school"', "no valid session cookie — POST /login first")
        return rec
    SCHEMES = {"basic": who_basic, "apikey": who_apikey, "token": who_token, "jwt": who_jwt, "hmac": who_hmac, "session": who_session, "oauth": who_oauth}

    def guarded(self):
        parts = [x for x in urlparse(self.path).path.split("/") if x]
        if len(parts) < 2 or parts[1] != "grades" or parts[0] not in self.SCHEMES:
            return self.send(404, {"error": "try /basic|apikey|token|jwt|hmac|session/grades"})
        try: user, role = self.SCHEMES[parts[0]](self)
        except Deny as d:                                              # 401: who are you? — with the challenge
            return self.send(401, {"error": {"code": "unauthenticated", "message": d.why}}, {"WWW-Authenticate": d.challenge})
        if self.command == "DELETE":                                    # 403: I know you, and no
            if role.startswith("client:") and "grades:write" not in role:      # OAuth: the SCOPE decides, not the person
                return self.send(403, {"error": "insufficient_scope", "error_description": f"token scope is '{self.scope}', DELETE needs grades:write"},
                                 {"WWW-Authenticate": 'Bearer realm="school", error="insufficient_scope", scope="grades:write"'})
            if role != "teacher" and not role.startswith("client:"): return self.send(403, {"error": {"code": "forbidden", "message": f"{user} is a {role}: may read grades, not delete them"}})
            return self.send(204)
        self.send(200, {"as": user, "role": role, "via": parts[0], "grades": GRADES})
    def do_GET(self): self.guarded()
    def do_DELETE(self): self.guarded()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/token": return self.token_endpoint()
        if path != "/login": return self.send(404, {"error": "POST /login or POST /token"})
        b = self.body(); u = USERS.get(b.get("user", ""))
        if not u or not hmac.compare_digest(u["password"], b.get("password", "")):
            return self.send(401, {"error": {"code": "unauthenticated", "message": "wrong user or password"}}, {"WWW-Authenticate": 'Basic realm="school"'})
        ttl = int(b.get("ttl", 3600)); now = time.time()
        tok, sid = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        TOKENS[tok] = (b["user"], u["role"], now + ttl); SESSIONS[sid] = (b["user"], u["role"])
        jwt = jwt_encode({"sub": b["user"], "role": u["role"], "iat": int(now), "exp": int(now + ttl)})
        self.send(200, {"token": tok, "jwt": jwt, "expires_in": ttl},
                  {"Set-Cookie": f"sid={sid}; HttpOnly; SameSite=Lax; Path=/"})

    # ── the OAuth 2.0 token endpoint (RFC 6749 §4.4 client_credentials, §6 refresh_token) ──
    def token_endpoint(self):
        if "application/x-www-form-urlencoded" not in self.headers.get("Content-Type", ""):   # OAuth speaks FORMS here, not JSON
            return self.send(400, {"error": "invalid_request", "error_description": "the token endpoint takes application/x-www-form-urlencoded"})
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()).items()}
        grant = form.get("grant_type")
        if grant in ("password", "implicit"):                          # the two grants the OAuth 2.1 draft removes
            return self.send(400, {"error": "unsupported_grant_type",
                                   "error_description": f"'{grant}' is not offered: people use authorization_code + PKCE, programs use client_credentials"})
        if grant == "refresh_token":
            client = REFRESH.pop(form.get("refresh_token", ""), None)
            if not client: return self.send(400, {"error": "invalid_grant", "error_description": "unknown or already-used refresh token"})
            return self.issue(client, "grades:read")
        if grant != "client_credentials":
            return self.send(400, {"error": "unsupported_grant_type", "error_description": "try grant_type=client_credentials or refresh_token"})
        cid, secret = form.get("client_id"), form.get("client_secret")
        a = self.headers.get("Authorization", "")
        if a.startswith("Basic "):                                      # RFC 6749 §2.3.1: client auth may also travel as Basic
            try: cid, secret = base64.b64decode(a[6:]).decode().split(":", 1)
            except Exception: pass
        c = CLIENTS.get(cid or "")
        if not c or not hmac.compare_digest(c["secret"], secret or ""):
            return self.send(401, {"error": "invalid_client"}, {"WWW-Authenticate": 'Basic realm="token endpoint"'})
        asked = set((form.get("scope") or "grades:read").split())
        if not asked <= c["scopes"]:
            return self.send(400, {"error": "invalid_scope", "error_description": f"{cid} may ask for {sorted(c['scopes'])}"})
        return self.issue(cid, " ".join(sorted(asked)))
    def issue(self, client, scope, ttl=900):
        tok, ref = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        OAUTH[tok] = (client, scope, time.time() + ttl); REFRESH[ref] = client
        self.send(200, {"access_token": tok, "token_type": "Bearer", "expires_in": ttl, "scope": scope, "refresh_token": ref},
                  {"Cache-Control": "no-store", "Pragma": "no-cache"})                 # RFC 6749 §5.1: never cache a token response

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
    print(f"🪪 six hall passes on http://127.0.0.1:{port} — POST /login · POST /token · GET /<basic|apikey|token|jwt|hmac|session|oauth>/grades", file=sys.stderr, flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
