"""Members that are chats: they discuss, and have no files, commands or workspace.

Hongyi's request (2026-10-18): the chat modes of both apps join the organization, so a Claude chat and a ChatGPT chat
can write to each other and discuss through Relic. What they do differs from a coding member's, and so does how
messages reach them:

  chatgpt      A ChatGPT chat in the ChatGPT desktop app has no Relic tools. Relic acts for it: when messages arrive
               for its seat, a wake-up puts their full text into the chat through the desktop app (desktop.py) and
               follows the chat's turn. The app does not give plugins the text of a ChatGPT reply, and the chat cannot
               call the app's tools to send it out (tested 2026-10-18), so the reply waits on the seat until the person,
               who reads it in the ChatGPT window, forwards it in the Relic App (转发回复 on its card); it then reaches
               the members as this member's message (Store.forward_reply). Its seat is wakeable once the person
               seated the chat in the Relic App, which gives it the config {"harness": "chatgpt"}.
  claude-chat  A Claude chat in the Claude desktop app gets the Relic tools from the app's MCP configuration
               (claude_desktop_config.json; RELIC_ACTOR=claude-chat:<name> names the seat's actor). Nothing outside the
               app can start a turn there, so it drives the exchange itself: it messages a member, then calls inbox
               with wait until the answer is in, and so on. RELIC_MAX_WAIT keeps each wait under the app's tool
               time-out.

Neither has a transcript on this machine, so their trajectories cannot be requested, and strong protocols (enforced
on tool calls by the hooks) have nothing to act on for them.
"""
from . import desktop, i18n

INTRODUCED = "chat_introduced"  # seat field: the ChatGPT chat has been told what the organization is
# The ChatGPT app does not give its tools the text of a ChatGPT chat's replies: read_thread shows each one as
# "::chatgpt-content-reference{...}" (seen 2026-10-18; asking as the chat itself or with includeOutputs is refused or
# the same). Such a reply is never passed on as the member's words.
UNREADABLE = "::chatgpt-content-reference"
RECEIPT_MARK = "[Relic auto-receipt]"  # as in wake.py: a note that never wakes anyone
HUMAN = "human"  # the sender name of the person's own messages (Store.send_from_human)


def thread_of(seat):
    carrier = (seat or {}).get("carrier") or ""
    return carrier.split(":", 1)[1] if carrier.startswith("chatgpt:") else None


def chat_prompt(org, member, messages, introduce=False):
    """What a ChatGPT chat reads: who it is in the organization (the first time), then each message in full. It opens
    with the message ids, so the turn it starts can be told apart from anything the person types there."""
    ids = ",".join(str(m["id"]) for m in messages)
    t = i18n.t
    senders = list(dict.fromkeys(t("chatgpt.the_person") if m["from"] == HUMAN else m["from"] for m in messages))
    parts = ["【Relic · %s · msg %s】" % (org["name"], ids)]
    if introduce:
        others = [m for m in org["members"] if m != member]
        purpose = t("chatgpt.purpose", purpose=org["purpose"]) if org.get("purpose") else ""
        parts.append(t("chatgpt.intro", org=org["name"], member=member, purpose=purpose, others=others))
        parts.append(t("chatgpt.how"))
    for m in messages:
        if m["from"] == HUMAN:
            parts.append(t("chatgpt.from_person", id=m["id"]) + "\n" + m["body"])
        else:
            parts.append(t("chatgpt.from_member", member=m["from"], id=m["id"]) + "\n" + m["body"])
    parts.append(t("chatgpt.reply_to", names=senders))
    return "\n\n".join(parts)


def reply_recipients(org, member, writers):
    """Who a chat member's reply goes to: the members who wrote to it. When the person wrote too (the discussion room
    writes to everyone), every other member, so the members stay in step with each other."""
    members = [w for w in dict.fromkeys(writers) if w in org["members"] and w != member]
    if HUMAN in writers or not members:
        members = [m for m in org["members"] if m != member]
    return members


def run_chatgpt(store, org, member, prompt, hop=0, connect=desktop.connect, caller=lambda app: app.find_caller()):
    """One turn of a ChatGPT chat member. Returns (session, reply, failed) like the runner's other harnesses.

    With unread messages, the chat gets their full text (chat_prompt); they count as read once the prompt may have
    reached the chat. Its reply goes to their writers as this member's message, carrying the turn's depth (hop): when
    the app hides the reply's text (it always does today), the reply waits on the seat for the person to forward it,
    and the members it answers get a receipt saying so. Without unread messages (a task the person sent from the Relic
    window) the chat gets the prompt as it is. A prompt is never sent twice, so a turn that fails in the chat is
    reported rather than retried."""
    seat = org["members"][member]
    thread = thread_of(seat)
    if not thread:
        raise RuntimeError("%s has no ChatGPT chat yet: seat one in the Relic App (%s → %s)."
                           % (member, i18n.t("common.add_member"), i18n.t("member.run_existing")))
    app = connect()
    if not app:
        raise desktop.DesktopError("the ChatGPT desktop app is not running, so the chat of %s cannot be reached" % member)
    calling = caller(app)
    if not calling:
        raise desktop.DesktopError("no Codex thread the ChatGPT app accepts to make its tool calls with")
    messages = store.unread(seat["carrier"], mark=False, limit=20)
    text = chat_prompt(org, member, messages, introduce=not seat.get(INTRODUCED)) if messages else prompt
    reply, failed = desktop.run_turn(app, thread, text, host=None, caller=calling)  # raises if nothing was sent
    store.mark_read(org["id"], member, [m["id"] for m in messages])
    if messages and not seat.get(INTRODUCED):
        store.set_seat_fields(org["id"], member, **{INTRODUCED: True})
    if failed:
        return "chatgpt:" + thread, ("The chat's turn failed in the ChatGPT app; the messages were delivered and are "
                                     "not sent again. " + reply), False
    if not messages:
        return "chatgpt:" + thread, reply, False
    to = reply_recipients(org, member, [m["from"] for m in messages])
    if UNREADABLE in (reply or ""):
        ids = [m["id"] for m in messages]
        store.note_hidden_reply(org["id"], member, to, ids, hop)
        store.send_as(org["id"], member, to, (
            "%s %s answered msg %s in its ChatGPT chat. The ChatGPT app does not give the text of ChatGPT replies to "
            "plugins, so the person forwards the reply in the Relic App; it reaches you as a "
            "message from %s, usually within a few minutes. Keep waiting with inbox." % (
                RECEIPT_MARK, member, ",".join(str(i) for i in ids), member)))
        return "chatgpt:" + thread, ("(the reply is only in the ChatGPT window: forward it in the Relic App's "
                                     "discussion room)"), False
    if (reply or "").strip():
        store.send_as(org["id"], member, to, reply, hop=hop, relayed=True)
    return "chatgpt:" + thread, reply, False
