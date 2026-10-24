import contextlib
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid


class OrgError(ValueError):
    pass


def uid(prefix):
    return prefix + "_" + uuid.uuid4().hex[:16]


def now():
    return datetime.now(timezone.utc).isoformat()


def data_home():
    return Path(os.getenv("RELIC_ORG_HOME", str(Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "relic-organization")))


def digest(tool, arguments):
    if tool in ("exec_command", "Bash"):
        tool = "Bash"
        arguments = dict(arguments)
        command = arguments.pop("cmd", arguments.get("command", ""))
        arguments["command"] = command
    return hashlib.sha256(json.dumps([tool, arguments], sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def short_tool(tool):
    return tool.rsplit("__", 1)[-1] if tool.startswith("mcp__") else tool


def matches(rule, actor, tool, arguments):
    names = [tool, short_tool(tool)]
    if tool in ("exec_command", "Bash"):
        names += ["Bash", "exec_command"]
    if not any(fnmatch.fnmatchcase(n, pattern) for n in names for pattern in rule["tools"]):
        return False
    if rule.get("members") and actor not in rule["members"]:
        return False
    body = json.dumps(arguments, ensure_ascii=False, sort_keys=True).casefold()
    if rule.get("input_contains") and not all(s.casefold() in body for s in rule["input_contains"]):
        return False
    for path, expected in rule.get("argument_equals", {}).items():
        value = arguments
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if value != expected:
            return False
    return True


def validate_rules(rules, members):
    if not isinstance(rules, list) or not rules:
        raise OrgError("Executable protocols need at least one structured rule; prose alone cannot block tools.")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("effect") not in ("deny", "require_peer_review"):
            raise OrgError("Rule effect must be deny or require_peer_review.")
        if not isinstance(rule.get("tools"), list) or not rule["tools"] or not all(isinstance(x, str) and x for x in rule["tools"]):
            raise OrgError("Each rule needs nonempty tool glob patterns.")
        if set(rule) - {"effect", "tools", "members", "input_contains", "argument_equals", "reason"}:
            raise OrgError("Unknown rule field.")
        if not isinstance(rule.get("input_contains", []), list) or not all(isinstance(x, str) and x for x in rule.get("input_contains", [])):
            raise OrgError("input_contains must be a list of nonempty strings.")
        if not isinstance(rule.get("argument_equals", {}), dict):
            raise OrgError("argument_equals must map dotted argument paths to values.")
        if set(rule.get("members", [])) - set(members):
            raise OrgError("Rule references a nonmember.")


def gate(org, actor, tool, arguments):
    action_hash = digest(tool, arguments)
    reasons = []
    used = []
    per_protocol = {}
    for p in org["protocols"].values():
        if p["status"] != "active" or p.get("strength", "strong") == "weak":
            continue
        start = len(reasons)
        matched = []
        reviews = []
        for index, rule in enumerate(p["rules"]):
            if not matches(rule, actor, tool, arguments):
                continue
            used.append(p["id"])
            matched.append(index)
            if rule["effect"] == "deny":
                reasons.append(p["title"] + ": " + rule.get("reason", "Action blocked by adopted protocol."))
            else:
                matching_reviews = [r['id'] for r in org['reviews'].values() if r["action_hash"] == action_hash and r["subject"] == actor
                         and r["reviewer"] != actor and r["reviewer"] in org["members"]
                         and r["expires_at"] > now() and r["protocol_id"] == p["id"]
                        ]
                reviews.extend(matching_reviews)
                if not matching_reviews:
                    reasons.append(p["title"] + ": another member must review these exact tool arguments.")
        if matched:
            per_protocol[p['id']] = {'allowed': len(reasons) == start, 'matched_rule_indexes': matched,
                                      'review_ids': sorted(set(reviews)), 'reasons': reasons[start:]}
    verdict = {"allowed": not reasons, "reasons": reasons, "action_hash": action_hash,
               "protocol_ids": sorted(set(used)), 'protocol_decisions': per_protocol}
    if org.get('scope_evolution', {}).get('deployments'):
        from .scope_evolution.runtime import scoped_gate
        scoped = scoped_gate(org, actor, tool, arguments)
        verdict.update(scope_deployment_ids=scoped['scope_deployment_ids'], scope_decisions=scoped['scope_decisions'])
        verdict['reasons'].extend(scoped['reasons'])
        verdict['allowed'] = verdict['allowed'] and scoped['allowed']
    if used:
        from .activity import decision_context
        return decision_context(org, actor, tool, arguments, verdict, source='gate_evaluation')
    return verdict


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_home() / "organization.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE, org_id TEXT, actor TEXT, kind TEXT, body TEXT, at TEXT);
                CREATE INDEX IF NOT EXISTS event_org ON events(org_id,seq);
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.execute("PRAGMA busy_timeout=3000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self, actor=None):
        with self.connect() as db:
            orgs = [json.loads(r[0]) for r in db.execute("SELECT body FROM organizations")]
        return [o for o in orgs if actor is None or actor in o["members"]]

    def get(self, org_id, actor=None):
        with self.connect() as db:
            row = db.execute("SELECT body FROM organizations WHERE id=?", (org_id,)).fetchone()
        if not row:
            raise OrgError("Unknown organization.")
        org = json.loads(row[0])
        if actor and actor != "human" and actor not in org["members"]:
            raise OrgError("This session is not an authorized organization member.")
        return org

    def events(self, org_id, after=0, limit=100):
        with self.connect() as db:
            rows = db.execute("SELECT seq,id,actor,kind,body,at FROM events WHERE org_id=? AND seq>? ORDER BY seq LIMIT ?",
                              (org_id, after, min(limit, 200))).fetchall()
        return [dict(seq=r[0], id=r[1], actor=r[2], kind=r[3], body=json.loads(r[4]), at=r[5]) for r in rows]

    def _event(self, db, org, actor, kind, body):
        event_id = uid("ev")
        db.execute("INSERT INTO events(id,org_id,actor,kind,body,at) VALUES(?,?,?,?,?,?)",
                   (event_id, org["id"], actor, kind, json.dumps(body, ensure_ascii=False), now()))
        return event_id

    @contextlib.contextmanager
    def transaction(self, org_id, actor, kind, detail):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM organizations WHERE id=?", (org_id,)).fetchone()
            if not row:
                raise OrgError("Unknown organization.")
            org = json.loads(row[0])
            if actor != "human" and actor not in org["members"]:
                raise OrgError("Session is not a member.")
            yield org, db
            org["revision"] += 1
            self._event(db, org, actor, kind, detail)
            db.execute("UPDATE organizations SET body=? WHERE id=?", (json.dumps(org, ensure_ascii=False), org_id))

    def create(self, name, members, leader, governance="leader_with_peer", execution_mode="quiet", delivery_mode="after_turn", *, native=None, _db=None):
        if not name.strip() or not members or len(members) > 24:
            raise OrgError("Choose a name and 1-24 sessions.")
        if governance not in ("leader_with_peer", "majority"):
            raise OrgError("Unsupported governance mode.")
        if execution_mode not in ("quiet", "desktop", "native"):
            raise OrgError("Execution mode must be quiet, desktop or native.")
        if execution_mode == 'native' and (not native or native.get('root_thread_id') != leader):
            raise OrgError('Native organizations require verified root metadata.')
        if delivery_mode not in ("after_turn", "immediate"):
            raise OrgError("Delivery mode must be after_turn or immediate.")
        roster = {}
        for m in members:
            if m.get("host_id", "local") != "local" or not m.get("thread_id") or m["thread_id"] in roster:
                raise OrgError("This version supports distinct local Codex sessions.")
            roster[m["thread_id"]] = dict(m, joined_at=now(), active_episode=None)
        if leader not in roster:
            raise OrgError("Leader must be a selected session.")
        org = {"id": uid("org"), "name": name, "members": roster, "leader": leader,
               "governance": governance, "execution_mode": execution_mode, "delivery_mode": delivery_mode, "status": "active", "revision": 1, "created_at": now(),
               "authorization": {"by": "human", "at": now(), "scope": "Internal member messaging, meetings, shared work and protocol governance. External actions retain host permissions."},
               "documents": {}, "tasks": {}, "messages": {}, "episodes": {}, "protocols": {}, "reviews": {}}
        if execution_mode == 'native':
            org.update(runtime='native_subagents', native=native, automatic_reflection=True)
        with (contextlib.nullcontext(_db) if _db is not None else self.connect()) as db:
            if _db is None:
                db.execute("BEGIN IMMEDIATE")
            # One active organization per chat makes hook scope unambiguous.
            for row in db.execute("SELECT body FROM organizations"):
                existing = json.loads(row[0])
                if existing["status"] == "active" and set(roster) & set(existing["members"]):
                    raise OrgError("A selected chat already belongs to an active organization; pause that organization first.")
            db.execute("INSERT INTO organizations VALUES(?,?)", (org["id"], json.dumps(org, ensure_ascii=False)))
            self._event(db, org, "human", "organization.created", {"members": list(roster), "leader": leader})
        return org

    def human_control(self, org_id, operation, value=None):
        with self.transaction(org_id, "human", "human." + operation, {"value": value}) as (org, db):
            if operation == "leader":
                if value not in org["members"]:
                    raise OrgError("Leader must be a member.")
                org["leader"] = value
            elif operation in ("pause", "resume"):
                if org['status'] == 'retired':
                    raise OrgError('A retired organization cannot be paused or resumed.')
                if operation == "resume":
                    for other in self.list():
                        if other["id"] != org_id and other["status"] == "active" and set(other["members"]) & set(org["members"]):
                            raise OrgError("A member is active in another organization.")
                org["status"] = "paused" if operation == "pause" else "active"
            elif operation == 'retire_organization':
                org['status'] = 'retired'
                org['retired_at'] = now()
            elif operation == "retire":
                org["protocols"][value]["status"] = "retired"
            elif operation == "execution_mode":
                if org.get('runtime') == 'native_subagents' or org.get('execution_mode') == 'native':
                    if value != 'native':
                        raise OrgError('Native organizations cannot switch to desktop or quiet execution.')
                    return org
                if value not in ("quiet", "desktop"):
                    raise OrgError("Execution mode must be quiet or desktop.")
                org["execution_mode"] = value
            elif operation == "delivery_mode":
                if value not in ("after_turn", "immediate"):
                    raise OrgError("Delivery mode must be after_turn or immediate.")
                org["delivery_mode"] = value
            elif operation == "automatic_reflection":
                if not isinstance(value, bool):
                    raise OrgError("Automatic reflection must be a human-selected boolean.")
                org["automatic_reflection"] = value
            else:
                raise OrgError("Unknown human control.")
        return self.get(org_id)

    def execute(self, org_id, actor, operation, args):
        # Commit decision evidence after the operation transaction, including a
        # rejected call whose transaction rolled back. Never turn a preflight
        # check into an actual blocked tool attempt.
        decisions = []
        status = 'completed'
        try:
            return self._execute(org_id, actor, operation, args, decisions)
        except Exception:
            status = 'blocked' if decisions and not decisions[0]['allowed'] else 'error'
            raise
        finally:
            if decisions:
                decisions[0]['operation_status'] = status
                self.record_protocol_decision(org_id, actor, decisions[0])

    def record_protocol_decision(self, org_id, actor, body, *, preflight=False):
        if not body.get('protocol_ids') and not body.get('scope_deployment_ids'):
            return None
        with self.connect() as db:
            org = self.get(org_id, actor)
            prefix = 'protocol' if body.get('protocol_ids') else 'scope'
            return self._event(db, org, actor, prefix + ('.preflight' if preflight else '.enforced'), body)

    def protocol_activity(self, org_id, actor=None, **kwargs):
        from .activity import protocol_activity
        return protocol_activity(self, org_id, actor, **kwargs)

    def _execute(self, org_id, actor, operation, args, decisions):
        # Protocol governance and reviews stay reachable so agents can repair bad rules.
        exempt = {"protocol_propose", "protocol_comment", "protocol_vote", "protocol_agree", "protocol_adopt", "protocol_retire", "protocol_record_use", "review_record", "message_ack"}
        result = None
        detail = {"operation": operation}
        with self.transaction(org_id, actor, operation, detail) as (org, db):
            if org["status"] != "active":
                raise OrgError("Organization is paused.")
            if operation not in exempt:
                verdict = gate(org, actor, "org_" + operation, args)
                if verdict['protocol_ids'] or verdict.get('scope_deployment_ids'):
                    from .activity import decision_context
                    decisions.append(decision_context(org, actor, 'org_' + operation, args, verdict, source='organization_server'))
                if not verdict["allowed"]:
                    raise OrgError("; ".join(verdict["reasons"]))
            if operation == "message_send":
                delivery_mode = args.get("delivery_mode", org.get("delivery_mode", "after_turn"))
                if delivery_mode not in ("after_turn", "immediate"):
                    raise OrgError("Delivery mode must be after_turn or immediate.")
                recipients = args.get("recipients") or [m for m in org["members"] if m != actor]
                if not recipients or set(recipients) - set(org["members"]):
                    raise OrgError("Messages can only target selected members.")
                key = args["idempotency_key"]
                existing = next((m for m in org["messages"].values() if m["key"] == key and m["sender"] == actor), None)
                if existing:
                    if existing["body"] != args["body"] or existing["recipients"] != recipients or existing["reply_to"] != args.get("reply_to") or existing["episode_id"] != args.get("episode_id") or ('delivery_mode' in args and existing.get('delivery_mode','after_turn') != delivery_mode):
                        raise OrgError("Idempotency key already identifies a different message.")
                    result = existing
                else:
                    if args.get("reply_to") and args["reply_to"] not in org["messages"]:
                        raise OrgError("Unknown parent message.")
                    if args.get("episode_id") and args["episode_id"] not in org["episodes"]:
                        raise OrgError("Unknown episode.")
                    ep = org["episodes"].get(args.get("episode_id"))
                    if ep and actor not in ep["participants"]:
                        raise OrgError("Only participants may reference this episode in a work message.")
                    if ep and ep["kind"] == "meeting" and ep["status"] != "open":
                        raise OrgError("Meeting contributions require an open meeting; send a separate work message.")
                    if ep and ep["kind"] == "meeting":
                        count = sum(m["sender"] == actor and m["episode_id"] == ep["id"] for m in org["messages"].values())
                        if count >= ep["rounds"]:
                            raise OrgError("Meeting contribution limit reached; organizer should resolve or open another meeting.")
                    m = {"id": uid("msg"), "key": key, "sender": actor, "recipients": recipients,
                         "body": args["body"], "created_at": now(), "reply_to": args.get("reply_to"),
                         "episode_id": args.get("episode_id"), "delivery_mode": delivery_mode, "deliveries": {r: {"status": "pending"} for r in recipients}}
                    org["messages"][m["id"]] = result = m
            elif operation == "message_ack":
                m = org["messages"][args["message_id"]]
                if actor not in m["recipients"]:
                    raise OrgError("Only a recipient can acknowledge a message.")
                m["deliveries"][actor].update(status="acknowledged", at=now())
                if m["deliveries"][actor].get("context_offered_at"):
                    m["deliveries"][actor]["context_state"] = "acknowledged"
                result = m
            elif operation == "message_configure":
                if actor not in ("human", org["leader"]):
                    raise OrgError("Only the human or leader can change the organization message default.")
                value = args["delivery_mode"]
                if value not in ("after_turn", "immediate"):
                    raise OrgError("Delivery mode must be after_turn or immediate.")
                org["delivery_mode"] = value
                result = {"delivery_mode":value}
            elif operation == "document_write":
                key = args["key"]
                old = org["documents"].get(key)
                revision = old["revision"] if old else 0
                if args["expected_revision"] != revision:
                    raise OrgError("Document revision conflict; read the current document before merging.")
                result = {"key": key, "body": args["body"], "revision": revision + 1, "author": actor, "updated_at": now()}
                org["documents"][key] = result
            elif operation == "task_update":
                task_id = args.get("task_id") or uid("task")
                old = org["tasks"].get(task_id)
                if old and old["revision"] != args.get("expected_revision"):
                    raise OrgError("Task revision conflict.")
                owner = args.get("owner", old["owner"] if old else actor)
                if owner not in org["members"]:
                    raise OrgError("Task owner must be a member.")
                if old and actor not in (old["owner"], org["leader"]):
                    raise OrgError("Only task owner or leader can update it.")
                status = args.get("status", old["status"] if old else "open")
                if status not in ("open", "working", "blocked", "done", "cancelled"):
                    raise OrgError("Unknown task status.")
                if status == "done" and not args.get("evidence"):
                    raise OrgError("Task completion needs outcome evidence.")
                result = {"id": task_id, "title": args.get("title", old["title"] if old else ""),
                          "owner": owner, "status": status, "evidence": args.get("evidence", []),
                          "revision": old["revision"] + 1 if old else 1, "updated_at": now()}
                org["tasks"][task_id] = result
            elif operation == "episode_open":
                participants = args.get("participants") or [actor]
                if set(participants) - set(org["members"]) or actor not in participants:
                    raise OrgError("Episode participants must be selected members including its author.")
                result = {"id": uid("ep"), "title": args["title"], "owner": actor, "participants": participants,
                          "status": "open", "kind": args.get("kind", "work"), "events": [], "reflections": {},
                          "opened_at": now(), "outcome": None, "evidence": [], "reflection_due": False}
                if result["kind"] == "meeting":
                    rounds = args.get("rounds", 3)
                    if not isinstance(rounds, int) or not 1 <= rounds <= 6:
                        raise OrgError("Meeting rounds must be 1-6.")
                    result["rounds"] = rounds
                org["episodes"][result["id"]] = result
                for member in participants:
                    if org["members"][member]["active_episode"]:
                        raise OrgError("A participant already has an open episode; finish it first.")
                    org["members"][member]["active_episode"] = result["id"]
            elif operation == "episode_close":
                ep = org["episodes"][args["episode_id"]]
                if actor not in (ep["owner"], org["leader"]):
                    raise OrgError("Only episode owner or leader can close it.")
                if ep["status"] != "open" or not args.get("evidence"):
                    raise OrgError("Closing an open episode requires outcome evidence.")
                if args["outcome"] not in ("success", "failure", "partial", "cancelled", "observed"):
                    raise OrgError("Unknown episode outcome.")
                ep.update(status="closed", outcome=args["outcome"], evidence=args["evidence"],
                          summary=args["summary"], closed_at=now(), reflection_due=True)
                for member in ep["participants"]:
                    if org["members"][member]["active_episode"] == ep["id"]:
                        org["members"][member]["active_episode"] = None
                result = ep
            elif operation == "episode_reflect":
                ep = org["episodes"][args["episode_id"]]
                if ep["status"] != "closed" or actor not in ep["participants"]:
                    raise OrgError("Reflection requires a closed episode you participated in.")
                ep["reflections"][actor] = {"body": args["body"], "at": now()}
                ep["reflection_due"] = set(ep["participants"]) != set(ep["reflections"])
                result = ep
            elif operation == "protocol_propose":
                ep = org["episodes"][args["episode_id"]]
                strength = args.get("strength", "strong")
                if strength not in ("weak", "strong"):
                    raise OrgError("Protocol strength must be weak or strong.")
                if actor not in ep["participants"]:
                    raise OrgError("Protocol authors must participate in the source episode.")
                if (strength == "strong" or ep["status"] == "closed") and (ep["status"] != "closed" or actor not in ep["reflections"]):
                    raise OrgError("Propose from a closed episode after recording your reflection.")
                if strength == "strong":
                    validate_rules(args["rules"], org["members"])
                else:
                    if args.get("rules"):
                        raise OrgError("Weak protocols carry guidance, not blocking rules. Propose a strong version for enforcement.")
                    if not all(isinstance(args.get(k), str) and args[k].strip() for k in ("guidance", "trigger", "scope")):
                        raise OrgError("Weak protocols need readable guidance, trigger and scope.")
                    if not isinstance(args.get("evidence"), list) or not args["evidence"] or not all(isinstance(x, str) and x.strip() for x in args["evidence"]):
                        raise OrgError("Weak protocol formation needs references to actual shared work or agreement.")
                parent = org["protocols"].get(args.get("supersedes"))
                if args.get("supersedes") and (not parent or parent["status"] != "active"):
                    raise OrgError("An amendment must reference a currently active protocol.")
                result = {"id": uid("proto"), "title": args["title"], "rationale": args["rationale"],
                          "author": actor, "episode_id": ep["id"], "rules": args.get("rules", []), "status": "proposed",
                          "strength": strength, "guidance": args.get("guidance", ""),
                          "trigger": args.get("trigger", ""), "scope": args.get("scope", ""),
                          "evidence": args.get("evidence", []), "uses": {},
                          "version": parent["version"] + 1 if parent else 1, "supersedes": args.get("supersedes"),
                          "comments": [], "votes": {}, "created_at": now()}
                org["protocols"][result["id"]] = result
            elif operation in ("protocol_comment", "protocol_vote", "protocol_agree", "protocol_adopt", "protocol_retire"):
                p = org["protocols"][args["protocol_id"]]
                if operation == "protocol_comment":
                    p["comments"].append({"author": actor, "body": args["body"], "at": now()})
                elif operation == "protocol_vote":
                    if p["status"] != "proposed" or args["vote"] not in ("approve", "reject"):
                        raise OrgError("Vote approve/reject on a proposal.")
                    p["votes"][actor] = {"vote": args["vote"], "reason": args["reason"], "at": now()}
                elif operation in ("protocol_adopt", "protocol_agree"):
                    if operation == "protocol_agree":
                        if p.get("strength", "strong") != "weak" or p["status"] != "proposed":
                            raise OrgError("Agree records your own acceptance of a proposed weak protocol.")
                        if not isinstance(args.get("body"), str) or not args["body"].strip():
                            raise OrgError("State how this shared agreement applies to your work.")
                        p["comments"].append({"author": actor, "body": args["body"], "at": now()})
                        p["votes"][actor] = {"vote": "approve", "reason": args["body"], "at": now(), "via": "agreement"}
                    if operation == "protocol_adopt" and (actor != org["leader"] or p["status"] != "proposed"):
                        raise OrgError("Leader adopts a proposed protocol after review.")
                    approvals = {m for m, v in p["votes"].items() if v["vote"] == "approve" and m in org["members"]}
                    needed = min(2, len(org["members"])) if org["governance"] == "leader_with_peer" else len(org["members"]) // 2 + 1
                    ready = org["leader"] in approvals and len(approvals) >= needed and bool(p["comments"])
                    if not ready and operation == "protocol_adopt":
                        raise OrgError("Adoption needs discussion, leader approval and the organization approval threshold.")
                    if ready and p["supersedes"]:
                        parent = org["protocols"][p["supersedes"]]
                        if parent["status"] != "active":
                            raise OrgError("Parent changed; propose an amendment against the current version.")
                        parent["status"] = "superseded"
                    if ready:
                        p.update(status="active", adopted_at=now(), adoption_mode="member_agreement" if operation == "protocol_agree" else "governed_vote")
                else:
                    if actor != org["leader"]:
                        raise OrgError("Leader retires a protocol; humans can also retire it from the panel.")
                    p.update(status="retired", retired_at=now(), retirement_reason=args["reason"])
                result = p
            elif operation == "protocol_record_use":
                if actor not in org["members"]:
                    raise OrgError("Only the actual member can report their protocol use.")
                p = org["protocols"][args["protocol_id"]]
                if p["status"] != "active" or args.get("version") != p["version"]:
                    raise OrgError("Record use against the exact active protocol version.")
                if args.get("outcome") not in ("followed", "deviated", "inapplicable"):
                    raise OrgError("Use outcome must be followed, deviated or inapplicable.")
                if not all(isinstance(args.get(k), str) and args[k].strip() for k in ("idempotency_key", "work_unit", "note")):
                    raise OrgError("Use needs an idempotency key, concrete work unit and explanatory note.")
                if not isinstance(args.get("evidence"), list) or not args["evidence"] or not all(isinstance(x, str) and x.strip() for x in args["evidence"]):
                    raise OrgError("Use needs actual work evidence, not a plan or acknowledgment alone.")
                payload = {k: args[k] for k in ("version", "idempotency_key", "work_unit", "outcome", "note", "evidence")}
                key = actor + ":" + args["idempotency_key"]
                uses = p.setdefault("uses", {})
                if key in uses:
                    if any(uses[key][k] != v for k, v in payload.items()):
                        raise OrgError("Use idempotency key already identifies different evidence.")
                    result = uses[key]
                else:
                    result = {"id": uid("use"), "protocol_id": p["id"], "actor": actor, "at": now(),
                              "evidence_source": "member_report", **payload}
                    uses[key] = result
            elif operation == "review_record":
                from datetime import timedelta
                p = org["protocols"][args["protocol_id"]]
                if p.get("strength", "strong") != "strong" or p["status"] != "active" or args["subject"] not in org["members"] or args["subject"] == actor:
                    raise OrgError("Review an active protocol's exact action for a different member.")
                if not args.get("evidence"):
                    raise OrgError("Review needs evidence.")
                result = {"id": uid("review"), "protocol_id": p["id"], "reviewer": actor,
                          "subject": args["subject"], "action_hash": digest(args["tool"], args["arguments"]),
                          "evidence": args["evidence"], "at": now(),
                          "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
                org["reviews"][result["id"]] = result
            else:
                raise OrgError("Unknown operation: " + operation)
            detail["object_id"] = result.get("id", result.get("key")) if result else None
        return result

    def offer_immediate(self, org_id, actor, turn_id=None):
        """Offer peer content at a hook boundary; recipient ack alone proves receipt."""
        selected = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM organizations WHERE id=?', (org_id,)).fetchone()
            org = json.loads(row[0]) if row else None
            if not org or org['status'] != 'active' or actor not in org['members']:
                return []
            for message in org['messages'].values():
                receipt = message['deliveries'].get(actor, {})
                if (message.get('delivery_mode','after_turn') == 'immediate' and receipt.get('status') == 'pending'
                        and not receipt.get('context_offered_at')):
                    receipt.update(context_offered_at=now(), context_turn_id=turn_id, context_state='offered')
                    selected.append({'message_id':message['id'], 'from':message['sender'], 'body':message['body'][:700]})
                    if len(selected) == 8:
                        break
            if selected:
                org['revision'] += 1
                self._event(db,org,actor,'message.context_offered',{'message_ids':[m['message_id'] for m in selected],'turn_id':turn_id,'transport':'trusted_hook_context','receipt':'offered_not_acknowledged'})
                db.execute('UPDATE organizations SET body=? WHERE id=?', (json.dumps(org,ensure_ascii=False), org_id))
        return selected

    def delivery(self, org_id, message_id, recipient, status, reason=None):
        with self.transaction(org_id, "human", "message.delivery", {"message_id": message_id, "recipient": recipient, "status": status}) as (org, db):
            if org.get('runtime') == 'native_subagents' or org.get('execution_mode') == 'native':
                raise OrgError('Native delivery stays pending until the actual recipient acknowledges through org_message.')
            target = org["messages"][message_id]["deliveries"][recipient]
            if target["status"] == "acknowledged":
                return False
            if status == "sending" and target["status"] != "pending":
                return False
            target.update(status=status, at=now(), reason=reason)
        return True

    def observe(self, org_id, actor, kind, body, turn_id=None):
        with self.transaction(org_id, actor, kind, {}) as (org, db):
            if org["status"] != "active":
                return
            if kind in ('protocol.checked', 'protocol.blocked'):
                body = {**body, 'source': 'trusted_local_hook', 'turn_id': turn_id,
                        'episode_id': org['members'][actor]['active_episode']}
            event_id = self._event(db, org, actor, "observation." + kind, body)
            ep_id = org["members"][actor]["active_episode"]
            if not ep_id and turn_id:
                ep_id = "turn_" + hashlib.sha256((org_id + actor + turn_id).encode()).hexdigest()[:24]
                if kind == "turn.stopped" and ep_id not in org["episodes"]:
                    return event_id
                if ep_id not in org["episodes"]:
                    org["episodes"][ep_id] = {"id": ep_id, "title": "Codex turn " + turn_id,
                        "owner": actor, "participants": [actor], "status": "open", "kind": "turn",
                        "events": [], "reflections": {}, "opened_at": now(), "outcome": None,
                        "evidence": [], "reflection_due": False}
            if ep_id and (kind == "protocol.blocked" or body.get("failed")):
                org["episodes"][ep_id]["reflection_due"] = True
            if ep_id and org["episodes"][ep_id]["status"] == "open":
                org["episodes"][ep_id]["events"].append(event_id)
            if kind == "turn.stopped" and ep_id and org["episodes"][ep_id]["kind"] == "turn":
                ep = org["episodes"][ep_id]
                ep.update(status="closed", closed_at=now(), outcome="observed", evidence=ep["events"][-20:],
                          summary="Turn stopped. Task outcome is not inferred from tool completion.")
        return event_id
