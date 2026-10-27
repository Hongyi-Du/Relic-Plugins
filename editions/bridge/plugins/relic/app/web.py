"""The Relic App's local server: the window's page, a JSON API over the organization store and the App's embedded
sessions, and a stream of changes (server-sent events).

Only this computer can reach it (127.0.0.1). A request must name this server in its Host header (no DNS rebinding),
and every write carries the App's token in X-Relic-Token. Only the App's own page can read that token, so other pages
open in the person's browser cannot send messages or approve actions in the organization.
"""
import json
import os
import queue
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from relic_core import __version__, runner, wake
from relic_core.store import OrgError, Store, data_home

from . import harness as harnesses
from . import hub as hubs
from . import explain, files, naming, prefs, views

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
         ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".woff2": "font/woff2"}
DEFAULT_PORT = 39321  # when taken (or reserved by Windows), the next free one; app.json records the port in use
VERSION = __version__  # the App ships with the plugin and carries its version
MANIFEST = {
    "name": "Relic", "short_name": "Relic", "description": "Relic 组织的聊天和概况",
    "id": "/", "start_url": "/?source=pwa", "scope": "/", "display": "standalone", "display_override": ["window-controls-overlay"],
    "background_color": "#F9F8F6", "theme_color": "#F9F8F6",
    "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
}


def info_path():
    return data_home() / "app.json"


class Bus:
    """Fan-out of events to every open event stream."""

    def __init__(self):
        self._subs = set()
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=2000)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            self._subs.discard(q)

    def publish(self, event):
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


class App:
    def __init__(self, port=DEFAULT_PORT, store=None):
        self.store = store or Store()
        self.bus = Bus()
        self.hub = hubs.Hub(publish=self.bus.publish, store=self.store)
        self.token = secrets.token_urlsafe(24)
        self.port = port
        self._stamps = {}
        self._orgs = None
        self.stopping = threading.Event()
        self.namer = naming.Namer(self.store, publish=self.bus.publish)
        self.explainer = explain.Explainer(self.store, publish=self.bus.publish)
        self.page_lang = ""
        self.installing = set()

    def watch(self):
        """Tell the page when an organization changed (any process may write the store)."""
        last_reap = time.time()
        while not self.stopping.wait(1.0):
            if time.time() - last_reap > 60:
                last_reap = time.time()
                try:
                    self.hub.reap()
                except Exception:
                    pass
            try:
                with self.store.db() as db:
                    stamps = {}
                    for table, column in (("events", "seq"), ("messages", "id"), ("activity", "id")):
                        for org_id, top in db.execute("SELECT org_id, MAX(%s) FROM %s GROUP BY org_id" % (column, table)):
                            stamps.setdefault(org_id, []).append(top or 0)
                    orgs = tuple(sorted(r[0] for r in db.execute("SELECT id FROM orgs")))
            except Exception:
                continue
            for org_id, stamp in stamps.items():
                key = tuple(stamp)
                if self._stamps.get(org_id) not in (None, key):
                    self.bus.publish({"type": "org", "org": org_id})
                self._stamps[org_id] = key
            if self._orgs is not None and orgs != self._orgs:
                self.bus.publish({"type": "orgs"})
            self._orgs = orgs

    # ---------------------------------------------------------------- writes
    def send(self, org_id, a):
        body = (a.get("body") or "").strip()
        reply_to = int(a["reply_to"]) if a.get("reply_to") else None
        to = a.get("to") or (None if reply_to else ["all"])  # a thread reply without recipients goes to its participants
        if isinstance(to, str):
            to = [to]
        channel = a.get("channel") if a.get("channel") in ("group", "private") else None
        if reply_to:
            mid = self.store.send_from_human(org_id, to, body, channel=channel, reply_to=reply_to)
        else:
            mid = self.store.send_from_human(org_id, to, body, channel=channel)
        with self.store.db() as db:
            row = db.execute("SELECT recipients FROM messages WHERE id=?", (mid,)).fetchone()
        sent_to = json.loads(row[0]) if row else (to or [])
        if len(sent_to) == 1 and self.hub.managed(org_id, sent_to[0]):
            threading.Thread(target=self._deliver, args=(org_id, sent_to[0], body, mid, reply_to), daemon=True).start()
        else:
            threading.Thread(target=self._dispatch, args=(org_id,), daemon=True).start()
        return {"id": mid, "to": sent_to}

    def _deliver(self, org_id, member, body, mid, reply_to=None):
        try:
            self.hub.deliver_human(org_id, member, body, mid, reply_to=reply_to)
        except Exception as error:
            self.store.send_as(org_id, member, [views.HUMAN], "（Relic App 没能把消息送进 %s 的会话：%s）" % (member, error))

    def rename(self, org_id, a):
        """The person renamed a member: shown everywhere in the App, and given to the member's own session."""
        member, name = a["member"], " ".join((a.get("name") or "").split())[:40]
        org = self.store.get(org_id)
        seat = org["members"].get(member)
        if seat is None:
            raise OrgError("Unknown member " + member)
        self.store.set_seat_fields(org_id, member, display_name=name)
        synced, note = (False, "")
        if name:
            try:
                synced, note = naming.rename_session(seat, name, lambda s: views.locate(s)[2])
            except Exception as error:
                note = "没能改到它自己的会话：%s" % error
        self.bus.publish({"type": "org", "org": org_id})
        return {"display": naming.display(self.store.get(org_id)["members"][member], member, self.lang()),
                "synced": synced, "note": note}

    def set_model(self, org_id, a):
        member = a["member"]
        model, effort = (a.get("model") or "").strip(), (a.get("effort") or "").strip()
        seat = self.store.get(org_id)["members"][member]
        config = dict(seat.get("config") or {})
        meta = views.session_meta(seat.get("carrier") or "") if seat.get("carrier") else {}
        surface = views.surface_of(seat, meta)
        info = views.model_info(seat.get("harness") or config.get("harness"), surface, config,
                                self.hub.status(org_id, member), (seat.get("carrier") or "").partition("/")[2])
        if not info["editable"]:
            raise OrgError(info["note"] or "这个成员的模型不能在 Relic App 里改。")
        if info["applies"] == "now":
            result = self.hub.set_model(org_id, member, model, effort)
        else:
            if model:
                config["model"] = model
            if effort:
                config["effort"] = effort
            runner.checked_model(config)
            self.store.set_config(org_id, member, config)
            result = {"model": config.get("model", ""), "effort": config.get("effort", ""), "applied": "next"}
        self.bus.publish({"type": "org", "org": org_id})
        return result

    def lang(self):
        return prefs.load().get("lang") or self.page_lang or "zh-CN"

    def install(self, harness):
        if harness not in harnesses.HARNESSES:
            raise OrgError("Unknown harness " + harness)
        if harness in self.installing:
            return {"started": False}
        self.installing.add(harness)

        def run():
            try:
                code = harnesses.install(harness, lambda line: self.bus.publish(
                    {"type": "install", "id": harness, "line": line[-300:]}))
            except Exception as error:
                self.bus.publish({"type": "install", "id": harness, "line": str(error)})
                code = 1
            finally:
                self.installing.discard(harness)
            self.bus.publish({"type": "install", "id": harness, "done": code})
        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    def _dispatch(self, org_id):
        try:
            wake.dispatch(self.store, org_id)
        except Exception:
            pass

    def turn(self, org_id, a):
        """A wake-up for a seat the App runs (relic_core.runner.start_turn hands surface=acp seats here)."""
        member = a["member"]
        origin = {"kind": "wake", "wake_from": a.get("wake_from") or [], "hop": a.get("wake_hop") or 0}

        def run():
            try:
                self.hub.prompt(org_id, member, a.get("prompt") or "", origin)
            except Exception as error:
                if origin["wake_from"]:
                    wake.finish(self.store, org_id, member, "Relic App could not start the turn: %s" % error)
        threading.Thread(target=run, daemon=True).start()
        return {"accepted": True}


class Handler(BaseHTTPRequestHandler):
    server_version = "RelicApp/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    @property
    def app(self):
        return self.server.app

    # ---------------------------------------------------------------- plumbing
    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        return host in ("127.0.0.1:%d" % self.app.port, "localhost:%d" % self.app.port)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _error(self, code, text):
        self._json({"error": text}, code)

    MAX_BODY = 8 * 1024 * 1024

    def _body(self):
        """The request's JSON body. Read before any answer, refusals included: the connection is kept open for the
        next request, which an unread body would corrupt."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > self.MAX_BODY:
            self.close_connection = True
            return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _route(self):
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
        query = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        return parts, query

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "wrong host")
        parts, q = self._route()
        try:
            if not parts or parts == ["index.html"]:
                page = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", self.app.token)
                return self._send(200, page, TYPES[".html"])
            if parts == ["manifest.webmanifest"]:
                return self._send(200, json.dumps(MANIFEST, ensure_ascii=False), "application/manifest+json")
            if parts == ["sw.js"]:
                return self._send(200, (STATIC / "sw.js").read_bytes(), TYPES[".js"], {"Service-Worker-Allowed": "/"})
            if parts[0] == "static" and len(parts) >= 2:
                path = (STATIC / "/".join(parts[1:])).resolve()
                if STATIC.resolve() not in path.parents or not path.is_file():
                    return self._error(404, "not found")
                return self._send(200, path.read_bytes(), TYPES.get(path.suffix, "application/octet-stream"))
            if parts[0] != "api":
                return self._error(404, "not found")
            api = parts[1:]
            if api == ["ping"]:
                return self._json({"app": "relic", "version": VERSION, "pid": os.getpid()})
            if api == ["events"]:
                return self._events()
            if api == ["orgs"]:
                return self._json(views.org_list(self.app.store))
            if api == ["harnesses"]:
                return self._json(harnesses.catalog())
            if api == ["prefs"]:
                return self._json(dict(prefs.load(), avatar=prefs.avatar_url(), data=str(data_home()),
                                       port=self.app.port, version=VERSION))
            if api and api[0] == "avatar":
                found = prefs.avatar_file(*api[1:3]) if len(api) == 3 else prefs.avatar_file()
                if not found:
                    return self._error(404, "no avatar")
                return self._send(200, found.read_bytes(), TYPES.get(found.suffix, "image/png"))
            if api[:1] == ["fs"] and len(api) == 2:
                store = self.app.store
                try:
                    if api[1] == "list":
                        return self._json(files.listdir(store, q.get("path") or ""))
                    if api[1] == "read":
                        return self._json(files.read(store, q.get("path") or ""))
                    if api[1] == "raw":
                        body, ctype = files.raw(store, q.get("path") or "")
                        return self._send(200, body, ctype)
                except PermissionError as error:
                    return self._error(403, str(error))
            if len(api) >= 2 and api[0] == "org":
                return self._org_get(api[1], api[2:], q)
            return self._error(404, "not found")
        except OrgError as error:
            return self._error(400, str(error))
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as error:
            return self._error(500, "%s: %s" % (type(error).__name__, error))

    def _org_get(self, org_id, rest, q):
        store, hub = self.app.store, self.app.hub
        if not rest:
            if q.get("lang"):
                self.app.page_lang = q["lang"][:20]
            lang = self.app.lang()
            if prefs.load().get("auto_names"):
                self.app.namer.ensure(org_id, lang)
            return self._json(views.snapshot(store, org_id, hub, lang))
        if rest in (["convo"], ["step"]):
            seat = store.get(org_id)["members"].get(q.get("member") or "")
            if not seat or not seat.get("carrier"):
                return self._json({"steps": [], "total": 0, "missing": True})
            if rest == ["step"]:
                return self._json(views.step(seat["carrier"], q.get("i") or 0))
            return self._json(views.convo(seat["carrier"]))
        if rest == ["thread"]:
            return self._json(views.thread(store, org_id, q.get("root") or 0))
        if rest == ["workspace"]:
            return self._json(files.workspace(store, org_id, q.get("member") or ""))
        if rest == ["chat"]:
            kind = q.get("kind") or "group"
            return self._json(views.chat(store, org_id, kind, q.get("member"), int(q.get("limit") or 200), q.get("before")))
        if rest == ["transcript"]:
            seat = store.get(org_id)["members"].get(q.get("member") or "")
            if not seat or not seat.get("carrier"):
                return self._json({"steps": [], "total": 0, "missing": True})
            before = q.get("before")
            return self._json(views.transcript(seat["carrier"], int(q.get("limit") or 300),
                                               int(before) if before not in (None, "") else None, q.get("full") == "1"))
        if rest == ["document"]:
            doc = (store.get(org_id).get("documents") or {}).get(q.get("key") or "")
            return self._json(dict(doc, key=q.get("key")) if doc else {"missing": True})
        if rest == ["live"]:
            return self._json({"items": hub.items(org_id, q.get("member"), int(q.get("after") or 0)),
                               "status": hub.status(org_id, q.get("member"))})
        if len(rest) == 2 and rest[0] == "member":
            org = store.get(org_id)
            name = rest[1]
            seat = org["members"].get(name)
            if not seat:
                return self._error(404, "no such member")
            acts = views.latest_activity(store, org_id)
            card = views.member_view(store, org, name, seat, hub, acts.get(name), 0, views.secretary_of(org),
                                     lang=self.app.lang())
            card["recent"] = views.recent_activity(store, org_id, name)
            return self._json(card)
        return self._error(404, "not found")

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.app.bus.subscribe()
        try:
            self.wfile.write(b": relic\n\n")
            self.wfile.flush()
            while not self.app.stopping.is_set():
                try:
                    event = q.get(timeout=15)
                    data = "data: %s\n\n" % json.dumps(event, ensure_ascii=False)
                except queue.Empty:
                    data = ": keep-alive\n\n"
                self.wfile.write(data.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.app.bus.unsubscribe(q)
            self.close_connection = True

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        a = self._body()
        if a is None:
            return self._error(413, "request too large")
        if not self._host_ok():
            return self._error(403, "wrong host")
        if not secrets.compare_digest(self.headers.get("X-Relic-Token") or "", self.app.token):
            return self._error(403, "missing token")
        parts, _ = self._route()
        app, store, hub = self.app, self.app.store, self.app.hub
        try:
            api = parts[1:] if parts and parts[0] == "api" else []
            if api == ["orgs"]:
                org = store.found(a["name"], a.get("purpose", ""), a.get("governance") or "leader")
                return self._json({"org_id": org["id"]})
            if len(api) == 2 and api[0] == "permission":
                return self._json(hub.decide(api[1], a.get("option")))
            if api == ["prefs"]:
                saved = prefs.save(a)
                app.bus.publish({"type": "prefs"})
                return self._json(saved)
            if api == ["avatar"]:
                if a.get("org"):
                    store.get(a["org"])["members"][a["member"]]  # a real seat
                prefs.save_avatar(a.get("data") or "", a.get("org"), a.get("member"))
                app.bus.publish({"type": "org", "org": a["org"]} if a.get("org") else {"type": "prefs"})
                return self._json({"avatar": prefs.avatar_url(a.get("org"), a.get("member"))})
            if len(api) == 3 and api[0] == "harnesses" and api[2] == "install":
                return self._json(app.install(api[1]))
            if api == ["fs", "open"]:
                try:
                    return self._json(files.open_path(store, a.get("path") or ""))
                except PermissionError as error:
                    return self._error(403, str(error))
            if api == ["install-window"]:
                return self._json(open_install_window(app.port))
            if api == ["open"]:
                target = {"data": data_home(), "logs": data_home() / "runs"}.get(a.get("what"), data_home())
                if os.name == "nt":
                    os.startfile(str(target))
                return self._json({"opened": str(target)})
            if len(api) >= 3 and api[0] == "org":
                org_id, action = api[1], api[2]
                if action == "send":
                    return self._json(app.send(org_id, a))
                if action == "turn":
                    return self._json(app.turn(org_id, a))
                if action == "members":
                    return self._json(hub.create_member(org_id, a["name"].strip(), a.get("role", ""), a["harness"],
                                                        a.get("model", ""), a.get("mode", ""), a.get("folder", ""),
                                                        bool(a.get("secretary"))))
                if action == "secretary":
                    hub.make_secretary(org_id, a["member"])
                    return self._json({"ok": True})
                if action == "plain":
                    return self._json(app.explainer.plain(org_id, [int(i) for i in a.get("ids") or []][:200], app.lang()))
                if action == "digest":
                    return self._json(app.explainer.digest(org_id, app.lang(), bool(a.get("refresh"))))
                if action == "rename":
                    return self._json(app.rename(org_id, a))
                if action == "model":
                    return self._json(app.set_model(org_id, a))
                if action == "auto_wake":
                    store.set_auto_wake(org_id, bool(a.get("on")))
                    return self._json({"ok": True})
                if action == "cancel":
                    hub.cancel(org_id, a["member"])
                    return self._json({"ok": True})
                if action == "trajectory_answer":
                    return self._json(store.answer_trajectory_as_human(org_id, a["request_id"], a["decision"],
                                                                       a.get("note", ""), a.get("redact", True)))
            return self._error(404, "not found")
        except (KeyError, OrgError, RuntimeError, ValueError) as error:
            return self._error(400, str(error))
        except Exception as error:
            return self._error(500, "%s: %s" % (type(error).__name__, error))


def open_install_window(port):
    """A normal Edge window on the App, where Edge offers to install it as an application (its own window, no
    system title bar). App windows started with --app cannot offer that."""
    import shutil
    import subprocess
    url = "http://127.0.0.1:%d/#install" % port
    candidates = [shutil.which("msedge")]
    for base in (os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")):
        if base:
            candidates.append(str(Path(base) / "Microsoft/Edge/Application/msedge.exe"))
    exe = next((c for c in candidates if c and Path(c).is_file()), None)
    if exe:
        subprocess.Popen([exe, "--new-window", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
    elif os.name == "nt":
        os.startfile(url)
    return {"opened": url, "browser": exe or "default"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def bind(port):
    """A server on `port`, or on one of the next few ports, or on any free port (port 0 asks for any)."""
    candidates = [port + i for i in range(10)] + [0] if port else [0]
    for candidate in candidates:
        try:
            return Server(("127.0.0.1", candidate), Handler)
        except OSError as error:
            failure = error
    raise failure


def serve(port=DEFAULT_PORT, store=None, write_info=True):
    app = App(port=port, store=store)
    server = bind(port)
    server.app = app
    app.port = server.server_address[1]
    threading.Thread(target=app.watch, name="relic-app-watch", daemon=True).start()
    if write_info:
        info_path().parent.mkdir(parents=True, exist_ok=True)
        info_path().write_text(json.dumps({"port": app.port, "pid": os.getpid(), "token": app.token,
                                           "started": time.time(), "version": VERSION}), encoding="utf-8")
    return app, server


def main(port=DEFAULT_PORT):
    app, server = serve(port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        app.stopping.set()
        app.hub.shutdown()
        try:
            info = json.loads(info_path().read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid():
                info_path().unlink()
        except (OSError, ValueError):
            pass
