import os
import secrets

root = "/opt/clinistry-token"
os.makedirs(root, mode=0o700, exist_ok=True)

service = r'''#!/usr/bin/env python3
import base64, hashlib, hmac, json, re, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LK = "/opt/livekit/livekit.yaml"
CODE = "/opt/clinistry-token/test_code"

def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

def credentials():
    text = open(LK, encoding="utf-8").read()
    match = re.search(r"(?ms)^keys:\s*\n\s+([^\s:]+):\s*([^\s#]+)", text)
    if not match:
        raise RuntimeError("LiveKit credentials unavailable")
    return match.group(1), match.group(2).strip('"\'')

def jwt(api_key, secret, identity, name, room):
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": api_key, "sub": identity, "name": name,
        "nbf": now - 5, "exp": now + 7200,
        "video": {"roomJoin": True, "room": room, "canPublish": True, "canSubscribe": True}
    }
    signing = b64(json.dumps(header, separators=(",", ":")).encode()) + "." + b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = b64(hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest())
    return signing + "." + signature

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        if self.path != "/api/token":
            return self.send_json(404, {"error": "Not found"})
        try:
            length = min(int(self.headers.get("content-length", "0")), 4096)
            data = json.loads(self.rfile.read(length))
            name = str(data.get("name", "")).strip()[:80]
            room = str(data.get("room", "")).strip().upper()[:40]
            expected = open(CODE, encoding="utf-8").read().strip()
            if len(name) < 2 or not hmac.compare_digest(room, expected):
                return self.send_json(403, {"error": "The test visit code is invalid."})
            api_key, secret = credentials()
            identity = re.sub(r"[^A-Za-z0-9_-]", "-", name) + "-" + uuid.uuid4().hex[:8]
            token = jwt(api_key, secret, identity, name, room)
            self.send_json(200, {"token": token, "serverUrl": "wss://video.clinistryhealth.com"})
        except Exception:
            self.send_json(500, {"error": "Unable to create the test-room token."})

ThreadingHTTPServer(("127.0.0.1", 7890), Handler).serve_forever()
'''

with open(root + "/server.py", "w", encoding="utf-8") as f:
    f.write(service)
os.chmod(root + "/server.py", 0o700)

alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
code = "TEST-" + "".join(secrets.choice(alphabet) for _ in range(6))
with open(root + "/test_code", "w", encoding="utf-8") as f:
    f.write(code + "\n")
os.chmod(root + "/test_code", 0o600)

unit = '''[Unit]
Description=Clinistry fictional-patient test token service
After=network-online.target livekit-docker.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/clinistry-token/server.py
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target
'''
with open("/etc/systemd/system/clinistry-test-token.service", "w", encoding="utf-8") as f:
    f.write(unit)

caddy_path = "/opt/livekit/caddy.yaml"
caddy = open(caddy_path, encoding="utf-8").read()
if "video_internal:" not in caddy:
    http_app = '''apps:
  http:
    servers:
      video_internal:
        listen: ["127.0.0.1:8080"]
        routes:
          - match:
              - path: ["/api/token"]
            handle:
              - handler: reverse_proxy
                upstreams:
                  - dial: "127.0.0.1:7890"
          - handle:
              - handler: reverse_proxy
                upstreams:
                  - dial: "127.0.0.1:7880"
  tls:
'''
    if "apps:\n  tls:\n" not in caddy:
        raise RuntimeError("Unexpected Caddy configuration")
    caddy = caddy.replace("apps:\n  tls:\n", http_app, 1)
    caddy = caddy.replace('dial: ["localhost:7880"]', 'dial: ["localhost:8080"]', 1)
    with open(caddy_path, "w", encoding="utf-8") as f:
        f.write(caddy)

print(code)
