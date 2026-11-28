"""Synthetic-only profile matching the 2026-11-02 aggregate store measurements.

No human content or identifiers are read. The reported 2.53 million characters
is represented as exactly 2,530,000 Unicode code points. Median is the mean of
the two central sorted lengths; p90/p99 use nearest rank (ceil(p*n), 1-based).
Only those reported aggregates are matched. The distribution between those
quantiles, private/group split, event kinds and task metadata are synthetic
choices, not claims about the person's unmeasured joint distribution.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
from pathlib import Path
import random
import re
import statistics

BASE = dt.datetime(2026, 10, 30, 10, tzinfo=dt.timezone.utc)
ORG_MESSAGES = (1506, 1337, 856, 561, 48, 40, 32, 24, 20, 16, 12, 10, 8, 6)
ORG_SEATS = (7, 6, 5, 5, 4, 4, 3, 3, 3, 3, 3, 3, 3, 3)
EXPECTED = {"organizations": 14, "actors": 39, "seats": 55, "messages": 4476,
            "message_chars": 2530000, "events": 14517, "activity": 30904, "reads": 6686,
            "bullet_messages": 612, "table_messages": 33, "code_messages": 14,
            "link_messages": 99, "reply_threads": 153}


def timestamp(number: int) -> str:
    return (BASE + dt.timedelta(seconds=number)).strftime("%Y-%m-%dT%H:%M:%SZ")


def message_lengths(seed_value: int) -> list[int]:
    # 2,237 entries below the median, two at 460; rank 4,029 is 935,
    # rank 4,432 is 2,467, and the final rank is 11,251. Raising 117 of
    # the 417-length rows to 418 yields the exact reported total.
    values = ([418] * 117 + [417] * (2237 - 117) + [460] * 2
              + [600] * 1789 + [935] + [1000] * 402 + [2467] * 44 + [11251])
    random.Random(seed_value).shuffle(values)
    return values


def synthetic_body(index: int, length: int) -> str:
    text = f"合成记录 {index + 1:04} / Synthetic record.\n\n"
    if index < 612:
        text += "- **交付检查**：保留测试证据。\n- **响应检查**：点击后显示最新消息。\n\n"
    elif index < 645:
        text += "| 项目 | 结果 |\n| --- | --- |\n| 窗口 | 合成待验收 |\n| 消息 | 合成记录 |\n\n"
    elif index < 659:
        text += "```python\nfor chat in synthetic_chats:\n    inspect(chat)\n```\n\n"
    elif index < 758:
        text += "[合成说明 / Synthetic instructions](https://example.invalid/synthetic)\n\n"
    filler = "这段文字仅用于合成负载，不来自任何人的聊天。 Check native rendering, selection and navigation. "
    if len(text) > length:
        raise ValueError("Synthetic markup exceeds its assigned length")
    return text + (filler * math.ceil((length - len(text)) / len(filler)))[:length - len(text)]


def measured_shape(store) -> dict:
    """Measure the generated database, rather than trusting generator counters."""
    with store.db() as db:
        counts = {label: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                  for label, table in (("organizations", "orgs"), ("actors", "actors"), ("seats", "seats"),
                                       ("messages", "messages"), ("events", "events"),
                                       ("activity", "activity"), ("reads", "reads"))}
        bodies = [row[0] for row in db.execute("SELECT body FROM messages ORDER BY id")]
        counts["reply_threads"] = db.execute("SELECT COUNT(DISTINCT reply_to) FROM messages WHERE reply_to IS NOT NULL").fetchone()[0]
        counts["message_chars"] = sum(map(len, bodies))
        counts["bullet_messages"] = sum(bool(re.search(r"(?m)^[-*+] ", body)) for body in bodies)
        counts["table_messages"] = sum(bool(re.search(r"(?m)^\|\s*---", body)) for body in bodies)
        counts["code_messages"] = sum("```" in body for body in bodies)
        counts["link_messages"] = sum(bool(re.search(r"\[[^\]]+\]\(https?://", body)) for body in bodies)
        lengths = sorted(map(len, bodies))
        counts.update(median_body_chars=statistics.median(lengths),
                      p90_body_chars=lengths[math.ceil(.90 * len(lengths)) - 1],
                      p99_body_chars=lengths[math.ceil(.99 * len(lengths)) - 1], max_body_chars=max(lengths))
        return counts


def seed_person_shape(folder: Path, seed_value: int = 1729):
    from app import prefs
    from relic_core import store as stores
    from relic_core.store import Store

    workspace = folder / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Entirely synthetic person-shaped fixture\n\nNo human messages are used.\n", encoding="utf-8")
    for index in range(25):
        (workspace / f"review-{index:02}.txt").write_text(f"Synthetic review file {index}.\n", encoding="utf-8")
    original_id, original_now = stores.short_id, stores.now
    counter = itertools.count(1)
    stores.short_id = lambda prefix: prefix + f"shape{next(counter):06d}"
    stores.now = lambda: timestamp(0)
    lengths = message_lengths(seed_value)
    store = Store()
    orgs, all_rows, seats = [], [], []
    message_ordinal = seat_ordinal = 0
    try:
        for org_index, (message_count, seat_count) in enumerate(zip(ORG_MESSAGES, ORG_SEATS)):
            members = ["secretary"] + [f"member{index:02}" for index in range(1, seat_count)]
            actor = f"synthetic-shape-{seat_ordinal % 39:02}"
            created = store.create(actor, f"合成组织 {org_index + 1:02}（实测规模）",
                                   "Synthetic aggregate-shape responsiveness data; no human content.", "secretary", "协调工作")
            oid = created["id"]
            config = {"harness": "chatgpt", "surface": "chat", "folder": str(workspace)}
            store.set_seat_fields(oid, "secretary", secretary=True, display_name="合成秘书", config=dict(config))
            seats.append((oid, "secretary"))
            seat_ordinal += 1
            for index, member in enumerate(members[1:], 1):
                actor = f"synthetic-shape-{seat_ordinal % 39:02}"
                store.add_seat(oid, member, f"合成职责 {index:02}", config=dict(config))
                store.join(actor, oid, member)
                seats.append((oid, member))
                seat_ordinal += 1
            store.set_auto_wake(oid, False)
            store.issue_by_person(oid, {"title": "保留验收证据", "rationale": "完全合成资料",
                                       "trigger": "修改共享行为时", "guidance": "记录测试结果", "inherit": True})
            with store.change(oid) as (org, db):
                for index in range(30):
                    tid = f"T{index + 1}"
                    org["tasks"][tid] = {"id": tid, "title": f"合成任务 {index + 1}",
                        "owner": members[index % seat_count], "status": ("open", "working", "blocked", "done")[index % 4],
                        "created_by": "secretary", "at": timestamp(index),
                        "evidence": [str(workspace / "README.md")], "report": "Synthetic evidence."}
                org["counters"]["task"] = 30
                for index in range(8 if org_index < 7 else 7):
                    eid = f"E{index + 1}"
                    org["episodes"][eid] = {"id": eid, "title": f"合成阶段 {index + 1}", "status": "closed",
                        "kind": "shared", "participants": members, "reflections": {}, "opened_at": timestamp(index),
                        "outcome": "Synthetic historical work."}
                org["counters"]["episode"] = len(org["episodes"])
                for index in range(2, 13):
                    org["protocols"][f"P{index}"] = dict(org["protocols"]["P1"], id=f"P{index}",
                        title=f"合成协议 {index}", inherit=bool(index % 2))
                org["counters"]["protocol"] = 12

            # Every member has one actual private message. The remaining rows
            # are group messages; 153 distinct roots each receive one reply.
            group_rows = message_count - seat_count
            replies = 153 if org_index == 0 else 0
            with store.db() as db:
                first_id = (db.execute("SELECT MAX(id) FROM messages").fetchone()[0] or 0) + 1
                rows = []
                for index in range(message_count):
                    body = synthetic_body(message_ordinal, lengths[message_ordinal])
                    message_ordinal += 1
                    if index >= group_rows:
                        sender, recipients = "human", [members[index - group_rows]]
                    else:
                        sender = "human" if index % 7 == 0 else members[index % seat_count]
                        recipients = members if sender == "human" else members + ["human"]
                    reply_to = first_id + index - 153 if org_index == 0 and 153 <= index < 306 else None
                    row = (oid, sender, json.dumps(recipients), body, None, timestamp(index + 100), 0, reply_to)
                    rows.append(row)
                    all_rows.append((first_id + index, oid, recipients))
                db.executemany("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) VALUES(?,?,?,?,?,?,?,?)", rows)
            orgs.append({"id": oid, "members": members, "total_messages": message_count,
                         "group_messages": group_rows - replies, "private_messages": seat_count,
                         "reply_messages": replies, "first_group_message_id": first_id,
                         "latest_group_message_id": first_id + group_rows - 1,
                         "latest_private_message_ids": {member: first_id + group_rows + index
                                                        for index, member in enumerate(members)},
                         "group_expected_empty": False,
                         "private_expected_empty": {member: False for member in members}})

        with store.db() as db:
            remaining_events = EXPECTED["events"] - db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            events = []
            for index in range(remaining_events):
                # Preserve large stored-event volume without pretending every
                # event is a visible notice: four tool checks per task notice.
                target = orgs[index % len(orgs)]
                member = target["members"][index % len(target["members"])]
                kind = "task.updated" if index % 5 == 0 else "tool.checked"
                body = {"id": f"T{index % 30 + 1}", "status": "done"} if kind == "task.updated" else {"tool": "Read", "result": "allow"}
                events.append((target["id"], member, kind, json.dumps(body), timestamp(100 + index % target["total_messages"])))
            db.executemany("INSERT INTO events(org_id,member,kind,body,at) VALUES(?,?,?,?,?)", events)
            activities = []
            for index in range(EXPECTED["activity"]):
                oid, member = seats[index % len(seats)]
                activities.append((oid, member, "Read", "read", f"Synthetic activity {index + 1}", 0,
                                   BASE.timestamp() + index, "[]"))
            db.executemany("INSERT INTO activity(org_id,member,tool,kind,summary,failed,at,paths) VALUES(?,?,?,?,?,?,?,?)", activities)
            reads = [(oid, mid, recipients[0], timestamp(mid + 200)) for mid, oid, recipients in all_rows]
            extra = EXPECTED["reads"] - len(reads)
            reads.extend((oid, mid, recipients[1], timestamp(mid + 201))
                         for mid, oid, recipients in all_rows if len(recipients) > 1)
            reads = reads[:len(all_rows) + extra]
            db.executemany("INSERT INTO reads(org_id,message_id,member,at) VALUES(?,?,?,?)", reads)
        counts = measured_shape(store)
        if any(counts[key] != value for key, value in EXPECTED.items()):
            raise AssertionError("Generated store does not match the required synthetic aggregate shape")
        counts.update(members=55, group_messages=sum(org["group_messages"] for org in orgs), private_messages=55,
                      reply_messages=153, tasks=420, episodes=105, protocols=168,
                      long_markdown_messages=sum(index < 758 and length > 2000 for index, length in enumerate(lengths)))
        prefs.save({"lang": "zh-CN", "theme": "light", "name": "Synthetic Person", "voice": "browser",
                    "notify": False, "font": "medium", "density": "comfortable"})
        return store, {"profile": "person-shape", "orgs": orgs, "workspace": str(workspace), "counts": counts,
                       "seed": seed_value, "shape_metadata": {
                           "source": "Only the aggregate counts supplied in Amendment 9; all contents and identities are synthetic.",
                           "character_total": "2.53 million represented as exactly 2,530,000 Unicode code points",
                           "quantiles": "median=mean of central pair; p90/p99=nearest rank ceil(p*n), 1-based",
                           "unmeasured_choices": "one private message per seat; 153 one-reply threads in first org; 4 tool checks per visible task event; synthetic task/episode/protocol metadata"}}
    finally:
        stores.short_id, stores.now = original_id, original_now
