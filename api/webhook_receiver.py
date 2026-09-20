"""Where the counter calls YOU back. (Lesson 11)   python3 api/webhook_receiver.py  → :9090"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        print("📣 webhook received:", json.loads(body or b"{}"), flush=True)
        self.send_response(204); self.end_headers()
    def log_message(self, *a): pass
print("📣 listening on http://127.0.0.1:9090/hook — register it: POST /v1/webhooks {\"url\":\"http://127.0.0.1:9090/hook\"}", file=sys.stderr)
HTTPServer(("127.0.0.1", 9090), H).serve_forever()
