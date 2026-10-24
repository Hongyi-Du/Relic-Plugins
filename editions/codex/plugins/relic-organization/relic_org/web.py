from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .store import OrgError


def make_server(service):
    assets = Path(__file__).resolve().parents[1] / "assets"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data, mime="application/json; charset=utf-8"):
            raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            host = "127.0.0.1:" + str(self.server.server_port)
            origin = self.headers.get("Origin")
            return (self.headers.get("Host") == host and (origin is None or origin == "http://" + host)
                    and secrets.compare_digest(self.headers.get("X-Relic-Token", ""), service.token))

        def do_GET(self):
            route = urlsplit(self.path).path
            files = {"/": ("panel.html", "text/html; charset=utf-8"),
                     "/panel.js": ("panel.js", "text/javascript; charset=utf-8"),
                     "/panel.css": ("panel.css", "text/css; charset=utf-8"),
                     "/icon.svg": ("icon.svg", "image/svg+xml")}
            if route in files:
                filename, mime = files[route]
                self.respond(200, (assets / filename).read_bytes(), mime)
            elif route == "/api/state":
                if not self.authorized():
                    return self.respond(403, {"error": "Open the panel URL returned by org_panel."})
                discovery = service.discover() if "discover=1" in urlsplit(self.path).query or not service.inventory else {"transport": "desktop", "sessions": service.inventory}
                self.respond(200, {"discovery": discovery, "organizations": service.store.list(),
                                  "caller_session": service.actor, "data_path": str(service.store.path.parent)})
            else:
                self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return self.respond(403, {"error": "Panel authorization required."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 256000:
                    raise OrgError("Invalid request size.")
                body = json.loads(self.rfile.read(length))
                route = urlsplit(self.path).path
                if route == "/api/create":
                    result = service.create(body)
                elif route == "/api/control":
                    result = service.store.human_control(body["org_id"], body["operation"], body.get("value"))
                elif route == "/api/message":
                    message = service.store.execute(body["org_id"], "human", "message_send", {
                        "body": body["body"], "recipients": body["recipients"], "idempotency_key": body["idempotency_key"]})
                    result = service.deliver(body["org_id"], message["id"])
                elif route == "/api/document":
                    result = service.store.execute(body["org_id"], "human", "document_write", body["data"])
                else:
                    return self.respond(404, {"error": "Not found"})
                self.respond(200, result)
            except (OrgError, KeyError, ValueError, TypeError) as error:
                self.respond(400, {"error": str(error)})
            except Exception as error:
                self.respond(500, {"error": "Operation failed: " + type(error).__name__})
    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)
