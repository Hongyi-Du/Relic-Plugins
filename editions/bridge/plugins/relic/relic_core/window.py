"""The Relic Bridge window: found organizations, add members on Claude Code or Codex, configure and start their
sessions, seat existing chats, answer trajectory requests, and message members. Standard library (tkinter) only.

The discussion room (讨论室) shows the organization's messages in full as they come, and the person writes to members
there. It is how a ChatGPT chat member takes part in a discussion (Hongyi's fallback of 2026-10-18, "几方的聊天室"):
Relic puts messages into the chat by itself, but the ChatGPT app keeps the chat's replies from plugins, so the person
copies each reply in the ChatGPT window and forwards it here, as that member's message (Store.forward_reply).

Besides the turns the person starts here, auto-wake (wake.py, on by default, switchable per organization in the
组织状态 tab) starts a turn for a configured seat that has new unread messages, including the person's own messages.
When the plugin is updated while the window is open, the window reopens itself on the new code, as soon as no dialog
is open and nothing typed would be lost.
"""
import calendar
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from . import code_stamp, runner, wake
from .chat import UNREADABLE
from .sessions import actor_for, all_sessions
from .store import OrgError, Store

HARNESS_LABEL = {"claude-code": "Claude Code", "codex": "Codex", "chatgpt": "ChatGPT", "claude-chat": "Claude"}
SURFACE_LABEL = {"cli": "命令行", "gui": "桌面版", "chat": "聊天"}
KINDS = [("claude-code", "cli"), ("claude-code", "gui"), ("codex", "cli"), ("codex", "gui")]


def kind_label(harness, surface):
    return "%s · %s" % (HARNESS_LABEL.get(harness, harness), SURFACE_LABEL.get(surface or "cli", surface))
STATUS_LABEL = {"running": "运行中", "done": "空闲", "failed": "出错", None: "未启动"}


def _when(epoch):
    return time.strftime("%m-%d %H:%M", time.localtime(epoch)) if epoch else ""


def _local(at):
    """A stored time (UTC, store.now()) as local month-day hour:minute."""
    try:
        return _when(calendar.timegm(time.strptime(at, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return at or ""


def _who(name):
    return "你" if name == "human" else name


def open_path(path):
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 - opens the file with the person's default app
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class MemberDialog(tk.Toplevel):
    """New member, or edit an existing member's configuration."""

    def __init__(self, app, org, member=None):
        super().__init__(app.root)
        self.app, self.org, self.member = app, org, member
        seat = org["members"].get(member) if member else None
        config = dict(runner.default_config("claude-code"), **((seat or {}).get("config") or {}))
        if seat and not (seat.get("config") or {}).get("harness") and seat.get("harness"):
            config["harness"] = seat["harness"]
        self.title("修改成员配置" if member else "新建成员")
        self.transient(app.root)
        self.resizable(True, False)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self.vars = {k: tk.StringVar(value=str(config.get(k) or "")) for k in
                     ("model", "effort", "folder", "environment", "permission")}
        self.name = tk.StringVar(value=member or "")
        self.role = tk.StringVar(value=(seat or {}).get("role", ""))
        self.harness = tk.StringVar(value=config["harness"])
        self.kind = tk.StringVar(value="%s/%s" % (config["harness"], config.get("surface") or "cli"))
        row = 0

        def label(text):
            nonlocal row
            ttk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))

        label("名字")
        name_entry = ttk.Entry(frame, textvariable=self.name, width=36)
        name_entry.grid(row=row, column=1, columnspan=2, sticky="ew")
        if member:
            name_entry.state(["disabled"])
        row += 1
        label("角色")
        ttk.Entry(frame, textvariable=self.role).grid(row=row, column=1, columnspan=2, sticky="ew")
        row += 1
        label("Harness")
        box = ttk.Frame(frame)
        box.grid(row=row, column=1, columnspan=2, sticky="w")
        for n, (harness, surface) in enumerate(KINDS):
            ttk.Radiobutton(box, text=kind_label(harness, surface), value="%s/%s" % (harness, surface),
                            variable=self.kind, command=self.harness_changed).grid(row=n // 2, column=n % 2,
                                                                                  sticky="w", padx=(0, 18))
        row += 1
        label("模型")
        self.model_box = ttk.Combobox(frame, textvariable=self.vars["model"], state="readonly")
        self.model_box.grid(row=row, column=1, columnspan=2, sticky="ew")
        row += 1
        label("推理强度")
        ttk.Combobox(frame, textvariable=self.vars["effort"], values=runner.EFFORTS, state="readonly").grid(
            row=row, column=1, sticky="w")
        row += 1
        label("工作文件夹")
        ttk.Entry(frame, textvariable=self.vars["folder"]).grid(row=row, column=1, sticky="ew")
        ttk.Button(frame, text="浏览…", command=self.browse).grid(row=row, column=2, padx=(6, 0))
        row += 1
        label("环境")
        box = ttk.Frame(frame)
        box.grid(row=row, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(box, text="本地文件夹", value="local", variable=self.vars["environment"]).pack(side="left")
        ttk.Radiobutton(box, text="独立 git worktree", value="worktree",
                        variable=self.vars["environment"]).pack(side="left", padx=14)
        row += 1
        label("权限")
        self.permission_box = ttk.Combobox(frame, textvariable=self.vars["permission"], state="readonly")
        self.permission_box.grid(row=row, column=1, sticky="w")
        row += 1
        label("环境变量")
        self.env_text = tk.Text(frame, height=4, width=36, font=app.mono)
        self.env_text.grid(row=row, column=1, columnspan=2, sticky="ew")
        self.env_text.insert("1.0", "\n".join("%s=%s" % kv for kv in (config.get("env") or {}).items()))
        row += 1
        ttk.Label(frame, text="每行一个 NAME=value", foreground="#777").grid(row=row, column=1, sticky="w")
        row += 1
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        if member:
            ttk.Button(buttons, text="保存", command=self.save).pack(side="right", padx=6)
        else:
            ttk.Button(buttons, text="创建并开会话", command=lambda: self.save(start=True)).pack(side="right", padx=6)
            ttk.Button(buttons, text="只建席位", command=self.save).pack(side="right")
        self.harness_changed(keep=True)
        self.grab_set()

    def harness_changed(self, keep=False):
        harness = self.kind.get().split("/")[0]
        changed = harness != self.harness.get()
        self.harness.set(harness)
        keep = keep or not changed
        allowed = runner.CLAUDE_MODES if harness == "claude-code" else runner.CODEX_SANDBOXES
        self.permission_box["values"] = allowed
        if not keep or self.vars["permission"].get() not in allowed:
            self.vars["permission"].set(allowed[0])
        if not keep:
            self.vars["model"].set("")
        self.model_box["values"] = runner.CLAUDE_MODELS if harness == "claude-code" else [""] + self.app.codex_models

    def browse(self):
        folder = filedialog.askdirectory(parent=self, initialdir=self.vars["folder"].get() or str(Path.home()))
        if folder:
            self.vars["folder"].set(folder)

    def save(self, start=False):
        config = {k: v.get().strip() for k, v in self.vars.items()}
        harness, surface = self.kind.get().split("/")
        config.update(harness=harness, surface=surface, env=runner.parse_env(self.env_text.get("1.0", "end")))
        try:
            runner.checked_permission(config)
            runner.checked_model(config)
            name = self.name.get().strip()
            if self.member:
                self.app.store.set_config(self.org["id"], name, config)
                if self.role.get().strip() != self.org["members"][name].get("role", ""):
                    self.app.store.add_seat(self.org["id"], name, self.role.get().strip())
            else:
                self.app.store.add_seat(self.org["id"], name, self.role.get().strip(), config)
                if start:
                    org = self.app.store.get(self.org["id"])
                    runner.start_turn(org["id"], name, runner.introduction(org, name), new_session=True, open_after=True)
        except (OrgError, RuntimeError, OSError) as error:
            messagebox.showerror("Relic", str(error), parent=self)
            return
        self.destroy()
        self.app.refresh()


class ForwardDialog(tk.Toplevel):
    """Forward a ChatGPT chat member's reply that the person copied in the ChatGPT window."""

    def __init__(self, app, org, chats):
        super().__init__(app.root)
        self.app, self.org = app, org
        self.title("转发 GPT 的回复")
        self.transient(app.root)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=("在 ChatGPT 窗口里点 GPT 那条回复下面的“复制”，回到这里：内容会自动填进来（也可以直接粘贴、修改）。"
                               "发出后它就是这个成员的消息。"), foreground="#555", wraplength=640,
                  justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        waiting = [c for c in chats if org["members"][c].get(Store.WAITING)]
        self.member = tk.StringVar(value=(waiting or chats)[0])
        ttk.Label(frame, text="谁的回复").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        box = ttk.Combobox(frame, textvariable=self.member, values=chats, state="readonly", width=24)
        box.grid(row=1, column=1, sticky="w")
        box.bind("<<ComboboxSelected>>", lambda e: self.member_changed())
        ttk.Label(frame, text="发给").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
        self.to = tk.StringVar()
        ttk.Entry(frame, textvariable=self.to).grid(row=2, column=1, columnspan=2, sticky="ew")
        self.note = ttk.Label(frame, text="", foreground="#a15c00", wraplength=640, justify="left")
        self.note.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 6))
        self.text = tk.Text(frame, height=16, width=80, wrap="word", font=app.reading)
        self.text.grid(row=4, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(4, weight=1)
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(buttons, text="从剪贴板粘贴", command=self.paste).pack(side="left")
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="发送", command=self.send).pack(side="right", padx=6)
        self.member_changed()
        self.paste()
        self.grab_set()

    def member_changed(self):
        name = self.member.get()
        waiting = self.org["members"][name].get(Store.WAITING) or []
        if waiting:
            first = waiting[0]
            self.to.set(",".join(first["to"]))
            self.note.configure(text="%s 有 %d 条回复等你转发。这一条回的是 msg %s；按顺序转，先复制最早的那条。" % (
                name, len(waiting), ",".join(str(i) for i in first["ids"])))
        else:
            self.to.set(",".join(m for m in self.org["members"] if m != name))
            self.note.configure(text="%s 现在没有等着转发的回复：发出去就是它的一条新消息。" % name)

    def paste(self):
        try:
            text = self.app.root.clipboard_get()
        except tk.TclError:
            return
        if text.strip():
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text.strip())

    def send(self):
        body = self.text.get("1.0", "end").strip()
        to = [t.strip() for t in self.to.get().split(",") if t.strip()]
        if body.startswith("【Relic") and not messagebox.askyesno(
                "Relic", "这段以“【Relic”开头，像是 Relic 发给 GPT 的消息，不是 GPT 的回复。还是发出去？", parent=self):
            return
        try:
            self.app.store.forward_reply(self.org["id"], self.member.get(), to, body)
        except OrgError as error:
            messagebox.showerror("Relic", str(error), parent=self)
            return
        self.destroy()
        self.app.dispatch_soon(self.org["id"])
        self.app.refresh()


class App:
    def __init__(self, store=None):
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        self.store = store or Store()
        self.stamp = code_stamp()
        self.root = tk.Tk()
        self.root.title("Relic Bridge")
        self.root.geometry("1080x680")
        self.root.minsize(860, 540)
        if os.name == "nt":
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                try:
                    tkfont.nametofont(name).configure(family="Microsoft YaHei UI")
                except tk.TclError:
                    pass
        self.mono = ("Consolas", 10) if os.name == "nt" else ("DejaVu Sans Mono", 10)
        self.reading = ("Microsoft YaHei UI", 10) if os.name == "nt" else tkfont.nametofont("TkDefaultFont")
        self.bold = tkfont.Font(root=self.root, font=self.reading)
        self.bold.configure(weight="bold")
        self.room_shown = (None, 0)  # discussion room: the organization shown and the last message id in it
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Treeview", rowheight=26)
        self.codex_models = []
        self.sessions = []
        self.inbox = queue.Queue()
        self.org_ids = []
        self.build()
        self.refresh()
        self.load_codex_models()
        self.root.after(2500, self.tick)

    # ---------------- layout ----------------
    def build(self):
        top = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="组织").pack(side="left")
        self.org_var = tk.StringVar()
        self.org_box = ttk.Combobox(top, textvariable=self.org_var, state="readonly", width=42)
        self.org_box.pack(side="left", padx=8)
        self.org_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(top, text="新建组织…", command=self.new_org).pack(side="left")
        ttk.Button(top, text="刷新", command=self.refresh).pack(side="left", padx=6)
        self.summary = ttk.Label(top, text="", foreground="#555")
        self.summary.pack(side="right")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.build_room()
        self.build_members()
        self.build_sessions()
        self.build_requests()
        self.build_org()

    def tree(self, parent, columns, widths, height=10):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show="headings", height=height, selectmode="browse")
        for (key, text), width in zip(columns, widths):
            tree.heading(key, text=text)
            tree.column(key, width=width, stretch=width > 150)
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        return frame, tree

    def build_room(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="讨论室")
        ttk.Label(tab, text=("组织里的全部消息，按时间排，原文不截断。你在下面写的消息发给选中的成员（开着自动唤醒时，ChatGPT 聊天会"
                             "自动收到原文）。ChatGPT 聊天的回复只在 ChatGPT 窗口里：在那里点回复下面的“复制”，再点“转发 GPT 的回复…”。"),
                  foreground="#555", wraplength=1020, justify="left").pack(anchor="w", pady=(0, 4))
        self.room_status = ttk.Label(tab, text="", foreground="#a15c00", wraplength=1020, justify="left")
        self.room_status.pack(anchor="w", pady=(0, 4))
        frame = ttk.Frame(tab)
        frame.pack(fill="both", expand=True)
        self.room_text = tk.Text(frame, wrap="word", state="disabled", font=self.reading, padx=8, pady=6, spacing1=2,
                                 spacing3=2, background="#fbfbfb")
        bar = ttk.Scrollbar(frame, orient="vertical", command=self.room_text.yview)
        self.room_text.configure(yscrollcommand=bar.set)
        self.room_text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.room_text.tag_configure("head", foreground="#1f5fa8", font=self.bold, spacing1=10)
        self.room_text.tag_configure("mine", foreground="#2e7d32", font=self.bold, spacing1=10)
        self.room_text.tag_configure("note", foreground="#999999", spacing1=6)
        box = ttk.Frame(tab)
        box.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="发给").pack(side="left")
        self.room_to = tk.StringVar(value="all")
        self.room_to_box = ttk.Combobox(row, textvariable=self.room_to, width=24)
        self.room_to_box.pack(side="left", padx=6)
        ttk.Button(row, text="转发 GPT 的回复…", command=self.forward_dialog).pack(side="right")
        ttk.Button(row, text="发送（Ctrl+Enter）", command=self.room_send).pack(side="right", padx=6)
        self.room_input = tk.Text(box, height=4, wrap="word", font=self.reading)
        self.room_input.pack(fill="x", pady=(6, 0))
        self.room_input.bind("<Control-Return>", lambda e: (self.room_send(), "break")[1])

    def build_members(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="成员")
        columns = [("member", "成员"), ("role", "角色"), ("harness", "Harness"), ("model", "模型"), ("env", "环境"),
                   ("session", "会话"), ("state", "状态"), ("unread", "未读")]
        frame, self.members = self.tree(tab, columns, [100, 90, 150, 130, 170, 140, 70, 50])
        frame.pack(fill="both", expand=True)
        self.members.bind("<<TreeviewSelect>>", lambda e: self.show_run())
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", pady=8)
        for text, command in (("新建成员…", self.new_member), ("修改配置…", self.edit_member),
                              ("换人（开新会话）", self.turnover), ("打开会话", self.open_terminal),
                              ("解除会话绑定", self.unbind)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 6))
        lower = ttk.Panedwindow(tab, orient="horizontal")
        lower.pack(fill="both", expand=True)
        left = ttk.Labelframe(lower, text="给选中成员一轮任务（在它自己的会话里跑）", padding=8)
        self.task_text = tk.Text(left, height=6, wrap="word")
        self.task_text.pack(fill="both", expand=True)
        ttk.Button(left, text="发送任务", command=self.send_task).pack(anchor="e", pady=(6, 0))
        right = ttk.Labelframe(lower, text="最近一轮", padding=8)
        self.run_text = tk.Text(right, height=6, wrap="word", state="disabled", background="#f6f6f6")
        self.run_text.pack(fill="both", expand=True)
        lower.add(left, weight=1)
        lower.add(right, weight=1)

    def build_sessions(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="已有会话")
        ttk.Label(tab, text="这台电脑上 Claude Code 和 Codex（桌面版和命令行）的会话。选一个放进席位，它下一轮起就是这个成员。",
                  foreground="#555").pack(anchor="w", pady=(0, 6))
        columns = [("harness", "Harness"), ("title", "标题"), ("cwd", "文件夹"), ("updated", "更新"), ("seat", "所在席位")]
        frame, self.session_tree = self.tree(tab, columns, [150, 330, 250, 100, 140], height=14)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="扫描会话", command=self.scan_sessions).pack(side="left")
        ttk.Label(row, text="放进席位").pack(side="left", padx=(16, 6))
        self.seat_var = tk.StringVar()
        self.seat_box = ttk.Combobox(row, textvariable=self.seat_var, width=24)
        self.seat_box.pack(side="left")
        ttk.Button(row, text="放进去", command=self.bind_session).pack(side="left", padx=6)
        self.scan_note = ttk.Label(row, text="", foreground="#777")
        self.scan_note.pack(side="left", padx=10)

    def build_requests(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="轨迹请求")
        ttk.Label(tab, text="成员要读别人的轨迹，先由对方同意；成员要读自己席位前任的轨迹，由你同意。同意后生成一个文件，只把路径发给请求方。",
                  foreground="#555", wraplength=980).pack(anchor="w", pady=(0, 6))
        columns = [("id", "编号"), ("requester", "请求方"), ("member", "被读成员"), ("carrier", "第几任"),
                   ("reason", "理由"), ("approver", "谁来批"), ("status", "状态")]
        frame, self.request_tree = self.tree(tab, columns, [60, 100, 100, 70, 380, 90, 80], height=14)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="同意", command=lambda: self.answer("approve")).pack(side="left")
        ttk.Button(row, text="拒绝", command=lambda: self.answer("deny")).pack(side="left", padx=6)
        self.redact_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="同意时脱敏导出（默认打开：API key、token、密码打码；原始会话记录不改）",
                        variable=self.redact_var).pack(side="left", padx=(10, 0))
        ttk.Button(row, text="打开轨迹文件", command=self.open_request_file).pack(side="left", padx=(16, 0))

    def build_org(self):
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="组织状态与消息")
        self.auto_wake = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, variable=self.auto_wake, command=self.toggle_auto_wake, text=(
            "自动唤醒：配置过会话的成员收到新消息时，自动在它自己的会话里开一轮（同一成员至少隔 2 分钟，"
            "组织每小时最多 30 次；对方正在使用时等它空闲）")).pack(anchor="w", pady=(0, 6))
        self.org_text = tk.Text(tab, wrap="word", state="disabled", font=self.mono, height=16)
        self.org_text.pack(fill="both", expand=True)
        box = ttk.Labelframe(tab, text="以你的名义给成员发消息（开着自动唤醒时，空闲的成员会自动开一轮来处理）", padding=8)
        box.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="发给").pack(side="left")
        self.to_var = tk.StringVar(value="all")
        self.to_box = ttk.Combobox(row, textvariable=self.to_var, width=20)
        self.to_box.pack(side="left", padx=6)
        self.msg_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.msg_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="发送", command=self.send_message).pack(side="left")

    # ---------------- data ----------------
    def org(self):
        index = self.org_box.current()
        if index < 0 or index >= len(self.org_ids):
            return None
        try:
            return self.store.get(self.org_ids[index])
        except OrgError:
            return None

    def selected_member(self):
        sel = self.members.selection()
        return sel[0] if sel else None

    def refresh(self):
        orgs = [o for o in self.store.list_orgs() if o.get("status") == "active"]
        orgs.sort(key=lambda o: o.get("created_at", ""))
        current = self.org_ids[self.org_box.current()] if 0 <= self.org_box.current() < len(self.org_ids) else None
        self.org_ids = [o["id"] for o in orgs]
        self.org_box["values"] = ["%s  (%s, %d 人)" % (o["name"], o["id"], len(o["members"])) for o in orgs]
        if self.org_ids:
            self.org_box.current(self.org_ids.index(current) if current in self.org_ids else len(self.org_ids) - 1)
        org = self.org()
        self.fill_room(org)
        self.fill_members(org)
        self.fill_requests(org)
        self.fill_org(org)
        names = list(org["members"]) if org else []
        self.seat_box["values"] = names
        self.to_box["values"] = ["all"] + names
        self.room_to_box["values"] = ["all"] + names
        self.fill_sessions()

    def fill_room(self, org):
        """Add the messages the room has not shown yet (all of them after a change of organization); stay at the
        bottom when the person was there, so a running discussion scrolls by itself."""
        text = self.room_text
        if not org:
            self.room_shown = (None, 0)
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.configure(state="disabled")
            self.room_status.configure(text="")
            return
        fresh = self.room_shown[0] != org["id"]
        new = self.store.history(org["id"], 300, after=0 if fresh else self.room_shown[1])
        if fresh or new:
            at_end = fresh or text.yview()[1] > 0.999
            text.configure(state="normal")
            if fresh:
                text.delete("1.0", "end")
            for m in new:
                self.room_line(m)
            text.configure(state="disabled")
            if at_end:
                text.see("end")
            last = new[-1]["id"] if new else (0 if fresh else self.room_shown[1])
            self.room_shown = (org["id"], last)
        self.room_status.configure(text=self.room_state(org))

    def room_line(self, m):
        text = self.room_text
        to = ", ".join(_who(t) for t in m["to"])
        if m["body"].startswith(wake.RECEIPT_MARK):  # automatic receipts: one grey line
            body = " ".join(m["body"][len(wake.RECEIPT_MARK):].split())
            text.insert("end", "msg %d · %s · 自动回执 %s → %s：%s\n" % (
                m["id"], _local(m["at"]), m["from"], to, body[:220] + ("…" if len(body) > 220 else "")), "note")
            return
        text.insert("end", "msg %d · %s · %s → %s\n" % (m["id"], _local(m["at"]), _who(m["from"]), to),
                    "mine" if m["from"] == "human" else "head")
        if UNREADABLE in m["body"]:  # relayed by 0.11.0 before it knew the app hides ChatGPT replies
            text.insert("end", "（ChatGPT 回复的占位引用：原文只在 ChatGPT 窗口里）\n", "note")
            return
        text.insert("end", m["body"].strip() + "\n")

    def room_state(self, org):
        """What the chat members are doing: a turn in the ChatGPT window, messages on their way in, replies waiting
        for the person to forward, a delivery that failed."""
        notes = []
        wakes = (org.get("wake") or {}).get("members") or {}
        for name, seat in org["members"].items():
            harness = seat.get("harness")
            unread = self.store.pending_count(org["id"], name) if harness in ("chatgpt", "claude-chat") else 0
            if harness == "chatgpt":
                running = (runner.run_state(org["id"], name) or {}).get("status") == "running"
                if running:
                    notes.append("%s：正在 ChatGPT 窗口里回复…" % name)
                elif unread:
                    notes.append("%s：%d 条消息正在送进它的 ChatGPT 聊天（自动）" % (name, unread))
                waiting = seat.get(Store.WAITING) or []
                if waiting:
                    notes.append("%s：%d 条回复只在 ChatGPT 窗口里，等你转发（最早一条回的是 msg %s）：复制它，再点“转发 GPT 的回复…”" % (
                        name, len(waiting), ",".join(str(i) for i in waiting[0]["ids"])))
                error = (wakes.get(name) or {}).get("error")
                if error and not running:
                    notes.append("%s：上次送达出错，会自动重试：%s" % (name, " ".join(error.split())[-160:]))
            elif harness == "claude-chat" and unread:
                notes.append("%s：%d 条未读，它在 Claude 的 Chat 里调用 inbox 时读到" % (name, unread))
        return "\n".join(notes)

    def fill_members(self, org):
        keep = self.selected_member()
        self.members.delete(*self.members.get_children())
        if not org:
            self.summary.configure(text="还没有组织：点“新建组织…”")
            return
        gov = "领导制（%s）" % (org.get("leader") or "第一个成员") if org["governance"] == "leader" else "同侪制"
        self.summary.configure(text="%s · %s" % (gov, org.get("purpose") or ""))
        for name, seat in org["members"].items():
            config = seat.get("config") or {}
            state = runner.run_state(org["id"], name) or {}
            harness = seat.get("harness") or config.get("harness") or ""
            shown = (kind_label(harness, config.get("surface")) if config.get("harness") == harness
                     else HARNESS_LABEL.get(harness, harness))
            env = (config.get("folder") or "") + ("  [worktree]" if config.get("environment") == "worktree" else "")
            carrier = seat.get("carrier") or ""
            chat = harness in ("chatgpt", "claude-chat")
            values = (name + ("  ★" if org.get("leader") == name else ""), seat.get("role", ""), shown,
                      config.get("model") or ("默认" if config and not chat else ""),
                      env or ("（聊天，只讨论）" if chat else "（自己加入的会话）"),
                      carrier.split(":", 1)[-1][:13] + ("…" if len(carrier) > 13 else ""),
                      STATUS_LABEL.get(state.get("status"), state.get("status")) if state else ("已入席" if carrier else "未启动"),
                      self.store.pending_count(org["id"], name) or "")
            self.members.insert("", "end", iid=name, values=values)
        if keep and self.members.exists(keep):
            self.members.selection_set(keep)
        self.show_run()

    def show_run(self):
        org, member = self.org(), self.selected_member()
        text = ""
        if org and member:
            state = runner.run_state(org["id"], member) or {}
            seat = org["members"].get(member, {})
            text = "会话：%s\n" % (seat.get("carrier") or "还没有")
            if seat.get("past_carriers"):
                text += "前任：%d 个\n" % len(seat["past_carriers"])
            if state:
                text += "状态：%s   开始 %s\n" % (STATUS_LABEL.get(state.get("status"), state.get("status")),
                                             _when(state.get("started")))
                if state.get("prompt"):
                    text += "\n任务：%s\n" % state["prompt"]
                if state.get("open_error"):
                    text += "\n打开会话出错：%s\n" % state["open_error"]
                if state.get("error"):
                    text += "\n错误：%s\n" % state["error"]
                if state.get("reply"):
                    text += "\n回复：%s\n" % state["reply"]
        self.run_text.configure(state="normal")
        self.run_text.delete("1.0", "end")
        self.run_text.insert("1.0", text)
        self.run_text.configure(state="disabled")

    def fill_requests(self, org):
        self.request_tree.delete(*self.request_tree.get_children())
        if not org:
            return
        status = {"pending": "待批", "approved": "已同意", "denied": "已拒绝"}
        for r in reversed(list(org.get("trajectory_requests", {}).values())):
            self.request_tree.insert("", "end", iid=r["id"], values=(
                r["id"], r["requester"], r["member"], "当前" if r["carrier"] == 0 else "前 %d 任" % r["carrier"],
                ("（轨迹和记忆）" if r.get("memory") else "（只要轨迹）") + r["reason"],
                "你" if r["approver"] == "human" else r["approver"], status.get(r["status"], r["status"])))

    def toggle_auto_wake(self):
        org = self.need_org()
        if org:
            self.guard(lambda: self.store.set_auto_wake(org["id"], self.auto_wake.get()))

    def fill_org(self, org):
        self.auto_wake.set(bool(org.get("auto_wake", True)) if org else True)
        lines = []
        if org:
            protocols = list(org["protocols"].values())
            lines.append("协议")
            for p in protocols:
                lines.append("  %s v%d [%s, %s] %s" % (p["id"], p.get("version", 1), p["strength"], p["status"], p["title"]))
            if not protocols:
                lines.append("  （还没有）")
            tasks = [t for t in org["tasks"].values() if t["status"] not in ("done", "dropped")]
            lines.append("\n进行中的任务")
            lines += ["  %s %s -> %s (%s)" % (t["id"], t["title"], t["owner"], t["status"]) for t in tasks] or ["  （没有）"]
            lines.append("\n共享文档")
            lines += ["  %s (r%d)" % (k, v["revision"]) for k, v in org["documents"].items()] or ["  （没有）"]
            lines.append("\n最近消息")
            for m in self.store.history(org["id"], 25):
                lines.append("  [%s] %s -> %s: %s" % (m["at"][11:16], m["from"], ",".join(m["to"]),
                                                      " ".join(m["body"].split())[:160]))
        self.org_text.configure(state="normal")
        self.org_text.delete("1.0", "end")
        self.org_text.insert("1.0", "\n".join(lines))
        self.org_text.configure(state="disabled")

    def fill_sessions(self):
        seats = self.store.bindings()
        orgs = {o["id"]: o["name"] for o in self.store.list_orgs()}
        self.session_tree.delete(*self.session_tree.get_children())
        for n, s in enumerate(self.sessions):
            seat = seats.get(actor_for(s))
            self.session_tree.insert("", "end", iid=str(n), values=(
                kind_label(s["harness"], s.get("surface")), s["title"], s["cwd"], _when(s["updated"]),
                "%s / %s" % (orgs.get(seat[0], seat[0]), seat[1]) if seat else ""))

    # ---------------- background work ----------------
    def background(self, work, done):
        def run():
            try:
                result = work()
            except Exception as error:  # shown in the window
                result = error
            self.inbox.put((done, result))
        threading.Thread(target=run, daemon=True).start()

    def tick(self):
        while not self.inbox.empty():
            done, result = self.inbox.get()
            done(result)
        org = self.org()
        if org and any(runner.run_state(org["id"], m) for m in org["members"]):
            self.fill_members(org)
        self.fill_room(org)
        if code_stamp() != self.stamp and self.reopen():
            return
        self.root.after(2500, self.tick)

    def reopen(self):
        """The plugin was updated: open a window on the new code and close this one, unless a dialog is open or
        something typed would be lost (then the title says so, and the next tick tries again)."""
        busy = (any(isinstance(w, tk.Toplevel) for w in self.root.winfo_children())
                or self.task_text.get("1.0", "end").strip() or self.msg_var.get().strip()
                or self.room_input.get("1.0", "end").strip())
        if busy:
            self.root.title("Relic Bridge（插件已更新：关掉对话框、发出或清空输入后自动换成新版本）")
            return False
        try:
            runner.open_window()
        except Exception:  # this window still works: keep it
            self.stamp = code_stamp()
            return False
        self.root.destroy()
        return True

    def load_codex_models(self):
        def done(result):
            if isinstance(result, list):
                self.codex_models = [m for m in result if m]
        self.background(runner.codex_models, done)

    def scan_sessions(self):
        self.scan_note.configure(text="扫描中…")

        def done(result):
            if isinstance(result, Exception):
                self.scan_note.configure(text=str(result))
                return
            self.sessions, problems = result
            self.scan_note.configure(text="找到 %d 个会话%s" % (len(self.sessions), ("；" + "；".join(problems)) if problems else ""))
            self.fill_sessions()
        self.background(all_sessions, done)

    # ---------------- actions ----------------
    def need_org(self):
        org = self.org()
        if not org:
            messagebox.showinfo("Relic", "先新建或选一个组织。", parent=self.root)
        return org

    def need_member(self):
        org = self.need_org()
        member = self.selected_member() if org else None
        if org and not member:
            messagebox.showinfo("Relic", "先在列表里选一个成员。", parent=self.root)
        return org, member

    def guard(self, action):
        try:
            action()
        except (OrgError, RuntimeError, OSError, KeyError) as error:
            messagebox.showerror("Relic", str(error), parent=self.root)
        self.refresh()

    def new_org(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("新建组织")
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        name, purpose, gov = tk.StringVar(), tk.StringVar(), tk.StringVar(value="leader")
        ttk.Label(frame, text="名字").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=name, width=40).grid(row=0, column=1, sticky="ew")
        ttk.Label(frame, text="目标").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=purpose).grid(row=1, column=1, sticky="ew")
        ttk.Label(frame, text="治理").grid(row=2, column=0, sticky="w", pady=4)
        box = ttk.Frame(frame)
        box.grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(box, text="领导制（第一个成员当领导）", value="leader", variable=gov).pack(side="left")
        ttk.Radiobutton(box, text="同侪制（多数决）", value="peer", variable=gov).pack(side="left", padx=10)

        def create():
            try:
                org = self.store.found(name.get(), purpose.get().strip(), gov.get())
            except OrgError as error:
                messagebox.showerror("Relic", str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh()
            self.org_box.current(self.org_ids.index(org["id"]))
            self.refresh()
        ttk.Button(frame, text="创建", command=create).grid(row=3, column=1, sticky="e", pady=(12, 0))
        dialog.grab_set()

    def new_member(self):
        org = self.need_org()
        if org:
            MemberDialog(self, org)

    def edit_member(self):
        org, member = self.need_member()
        if member:
            MemberDialog(self, org, member)

    def turnover(self):
        org, member = self.need_member()
        if not member:
            return
        seat = org["members"][member]
        if not seat.get("config"):
            messagebox.showinfo("Relic", "这个成员是自己加入的会话，先“修改配置…”选好 harness 和模型。", parent=self.root)
            return
        if seat.get("carrier") and not messagebox.askyesno(
                "Relic", "给 %s 开一个新会话？席位、角色、任务和协议留下，旧会话的私人笔记不带过去。" % member, parent=self.root):
            return
        self.guard(lambda: runner.start_turn(org["id"], member, runner.introduction(org, member), new_session=True,
                                             open_after=True))

    def send_task(self):
        org, member = self.need_member()
        text = self.task_text.get("1.0", "end").strip()
        if not member or not text:
            return
        seat = org["members"][member]
        if not seat.get("carrier"):
            messagebox.showinfo("Relic", "%s 还没有会话：先“换人（开新会话）”或在“已有会话”里放一个进来。" % member, parent=self.root)
            return
        if not seat.get("config"):
            messagebox.showinfo("Relic", "这个成员是自己加入的会话，直接在它的应用里给任务；或先“修改配置…”。", parent=self.root)
            return
        if seat.get("harness") != seat["config"].get("harness"):
            messagebox.showinfo("Relic", "%s 现在坐着的是 %s 会话，配置写的是 %s：在它自己的应用里给任务，或者“换人（开新会话）”。" % (
                member, HARNESS_LABEL.get(seat.get("harness"), seat.get("harness")),
                HARNESS_LABEL.get(seat["config"].get("harness"), seat["config"].get("harness"))), parent=self.root)
            return

        def go():
            runner.start_turn(org["id"], member, text)
            self.task_text.delete("1.0", "end")
        self.guard(go)

    def open_terminal(self):
        org, member = self.need_member()
        if not member:
            return
        seat = org["members"][member]
        carrier = seat.get("carrier")
        if not carrier:
            messagebox.showinfo("Relic", "%s 还没有会话。" % member, parent=self.root)
            return
        harness = seat.get("harness") or (seat.get("config") or {}).get("harness")
        if harness in ("chatgpt", "claude-chat"):
            messagebox.showinfo("Relic", "%s 是聊天成员：在%s里打开它的聊天。" % (
                member, "ChatGPT 桌面版" if harness == "chatgpt" else " Claude 桌面版的 Chat "), parent=self.root)
            return
        config = seat.get("config") if (seat.get("config") or {}).get("harness") == harness else {}
        session = carrier.split(":", 1)[1] if carrier.startswith("codex:") else carrier.split("/", 1)[0]
        state = runner.run_state(org["id"], member) or {}
        cwd = state.get("cwd") or config.get("folder") or str(Path.home())
        self.guard(lambda: runner.open_session(config, session, harness, cwd))

    def unbind(self):
        org, member = self.need_member()
        if not member:
            return
        carrier = org["members"][member].get("carrier")
        if carrier and messagebox.askyesno("Relic", "让 %s 的当前会话离开席位？席位和它的任务、协议都留着。" % member,
                                           parent=self.root):
            self.guard(lambda: self.store.unbind(carrier))

    def bind_session(self):
        org = self.need_org()
        sel = self.session_tree.selection()
        member = self.seat_var.get().strip()
        if not org or not sel or not member:
            messagebox.showinfo("Relic", "选一个会话，再填或选一个席位名。", parent=self.root)
            return
        session = self.sessions[int(sel[0])]

        def seat():
            self.store.join(actor_for(session), org["id"], member)
            if session["harness"] == "chatgpt":  # a ChatGPT chat can only take part through Relic: make it wakeable
                self.store.set_config(org["id"], member, runner.default_config("chatgpt"))
        self.guard(seat)

    def answer(self, decision):
        org = self.need_org()
        sel = self.request_tree.selection()
        if not org or not sel:
            return
        request = org.get("trajectory_requests", {}).get(sel[0], {})
        if request.get("approver") != "human":
            messagebox.showinfo("Relic", "这条请求由 %s 自己决定。" % request.get("approver"), parent=self.root)
            return
        self.guard(lambda: self.store.answer_trajectory_as_human(org["id"], sel[0], decision,
                                                                 redact=self.redact_var.get()))

    def open_request_file(self):
        org = self.need_org()
        sel = self.request_tree.selection()
        if org and sel:
            path = org.get("trajectory_requests", {}).get(sel[0], {}).get("file")
            if path:
                self.guard(lambda: open_path(path))

    def send_message(self):
        org = self.need_org()
        body = self.msg_var.get().strip()
        if not org or not body:
            return
        to = self.to_var.get().strip()

        def go():
            self.store.send_from_human(org["id"], ["all"] if to in ("", "all") else [t.strip() for t in to.split(",")], body)
            self.msg_var.set("")
            self.dispatch_soon(org["id"])
        self.guard(go)

    def room_send(self):
        org = self.need_org()
        body = self.room_input.get("1.0", "end").strip()
        if not org or not body:
            return
        to = self.room_to.get().strip()

        def go():
            self.store.send_from_human(org["id"], ["all"] if to in ("", "all") else [t.strip() for t in to.split(",")
                                                                                     if t.strip()], body)
            self.room_input.delete("1.0", "end")
            self.dispatch_soon(org["id"])
        self.guard(go)

    def forward_dialog(self):
        org = self.need_org()
        if not org:
            return
        chats = [n for n, s in org["members"].items() if s.get("harness") == "chatgpt"]
        if not chats:
            messagebox.showinfo("Relic", "这个组织里没有 ChatGPT 聊天成员。", parent=self.root)
            return
        ForwardDialog(self, org, chats)

    def dispatch_soon(self, org_id):
        """The person's messages wake the members they are for, as members' messages do (wake.py); in the background,
        since a wake-up starts a runner process."""
        def done(result):
            if isinstance(result, Exception):
                self.room_status.configure(text="自动唤醒没能开始：%s" % result)
        self.background(lambda: wake.dispatch(self.store, org_id), done)

    def run(self):
        self.root.mainloop()


def main():
    App().run()


if __name__ == "__main__":
    sys.exit(main())
