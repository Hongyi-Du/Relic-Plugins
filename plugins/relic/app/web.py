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
import signal
import socketserver
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from relic_core import __version__, i18n, platform_support, runner, wake
from relic_core.sessions import actor_for, all_sessions
from relic_core.store import OrgError, Store, data_home, person_language

from . import harness as harnesses
from . import hub as hubs
from . import explain, files, naming, prefs, views
from .processes import ProcessRegistry

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
         ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".woff2": "font/woff2"}
DEFAULT_PORT = 39321  # when taken (or reserved by Windows), the next free one; app.json records the port in use
VERSION = __version__  # the App ships with the plugin and carries its version
MANIFEST = {
    "name": "Relic", "short_name": "Relic", "description": "",
    "id": "/", "start_url": "/?source=pwa", "scope": "/", "display": "standalone", "display_override": ["window-controls-overlay"],
    "background_color": "#F9F8F6", "theme_color": "#F9F8F6",
    "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
}


def info_path():
    return data_home() / "app.json"


def atomic_json(path, value):
    """Publish complete private lifecycle records; readers never see half a token."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class LifecycleLock:
    """An atomic OS lease, released even after a crash; stale PID text never owns a lock.

    Keep the inode in place: unlinking a lock file lets old and new readers lock different files.
    The owner record is diagnostic only, so PID reuse cannot cause an unrelated process to be killed.
    """

    def __init__(self, name, timeout=20):
        self.path = data_home() / name
        self.timeout, self.handle = timeout, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        if self.handle.seek(0, os.SEEK_END) == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise RuntimeError("Another Relic App operation owns %s; try again shortly." % self.path.name) from None
                time.sleep(0.05)
        try:
            self.handle.seek(0)
            self.handle.truncate()
            self.handle.write(json.dumps({"pid": os.getpid(), "acquired": time.time()}).encode("utf-8"))
            self.handle.flush()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *args):
        if self.handle is not None:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def remove_own_info(app):
    """An exiting server can remove only the record it published, never a successor's."""
    try:
        current = json.loads(info_path().read_text(encoding="utf-8"))
        if current.get("pid") == os.getpid() and current.get("instance") == app.instance and current.get("token") == app.token:
            info_path().unlink()
    except (OSError, ValueError, AttributeError):
        pass


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
        hubs.LANG[0] = self.lang  # what the hub shows the person (states, turn notes) is in the page's language
        self.token = secrets.token_urlsafe(24)
        self.instance = secrets.token_hex(16)
        self.port = port
        self._stamps = {}
        self._orgs = None
        self.stopping = threading.Event()
        self.processes = ProcessRegistry()
        self.namer = naming.Namer(self.store, publish=self.bus.publish, processes=self.processes)
        self.explainer = explain.Explainer(self.store, publish=self.bus.publish, processes=self.processes)
        self.page_lang = ""
        self.installing = set()
        self.server = None
        self._shutdown_lock = threading.Lock()

    def request_shutdown(self):
        """Stop accepting work immediately; shutdown must run outside serve_forever's thread."""
        with self._shutdown_lock:
            if self.stopping.is_set():
                return
            self.stopping.set()
            self.hub.begin_shutdown()
            self.processes.begin_shutdown()
            self.bus.publish({"type": "shutdown"})
            threading.Thread(target=self.processes.shutdown, name="relic-app-jobs-stop", daemon=True).start()
            if self.server:
                threading.Thread(target=self.server.shutdown, name="relic-app-stop", daemon=True).start()

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
            self.store.send_as(org_id, member, [views.HUMAN],
                               i18n.t("api.deliver_failed", self.lang(), member=member, error=error))

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
                synced, note = naming.rename_session(seat, name, lambda s: views.locate(s)[2], self.lang())
            except Exception as error:
                note = i18n.t("api.rename_failed", self.lang(), error=error)
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
                                self.hub.status(org_id, member), (seat.get("carrier") or "").partition("/")[2],
                                self.lang())
        if not info["editable"]:
            raise OrgError(info["note"] or i18n.t("api.model_locked", self.lang()))
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

    # ---------------------------------------------------------------- seats whose sessions run outside the App
    @staticmethod
    def seat_options():
        """The choices for a member whose session runs in Claude Code or Codex itself (命令行 or 桌面版)."""
        return {"efforts": runner.EFFORTS, "claude_modes": runner.CLAUDE_MODES, "codex_sandboxes": runner.CODEX_SANDBOXES,
                "claude_models": runner.CLAUDE_MODELS}

    def add_seat(self, org_id, a):
        """A member whose session runs in Claude Code or Codex itself, on the command line or in the desktop app: model,
        effort, folder or its own git worktree, permission and environment variables. With edit, the member's
        configuration changes; with start, its first session starts now (the introduction turn)."""
        name = (a.get("name") or "").strip()
        if not name:
            raise OrgError(i18n.t("api.need_name", self.lang()))
        config = {k: str(a.get(k) or "").strip() for k in ("model", "effort", "folder", "environment", "permission")}
        config.update(harness=a.get("harness") or "claude-code", surface=a.get("surface") or "cli",
                      env=runner.parse_env(a.get("env") or ""))
        if config["harness"] not in ("claude-code", "codex") or config["surface"] not in ("cli", "gui"):
            raise OrgError(i18n.t("api.host_harness", self.lang()))
        config["folder"] = config["folder"] or str(Path.home())
        config["environment"] = config["environment"] if config["environment"] in ("local", "worktree") else "local"
        config["permission"] = runner.checked_permission(config)
        runner.checked_model(config)
        role = (a.get("role") or "").strip()
        if a.get("edit"):
            seat = self.store.get(org_id)["members"].get(name)
            if seat is None:
                raise OrgError("Unknown member " + name)
            self.store.set_config(org_id, name, config)
            if role and role != seat.get("role", ""):
                self.store.add_seat(org_id, name, role)
        else:
            self.store.add_seat(org_id, name, role, config)
            if a.get("start"):
                org = self.store.get(org_id)
                runner.start_turn(org_id, name, runner.introduction(org, name), new_session=True, open_after=True)
        self.bus.publish({"type": "org", "org": org_id})
        return {"member": name, "config": config}

    @staticmethod
    def sessions():
        """Sessions on this computer that can take a seat: Claude Code sessions, Codex threads, ChatGPT chats."""
        found, problems = all_sessions()
        return {"sessions": found[:300], "problems": problems}

    def bind(self, org_id, a):
        """An existing session takes a seat (a new member or an existing one), as it would by joining itself."""
        session, member = a.get("session") or {}, (a.get("member") or "").strip()
        if not member or not session.get("id") or not session.get("harness"):
            raise OrgError(i18n.t("api.pick_session", self.lang()))
        actor = actor_for(session)
        for other, name, _ in self.store.seats_of(actor):  # it keeps its other seats; one run in the App cannot
            if other["id"] != org_id and ((other["members"].get(name) or {}).get("config") or {}).get("surface") == "acp":
                raise OrgError(i18n.t("api.acp_one_seat", self.lang(), member=name, org=other["name"]))
        self.store.join(actor, org_id, member, (a.get("role") or "").strip())
        if session["harness"] == "chatgpt":  # a ChatGPT chat takes part only through Relic: make it wakeable
            self.store.set_config(org_id, member, runner.default_config("chatgpt"))
        self.bus.publish({"type": "org", "org": org_id})
        return {"member": member}

    def fresh(self, org_id, a):
        """A new session for a seat: role, tasks and protocols stay; the old session's private notes do not."""
        member = a["member"]
        org = self.store.get(org_id)
        config = (org["members"][member].get("config") or {})
        if config.get("surface") == "acp":
            self.hub.fresh(org_id, member)
        elif not config.get("harness") or config.get("surface") == "chat":
            raise OrgError(i18n.t("api.self_joined", self.lang(), member=member))
        else:
            runner.start_turn(org_id, member, runner.introduction(org, member), new_session=True, open_after=True)
        self.bus.publish({"type": "org", "org": org_id})
        return {"ok": True}

    def open_session(self, org_id, a):
        """Open a seat's session for the person: a terminal, or the Claude / Codex desktop app."""
        member = a["member"]
        seat = self.store.get(org_id)["members"][member]
        carrier = seat.get("carrier")
        if not carrier:
            raise OrgError(i18n.t("api.no_session", self.lang(), member=member))
        harness = seat.get("harness") or (seat.get("config") or {}).get("harness")
        if harness in ("chatgpt", "claude-chat"):
            raise OrgError(i18n.t("api.chat_member_chatgpt" if harness == "chatgpt" else "api.chat_member_claude",
                                  self.lang(), member=member))
        if (seat.get("config") or {}).get("surface") == "acp":
            raise OrgError(i18n.t("api.in_app", self.lang(), member=member))
        config = seat.get("config") if (seat.get("config") or {}).get("harness") == harness else {}
        session = carrier.split(":", 1)[1] if carrier.startswith("codex:") else carrier.split("/", 1)[0]
        state = runner.run_state(org_id, member) or {}
        cwd = state.get("cwd") or (config or {}).get("folder") or str(Path.home())
        runner.open_session(config or {}, session, harness, cwd)
        return {"ok": True}

    def unbind(self, org_id, a):
        """The seat's current session leaves it; the seat, its tasks and protocols stay."""
        member = a["member"]
        seat = self.store.get(org_id)["members"][member]
        if (seat.get("config") or {}).get("surface") == "acp":
            self.hub.stop(org_id, member)
        if seat.get("carrier"):
            self.store.unbind(seat["carrier"], org_id)  # its seats in other organizations stay
        self.bus.publish({"type": "org", "org": org_id})
        return {"ok": True}

    # ---------------------------------------------------------------- the organization model
    def set_cabinet(self, org_id, a):
        """The person marks an organization as the cabinet (secretariat), or unmarks it."""
        result = self.store.set_cabinet(org_id, bool(a.get("on", True)))
        self._changed_all()
        return result

    def set_leader(self, org_id, a):
        """The person gives an organization a new leader (at once; a member's request waits for approval)."""
        result = self.store.set_leader(org_id, (a.get("member") or "").strip())
        self._changed_all()
        return result

    def decide_request(self, org_id, a):
        """The person approves or denies a request kept in org_id (the cabinet, or the requester's organization)."""
        result = self.store.decide_request_as_human(org_id, a.get("request_id") or "", a.get("decision") or "",
                                                    a.get("note") or "")
        self._changed_all()
        threading.Thread(target=self._dispatch_all, daemon=True).start()  # the requester's message wakes it
        return result

    def close_group(self, org_id, a):
        """The person closes a subgroup."""
        result = self.store.close_group_as(org_id)
        self._changed_all()
        return result

    def _changed_all(self):
        self.bus.publish({"type": "orgs"})
        for org in self.store.list_orgs():
            self.bus.publish({"type": "org", "org": org["id"]})

    def _dispatch_all(self):
        for org in self.store.list_orgs():
            if org.get("status") == "active":
                self._dispatch(org["id"])

    def waiting(self, org_id, member):
        """A ChatGPT chat member's replies that wait to be forwarded (the oldest first)."""
        seat = self.store.get(org_id)["members"].get(member) or {}
        return {"waiting": seat.get(Store.WAITING) or [],
                "members": [n for n in self.store.get(org_id)["members"] if n != member]}

    def forward(self, org_id, a):
        """A ChatGPT chat member's reply, copied by the person in the ChatGPT window, becomes that member's message."""
        to = a.get("to") or []
        if isinstance(to, str):
            to = [t.strip() for t in to.split(",") if t.strip()]
        result = self.store.forward_reply(org_id, a["member"], to, (a.get("body") or "").strip())
        threading.Thread(target=self._dispatch, args=(org_id,), daemon=True).start()
        self.bus.publish({"type": "org", "org": org_id})
        return result if isinstance(result, dict) else {"ok": True}

    def lang(self):
        return prefs.load().get("lang") or self.page_lang or person_language()

    def set_parent(self, org_id, a):
        """The person places an organization under another one, or on its own (parent empty)."""
        result = self.store.set_parent(org_id, a.get("parent") or None)
        self._changed_all()  # ex officio seats may have moved in other organizations too
        return result

    def install(self, harness):
        if harness not in harnesses.HARNESSES:
            raise OrgError("Unknown harness " + harness)
        if harness in self.installing:
            return {"started": False}
        self.installing.add(harness)

        def run():
            try:
                code = harnesses.install(harness, lambda line: self.bus.publish(
                    {"type": "install", "id": harness, "line": line[-300:]}), processes=self.processes)
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
                lang = self.app.lang()
                manifest = dict(MANIFEST, description=i18n.t("page.manifest", lang), lang=i18n.resolve(lang))
                return self._send(200, json.dumps(manifest, ensure_ascii=False), "application/manifest+json")
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
            if api == ["lifecycle"]:
                if not secrets.compare_digest(self.headers.get("X-Relic-Token") or "", self.app.token):
                    return self._error(403, "missing token")
                return self._json({"app": "relic", "version": VERSION, "pid": os.getpid(), "port": self.app.port,
                                   "instance": self.app.instance,
                                   "state": "stopping" if self.app.stopping.is_set() else "running"})
            if api == ["platform"]:
                return self._json(platform_support.capabilities())
            if api == ["events"]:
                return self._events()
            if api == ["orgs"]:
                return self._json(views.org_list(self.app.store))
            if api == ["orgchart"]:
                return self._json(views.orgchart(self.app.store, self.app.hub, self.app.lang()))
            if api == ["harnesses"]:
                return self._json(harnesses.catalog())
            if api == ["seat-options"]:
                return self._json(self.app.seat_options())
            if api == ["sessions"]:
                return self._json(self.app.sessions())
            if api == ["prefs"]:
                return self._json(dict(prefs.load(), avatar=prefs.avatar_url(), data=str(data_home()),
                                       port=self.app.port, version=VERSION))
            if api == ["i18n"]:  # the word list of the page's language, and the languages there are
                if q.get("lang"):
                    self.app.page_lang = q["lang"][:20]
                code, words = i18n.strings(self.app.lang())
                return self._json({"lang": code, "languages": i18n.languages(), "strings": words})
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
        if rest == ["waiting"]:
            return self._json(self.app.waiting(org_id, q.get("member") or ""))
        if rest == ["workspace"]:
            return self._json(files.workspace(store, org_id, q.get("member") or ""))
        if rest == ["chat"]:
            kind = q.get("kind") or "group"
            return self._json(views.chat(store, org_id, kind, q.get("member"), int(q.get("limit") or 200), q.get("before"),
                                         lang=self.app.lang()))
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
            # how the seat's sessions start (for 改配置); the seat token stays on the server
            card["config"] = {k: v for k, v in (seat.get("config") or {}).items() if k not in ("seat_token", "session")}
            card["waiting_replies"] = len(seat.get(Store.WAITING) or [])
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
            if api == ["shutdown"]:
                if not secrets.compare_digest(str(a.get("instance") or ""), app.instance):
                    return self._error(409, "the Relic App instance changed")
                try:
                    return self._json({"stopping": True, "instance": app.instance})
                finally:
                    app.request_shutdown()
            if getattr(app, "stopping", None) and app.stopping.is_set():
                return self._error(503, "the Relic App is stopping")
            if api == ["platform"]:
                return self._json(platform_support.configure_capabilities(a))
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
                platform_support.open_external(str(target))
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
                if action == "parent":
                    return self._json(app.set_parent(org_id, a))
                if action == "cabinet":
                    return self._json(app.set_cabinet(org_id, a))
                if action == "leader":
                    return self._json(app.set_leader(org_id, a))
                if action == "request":
                    return self._json(app.decide_request(org_id, a))
                if action == "close":
                    return self._json(app.close_group(org_id, a))
                if action == "secretary":
                    hub.make_secretary(org_id, a["member"])
                    return self._json({"ok": True})
                if action == "seat":
                    return self._json(app.add_seat(org_id, a))
                if action == "bind":
                    return self._json(app.bind(org_id, a))
                if action == "fresh":
                    return self._json(app.fresh(org_id, a))
                if action == "open_session":
                    return self._json(app.open_session(org_id, a))
                if action == "unbind":
                    return self._json(app.unbind(org_id, a))
                if action == "forward":
                    return self._json(app.forward(org_id, a))
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
    """Open a normal browser window, where supported browsers can offer app installation."""
    import subprocess
    url = "http://127.0.0.1:%d/#install" % port
    exe = platform_support.browser_executable()
    if exe:
        try:
            subprocess.Popen([exe, "--new-window", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
        except OSError:
            exe = None  # an application removed since discovery: try the default browser
    if not exe:
        platform_support.open_external(url)
    return {"opened": url, "browser": exe or "default"}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"  # POSIX restarts may reuse our TIME_WAIT port; Windows keeps exclusive binds.

    def server_bind(self):
        # HTTPServer reverse-resolves its address here, which can block startup
        # while DNS is unavailable. This server only uses numeric loopback URLs.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


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
    app.server = server
    app.port = server.server_address[1]
    try:
        if write_info:
            atomic_json(info_path(), {"port": app.port, "pid": os.getpid(), "token": app.token,
                                      "instance": app.instance, "started": time.time(), "version": VERSION})
            atomic_json(data_home() / "app-port.json", {"port": app.port})
        threading.Thread(target=app.watch, name="relic-app-watch", daemon=True).start()
    except BaseException:
        app.stopping.set()
        server.server_close()
        if write_info:
            remove_own_info(app)
        raise
    return app, server


def main(port=DEFAULT_PORT):
    with LifecycleLock("app-server.lock", timeout=0):
        app, server = serve(port)
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: app.request_shutdown())
        try:
            server.serve_forever(poll_interval=0.1)
        finally:
            app.stopping.set()
            try:
                app.hub.shutdown()
            finally:
                try:
                    app.processes.shutdown()
                finally:
                    server.server_close()
                    remove_own_info(app)
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)
