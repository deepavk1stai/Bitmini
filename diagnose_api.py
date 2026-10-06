import json
import socket
import threading
import urllib.error
import urllib.request

from werkzeug.serving import make_server

from app import app, reset_runtime_state


def http_json(method, url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body}


reset_runtime_state(persist=True)
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
server = make_server("127.0.0.1", port, app)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{port}"
print("register", http_json("POST", f"{base}/api/register", {"name": "A", "username": "@a1", "dateOfBirth": "2000-01-01", "zipCode": "10001", "email": "a1@example.com", "password": "StrongPass123!"}))
print("public", http_json("GET", f"{base}/api/network/public"))
print("consensus", http_json("GET", f"{base}/api/consensus"))
print("login", http_json("POST", f"{base}/api/login", {"walletAddress": "B123", "method": "password", "secret": "x"}))
server.shutdown()
server.server_close()
thread.join(timeout=5)
