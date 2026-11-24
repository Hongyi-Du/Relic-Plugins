"""Automatic wake-ups: a member with new unread messages gets a turn in its own session, with nobody clicking.

Hongyi's request (2026-10-16): the organization must run on its own. A message from one member to another (including
a trajectory request, which arrives as a message) starts the recipient's next turn through the same runner the Relic
window uses for 发送任务, with the recipient's own seat config (model, folder, permission).

dispatch() is cheap and idempotent, so it runs wherever the organization changes: in the MCP server after a Relic call,
on hook events of every member, when a runner turn ends, and from a delayed retry. A seat is woken when all hold:
  * the organization has auto-wake on (default on; the Relic App can switch it off)
  * the seat has a session and a config for that session's harness (the seats the window can give tasks to)
  * it has an unread message newer than the one it was last woken for (automatic receipts never wake anyone), and
    the newest is SETTLE seconds old, so several messages sent in a row make one wake-up
  * that message is less than MAX_HOPS wake-ups deep: a message sent during an automatically started turn carries the
    turn's depth, so members answering each other stop waking each other after MAX_HOPS, however slowly they go
  * its runner process is not alive, and its transcript has been still for QUIET seconds (the person may be using it)
  * it was not woken in the last GAP seconds (CHAT_GAP for a ChatGPT chat member), any back-off after a failed
    start is over, and the organization is
    under HOURLY_CAP wakes in the past hour
A seat that has to wait is retried later; a start that fails gives its claim back and is retried with back-off, so a
message is never stranded. Its wakers get one receipt for the failure; the retries that fail the same way for the same
messages stay quiet (repeated_failure).
A Codex chat open in the Codex desktop app gets its turn through the app (desktop.py); while a turn is already running
there the wake-up waits GAP and tries again. A chat held by something Relic cannot reach (a Codex CLI session in a
terminal) is looked at again every RECHECK seconds, MAX_IN_USE times, and then its messages wait for normal delivery.
"""
import calendar
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import desktop, gui_receipt, i18n, runner
from .store import HUMAN, SYSTEM, away_note, central, codex_parent, codex_thread, epoch, iso, leaders

SETTLE = 10  # seconds after the newest unread message before waking: messages sent in a row make one wake-up
QUIET = 60
GAP = 120
CHAT_GAP = 10  # a ChatGPT chat member (chat.py) answers inside its own conversation: a discussion should not crawl
HOURLY_CAP = 30
MAX_HOPS = 6
BACKOFF = (60, 120, 300, 900, 1800)
RECHECK = 300  # look again at a seat that is still running a turn, or whose chat another app holds
MAX_FAILURES = 5  # after this many failed wake-ups in a row the messages wait for normal delivery
MAX_IN_USE = 6  # rechecks of a chat held by an app Relic cannot reach (30 minutes) before its messages wait
IN_USE = "already has an active writer"  # Codex: the chat is open for writing elsewhere
RECEIPT_MARK = "[Relic auto-receipt]"
SUBAGENT_INPUT = "direct app-server input is not allowed for multi-agent v2 sub-agents"  # the Codex app's refusal


def no_turn(error):
    """Whether a failed wake-up never reached the member's model: its chat was held, or busy in the desktop app
    (a Claude Desktop session that still owes an earlier request its Stop counts as busy)."""
    text = str(error or "")
    return bool(text) and (IN_USE in text or desktop.BUSY in text or gui_receipt.WAITING in text or
                           gui_receipt.DESKTOP_BUSY in text or SUBAGENT_INPUT in text)


def desktop_hold(store, seat, config):
    """Seconds a Claude Desktop seat waits because its session still owes an earlier Relic request its GUI Stop,
    whichever of the session's seats that request was for (at most claude_desktop.PENDING_EXPIRY); 0 otherwise."""
    config = config if config is not None else (seat or {}).get("config") or {}
    if (store is None or config.get("harness") != "claude-code" or config.get("surface") != "gui" or
            not (seat or {}).get("carrier")):
        return 0
    from . import claude_desktop
    return claude_desktop.hold(store, seat["carrier"])


def wakeable(seat, config=None):
    """config: how the seat's turns start (Store.seat_config: an ex officio or subgroup seat starts its turns like
    the seat its session holds elsewhere); default: the seat's own."""
    config = (config if config is not None else (seat or {}).get("config")) or {}
    if sys.platform == "darwin" and (config.get("surface") == "gui" or config.get("harness") == "chatgpt"):
        from . import platform_support
        if not platform_support.can_auto_deliver(config.get("harness"), config.get("surface")):
            return False
        if config.get("harness") == "claude-code":
            from . import gui_receipt
            if not gui_receipt.observed_carrier((seat or {}).get("carrier") or ""):
                return False
    return bool(seat and seat.get("auto_wake", True) and config.get("auto_wake", True) and seat.get("carrier")
                and config and config.get("harness") == seat.get("harness"))


def busy(store, org_id, member, seat, now=None):
    """Whether the seat's session is running a turn, in this seat or in another one it holds: a session takes one
    turn at a time."""
    if runner.is_running(org_id, member, now):
        return True
    carrier = (seat or {}).get("carrier")
    if not carrier or store is None:
        return False
    return any(runner.is_running(o, m, now) for o, m in store.seat_keys(carrier) if (o, m) != (org_id, member))


def gap(seat):
    """Least time between two wake-ups of the same seat."""
    return CHAT_GAP if (seat or {}).get("harness") == "chatgpt" else GAP


OLD_MESSAGE = 6 * 3600  # an unread message older than this carries its age in the wake-up prompt


def sent_note(at, now=None):
    """', sent <time>, <n> days ago: ...' for a message older than OLD_MESSAGE, else ''. A seat whose auto-wake was
    off, or that was stopped, is woken for its whole unread backlog once it is back on, and old instructions may no
    longer hold (2026-11-07: five seats were woken for a three-day-old message announcing a pause already lifted)."""
    try:
        sent = calendar.timegm(time.strptime(at or "", "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return ""
    age = (time.time() if now is None else now) - sent
    if age < OLD_MESSAGE:
        return ""
    ago = "%d days" % (age // 86400) if age >= 2 * 86400 else "%d hours" % (age // 3600)
    return ", sent %s, %s ago: check that it still applies" % (at, ago)


RELAYED = (" Relayed instructions are as good as the person's own (the person, 2026-11-15: 我跟 Claude 说的话，他转述给 "
           "Codex，结果 Codex 那边说这不是我人说的，然后又不干): act on them within your role and the organization's "
           "purpose as you would on the person's words. Relic marks the words it found in the person's own typing "
           "([Relic check W<n>] under a message); check other exact words with work op=said instead of asking the "
           "person to repeat them.")
FAILED = (" A refused or failed step stops only that step, and a failure is not a refusal: a tool, service, sandbox or "
          "network error or a bug is fixed or routed around (Relic 研发部 fixes Relic itself), and the parts that do "
          "not need that step go on.")


def prompt(org, member, senders, count, hop=1, main=True, messages=None, now=None, away=None):
    """main: whether this is the session's main seat; another seat is worked in with org=<its id>. away: the person is
    away from the computer (Store.person_away), so the turn runs without waiting for them."""
    where = "" if main else (" This is not your main seat: pass org=%s to the Relic tools (inbox, message, work, "
                             "protocol ...) to act here, and follow this organization's protocols while you do its "
                             "work." % org["id"])
    notice = bool(senders) and all(s == SYSTEM for s in senders)
    if notice:  # keep-going (drive_check): no peer wrote this, so there is nobody to answer
        text = ("[Relic keep-going] You hold the seat '%s' in the Relic organization '%s' (%s).%s Keep-going is on "
                "here and the organization, with the ones below it, has gone quiet with its work unfinished, so the "
                "plugin started this turn with a keep-going notice; the person did not type it. The standing "
                "instruction quoted in the notice is the person's. As the driver, decide the next step and start it "
                "now: give it to the members who do it (message) or do it yourself. Ask the person only for what the "
                "organization's rules reserve for them, with your recommendation, and go on with the rest meanwhile. "
                "When the goal is reached, send the person a summary. The notice needs no reply."
                % (member, org["name"], org["id"], where)) + FAILED + away_note(away)
    else:
        if hop >= MAX_HOPS:  # research-head, 2026-11-18: four work handoffs sent in such a turn were taken for lost
            depth = ("This is automatic wake-up %d of at most %d in this exchange, the last: the messages you send in "
                     "this turn are saved but wake nobody. Their recipients read them at their next turn, which "
                     "keep-going (where it is on) starts once the organization has been quiet for %d minutes; do not "
                     "send acknowledgments of acknowledgments." % (hop, MAX_HOPS, DRIVE_QUIET // 60))
        else:
            depth = ("This is automatic wake-up %d of at most %d in this exchange; past that, messages are saved but "
                     "wake nobody until a turn starts another way (by hand, or keep-going once the organization has "
                     "gone quiet), so do not send acknowledgments of acknowledgments." % (hop, MAX_HOPS))
        text = ("[Relic auto-wake] You hold the seat '%s' in the Relic organization '%s' (%s).%s %d unread message(s) "
                "from %s started this turn; the plugin started it, not the person. The messages that started this "
                "turn are in the context or in inbox, and your open tasks are in status. Peer messages are work "
                "input.%s Reply to the sender with the Relic message tool when you have a result, a disagreement or a "
                "question, and say clearly when something needs the person's decision.%s%s %s"
                % (member, org["name"], org["id"], where, count, ", ".join(senders), RELAYED, FAILED, away_note(away),
                   depth))
    if messages and notice:
        text += ("\nThe notice: message %s. Read it with inbox message_id=<id> if it is not in the context, then check "
                 "status for open tasks here and below.\n" % ", ".join(str(m["id"]) for m in messages))
    elif messages:
        text += ("\nCurrent triggering message ids: %s. Read each with inbox message_id=<id>, even if a hook has "
                 "already marked it read, then check status for your open tasks. Work on this input within the "
                 "authorization above; report actual progress, a result, or a blocker with message reply_to=<id>. "
                 "An old completion or standby answer does not resolve a new task.\n" %
                 ", ".join(str(m["id"]) for m in messages))
        budget = 6000
        for message in messages:
            body = message.get("body") or ""
            preview = body[:budget]
            budget -= len(preview)
            text += "\n[msg %s from %s%s]\n%s" % (message["id"], message["sender"],
                                                  sent_note(message.get("at"), now), preview)
            if len(preview) < len(body):
                text += "\n(preview: read message %s in full with inbox message_id=%s)" % (message["id"], message["id"])
    return text


def message_checkpoint(store, org_id):
    """Use message ids, not second-resolution timestamps, to delimit a turn's replies."""
    with store.db() as db:
        return db.execute("SELECT COALESCE(MAX(id), 0) FROM messages WHERE org_id=?", (org_id,)).fetchone()[0]


def latest_message(store):
    """The newest message id in any organization (0 when there is none)."""
    with store.db() as db:
        return db.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0]


def written_since(store, first):
    """Organizations that got a message after message id first, oldest first."""
    with store.db() as db:
        rows = db.execute("SELECT org_id, MIN(id) FROM messages WHERE id>? GROUP BY org_id ORDER BY MIN(id)", (first,))
        return [row[0] for row in rows]


def receipt(store, org_id, member, wake_from, after, state):
    """Report turn completion and only replies in its triggering threads, separately for each waker.

    Session final text can be stale, or answer a human redirect. It is never a message receipt, even on failure.
    Older runners without trigger ids get status-only receipts rather than guesses based on recipient or time.
    """
    ids = set(state.get("wake_message_ids") or [])
    with store.db() as db:
        triggers = [r for r in db.execute("SELECT id,sender,recipients,reply_to FROM messages WHERE org_id=?",
                                         (org_id,)) if r[0] in ids and member in json.loads(r[2])]
        replies = db.execute("SELECT id,body,reply_to FROM messages WHERE org_id=? AND sender=? AND id>? ORDER BY id",
                             (org_id, member, after)).fetchall()
    if state.get("status") == "done":
        status = "the turn finished"
    elif state.get("status") == "failed":
        status = ("the turn failed: " + (state.get("error") or "no completion confirmed")[-1200:] +
                  ". Relic retries a few times without repeating this receipt; if the retries fail too, the messages "
                  "wait in %s's inbox for its next turn" % member)
    else:
        status = "the turn is not complete: " + (state.get("error") or "no completion confirmed")[-1200:]
    sent = []
    for sender in dict.fromkeys(wake_from):
        own = [r for r in triggers if r[1] == sender]
        roots = {r[3] or r[0] for r in own}
        related = [r for r in replies if r[2] in roots and not r[1].startswith(RECEIPT_MARK)]
        label = " (ids %s)" % ", ".join(str(r[0]) for r in own) if own else ""
        body = "%s %s was woken by your message(s)%s; %s." % (RECEIPT_MARK, member, label, status)
        if related:
            body += "\nReplies in the triggering thread(s) during this turn:\n" + "\n".join(
                "[msg %s, thread %s] %s" % (r[0], r[2], r[1]) for r in related)
        else:
            body += " No reply in the triggering thread(s) was recorded during this turn."
        sent.append(store.send_as(org_id, member, [sender], body,
                                  reply_to=next(iter(roots)) if len(roots) == 1 else None))
    return sent


def _failure_kind(error):
    """A failure's text without the numbers and ids that change from one attempt to the next."""
    return re.sub(r"[0-9a-f]{8,}|\d+", "#", str(error or ""))[-300:]


def repeated_failure(store, org_id, member, error, message_ids):
    """Whether a failed wake-up only repeats a failure its wakers already have a receipt for: the same failure, for
    messages they were all told about. Otherwise it is remembered, so the retries that fail the same way stay quiet;
    a turn that goes through forgets it (_settle). A retry that also carries a newer message gets a receipt."""
    kind = _failure_kind(error)
    ids = {i for i in message_ids or () if isinstance(i, int)}
    with store.change(org_id) as (org, db):
        mine = org.setdefault("wake", {}).setdefault("members", {}).setdefault(member, {})
        told = mine.get("told") or {}
        known = set(told.get("ids") or []) if told.get("kind") == kind else set()
        if ids and ids <= known:
            return True
        mine["told"] = {"kind": kind, "ids": sorted(known | ids)}
        return False


def _cache_path():
    return runner.runs_dir() / "transcripts.json"


def transcripts(seat):
    """Transcript files of the seat's current session, remembered after the first (slower) search."""
    carrier = seat.get("carrier") or ""
    try:
        cache = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        cache = {}
    known = [Path(p) for p in cache.get(carrier, []) if Path(p).is_file()]
    if known:
        return known
    if carrier.split(":", 1)[0] in ("chatgpt", "claude-chat"):
        return []  # a chat member's conversation is kept by its chat app, not on this machine
    if carrier.startswith("codex:"):
        root = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex") / "sessions"
        found = list(root.rglob("*%s*.jsonl" % codex_thread(carrier))) if root.is_dir() else []
    else:
        root = Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
        found = list(root.glob("*/%s.jsonl" % carrier.split("/", 1)[0])) if root.is_dir() else []
    if found:
        cache[carrier] = [str(p) for p in found]
        try:
            _cache_path().write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return found


def transcript_age(seat, now=None):
    """Seconds since the seat's transcript last changed; None when there is no transcript to look at."""
    files = transcripts(seat)
    if not files:
        return None
    return (time.time() if now is None else now) - max(f.stat().st_mtime for f in files)


def _epoch(at):
    """A message's time (store.now(): UTC, seconds) as epoch seconds; 0 when missing or unreadable."""
    try:
        return calendar.timegm(time.strptime(at, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0


def _due(org, org_id, member, messages, mine, now, age, store=None):
    """(wait in seconds, None) while the seat must wait, (0, info) when it can be woken, (None, None) when not at all."""
    seat = org["members"].get(member)
    fresh = [m for m in messages if m["id"] > mine.get("last_id", 0)]
    triggers = [m for m in fresh if m["hop"] < MAX_HOPS]
    config = store.seat_config(org_id, member, org) if store is not None and seat else None
    if not wakeable(seat, config) or not triggers:
        return None, None
    if codex_parent(seat.get("carrier")):
        # A Codex subagent with a seat of its own takes input only from the session that spawned it: the Codex
        # desktop app refuses direct input to multi-agent v2 sub-agents (SUBAGENT_INPUT), and while the app holds
        # its thread no other process can write there (2026-11-16, Learning's astra-systems-lead)
        return None, None
    if busy(store, org_id, member, seat, now):
        return RECHECK, None  # its runner dispatches when the turn ends; the retry covers a runner that dies
    held = desktop_hold(store, seat, config)
    if held:
        return min(held, RECHECK), None  # never a second request while the Desktop session owes the first its Stop
    wait = max(gap(seat) - (now - mine.get("last_at", 0)), mine.get("retry_at", 0) - now)
    if SETTLE:
        wait = max(wait, SETTLE - (now - max(_epoch(m.get("at")) for m in fresh)))
    still = age(seat)
    if still is not None:
        wait = max(wait, QUIET - still)
    if wait > 0:
        return wait, None
    return 0, {"last_id": max(m["id"] for m in fresh), "count": len(fresh),
               "senders": list(dict.fromkeys(m["sender"] for m in fresh)),
               "messages": fresh,
               "hop": min(m["hop"] for m in triggers) + 1}


def waits_text(member, waits):
    """What the person is told when a seat's chat waits for them in the Codex desktop app (desktop.WAITS matched the
    wake-up's error): which chat, since when, for what, and that only they can answer it."""
    flags, since, title = waits.groups()
    names = {"waitingOnApproval": i18n.t("wake.waiting_on_approval"),
             "waitingOnUserInput": i18n.t("wake.waiting_on_input")}
    what = " / ".join(names.get(f, f) for f in flags.split(","))
    when = central(epoch(since)) if epoch(since) else since
    return i18n.t("wake.waits_for_person", member=member, title=title, since=when, what=what)


def _settle(store, org_id, member, claimed_at, error=None, busy=False):
    """Close a wake-up: on success clear its claim and failures; on failure give the claim back so the messages are
    tried again: after GAP when the seat was busy (its runner, or a turn in the desktop app), after RECHECK when its
    chat is held by an app Relic cannot reach (MAX_IN_USE times), else with back-off until MAX_FAILURES in a row.
    None of the waiting counts as a failure. Returns the retry delay (None on success or when the messages are left
    for normal delivery)."""
    with store.change(org_id) as (org, db):
        wake = org.setdefault("wake", {})
        mine = wake.setdefault("members", {}).setdefault(member, {})
        claim = mine.pop("claim", {})
        if error is None:
            for key in ("failures", "error", "retry_at", "in_use", "waiting_since", "gave_up_at", "told",
                        "person_told"):
                mine.pop(key, None)
            return None
        # A Claude Desktop session in a turn (its own, or the one that would start it) waits like a busy Codex chat:
        # counted as a failure, a seat whose earlier wake-ups failed gave up at once (2026-11-24, benchlead).
        busy = (busy or desktop.BUSY in str(error) or gui_receipt.WAITING in str(error) or
                gui_receipt.DESKTOP_BUSY in str(error))
        waits = desktop.WAITS.search(str(error))
        if waits and mine.get("person_told") != waits.group(2):  # once for each wait, however often it is retried
            mine["person_told"] = waits.group(2)
            store._post(db, org_id, SYSTEM, [HUMAN], waits_text(member, waits))
            store._event(db, org_id, member, "member.waits_for_person", {"flags": waits.group(1),
                                                                         "since": waits.group(2)})
        held = not busy and IN_USE in str(error)
        if held:
            mine["in_use"] = mine.get("in_use", 0) + 1
        if held and mine["in_use"] >= MAX_IN_USE:
            mine.pop("in_use")  # a newer message gets its own round of rechecks
            mine.update(error=str(error)[-500:], waiting_since=claimed_at)
            store._event(db, org_id, member, "member.wake_waiting", {"error": str(error)[-300:]})
            return None  # the chat stays held: its messages reach it at its next Relic call, or a newer one wakes it
        if not (busy or held) and mine.get("failures", 0) + 1 >= MAX_FAILURES:
            mine.update(failures=mine.get("failures", 0) + 1, error=str(error)[-500:], gave_up_at=claimed_at)
            store._event(db, org_id, member, "member.wake_gave_up", {"error": str(error)[-300:]})
            return None  # the messages stay unread and reach the seat at its next tool call
        for key, value in claim.items():
            if value is None:
                mine.pop(key, None)
            else:
                mine[key] = value
        wake["recent"] = [t for t in wake.get("recent", []) if t != claimed_at]
        if busy:
            delay = gap(org["members"].get(member))
        elif held:
            delay = RECHECK
        else:
            mine["failures"] = mine.get("failures", 0) + 1
            delay = BACKOFF[min(mine["failures"], len(BACKOFF)) - 1]
            mine["error"] = str(error)[-500:]
        mine["retry_at"] = claimed_at + delay
        store._event(db, org_id, member, "member.wake_failed", {"error": str(error)[-300:], "busy": busy,
                                                                "in_use": held, "retry_in": delay})
        return delay


def finish(store, org_id, member, error=None):
    """Called when a woken turn ends: success clears the claim; a failure inside the turn (the runner started, the
    harness did not) gives it back like a failed start. Returns the retry delay, if any."""
    mine = ((store.get(org_id).get("wake") or {}).get("members") or {}).get(member, {})
    if "claim" not in mine:
        return None
    return _settle(store, org_id, member, mine.get("last_at") or time.time(), error)


def dispatch(store, org_id, now=None, start=None, age=None, retry=None, arm=None):
    """Wake every seat that is due; returns the members started. Seats that must wait get a delayed retry. Then the
    keep-going checks that are due run (drive_due, arm: its delayed check), in any organization: one small query when
    none is."""
    now = time.time() if now is None else now
    start = start or runner.start_turn
    age = age or transcript_age
    retry = retry or schedule_retry
    started = _dispatch(store, org_id, now, start, age, retry)
    try:
        drive_due(store, now, start, age, retry, arm)
    except Exception:  # keep-going must never stand in the way of a wake-up
        pass
    return started


def _dispatch(store, org_id, now, start, age, retry):
    org = store.get(org_id)
    if org.get("status") != "active" or not org.get("auto_wake", True):
        return []
    state = (org.get("wake") or {}).get("members", {})
    due, waits = [], []
    for member, messages in store.unread_by_member(org_id, skip_prefix=RECEIPT_MARK).items():
        wait, info = _due(org, org_id, member, messages, state.get(member, {}), now, age, store)
        if info:
            due.append((member, info))
        elif wait:
            waits.append(wait)
    chosen = []
    if due:
        with store.change(org_id) as (org, db):
            wake = org.setdefault("wake", {})
            members = wake.setdefault("members", {})
            recent = wake["recent"] = [t for t in wake.get("recent", []) if now - t < 3600]
            for member, info in due:
                mine = members.setdefault(member, {})
                if info["last_id"] <= mine.get("last_id", 0) or now - mine.get("last_at", 0) < gap(org["members"].get(member)):
                    continue  # another dispatcher took it a moment ago
                if len(recent) >= HOURLY_CAP:
                    waits.append(3600 - (now - recent[0]))
                    break
                mine["claim"] = {"last_id": mine.get("last_id"), "last_at": mine.get("last_at")}
                mine.update(last_id=info["last_id"], last_at=now)
                recent.append(now)
                chosen.append((member, info))
                store._event(db, org_id, member, "member.woken", {"from": info["senders"], "unread": info["count"],
                                                                  "hop": info["hop"],
                                                                  "message_ids": [m["id"] for m in info["messages"]]})
    started = []
    try:
        away = store.person_away() if chosen else None
    except Exception:  # not knowing whether the person is around never stops a wake-up
        away = None
    for member, info in chosen:
        carrier = (org["members"].get(member) or {}).get("carrier")
        main = not carrier or (store.seat_keys(carrier)[:1] or [(org_id, member)])[0] == (org_id, member)
        try:
            start(org_id, member, prompt(org, member, info["senders"], info["count"], info["hop"], main, info["messages"],
                                         away=away),
                  wake_from=info["senders"], wake_hop=info["hop"],
                  wake_message_ids=[m["id"] for m in info["messages"]])
        except Exception as error:  # the seat's run state is left alone: it may belong to a turn still running
            delay = _settle(store, org_id, member, now, error,
                            busy=busy(store, org_id, member, org["members"].get(member)))
            if delay:
                waits.append(delay)
            continue
        started.append(member)  # the claim stays until the turn ends (finish), so a turn that fails is retried
    if waits:
        retry(org_id, max(5, min(waits)) + 1)
    return started


# ---------------- keep-going (持续推进) ----------------
# Hongyi, 2026-11-07: "I give them an auto research task, they don't finish it and stop ... I want them to go on by
# themselves: when a step is done they tell the head, and the head goes on with the next step of the research."
# Auto-wake answers messages, and an exchange ends after MAX_HOPS, so a head that stops after a batch, or a member that
# finishes without telling anyone, leaves the work standing until the person comes back. With keep-going on
# (Store.set_drive), an organization whose subtree has gone quiet (nobody working, nothing waiting to be delivered) for
# DRIVE_QUIET gets one notice to its driver with the person's standing instruction and the work still open; the notice
# starts a new exchange (hop 0). It is not a timer: a notice needs progress since the previous one (a message that is
# not a notice, a receipt or a report to the person; or an edit or a command anywhere in the subtree), so an
# organization that has stopped for good costs one notice, and DRIVE_DAILY bounds the rest.
# Messages sent in the last turn of an exchange (hop MAX_HOPS) wake nobody, though they are often work handed on: on
# 2026-11-18 research-head's four handoffs to research-coordinator sat unread for 20 minutes, and the notice said nothing
# was waiting (in the three days before, 51 of 62 such recipients stayed silent for more than 10 minutes). So the same
# check first hands them over: each seat below whose new unread messages all came that way gets a note of its own,
# which starts a new exchange with them, and the driver's notice says who got what, so that nobody sends them again.
DRIVE_QUIET = 600
DRIVE_DAILY = 12
DRIVE_ASK_WAIT = 3600  # a question to the person with no work after it holds the notices this long
DRIVE_STALE = 1800  # an open turn whose transcript is this still, or a wake-up claimed this long ago with no runner
#                     alive, is a turn that ended without its Stop (interrupted, or its session died)
DRIVE_RECHECK = 300  # look again this soon while someone is working
DRIVE_IDLE = 1800  # look again this long after an organization stopped, or while it cannot get a notice
DRIVE_TASKS = 8  # unfinished tasks listed in a notice
WORK_KINDS = ("edit", "run")  # activity kinds that count as progress (reading around does not)
# A background job a task waits on (work op=task job=<pid>: a controller, an experiment) is work going on, though no
# seat has a turn (research-head, 2026-11-16: the Glaze S model and its controller ran for hours while keep-going said
# three times that nobody worked). While one runs, drive_check holds the organization's next check until the job's
# horizon, so that an older Relic process (a Codex plugin waiting for the person to trust its new hooks) cannot claim
# the check and send such a notice; watch_jobs looks at the job's process every JOB_LOOK and makes the check due once
# it is gone. Its end counts as progress, and the next notice says it ended.
JOB_HORIZON = 24 * 3600  # a job counts as work at most this long after it was attached: one that never ends must not
#                          silence keep-going for good
JOB_LOOK = 300
JOB_EVERY = 60  # at most one look a minute, machine-wide: drive_due runs on every member's tool call


def _drive_scope(store, org_id):
    """(the organization, it and the active organizations below it, every active organization by id)."""
    everything = {o["id"]: o for o in store.list_orgs() if o.get("status") == "active"}
    if org_id not in everything:
        return None, [], everything
    below = store._ids_below(list(everything.values()), org_id)
    return everything[org_id], [everything[org_id]] + [everything[i] for i in below if i in everything], everything


def _drive_seats(subtree, everything):
    """Every seat of the sessions that sit in the subtree, wherever it is (a session works in one seat at a time, and
    its work for the subtree may be recorded under another of its seats), and one seat per session (transcripts)."""
    keys = {(o["id"], m) for o in subtree for m in o["members"]}
    sessions = {}
    for o in subtree:
        for s in o["members"].values():
            if s.get("carrier"):
                sessions.setdefault(s["carrier"], s)
    for o in everything.values():
        for m, s in o["members"].items():
            if s.get("carrier") in sessions:
                keys.add((o["id"], m))
    return keys, list(sessions.values())


def _drive_tools(store, keys):
    """{(org_id, member): {activity kind: time of the seat's last tool call of that kind}} for the given seats."""
    places = sorted({k[0] for k in keys})
    if not places:
        return {}
    with store.db() as db:
        rows = db.execute("SELECT org_id, member, kind, MAX(at) FROM activity WHERE org_id IN (%s) "
                          "GROUP BY org_id, member, kind" % ",".join("?" * len(places)), places).fetchall()
    tools = {}
    for org_id, member, kind, at in rows:
        if (org_id, member) in keys and at:
            tools.setdefault((org_id, member), {})[kind] = at
    return tools


def job_runs(job):
    """Whether a task's background job still runs: its process is alive and, where its start time can be read, it is
    the process that was attached, not a later one that got the same id."""
    alive, started = runner.process_start(job.get("pid"))
    if not alive:
        return False
    return started is None or job.get("started") is None or abs(started - job["started"]) < 2


def _job_counts(task, job, now):
    """Whether a job can still count as work: its task is unfinished, it has not been seen to end, and it was attached
    less than JOB_HORIZON ago."""
    return (task.get("status") in ("open", "working", "blocked") and not job.get("ended_at")
            and now - (_epoch(job.get("at")) or now) < JOB_HORIZON)


def _jobs(subtree):
    """[(org, task, job)] for the tasks in the subtree that name a background job."""
    return [(o, t, t["job"]) for o in subtree for t in (o.get("tasks") or {}).values() if t.get("job")]


def _job_ended(store, org_id, task_id, job, now):
    """Record that a task's background job is gone (its process exited); the end counts as progress, and the task's
    owner is told (_tell_job_ended)."""
    job["ended_at"] = iso(now)
    with store.change(org_id) as (org, db):
        stored = ((org.get("tasks") or {}).get(task_id) or {}).get("job")
        if not stored or stored.get("pid") != job.get("pid") or stored.get("ended_at"):
            return
        stored["ended_at"] = job["ended_at"]
        store._event(db, org_id, SYSTEM, "task.job_ended", {"id": task_id, "pid": job.get("pid")})
    _tell_job_ended(store, org_id, task_id, now)
    job["told_at"] = iso(now)  # the caller's copy: drive_check does not look at it again


def _tell_job_ended(store, org_id, task_id, now):
    """Tell the owner of an unfinished task (or, when no seated member owns it, the organization's leaders) that its
    background job ended, once, in a message that wakes them (drive_due): a job may leave nobody else to say so
    (research-head, 2026-11-17: the OrgBench replay batch only runs, stops and writes its results), and keep-going
    speaks only once the whole subtree has gone quiet. The job is marked told, so the message goes out once whoever
    records the end; drive_check catches up on an end that an older Relic recorded without telling."""
    with store.change(org_id) as (org, db):
        task = (org.get("tasks") or {}).get(task_id) or {}
        job = task.get("job") or {}
        if not job.get("ended_at") or job.get("told_at") or task.get("status") not in ("open", "working", "blocked"):
            return
        job["told_at"] = iso(now)
        owner = task.get("owner")
        to = [owner] if owner in (org.get("members") or {}) else leaders(org)
        body = i18n.t("task.job_ended", org=org.get("name", org_id), id=task_id,
                      title=(task.get("title") or "")[:120], pid=job.get("pid"), when=job["ended_at"])
    if to:
        store.send_system(org_id, to, body)


def _running_jobs(store, subtree, now):
    """[(org, task, job)] for the background jobs in the subtree that still run and count as work; the ones found gone
    are recorded as ended."""
    running = []
    for o, t, job in _jobs(subtree):
        if not _job_counts(t, job, now):
            continue
        if job_runs(job):
            running.append((o, t, job))
        else:
            _job_ended(store, o["id"], t["id"], job, now)
    return running


def _hold(store, org, keys):
    """Remember which jobs ("<org id>/<task id>") hold the organization's keep-going for watch_jobs, or that none does."""
    keys = sorted(keys)
    if ((org.get("drive") or {}).get("held") or []) == keys:
        return
    with store.change(org["id"]) as (fresh, db):
        drive = fresh.setdefault("drive", {})
        if keys:
            drive["held"] = keys
        else:
            drive.pop("held", None)


def _jobs_look_path():
    return runner.runs_dir() / "jobs-look.json"


def watch_jobs(store, now):
    """Look at the processes of the background jobs that hold keep-going somewhere (drive_check); an organization none
    of whose jobs runs any longer has its check made due now. Returns when to look again, or None when no job holds
    anything. At most one look every JOB_EVERY, machine-wide."""
    path = _jobs_look_path()
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    if now - seen.get("looked", 0) < JOB_EVERY:
        return seen.get("next")
    held = False
    for org_id in store.drive_checks():
        try:
            org = store.get(org_id)
        except Exception:  # an organization that is gone
            continue
        keys = (org.get("drive") or {}).get("held") or []
        if not keys:
            continue
        runs = False
        for key in keys:
            place, _, task_id = key.partition("/")
            try:
                task = (store.get(place).get("tasks") or {}).get(task_id) or {}
            except Exception:
                continue
            job = task.get("job")
            if not job or not _job_counts(task, job, now):
                continue
            if job_runs(job):
                runs = True
            else:
                _job_ended(store, place, task_id, job, now)
        if runs:
            held = True
        else:
            _hold(store, org, [])
            store.set_drive_check(org_id, now)
    following = now + JOB_LOOK if held else None
    try:
        temp = path.with_name(path.name + ".%d" % os.getpid())
        temp.write_text(json.dumps({"looked": now, "next": following}), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass
    return following


def _drive_busy(store, keys, everything, now, stillness, tools):
    """Why the subtree is not quiet (a turn runs, a wake-up is under way or due), or None. stillness: {session:
    seconds since its transcript changed, or None}; tools: _drive_tools."""
    for org_id, member in sorted(keys):
        org = everything.get(org_id) or {}
        seat = (org.get("members") or {}).get(member) or {}
        if runner.is_running(org_id, member, now):
            return "%s runs a turn" % member
        episode = (org.get("episodes") or {}).get(seat.get("turn_episode") or "")
        still = stillness.get(seat.get("carrier"))
        if still is None:  # no transcript to look at (another CODEX_HOME, a chat): its own last tool call tells
            last = max((tools.get((org_id, member)) or {}).values() or [_epoch((episode or {}).get("opened_at"))])
            still = now - last
        if episode and episode.get("status") == "open" and still < DRIVE_STALE:
            return "%s is in a turn" % member
        mine = ((org.get("wake") or {}).get("members") or {}).get(member) or {}
        if "claim" in mine and now - mine.get("last_at", 0) < DRIVE_STALE:
            return "%s is being woken" % member
        if mine.get("retry_at", 0) > now and not mine.get("gave_up_at"):
            return "%s is due to be woken" % member
        if seat.get("carrier") and seat.get("harness") == "claude-code" and desktop_hold(
                store, seat, store.seat_config(org_id, member, org)):
            return "%s owes a Desktop request its Stop" % member
    return None


def _drive_record(store, subtree_ids, tools, stillness, now, since_id, since_at):
    """What happened in the subtree: times (epoch) of the last message, tool call and transcript change; whether
    anything moved after the last notice (since_id, since_at); the newest message to the person that neither the
    person's answer nor any progress has followed (question)."""
    marks = ",".join("?" * len(subtree_ids))
    acts = [(kind, at) for kinds in tools.values() for kind, at in kinds.items()]
    work = max([at for kind, at in acts if kind in WORK_KINDS] or [0])
    with store.db() as db:
        last_message = db.execute("SELECT MAX(at) FROM messages WHERE org_id IN (%s)" % marks,
                                  subtree_ids).fetchone()[0]

        def moved(after_id, after_at):
            """Progress after a message: a message that is not a notice, a receipt or a report to the person only,
            or an edit or a command (reading around is not progress)."""
            if work > after_at:
                return True
            return db.execute("SELECT 1 FROM messages WHERE org_id IN (%s) AND id>? AND sender<>? AND body NOT LIKE ? "
                              "AND recipients<>? LIMIT 1" % marks,
                              subtree_ids + [after_id, SYSTEM, RECEIPT_MARK + "%", json.dumps([HUMAN])]).fetchone() \
                is not None

        asked = db.execute("SELECT id, at FROM messages WHERE org_id IN (%s) AND sender NOT IN (?, ?) AND recipients "
                           "LIKE ? AND body NOT LIKE ? ORDER BY id DESC LIMIT 1" % marks,
                           subtree_ids + [HUMAN, SYSTEM, '%"' + HUMAN + '"%', RECEIPT_MARK + "%"]).fetchone()
        answered = db.execute("SELECT MAX(id) FROM messages WHERE org_id IN (%s) AND sender=?" % marks,
                              subtree_ids + [HUMAN]).fetchone()[0] or 0
        question = None
        if asked and asked[0] > answered and not moved(asked[0], _epoch(asked[1])):
            question = {"id": asked[0], "at": _epoch(asked[1])}
        progress = moved(since_id, since_at)
    transcript = max([now - still for still in stillness.values() if still is not None] or [0])
    return {"message": _epoch(last_message), "tool": max([at for _, at in acts] or [0]), "transcript": transcript,
            "moved": progress, "question": question}


def _stranded(store, subtree):
    """Seats in the subtree whose unread messages newer than their last wake-up all came at the end of an exchange
    (hop MAX_HOPS), so that auto-wake leaves them for a turn that may never come: [(org, member, messages)]. Only
    seats a wake-up can reach (not the own seat of a Codex subagent: the session that spawned it drives it)."""
    found = []
    for o in subtree:
        if not o.get("auto_wake", True):
            continue
        state = (o.get("wake") or {}).get("members") or {}
        for member, messages in store.unread_by_member(o["id"], skip_prefix=RECEIPT_MARK).items():
            fresh = [m for m in messages if m["id"] > (state.get(member) or {}).get("last_id", 0)]
            if not fresh or any(m["hop"] < MAX_HOPS for m in fresh):
                continue  # nothing new, or auto-wake delivers it
            seat = o["members"].get(member)
            if not wakeable(seat, store.seat_config(o["id"], member, o) if seat else None) or \
                    codex_parent(seat.get("carrier")):
                continue
            found.append((o, member, fresh))
    return found


def _stranded_line(o, member, fresh):
    return i18n.t("drive.stranded_line", org=o["name"], member=member, ids=", ".join(str(m["id"]) for m in fresh),
                  senders=", ".join(dict.fromkeys(m["sender"] for m in fresh)))


def drive_notice(org, subtree, drive, quiet, ended=(), stranded=()):
    """The notice the driver gets, in the person's language: the standing instruction, the background jobs that ended
    since the previous notice (ended: [(org, task, job)]), the messages handed over that had woken nobody (stranded:
    [(org, member, messages)]) and the work still open."""
    open_tasks = [(o["name"], t) for o in subtree for t in (o.get("tasks") or {}).values()
                  if t.get("status") in ("open", "working", "blocked")]
    lines = ["- %s %s [%s] %s: %s" % (name, t["id"], t["status"], t.get("owner", ""), (t.get("title") or "")[:120])
             for name, t in open_tasks[-DRIVE_TASKS:]]
    if len(open_tasks) > DRIVE_TASKS:
        lines.insert(0, i18n.t("drive.more_tasks", n=len(open_tasks) - DRIVE_TASKS))
    jobs = [i18n.t("drive.job_ended", org=o["name"], id=t["id"], title=(t.get("title") or "")[:120],
                   pid=job.get("pid"), when=job.get("ended_at", "")) for o, t, job in ended]
    handed = [_stranded_line(o, member, fresh) for o, member, fresh in stranded]
    by = drive.get("set_by") or HUMAN
    return i18n.t("drive.notice", org=org["name"], minutes=int(quiet // 60), goal=drive.get("goal", ""),
                  when=drive.get("set_at", ""),
                  by=i18n.t("drive.by_person") if by == HUMAN else i18n.t("drive.by_member", member=by),
                  tasks=(i18n.t("drive.jobs", list="\n".join(jobs)) if jobs else "") +
                  (i18n.t("drive.stranded", list="\n".join(handed)) if handed else "") +
                  (i18n.t("drive.tasks", list="\n".join(lines)) if lines else ""))


def drive_check(store, org_id, now=None, age=None, start=None, retry=None):
    """Look at one organization with keep-going on (drive_due hands it over, claimed) and send its driver a notice when
    it is due. Returns {"state": off | paused | busy | wait | idle | asked | capped | unreachable | nudged, "next": when
    to look again, ...}; drive_due makes sure something looks again then."""
    now = time.time() if now is None else now
    age = age or transcript_age
    retry = retry or schedule_retry
    org, subtree, everything = _drive_scope(store, org_id)
    drive = (org or {}).get("drive") or {}
    if not drive.get("on"):
        store.set_drive_check(org_id, None)
        return {"state": "off"}

    def later(state, at, **extra):
        store.set_drive_check(org_id, at)
        return dict({"state": state, "next": at}, **extra)

    if not org.get("auto_wake", True):  # Stop all, or the person switched auto-wake off here: nothing starts by itself
        return later("paused", now + DRIVE_IDLE)
    running = _running_jobs(store, subtree, now)
    for o, t, job in _jobs(subtree):  # an end an older Relic recorded without telling the task's owner
        if job.get("ended_at") and not job.get("told_at") and now - _epoch(job["ended_at"]) < JOB_HORIZON:
            _tell_job_ended(store, o["id"], t["id"], now)
    _hold(store, org, ["%s/%s" % (o["id"], t["id"]) for o, t, _ in running])
    if running:  # held until the earliest horizon; watch_jobs makes the check due once the jobs are gone
        o, t, job = running[0]
        return later("busy", min(_epoch(j.get("at")) or now for _, _, j in running) + JOB_HORIZON,
                     why="%s %s waits on its background job (process %s)" % (o["name"], t["id"], job.get("pid")),
                     held=len(running))
    keys, sessions = _drive_seats(subtree, everything)
    stillness = {seat["carrier"]: age(seat) for seat in sessions}
    tools = _drive_tools(store, keys)
    why = _drive_busy(store, keys, everything, now, stillness, tools)
    if why:
        return later("busy", now + DRIVE_RECHECK, why=why)
    last = drive.get("last") or {}
    seen = _drive_record(store, [o["id"] for o in subtree], tools, stillness, now, last.get("id", 0),
                         last.get("at", 0))
    ended = [(o, t, job) for o, t, job in _jobs(subtree) if _epoch(job.get("ended_at"))]
    finished = max([_epoch(job["ended_at"]) for _, _, job in ended] or [0])  # a job's end is progress
    quiet_since = max(seen["message"], seen["tool"], seen["transcript"], finished)
    if now - quiet_since < DRIVE_QUIET:
        return later("wait", quiet_since + DRIVE_QUIET)
    if last and not seen["moved"] and finished <= last.get("at", 0):
        return later("idle", now + DRIVE_IDLE)
    question = seen["question"]
    if question and question["id"] > last.get("id", 0) and now - question["at"] < DRIVE_ASK_WAIT:
        return later("asked", question["at"] + DRIVE_ASK_WAIT, question=question["id"])
    sent = [t for t in drive.get("nudges", []) if now - t < 86400]
    if len(sent) >= DRIVE_DAILY:
        return later("capped", sent[0] + 86400)
    driver = drive.get("driver")
    stranded = _stranded(store, subtree)
    handed = []  # the seats that got a note: the driver gets its own messages with its notice
    for o, member, fresh in stranded:
        if (o["id"], member) == (org_id, driver):
            continue
        store.send_system(o["id"], [member], i18n.t(
            "drive.stranded_note", org=org["name"], minutes=int((now - quiet_since) // 60),
            ids=", ".join(str(m["id"]) for m in fresh), senders=", ".join(dict.fromkeys(m["sender"] for m in fresh))))
        handed.append((o["id"], member, [m["id"] for m in fresh]))
    if handed:
        with store.db() as db:
            store._event(db, org_id, SYSTEM, "organization.drive_handed",
                         {"seats": [{"org": o, "member": m, "message_ids": ids} for o, m, ids in handed]})
        for place in dict.fromkeys(o for o, _, _ in handed):  # a new exchange: hop 0, so it wakes them
            _dispatch(store, place, now, start or runner.start_turn, age, retry)
    handed = ["%s/%s" % (o, m) for o, m, _ in handed]
    seat = org["members"].get(driver)
    if not wakeable(seat, store.seat_config(org_id, driver, org) if seat else None):
        if not drive.get("unreachable_at"):
            store.send_system(org_id, [HUMAN], i18n.t("drive.unreachable", org=org["name"], driver=driver))
            with store.change(org_id) as (fresh, db):
                fresh.setdefault("drive", {})["unreachable_at"] = now
        return later("unreachable", now + DRIVE_IDLE, driver=driver, handed=handed)
    mid = store.send_system(org_id, [driver], drive_notice(
        org, subtree, drive, now - quiet_since,
        ended=[(o, t, job) for o, t, job in ended if _epoch(job["ended_at"]) > last.get("at", 0)], stranded=stranded))
    with store.change(org_id) as (fresh, db):
        record = fresh.setdefault("drive", {})
        record["last"] = {"id": mid, "at": now}
        record["nudges"] = sent + [now]
        store._event(db, org_id, SYSTEM, "organization.drive_notice",
                     {"driver": driver, "message_id": mid, "quiet": int(now - quiet_since)})
    store.set_drive_check(org_id, now + DRIVE_QUIET)
    _dispatch(store, org_id, now, start or runner.start_turn, age, retry)  # the notice wakes the driver
    return {"state": "nudged", "next": now + DRIVE_QUIET, "driver": driver, "message_id": mid, "handed": handed}


# ---------------- Desktop wake-ups an older Relic could not deliver ----------------
# Until 2026-11-14 the only route into a Claude Desktop session was a CLI message router, which needs a separate
# claude.ai CLI login; Relic now writes into the session's own inbox (claude_desktop.deliver). An older copy of Relic
# that a long-running process still has loaded (a session's MCP server, the Codex plugin until the person trusts the
# new hooks) starts those wake-ups with its old route, and they fail on the missing login. The next newer Relic that
# runs hands them over: it clears the failure and starts them again its own way. While such failures were seen in the
# last HANDOVER_WATCH, the delayed background check keeps looking every HANDOVER_HEARTBEAT, so they are picked up when
# no newer process happens to run.
OLD_DESKTOP_ROUTE = "Claude Desktop unavailable: an existing official claude.ai CLI login is required"
HANDOVER_EVERY = 60  # at most one look a minute, machine-wide: dispatch runs on every member's tool call
HANDOVER_HEARTBEAT = 120
HANDOVER_WATCH = 24 * 3600


def _handover_path():
    return runner.runs_dir() / "desktop-handover.json"


def _hand_over(store, now):
    """Clear the failures an older Relic's CLI route left on Claude Desktop seats; returns [(org_id, member)]."""
    found = []
    for org in store.list_orgs():
        if org.get("status") != "active":
            continue
        for member, mine in ((org.get("wake") or {}).get("members") or {}).items():
            seat = (org.get("members") or {}).get(member)
            if (not str(mine.get("error") or "").startswith(OLD_DESKTOP_ROUTE) or "claim" in mine or not seat or
                    seat.get("harness") != "claude-code" or runner.is_running(org["id"], member, now)):
                continue
            if (store.seat_config(org["id"], member, org) or {}).get("surface") == "gui":
                found.append((org["id"], member))
    handed = []
    for org_id, member in found:
        unread = [m["id"] for m in store.unread_by_member(org_id, skip_prefix=RECEIPT_MARK).get(member, [])]
        with store.change(org_id) as (org, db):
            mine = ((org.get("wake") or {}).get("members") or {}).get(member)
            if not mine or "claim" in mine or not str(mine.get("error") or "").startswith(OLD_DESKTOP_ROUTE):
                continue  # another process handed it over, or a wake-up is under way
            error = mine["error"]
            if mine.get("gave_up_at") and unread:  # the messages the old route gave up on are due again
                mine["last_id"] = min(mine.get("last_id", 0), min(unread) - 1)
            for key in ("failures", "error", "retry_at", "gave_up_at", "told", "last_at"):
                mine.pop(key, None)
            store._event(db, org_id, member, "member.wake_handed_over", {"error": error[-300:], "unread": len(unread)})
        handed.append((org_id, member))
    return handed


def hand_over_desktop(store, now, start, age, retry):
    """Start again, with this Relic's own route, the Desktop wake-ups an older Relic failed to deliver; at most once a
    minute. Returns when the background check is to look again (while such failures were seen lately), else None."""
    path = _handover_path()
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    if now - seen.get("looked", 0) >= HANDOVER_EVERY:
        seen["looked"] = now
        handed = _hand_over(store, now)
        if handed:
            seen["failure"] = now
        try:
            temp = path.with_name(path.name + ".%d" % os.getpid())
            temp.write_text(json.dumps(seen), encoding="utf-8")
            os.replace(temp, path)
        except OSError:
            pass
        for org_id in dict.fromkeys(o for o, _ in handed):
            _dispatch(store, org_id, now, start, age, retry)
    if now - seen.get("failure", 0) < HANDOVER_WATCH:
        return seen["looked"] + HANDOVER_HEARTBEAT
    return None


def _wake_posted(store, now, start, age, retry):
    """Wake whom the plugin itself wrote to (Store.send_system notes the organizations in store.posted): a pause that
    ended, a question to the person that ran out, a background job that ended."""
    for org_id in dict.fromkeys(store.__dict__.pop("posted", [])):
        try:
            _dispatch(store, org_id, now, start or runner.start_turn, age or transcript_age, retry or schedule_retry)
        except Exception:  # one organization that cannot be woken must not stand in the way of the others
            pass


def drive_due(store, now=None, start=None, age=None, retry=None, arm=None):
    """Run the keep-going checks that are due (Store.drive_due claims them); returns [(org_id, outcome)]. Then make
    sure one delayed check comes for the earliest next one (arm, default schedule_drive; Store.arm_drive makes it one,
    however many processes get here at once), so the checks go on when no member's hooks run this code and the Relic
    App is closed: a look on this machine, no turn. retry: delayed wake-ups (the driver's, after a notice)."""
    now = time.time() if now is None else now
    arm = arm or schedule_drive
    results = []
    try:  # pauses that end and questions to the person that run out (Store.fire_timers), then wake who heard of it
        store.fire_timers(now)
        _wake_posted(store, now, start, age, retry)
    except Exception:  # timers must never stand in the way of keep-going or a wake-up
        pass
    try:  # background jobs that hold keep-going: an organization whose jobs are gone is checked now
        jobs = watch_jobs(store, now)
    except Exception:
        jobs = None
    for org_id in store.drive_due(now):
        try:
            results.append((org_id, drive_check(store, org_id, now, age, start, retry)))
        except Exception as error:  # a check that breaks is not retried on every call
            store.set_drive_check(org_id, now + DRIVE_QUIET)
            results.append((org_id, {"state": "error", "error": str(error)[-300:]}))
    _wake_posted(store, now, start, age, retry)  # the owners told that a background job ended (_job_ended)
    due = list(store.drive_checks().values())
    if any(outcome.get("held") for _, outcome in results):  # a hold that began here: the jobs are looked at again
        jobs = min(jobs or now + JOB_LOOK, now + JOB_LOOK)
    if jobs is not None:
        due.append(jobs)
    next_timer = store.next_timer(now)
    if next_timer is not None:
        due.append(next_timer)
    try:
        look = hand_over_desktop(store, now, start or runner.start_turn, age or transcript_age,
                                 retry or schedule_retry)
    except Exception:  # a hand-over that breaks must never stand in the way of keep-going or a wake-up
        look = None
    if look is not None:
        due.append(look)
    if due:
        at = max(min(due), now) + 1
        if store.arm_drive(at, now):
            arm(at - now)
    return results


def schedule_drive(delay):
    """The delayed keep-going check (scripts/relic_dispatch.py --drive), in the background like schedule_retry."""
    if not runner.detach_allowed():
        return
    python = Path(sys.executable)
    if runner.WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    script = runner.entry("relic_dispatch.py")
    flags = (runner.NO_WINDOW | 0x00000200) if runner.WINDOWS else 0
    subprocess.Popen([str(python), "-X", "utf8", str(script), "--drive", "--after", "%.0f" % delay],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=not runner.WINDOWS, close_fds=True,
                     env=runner.detached_env())


def dispatch_for_actor(store, actor):
    """Dispatch in every organization the session holds a seat in (what it wrote from any seat can wake someone)."""
    started = []
    for org_id in dict.fromkeys(o for o, _ in store.seat_keys(actor)):
        try:
            started += dispatch(store, org_id)
        except Exception:  # an organization that is gone or closed
            continue
    return started


def schedule_retry(org_id, delay):
    """One background retry per organization, at the earliest time a waiting seat can be woken."""
    if not runner.detach_allowed():
        return
    marker = runner.runs_dir() / ("%s.retry" % org_id)
    due = time.time() + delay
    try:
        pending = float(marker.read_text())
    except (FileNotFoundError, ValueError):
        pending = 0
    if time.time() < pending <= due:
        return  # an earlier retry is already scheduled
    marker.write_text(str(due))
    python = Path(sys.executable)
    if runner.WINDOWS and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")
    script = runner.entry("relic_dispatch.py")
    flags = (runner.NO_WINDOW | 0x00000200) if runner.WINDOWS else 0
    subprocess.Popen([str(python), "-X", "utf8", str(script), "--org", org_id, "--after", "%.0f" % delay],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=not runner.WINDOWS, close_fds=True,
                     env=runner.detached_env())
