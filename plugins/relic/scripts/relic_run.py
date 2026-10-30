"""Run one turn of a Relic seat in the background (started through runner.start_turn by the Relic App, or by an
automatic wake-up).

--new creates the seat's session: a fresh Claude Code session or Codex thread with the seat's model, effort,
folder and permission, seated in the organization before its first turn. Without --new the turn resumes the seat's
current CLI session; an existing Claude GUI seat uses native peer messaging and waits for a GUI Stop receipt.
The prompt is the introduction (on --new), text the person wrote in the window, or an auto-wake
prompt (--wake-from names the senders). Each waker gets a completion receipt quoting only replies in the triggering
message threads; when the turn ends, waiting wake-ups of the organization are dispatched.

A surface=gui Codex chat open in the desktop app uses desktop.py. A CLI seat keeps its app-server route and reports
a writer lock when its old thread is desktop-owned; it never injects that prompt into the GUI.
A ChatGPT chat member (chat.py) has no Relic tools: its turn carries the messages' text, and its reply goes back to
their writers as its message (forwarded by the person when the ChatGPT app hides its text), which stands in for the
receipt.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import chat, claude_desktop, desktop, platform_support, runner, wake  # noqa: E402
from relic_core.store import Store  # noqa: E402


def run_claude(store, org, member, config, prompt, new, cwd):
    if config.get("surface") == "gui":
        raise RuntimeError("Claude GUI seats require native messaging and a GUI Stop receipt; CLI resume is forbidden.")
    exe = runner.find_claude()
    if not exe:
        raise RuntimeError("Claude Code CLI not found (install Claude Code, or put claude on PATH).")
    seat = org["members"][member]
    if new or not seat.get("carrier") or seat.get("harness") != "claude-code":
        session = str(uuid.uuid4())
        store.join(session, org["id"], member)  # seated before its first turn; the hook sees the seat at SessionStart
        args = [exe, "-p", prompt, "--session-id", session, "--name", "%s · %s" % (org["name"], member)]
    else:
        session = seat["carrier"].split("/", 1)[0]
        args = [exe, "-p", prompt, "--resume", session]
    if runner.checked_model(config):
        args += ["--model", config["model"]]
    if config.get("effort"):
        args += ["--effort", config["effort"]]
    args += ["--permission-mode", runner.checked_permission(config), "--output-format", "json"]
    proc = subprocess.run(args, cwd=cwd, env=runner.session_env(config), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=runner.NO_WINDOW)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {}
    if proc.returncode != 0 and not result:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[-800:] or "claude exited with %d" % proc.returncode)
    return session, str(result.get("result") or ""), bool(result.get("is_error")), None


def run_in_desktop(app, thread, prompt):
    """The chat is open in the Codex desktop app: the app runs the turn there, and the runner follows it. Once the
    prompt may have reached the app it is never sent again, so a turn that fails there is reported in the receipt
    instead of being retried (a retry would send the same prompt a second time)."""
    reply, failed = desktop.run_turn(app, thread, prompt)
    if failed:
        reply = "The turn ended as failed in the Codex desktop app; the prompt was delivered and is not sent again. " + reply
    return "codex:" + thread, reply, False, None


def open_in_desktop(app, thread):
    """Whether the Codex desktop app has this chat loaded (then only the app can run a turn in it)."""
    try:
        return desktop.status(app.read(thread)) not in (None, desktop.NOT_LOADED)
    except desktop.DesktopError:
        return False


def run_codex(store, org, member, config, prompt, new, cwd, connect=desktop.connect):
    if sys.platform == "darwin" and config.get("surface") == "gui":
        capability = desktop.transport_capability()
        if not platform_support.can_auto_deliver("codex", "gui"):
            raise RuntimeError("Codex desktop wake-up is unavailable on macOS: " + capability["reason"])
        seat = org["members"][member]
        if new or not seat.get("carrier") or seat.get("harness") != "codex":
            raise RuntimeError("An existing Codex desktop seat is required; GUI bootstrap through a CLI writer is forbidden.")
        thread = seat["carrier"].split(":", 1)[1]
        app = connect()
        if app is None or not open_in_desktop(app, thread):
            raise desktop.DesktopError("Open the existing chat in the desktop app; no CLI app-server fallback was started.")
        return run_in_desktop(app, thread, prompt)
    exe = runner.find_codex()
    if not exe:
        raise RuntimeError("Codex CLI not found (the Codex app installs one; set CODEX_CLI_PATH if it is elsewhere).")
    seat = org["members"][member]
    resume = not new and bool(seat.get("carrier")) and seat.get("harness") == "codex"
    held = seat["carrier"].split(":", 1)[1] if resume else None
    gui = config.get("surface") == "gui"
    app = connect() if held and gui else None
    if app and open_in_desktop(app, held):
        return run_in_desktop(app, held, prompt)
    settings = {"cwd": cwd, "approvalPolicy": "on-request", "sandbox": runner.checked_permission(config),
                "approvalsReviewer": config.get("reviewer") or runner.CODEX_REVIEWER}
    if runner.checked_model(config):
        settings["model"] = config["model"]

    def open_thread(server, settings):
        if not resume:
            thread = server.request("thread/start", settings)["thread"]["id"]
            store.join("codex:" + thread, org["id"], member)
            server.request("thread/name/set", {"threadId": thread, "name": "%s · %s" % (org["name"], member)})
            return thread
        server.request("thread/resume", dict(settings, threadId=held, excludeTurns=True))
        return held

    try:
        with runner.CodexAppServer(exe, env=runner.session_env(config), cwd=cwd) as server:
            try:
                thread = open_thread(server, settings)
            except RuntimeError as error:
                if "approvalsReviewer" not in str(error) and "auto_review" not in str(error):
                    raise
                # an older Codex without the automatic reviewer: approvals then reach the runner, which allows the
                # member's Relic tools and declines the rest
                settings.pop("approvalsReviewer")
                thread = open_thread(server, settings)
            turn = {"threadId": thread, "input": [{"type": "text", "text": prompt, "text_elements": []}]}
            if config.get("effort"):
                turn["effort"] = config["effort"]
            server.request("turn/start", turn)
            done = server.wait_turn(thread)
    except RuntimeError as error:
        # the desktop app opened the chat after the check above: hand the turn to the app after all (a chat held by
        # a Codex CLI session in a terminal stays held: the wake-up is retried later)
        if held and gui and wake.IN_USE in str(error):
            app = app or connect()
            if app and open_in_desktop(app, held):
                return run_in_desktop(app, held, prompt)
        if held and not gui and wake.IN_USE in str(error):
            raise RuntimeError(str(error) + "; surface=cli will not inject into GUI. Release the writer or use a fresh CLI session.") from None
        raise
    reply = ""
    for item in done.get("items") or []:
        if item.get("type") == "agentMessage" and item.get("text"):
            reply = item["text"]
    if not reply:
        for message in server.notifications:
            item = (message.get("params") or {}).get("item") or {}
            if message.get("method") == "item/completed" and item.get("type") == "agentMessage":
                reply = item.get("text") or reply
    failed = done.get("status") not in ("completed", None)
    error = (done.get("error") or {}).get("message") if isinstance(done.get("error"), dict) else done.get("error")
    approvals = {"accepted": server.answered, "declined": server.declined} if server.answered or server.declined else None
    return "codex:" + thread, reply or (error or ""), failed, approvals


def receipt(store, org_id, member, wake_from, after, state):
    return wake.receipt(store, org_id, member, wake_from, after, state)


def needs_receipt(harness, error):
    """No receipt when no turn ran (the chat was held or busy elsewhere: retried quietly), nor after a ChatGPT chat's
    turn that went through: its reply already reached the writers as its message."""
    if wake.no_turn(error):
        return False
    return not (harness == "chatgpt" and error is None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    parser.add_argument("--member", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--open", action="store_true", help="open the session for the person after the turn")
    parser.add_argument("--wake-from", default="", help="senders whose messages woke this seat, comma-separated")
    a = parser.parse_args()
    prompt_file = Path(a.prompt_file)
    prompt = prompt_file.read_text(encoding="utf-8")
    state = runner.run_state(a.org, a.member) or {}
    state.update(status="running", started=state.get("started") or time.time(), pid=os.getpid())
    runner.write_state(a.org, a.member, state)  # liveness: others check this pid before starting another turn
    after = 0
    harness = None
    try:
        store = Store()
        after = wake.message_checkpoint(store, a.org)
        state["wake_after"] = after
        org = store.get(a.org)
        seat = org["members"][a.member]
        config = store.seat_config(a.org, a.member, org) or runner.default_config(seat.get("harness") or "codex")
        harness = config.get("harness")
        if sys.platform == "darwin" and (harness == "chatgpt" or config.get("surface") == "gui"):
            capability = (claude_desktop if harness == "claude-code" else desktop).transport_capability()
            if not platform_support.can_auto_deliver(harness, config.get("surface")):
                raise RuntimeError("Desktop wake-up is unavailable on macOS for %s: %s" % (harness, capability["reason"]))
        if harness == "claude-chat":
            raise RuntimeError("%s is a Claude chat: it takes its turns in the Claude app, where nothing outside can "
                               "start one. Write to it; it reads messages with inbox." % a.member)
        if harness == "chatgpt":
            cwd, approvals = None, None
            session, reply, failed = chat.run_chatgpt(store, org, a.member, prompt, hop=state.get("wake_hop", 0))
        else:
            cwd = runner.workspace(config, a.member)
            run = (run_codex if harness == "codex" else
                   claude_desktop.run_turn if config.get("surface") == "gui" else run_claude)
            session, reply, failed, approvals = run(store, org, a.member, config, prompt, a.new, cwd)
        state.update(status="failed" if failed else "done", session=session, reply=reply[-4000:], cwd=cwd, error=None,
                     approvals=approvals)
        if (a.open and not a.wake_from and not state.get("wake_hop") and not state.get("wake_from")
                and not failed and harness != "chatgpt" and config.get("surface") != "gui"):
            harness = "codex" if session.startswith("codex:") else "claude-code"
            try:
                runner.open_session(config, session.split(":", 1)[1] if harness == "codex" else session, harness, cwd)
            except Exception as error:  # the session exists; the window can open it again
                state["open_error"] = str(error)[-500:]
    except claude_desktop.TransportError as error:
        state.update(status="incomplete" if error.possible else "failed", error=str(error),
                     delivery=error.outcome, delivery_possible=error.possible)
    except Exception as error:  # the window shows what went wrong
        state.update(status="failed", error=str(error)[-1500:])
    finally:
        state["finished"] = time.time()
        runner.write_state(a.org, a.member, state)
        try:
            prompt_file.unlink()
        except OSError:
            pass
        try:
            store = Store()
            if state.get("session"):  # hooks end a turn; this covers a harness that ran it without them
                store.clear_focus(state["session"])
            wake_from = [m for m in a.wake_from.split(",") if m]
            if wake_from:
                error = None if state.get("status") == "done" else str(state.get("error") or state.get("reply") or "failed")
                if needs_receipt(harness, error):
                    receipt(store, a.org, a.member, wake_from, after, state)
                # A held/unknown/sent GUI request can still arrive. Consume this wake
                # claim without calling it complete or scheduling a duplicate send.
                wake.finish(store, a.org, a.member, None if state.get("delivery_possible") else error)
            wake.dispatch(store, a.org)  # messages that arrived while this seat or others were busy
        except Exception as error:  # the turn itself is recorded; the next dispatch elsewhere catches up
            state["after_turn_error"] = str(error)[-500:]
            runner.write_state(a.org, a.member, state)


if __name__ == "__main__":
    main()
