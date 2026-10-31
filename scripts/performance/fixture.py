"""Synthetic, isolated large-store fixture. No access to the person's store."""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
from pathlib import Path
import random
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins" / "relic"))
BASE = dt.datetime(2026, 10, 30, 10, tzinfo=dt.timezone.utc)


def timestamp(number: int) -> str:
    return (BASE + dt.timedelta(seconds=number)).strftime("%Y-%m-%dT%H:%M:%SZ")


def message_body(index: int, org: int) -> str:
    heading = f"合成压力消息 {org + 1}/{index + 1} — Synthetic responsiveness record"
    if index % 13 == 0:
        paragraph = ("这是一段完全合成的较长交付说明，用来验证消息换行、选择和虚拟列表回收。"
                     "实际工作包含任务、协议、决策与文件；界面必须保持可交互。 "
                     "The native interface must stay responsive while processing long messages. ")
        return (f"# {heading}\n\n" + "\n\n".join(paragraph * 3 for _ in range(12))
                + "\n\n```python\nfor platform in ['windows', 'macos']:\n    review(platform)\n```\n"
                "\n| 项目 | 结果 |\n| --- | --- |\n| 消息 | 待检查 |\n| 窗口 | 待检查 |\n")
    if index % 4 == 0:
        return f"{heading}\n\n- **原生窗口**与当前显示器相适应。\n- 保持 `UI dispatcher` 可响应。\n\n> 合成引用，不含任何人的数据。"
    return f"{heading}。检查页面、任务和协议，保留可核查的记录。"


def seed(folder: Path, seed_value: int = 1729):
    """Bulk insert historical rows, while creating valid org/seat records via Store."""
    from app import prefs
    from relic_core import store as stores
    from relic_core.store import Store

    workspace = folder / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Synthetic large workspace\n\n" + message_body(0, 0), encoding="utf-8")
    for index in range(25):
        (workspace / f"review-{index:02}.txt").write_text(message_body(index, 0), encoding="utf-8")
    original_id, original_now = stores.short_id, stores.now
    counter = itertools.count(1)
    stores.short_id = lambda prefix: prefix + f"perf{next(counter):06d}"
    stores.now = lambda: timestamp(0)
    store = Store()
    orgs = []
    rng = random.Random(seed_value)
    totals = {"organizations": 13, "members": 0, "messages": 0, "group_messages": 0,
              "private_messages": 0, "tasks": 0, "events": 0, "episodes": 0, "protocols": 0,
              "long_markdown_messages": 0, "max_body_chars": 0}
    try:
        for org_index in range(13):
            actor = f"synthetic-secretary-{org_index}"
            created = store.create(actor, "秘书处（合成压力数据）" if org_index == 0 else f"合成组织 {org_index + 1:02}",
                                   "CI responsiveness fixture; contains no personal data.", "secretary", "协调工作")
            oid = created["id"]
            count = 42 if org_index == 0 else 4
            members = ["secretary"] + [f"member{n:02}" for n in range(1, count)]
            config = {"harness": "chatgpt", "surface": "chat", "folder": str(workspace)}
            store.set_seat_fields(oid, "secretary", secretary=True, display_name="合成秘书", config=config)
            for index, member in enumerate(members[1:], 1):
                store.add_seat(oid, member, f"合成成员职责 {index:02}", config=dict(config))
            store.set_auto_wake(oid, False)
            store.issue_by_person(oid, {"title": "交付须有证据", "rationale": "合成压力数据",
                                       "trigger": "修改共享行为时", "guidance": "记录测试结果", "inherit": True})
            task_count = 180 if org_index == 0 else 20
            episode_count = 45 if org_index == 0 else 5
            with store.change(oid) as (org, db):
                for index in range(task_count):
                    tid = f"T{index + 1}"
                    status = ("open", "working", "blocked", "done")[index % 4]
                    org["tasks"][tid] = {"id": tid, "title": f"合成验收任务 {index + 1}：检查长消息、布局与事件",
                                         "owner": members[index % count], "status": status, "created_by": "secretary",
                                         "at": timestamp(index), "evidence": [str(workspace / "README.md")],
                                         "report": "Synthetic historical record."}
                org["counters"]["task"] = task_count
                for index in range(episode_count):
                    eid = f"E{index + 1}"
                    org["episodes"][eid] = {"id": eid, "title": f"合成工作阶段 {index + 1}",
                                            "status": "closed" if index % 2 else "open", "kind": "shared",
                                            "participants": members[:4], "reflections": {}, "opened_at": timestamp(index),
                                            "outcome": "Synthetic historical work."}
                org["counters"]["episode"] = episode_count
                template = org["protocols"]["P1"]
                for index in range(2, 13):
                    org["protocols"][f"P{index}"] = dict(template, id=f"P{index}", title=f"合成协议 {index}", inherit=bool(index % 2))
                org["counters"]["protocol"] = 12
            group_count = 5500 if org_index == 0 else 1250 if org_index < 4 else 100
            first_id = None
            rows = []
            for index in range(group_count):
                body = message_body(index, org_index)
                totals["max_body_chars"] = max(totals["max_body_chars"], len(body))
                totals["long_markdown_messages"] += index % 13 == 0
                sender = "human" if index % 7 == 0 else members[index % count]
                recipients = members if sender == "human" else members + ["human"]
                rows.append((oid, sender, json.dumps(recipients), body, None, timestamp(index + 100), 0, None))
            with store.db() as db:
                first_id = (db.execute("SELECT MAX(id) FROM messages").fetchone()[0] or 0) + 1
                db.executemany("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) VALUES(?,?,?,?,?,?,?,?)", rows)
                private_rows = []
                for member_index, member in enumerate(members):
                    for index in range(24):
                        sender, recipients = ("human", [member]) if index % 2 == 0 else (member, ["human"])
                        private_rows.append((oid, sender, json.dumps(recipients), message_body(index, org_index), None,
                                             timestamp(group_count + member_index * 24 + index + 200), 0, None))
                db.executemany("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) VALUES(?,?,?,?,?,?,?,?)", private_rows)
                event_count = 350 if org_index == 0 else 20
                events = [(oid, rng.choice(members), "task.updated",
                           json.dumps({"id": f"T{index % task_count + 1}", "status": "blocked" if index % 2 else "done"}),
                           timestamp(100 + int(index * group_count / event_count))) for index in range(event_count)]
                db.executemany("INSERT INTO events(org_id,member,kind,body,at) VALUES(?,?,?,?,?)", events)
            orgs.append({"id": oid, "members": members, "group_messages": group_count, "first_group_message_id": first_id})
            totals["members"] += count
            totals["group_messages"] += group_count
            totals["private_messages"] += len(private_rows)
            totals["tasks"] += task_count
            totals["episodes"] += episode_count
            totals["protocols"] += 12
        with store.db() as db:
            totals["events"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            totals["messages"] = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        prefs.save({"lang": "zh-CN", "theme": "light", "name": "Synthetic Person", "voice": "browser",
                    "notify": False, "font": "medium", "density": "comfortable"})
        return store, {"orgs": orgs, "workspace": str(workspace), "counts": totals, "seed": seed_value}
    finally:
        stores.short_id, stores.now = original_id, original_now


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Synthetic native performance runs are CI-only.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ.update(RELIC_HOME=str(folder / "relic"), RELIC_LANG="zh-CN", CLAUDE_CONFIG_DIR=str(folder / "claude"),
                      CODEX_HOME=str(folder / "codex"))
    from app import web
    store, fixture = seed(folder, args.seed)
    app, server = web.serve(0, store)
    fixture.update(port=app.port, token=app.token, instance=app.instance, pid=os.getpid(), home=os.environ["RELIC_HOME"],
                   monkey_trigger=str(folder / "monkey-enabled"), live_report=str(folder / "live-updates.json"))
    (folder / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    # Fixed producer count and bounded rate: stress event coalescing without
    # starting providers or creating one task/thread per update.
    def hints():
        ordinal = 0
        monkey_ordinal = 0
        events_published = stored_messages = 0
        while not app.stopping.wait(.1):
            monkey_active = (folder / "monkey-enabled").exists()
            if monkey_active:
                target = fixture["orgs"][(monkey_ordinal // 20) % len(fixture["orgs"])]
                if monkey_ordinal % 20 == 0:
                    # Genuine stored messages plus ordinary app event delivery;
                    # no provider, wake, CLI, or extra thread per message.
                    with store.db() as db:
                        db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop,reply_to) VALUES(?,?,?,?,?,?,?,?)",
                                   (target["id"], "human", json.dumps(target["members"]),
                                    f"合成实时更新 {stored_messages + 1}\n\n" + message_body(stored_messages + 1, 0),
                                    None, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), 0, None))
                    stored_messages += 1
                app.bus.publish({"type": "org", "org": target["id"]})
                events_published += 1
                monkey_ordinal += 1
            elif ordinal % 50 < 10:
                app.bus.publish({"type": "org", "org": fixture["orgs"][ordinal % 13]["id"]})
            if ordinal % 10 == 0:
                data = {"events_published": events_published, "stored_messages": stored_messages,
                        "worker_threads": 1, "monkey_active": monkey_active,
                        "source": "Real app.bus SSE hints and synthetic rows in the isolated real store"}
                temporary = folder / "live-updates.tmp"
                temporary.write_text(json.dumps(data), encoding="utf-8")
                temporary.replace(folder / "live-updates.json")
            ordinal += 1
    worker = threading.Thread(target=hints, name="synthetic-sse-bursts", daemon=True)
    worker.start()
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        app.stopping.set()
        worker.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
