"""CI-only realistic visual fixture served by the real Relic HTTP handler.

No provider, runner, browser or member session is launched. The database belongs
to this process's output directory. UI clients all consume these same routes.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/relic"))


def seed(folder, lang):
    from relic_core import store as stores
    from relic_core.store import Store
    from app import prefs
    from PIL import Image, ImageDraw

    zh = lang == "zh-CN"
    def word(zh_text, en_text):
        return zh_text if zh else en_text
    workspace = folder / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text(word(
        "# 原生应用验收\n\n保留熟悉的三栏布局，使用系统原生控件。\n\n## 本周交付\n\n- 紧凑的组织树\n- 清晰的聊天与输入区\n- 浅色与深色主题\n\n| 项目 | 状态 |\n| --- | --- |\n| Windows | 审阅中 |\n| macOS | 审阅中 |\n",
        "# Native app review\n\nKeep the familiar three-column layout with native system controls.\n\n## This week\n\n- Compact organization tree\n- Clear conversation and composer\n- Light and dark themes\n\n| Project | Status |\n| --- | --- |\n| Windows | In review |\n| macOS | In review |\n"), encoding="utf-8")
    (workspace / "review.py").write_text('def review(platform: str) -> str:\n    """Keep evidence next to each decision."""\n    return f"Ready to review: {platform}"\n', encoding="utf-8")
    image = Image.new("RGB", (560, 300), "#f4f3f0")
    draw = ImageDraw.Draw(image)
    for xy, color in [((24, 24, 145, 276), "#e7e5df"), ((161, 24, 375, 276), "#ffffff"), ((391, 24, 536, 276), "#ffffff")]:
        draw.rounded_rectangle(xy, 12, fill=color)
    for y in (52, 94, 136, 178):
        draw.rounded_rectangle((176, y, 346, y + 28), 8, fill="#f6e8e0")
    image.save(workspace / "layout.png")
    store = Store()
    import itertools
    ids = itertools.count(1)
    stores.short_id = lambda prefix="": prefix + ("%06d" % next(ids))
    stores.now = lambda: "2026-10-29T11:00:00Z"
    lead, design, build = "visual-lead-session", "visual-design-session", "visual-build-session"
    parent = store.create("visual-parent", word("Relic 工作室", "Relic Studio"), word("让协作有据可查", "Make collaboration traceable"), "director")["id"]
    store.issue_by_person(parent, {"title": word("重要变更先评审", "Review important changes"), "rationale": word("保持团队行动一致", "Keep the team aligned"), "trigger": word("发布或修改共享行为时", "Before release or shared behavior changes"), "guidance": word("提交证据并等待本人确认。", "Present evidence and wait for the person's decision."), "inherit": True})
    oid = store.create(lead, word("秘书处", "Secretariat"), word("为 Hongyi Du 统筹 Codex 与 Claude Code 的日常协作，跟进任务、整理决策，并保留可核查的交付记录。", "Coordinate Hongyi Du's daily work with Codex and Claude Code, follow up tasks, organize decisions, and retain verifiable delivery records."), "secretary", word("秘书处负责人", "Secretary"))["id"]
    store.set_parent(oid, parent)
    store.set_seat_fields(oid, "secretary", secretary=True, display_name=word("秘书处负责人", "Secretary"), harness="claude-code", config={"harness": "claude-code", "surface": "cli", "folder": str(workspace), "model": "Claude"})
    for actor, name, role, harness in [(design, "designer", word("界面设计与交互", "Interface and interaction"), "claude-code"), (build, "engineer", word("原生应用开发", "Native app development"), "codex")]:
        store.join(actor, oid, name, role)
        store.set_seat_fields(oid, name, display_name=word("设计师" if name == "designer" else "工程师", "Designer" if name == "designer" else "Engineer"), harness=harness, config={"harness": harness, "surface": "cli", "folder": str(workspace), "model": harness})
    store.add_seat(oid, "reviewer", word("验收与回归检查", "Acceptance and regression checks"), {"harness": "codex", "surface": "cli", "folder": str(workspace)})
    store.add_seat(oid, "advisor", word("产品建议", "Product advice"), {"harness": "chatgpt", "surface": "chat"})
    store.set_auto_wake(oid, False)
    group = store.create_group(lead, word("原生界面验收", "Native interface review"), word("逐屏检查视觉与交互", "Review each screen and interaction"), "designer", members=["designer", "engineer"])["id"]
    store.set_focus(lead, oid)
    store.issue_by_person(oid, {"title": word("页面尽量保持一致", "Keep the pages consistent"), "rationale": word("两端应有相同的信息层次与操作顺序。", "Both platforms should share information hierarchy and action order."), "trigger": word("调整原生界面时", "When changing native screens"), "guidance": word("对照参考截图检查布局、文字、间距和状态。", "Compare layout, wording, spacing, and states with reference screenshots."), "inherit": True})
    store.work(lead, "task", {"title": word("确认通知与麦克风权限", "Confirm notification and microphone permissions"), "owner": "designer", "status": "blocked"})
    store.work(lead, "task", {"title": word("整理双平台截图", "Collect cross-platform screenshots"), "owner": "engineer", "status": "working"})
    done = store.work(lead, "task", {"title": word("检查消息与线程", "Review messages and threads"), "owner": "secretary"})
    # Fixture storage contains completed historical records; no tool or check program runs.
    with store.change(oid) as (o, db):
        o["episodes"]["E1"] = {"id": "E1", "title": word("原生页面复核", "Native screen review"), "status": "open", "participants": ["engineer"], "reflections": {}, "kind": "shared", "opened_at": stores.now()}
        o["members"]["engineer"]["turn_episode"] = "E1"
        o["tasks"][done["id"]].update(status="done", report=word("消息、引用与线程已逐项核对。", "Messages, quotes, and threads have been reviewed."), evidence=[str(workspace / "README.md")], done_at=stores.now())
        p = dict(o["protocols"]["P1"], id="P2", title=word("交付须附检查记录", "Attach checks to deliveries"), author="engineer", issued_by=None, strength="strong", summary_for_person=word("发送交付前确认附有检查结果；需要额外确认时交给本人决定。", "Before delivery, require check evidence and route exceptions to the person."), rules=[{"effect": "check", "tools": ["Bash"], "code": "result = {'decision': 'allow', 'reason': 'Evidence attached'}", "examples": []}], votes={"designer": {"vote": "approve"}}, inherit=True)
        o["protocols"]["P2"] = p
        o["counters"]["protocol"] = 2
        store._copy_to_person(db, o, p)
    store.record_activity(build, "Read", {"file_path": "README.md"}, cwd=str(workspace))
    store.record_activity(design, "Read", {"file_path": "layout.png"}, cwd=str(workspace))
    # Real transcript/session discovery formats, written as fixture data only.
    # No CLI, provider, peer bridge, or member session is started.
    project = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "visual-workspace"
    project.mkdir(parents=True)
    transcript = [
        {"type": "user", "timestamp": stores.now(), "cwd": str(workspace), "message": {"content": word("请核对本轮界面交付和截图记录。", "Review this delivery and its screenshot evidence.")}},
        {"type": "assistant", "timestamp": stores.now(), "message": {"model": "Claude", "content": [{"type": "text", "text": word("我先读取验收计划，再对照页面检查。", "I'll read the review plan and compare the screens.")}, {"type": "tool_use", "id": "visual-read", "name": "Read", "input": {"file_path": str(workspace / "README.md")}}]}},
        {"type": "user", "timestamp": stores.now(), "message": {"content": [{"type": "tool_result", "tool_use_id": "visual-read", "content": (workspace / "README.md").read_text(encoding="utf-8")}]}},
        {"type": "assistant", "timestamp": stores.now(), "message": {"content": [{"type": "text", "text": word("已列出三种窗口尺寸、两种语言和浅深主题的检查项。", "The checklist now covers three sizes, both languages, and light and dark themes.")}]}}
    ]
    (project / (lead + ".jsonl")).write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in transcript), encoding="utf-8")
    (project / "visual-existing-session.jsonl").write_text(json.dumps({"type": "user", "timestamp": stores.now(), "cwd": str(workspace), "message": {"content": word("准备接手原生界面的验收工作", "Prepare to review the native interface")}}, ensure_ascii=False), encoding="utf-8")
    # Keep activity states stable during the longer full screenshot matrix.
    from app import views
    from types import SimpleNamespace
    fixture_now = datetime.datetime(2026, 10, 29, 11, 2, tzinfo=datetime.timezone.utc).timestamp()
    # record_activity stores numeric wall time separately from stores.now().
    # These are historical fixture records, set before any client loads them.
    with store.db() as db:
        db.execute("UPDATE activity SET at = ?", (fixture_now - 120,))
    for path in (workspace / "README.md", workspace / "review.py", workspace / "layout.png", project / (lead + ".jsonl"), project / "visual-existing-session.jsonl"):
        os.utime(path, (fixture_now - 120, fixture_now - 120))
    views.time = SimpleNamespace(time=lambda: fixture_now, strptime=time.strptime, strftime=time.strftime, gmtime=time.gmtime)
    store.work(lead, "doc_write", {"key": "review-plan", "body": (workspace / "README.md").read_text(encoding="utf-8")})
    store.file_request(design, "leader", {"org": oid, "member": "engineer"}, word("让工程师协调本轮集成。", "Let the engineer coordinate this integration."))
    root_message = store.send_from_human(oid, ["all"], word("这轮请把两个平台的页面放在一起看。布局要一致，也要像各自系统里完成度高的应用。", "Please compare both platforms side by side. Keep the layout consistent and make each feel like a finished desktop app."), channel="group")
    everyone = list(store.get(oid)["members"]) + ["human"]
    store.send_as(oid, "secretary", everyone, word("收到。我会按 **聊天、概况、工作区、设置** 的顺序整理验收记录。\n\n需要您决定的事项会留在右侧，不打断当前对话。", "Understood. I'll organize review evidence for **Chat, Overview, Workspace, and Settings**.\n\nDecisions will stay in the right pane without interrupting the conversation."))
    store.send_as(oid, "designer", everyone, word("组织树使用紧凑行；消息保留头像、名称和时间。输入框里的工具会收在同一行。", "The tree uses compact rows. Messages keep avatars, names, and times. Composer tools stay on one line."))
    store.send_as(oid, "engineer", everyone, word("工作区中的 `README.md` 已补充检查项。\n\n```python\nreview('Windows')\nreview('macOS')\n```", "The workspace `README.md` now includes review items.\n\n```python\nreview('Windows')\nreview('macOS')\n```"))
    store.send_as(oid, "designer", ["human"], word("三个窗口尺寸都会检查，长标题会换行或显示省略提示。", "I'll check all three window sizes. Long titles will wrap or show an ellipsis with a tooltip."), reply_to=root_message)
    store.send_from_human(oid, ["secretary"], word("请先整理今天需要我决定的事项。", "Please summarize the decisions I need to make today."), channel="private")
    store.send_as(oid, "secretary", ["human"], word("目前有两项：确认权限设置，以及本轮集成负责人。任务和相关协议都在右侧概况中。", "There are two items: confirm permissions and choose the integration lead. Tasks and related protocols are in Overview."))
    prefs.save({"lang": lang, "theme": "light", "name": "Hongyi Du", "voice": "browser", "notify": False, "font": "medium", "density": "comfortable"})
    return store, {"org": oid, "parent": parent, "subgroup": group, "member": "secretary", "thread": str(root_message), "task": done["id"], "workspace": str(workspace), "files": {"markdown": str(workspace / "README.md"), "code": str(workspace / "review.py"), "image": str(workspace / "layout.png")}}


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Visual fixture is CI-only; it must not launch on the person's computer.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lang", choices=["en-US", "zh-CN"], required=True)
    args = parser.parse_args()
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    os.environ.update(RELIC_HOME=str(folder / "relic"), RELIC_LANG=args.lang, CLAUDE_CONFIG_DIR=str(folder / "claude"), CODEX_HOME=str(folder / "codex"))
    from app import web
    store, fixture = seed(folder, args.lang)
    app, server = web.serve(0, store)
    fixture.update(port=app.port, token=app.token, instance=app.instance, pid=os.getpid(), lang=args.lang, home=os.environ["RELIC_HOME"])
    (folder / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        app.stopping.set()
        server.server_close()


if __name__ == "__main__":
    main()
