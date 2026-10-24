"""Tk native organization console. Network work stays off the UI thread."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import uuid

from .service import Service
from .store import data_home, now


def request_native_organization(service, root_session, data):
    """Persist before sending, so an uncertain desktop request is never retried."""
    root_id = root_session["id"]
    with service.store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS native_window_requests(root_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM native_window_requests WHERE root_id=?", (root_id,)).fetchone()
        if row:
            previous = json.loads(row[0])
            if previous["status"] in ("dispatching", "accepted", "uncertain"):
                return previous
        request = {"request_id": str(uuid.uuid4()), "root_id": root_id, "data": data,
                   "status": "dispatching", "requested_at": now()}
        db.execute("INSERT OR REPLACE INTO native_window_requests VALUES(?,?)", (root_id, json.dumps(request, ensure_ascii=False)))
    prompt = ("$relic-organization\nThe human clicked Start in the Relic window and authorizes this native SubAgent organization, "
              "its requested children, and internal member messaging. You are the selected root. Read the native-subagents skill reference. "
              "Call org_organize with the exact request below, then create the requested children within host limits using collaboration.spawn_agent "
              "and pass the returned join payload to each child. "
              "Each actual child must enroll itself with its authenticated identity. Preserve the human task constraints in every child prompt; "
              "use fork_turns='none' when those constraints require a clean start. "
              "Members determine their own division of work. Keep reflection enabled and form protocols from observed episodes. "
              "Report enrollment and actual outcomes separately.\n\n" +
              json.dumps({"operation": "start", "request_id": request["request_id"], "data": data}, ensure_ascii=False))
    try:
        receipt = service.bridge.send({"thread_id": root_id, "host_id": root_session.get("hostId", "local")}, prompt)
        request["host_receipt"] = receipt
        if not isinstance(receipt, dict):
            request.update(status="uncertain", reason="Host returned an unrecognized delivery receipt.")
        elif receipt.get("success") is False or receipt.get("sent") is False or receipt.get("status") in ("failed", "rejected", "blocked", "error"):
            request.update(status="rejected", reason="Host rejected the start request; inspect the saved receipt.")
        elif receipt.get("success") is True or receipt.get("sent") is True or receipt.get("status") in ("accepted", "sent", "queued", "success"):
            request["status"] = "accepted"
        else:
            request.update(status="uncertain", reason="Host acceptance was not confirmed; inspect the selected root before retrying.")
    except Exception as error:
        request.update(status="uncertain", reason=str(error))
    with service.store.connect() as db:
        db.execute("UPDATE native_window_requests SET body=? WHERE root_id=?", (json.dumps(request, ensure_ascii=False), root_id))
    return request


def matching_sessions(sessions, query="", workspace="全部 workspace", selected_only=False, chosen=()):
    terms = query.casefold().split()
    return [s for s in sessions if (workspace == "全部 workspace" or s.get("cwd", "") == workspace)
            and (not selected_only or s["id"] in chosen)
            and all(term in " ".join(str(s.get(k, "")) for k in ("title", "cwd", "id")).casefold()
                    for term in terms)]


def session_label(session):
    title = " ".join(session.get("title", session["id"]).split())
    return title[:95] + "  ·  " + session["id"][-8:]


def enable_high_dpi():
    """Must run before creating any Tk/HWND; avoid Windows bitmap scaling."""
    if os.name != "nt":
        return "native"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        setter = user32.SetProcessDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_int
        if setter(ctypes.c_void_p(-4)):  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            return "per_monitor_v2"
    except AttributeError:
        pass
    try:
        shcore = ctypes.WinDLL("shcore")
        if shcore.SetProcessDpiAwareness(2) == 0:
            return "per_monitor"
    except (AttributeError, OSError):
        pass
    user32.SetProcessDPIAware()
    return "system_or_existing"


def window_dpi(root):
    if os.name == "nt":
        try:
            get_dpi = ctypes.WinDLL("user32").GetDpiForWindow
            get_dpi.argtypes = [ctypes.c_void_p]
            get_dpi.restype = ctypes.c_uint
            return get_dpi(root.winfo_id()) or 96
        except AttributeError:
            pass
    return round(root.winfo_fpixels("1i"))


class WindowInstance:
    """Windows single instance: reopen requests signal the existing Tk window."""
    def __init__(self):
        self.kernel = None
        self.mutex = self.event = None
        self.existing = False
        if os.name != "nt":
            return
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name in ("CreateMutexW", "CreateEventW"):
            getattr(self.kernel, name).restype = ctypes.c_void_p
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.SetEvent.argtypes = [ctypes.c_void_p]
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        name = "Local\\RelicOrganization-" + hashlib.sha256(str(data_home().resolve()).encode()).hexdigest()[:24]
        self.mutex = self.kernel.CreateMutexW(None, False, name)
        self.existing = ctypes.get_last_error() == 183
        self.event = self.kernel.CreateEventW(None, False, False, name + "-Show")
        if not self.mutex or not self.event:
            raise OSError("Could not create native window instance handles.")
        if self.existing:
            self.kernel.SetEvent(self.event)

    def requested(self):
        return bool(self.kernel and self.kernel.WaitForSingleObject(self.event, 0) == 0)

    def close(self):
        if self.kernel:
            for handle in (self.event, self.mutex):
                if handle:
                    self.kernel.CloseHandle(handle)


class OrganizationWindow:
    def __init__(self, root, service, instance=None, receipt=None, maximize=True):
        self.root, self.service, self.instance, self.receipt = root, service, instance, receipt
        self.sessions, self.organizations, self.chosen = [], [], set()
        self.org_id = None
        self.native_request = None
        self.closed = False
        self.jobs, self.results = queue.Queue(), queue.Queue()
        self.pending = 0
        self.dpi = window_dpi(root)
        self.scale = self.dpi / 96
        self.root.tk.call("tk", "scaling", self.dpi / 72)
        self.root.title("Relic Organization")
        width = min(round(1500*self.scale), root.winfo_screenwidth()-round(60*self.scale))
        height = min(round(920*self.scale), root.winfo_screenheight()-round(90*self.scale))
        self.root.geometry(f"{max(800, width)}x{max(550, height)}")
        self.root.minsize(min(round(1000*self.scale), width), min(round(650*self.scale), height))
        self.root.configure(bg="#f4f2ed")
        if os.name == "nt" and maximize:
            self.root.state("zoomed")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.setup_style()
        self.build()
        threading.Thread(target=self.worker, daemon=True).start()
        self.root.after(60, self.poll)
        self.root.after(4000, self.periodic)
        self.refresh(True)

    def setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background="#f4f2ed", foreground="#232a32")
        style.configure("TButton", padding=(round(12*self.scale), round(7*self.scale)))
        style.configure("Accent.TButton", background="#812b43", foreground="white", padding=(round(18*self.scale), round(10*self.scale)))
        style.map("Accent.TButton", background=[("active", "#9a3854"), ("disabled", "#aaa")])
        style.configure("Brand.TLabel", font=("Segoe UI", 10, "bold"), foreground="#812b43")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 28, "bold"))
        style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Muted.TLabel", foreground="#65717b")
        style.configure("Treeview", font=("Microsoft YaHei UI", 11), rowheight=round(46*self.scale), background="#fff", fieldbackground="#fff", borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#e8d4db")], foreground=[("selected", "#232a32")])
        style.configure("TNotebook", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(round(15*self.scale), round(9*self.scale)))
        style.map("TNotebook.Tab", background=[("selected", "#fff")], foreground=[("selected", "#812b43")])

    def build(self):
        outer = ttk.Frame(self.root, padding=round(26*self.scale))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="RELIC / CODEX ORGANIZATIONS", style="Brand.TLabel").pack(side="left")
        ttk.Button(header, text="刷新全部聊天", command=lambda: self.refresh(True)).pack(side="right")
        ttk.Label(outer, text="让每一次协作，成为组织的经验。", style="Title.TLabel").pack(anchor="w", pady=(round(8*self.scale), round(8*self.scale)))
        ttk.Label(outer, text="原生 SubAgent 或独立桌面聊天 · 从协作经历中反思并形成协议", style="Muted.TLabel").pack(anchor="w", pady=(5, 12))
        self.status = tk.StringVar(value="正在读取本机聊天…")
        ttk.Label(outer, textvariable=self.status, style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        split = ttk.Panedwindow(outer, orient="horizontal")
        self.split = split
        split.pack(fill="both", expand=True)
        left, right = ttk.Frame(split, padding=(0, 0, 14, 0)), ttk.Frame(split, padding=(14, 0, 0, 0))
        split.add(left, weight=7)
        split.add(right, weight=3)
        self.root.after_idle(lambda: split.sashpos(0, round(split.winfo_width()*0.66)))
        ttk.Label(left, text="选择已有聊天", style="Heading.TLabel").pack(anchor="w")
        self.query = tk.StringVar()
        search = ttk.Entry(left, textvariable=self.query)
        search.pack(fill="x", pady=(10, 3))
        ttk.Label(left, text="搜索标题、workspace 或 session ID", style="Muted.TLabel").pack(anchor="w")
        self.query.trace_add("write", lambda *_: self.render_sessions())
        self.workspace = tk.StringVar(value="全部 workspace")
        self.workspaces = ttk.Combobox(left, textvariable=self.workspace, state="readonly", values=["全部 workspace"])
        self.workspaces.pack(fill="x", pady=10)
        self.workspaces.bind("<<ComboboxSelected>>", lambda e: self.render_sessions())
        options = ttk.Frame(left)
        options.pack(fill="x", pady=(0, 10))
        self.archived, self.selected_only = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="显示已归档", variable=self.archived, command=lambda: self.refresh(True)).pack(side="left")
        ttk.Checkbutton(options, text="只看已选", variable=self.selected_only, command=self.render_sessions).pack(side="left", padx=12)
        ttk.Button(options, text="清空选择", command=self.clear_selection).pack(side="right")
        table = ttk.Frame(left)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("chosen", "title", "workspace", "state"), show="headings", selectmode="browse")
        for key, title, width in (("chosen", "选择", 56), ("title", "聊天", 350), ("workspace", "Workspace", 320), ("state", "状态", 85)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=round(width*self.scale), minwidth=round(40*self.scale), stretch=key in ("title", "workspace"))
        self.tree.tag_configure("unavailable", foreground="#93969b")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.click_session)
        self.tree.bind("<Double-1>", self.double_session)
        self.tree.bind("<space>", lambda e: self.toggle_session(self.tree.focus()))
        self.selection_summary = tk.StringVar()
        ttk.Label(left, textvariable=self.selection_summary, style="Muted.TLabel").pack(anchor="w", pady=(10, 3))
        ttk.Label(left, text="点选择列勾选；双击或空格切换。归档聊天须先在 Codex 恢复。", style="Muted.TLabel", wraplength=610).pack(anchor="w")
        self.session_detail = tk.StringVar()
        ttk.Label(left, textvariable=self.session_detail, style="Muted.TLabel", wraplength=610).pack(anchor="w", pady=6)
        self.tree.bind("<<TreeviewSelect>>", self.show_session)
        self.right_tabs = ttk.Notebook(right)
        self.right_tabs.pack(fill="both", expand=True)
        create, shared = ttk.Frame(self.right_tabs, padding=18), ttk.Frame(self.right_tabs, padding=12)
        self.right_tabs.add(create, text="组建组织")
        self.right_tabs.add(shared, text="共同组织空间")
        ttk.Label(create, text="选择组织运行方式", style="Heading.TLabel").pack(anchor="w", pady=(4, 8))
        self.runtime = ttk.Combobox(create, state="readonly", values=["独立桌面聊天", "原生 SubAgent · 一个根聊天"])
        self.runtime.current(0)
        self.runtime.pack(fill="x", pady=(0, 10))
        self.runtime.bind("<<ComboboxSelected>>", self.runtime_changed)
        ttk.Label(create, text="组织名称").pack(anchor="w")
        self.name = tk.StringVar()
        ttk.Entry(create, textvariable=self.name).pack(fill="x", pady=(6, 18))
        ttk.Label(create, text="组织任务 · 成员自行商量分工与接口").pack(anchor="w")
        self.task_brief = tk.Text(create, height=4, wrap="word", font=("Microsoft YaHei UI", 10), relief="solid", borderwidth=1)
        self.task_brief.pack(fill="x", pady=(6, 12))
        new_row = ttk.Frame(create)
        new_row.pack(fill="x", pady=(0, 12))
        self.new_member_label = ttk.Label(new_row, text="直接创建新成员")
        self.new_member_label.pack(side="left")
        self.new_members = tk.StringVar(value="2")
        ttk.Spinbox(new_row, from_=0, to=12, width=4, textvariable=self.new_members).pack(side="left", padx=10)
        self.new_member_hint = ttk.Label(new_row, text="各自新 workspace；不选已有聊天时，首位新成员负责", style="Muted.TLabel", wraplength=340)
        self.new_member_hint.pack(side="left", fill="x", expand=True)
        ttk.Label(create, text="负责人 · 你主要与这个聊天对话").pack(anchor="w")
        self.leader = ttk.Combobox(create, state="readonly")
        self.leader.pack(fill="x", pady=(6, 18))
        ttk.Label(create, text="协议采纳方式").pack(anchor="w")
        self.governance = ttk.Combobox(create, state="readonly", values=["负责人 + 至少一名成员同意", "负责人 + 多数成员同意"])
        self.governance.current(0)
        self.governance.pack(fill="x", pady=(6, 20))
        ttk.Label(create, text="消息默认投递方式").pack(anchor="w")
        self.delivery_default = ttk.Combobox(create, state="readonly", values=["当前轮结束后", "尽快插入当前工作流 · 工具边界"])
        self.delivery_default.current(0)
        self.delivery_default.pack(fill="x", pady=(6, 12))
        self.quiet = tk.BooleanVar(value=True)
        self.quiet_option = ttk.Checkbutton(create, text="合并内部消息 · 完成提醒需在 Codex 全局关闭", variable=self.quiet)
        self.quiet_option.pack(anchor="w")
        self.runtime_hint = ttk.Label(create, text="启动后，成员可以互相发消息、召开文字会议、共享工作，并讨论和修订 protocol。", wraplength=430, style="Muted.TLabel")
        self.runtime_hint.pack(anchor="w", pady=12)
        self.start = ttk.Button(create, text="启动组织 →", style="Accent.TButton", command=self.create)
        self.start.pack(anchor="w", pady=10)
        self.chosen_heading = ttk.Label(create, text="本次选择的成员 · 每个组织 1–24 位", style="Heading.TLabel")
        self.chosen_heading.pack(anchor="w", pady=(14, 8))
        self.chosen_list = tk.Listbox(create, relief="flat", bg="white", font=("Microsoft YaHei UI", 10), height=5)
        self.chosen_list.pack(fill="both", expand=True)
        ttk.Label(shared, text="当前组织").pack(anchor="w")
        self.org_select = ttk.Combobox(shared, state="readonly")
        self.org_select.pack(fill="x", pady=(5, 8))
        self.org_select.bind("<<ComboboxSelected>>", self.choose_org)
        controls = ttk.Frame(shared)
        controls.pack(fill="x")
        self.pause_button = ttk.Button(controls, text="暂停组织", command=self.pause)
        self.pause_button.pack(side="left")
        ttk.Button(controls, text="更换负责人", command=self.change_leader).pack(side="left", padx=6)
        ttk.Button(controls, text="刷新记录", command=lambda: self.refresh(False)).pack(side="right")
        self.mode_button = ttk.Button(shared, text="切换后台静默", command=self.execution_mode)
        self.delivery_button = ttk.Button(shared, text="设置消息默认方式", command=self.delivery_mode)
        self.delivery_button.pack(anchor="w", pady=4)
        self.mode_button.pack(anchor="w", pady=(8, 0))
        self.notifications_button = ttk.Button(shared, text="我已在 Codex 关闭通知 · 确认设置", command=self.confirm_notifications)
        self.notifications_button.pack(anchor="w", pady=(6, 0))
        bench_controls=ttk.Frame(shared)
        bench_controls.pack(fill="x",pady=(8,0))
        ttk.Button(bench_controls,text="启动三人开发任务",command=self.development_task).pack(side="left")
        ttk.Button(bench_controls,text="启动 OrganizationBench",command=self.organizationbench_task).pack(side="left",padx=6)
        self.org_summary = tk.StringVar(value="选择成员并启动后，共同记录会出现在这里。")
        ttk.Label(shared, textvariable=self.org_summary, style="Muted.TLabel", wraplength=440).pack(anchor="w", pady=12)
        self.category = ttk.Combobox(shared, state="readonly", values=["成员", "后台进度", "消息", "文档", "任务", "Episodes", "Protocols", "开发验收", "OrganizationBench", "事件记录"])
        self.category.current(0)
        self.category.pack(fill="x")
        self.category.bind("<<ComboboxSelected>>", lambda e: self.render_records())
        self.records = tk.Listbox(shared, font=("Microsoft YaHei UI", 10), bg="white", relief="flat", height=7, exportselection=False)
        self.records.pack(fill="x", pady=8)
        self.records.bind("<<ListboxSelect>>", self.show_record)
        self.details = tk.Text(shared, font=("Microsoft YaHei UI", 10), wrap="word", bg="white", relief="flat", state="disabled", height=12)
        self.details.pack(fill="both", expand=True)
        buttons = ttk.Frame(shared)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="发送消息", command=self.message).pack(side="left")
        ttk.Button(buttons, text="编辑文档", command=self.document).pack(side="left", padx=6)
        ttk.Button(buttons, text="废止协议", command=self.retire).pack(side="right")
        ttk.Label(outer, text="EPISODE → REFLECTION → DISCUSSION → PROTOCOL → USE → REVISION", style="Muted.TLabel").pack(anchor="w", pady=(15, 4))
        ttk.Label(outer, text="组织数据：" + str(self.service.store.path.parent), style="Muted.TLabel").pack(anchor="w")

    def worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                self.service.close()
                return
            function, callback = job
            try:
                self.results.put((callback, function(), None))
            except Exception as error:
                self.results.put((callback, None, str(error)))

    def submit(self, function, callback):
        self.pending += 1
        self.start.configure(state="disabled")
        self.jobs.put((function, callback))

    def poll(self):
        if self.closed:
            return
        while True:
            try:
                callback, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            self.pending -= 1
            if error:
                self.status.set("操作未完成：" + error)
                messagebox.showerror("Relic Organization", error, parent=self.root)
            else:
                callback(result)
            if not self.pending:
                self.start.configure(state="normal")
        if self.instance and self.instance.requested():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.reconnect()
        self.root.after(60, self.poll)

    def periodic(self):
        if self.closed:
            return
        if not self.pending and (self.org_id or self.native_request):
            self.refresh(False)
        self.root.after(4000, self.periodic)

    def reconnect(self):
        # A new Codex process may have a new bridge endpoint. The worker serializes
        # reconnection with deliveries, so an in-flight send is never retried.
        include_archived = self.archived.get()
        def read():
            from .window import restore_context
            restore_context(force=True)
            self.service.bridge.close()
            self.service.bridge.process = None
            self.service.actor = os.getenv("CODEX_THREAD_ID")
            self.service.bridge.actor = self.service.actor
            return {"discovery": self.service.discover(include_archived), "organizations": self.service.store.list()}
        self.submit(read, self.loaded)

    def refresh(self, discover=True):
        include_archived = self.archived.get()
        if discover:
            self.status.set("正在分页读取完整本机聊天列表…")
        def read():
            return {"discovery": self.service.discover(include_archived) if discover else None,
                    "organizations": self.service.store.list()}
        self.submit(read, self.loaded)

    def loaded(self, state):
        self.organizations = state["organizations"]
        discovery = state["discovery"]
        if discovery is not None:
            self.sessions = discovery["sessions"]
            count_archived = sum(s.get("archived", False) for s in self.sessions)
            notice = "完整本机列表" if discovery.get("catalog") == "complete_local" else "列表未完整加载"
            self.status.set(f"{notice} · {len(self.sessions)} 个聊天 · {count_archived} 个已归档" +
                            (" · 通信已连接" if discovery["transport"] == "desktop" else " · 通信暂不可用") +
                            (" · " + discovery["reason"] if discovery.get("reason") else ""))
            self.workspaces.configure(values=["全部 workspace"] + sorted({s.get("cwd", "") for s in self.sessions if s.get("cwd")}))
        self.render_sessions()
        self.org_labels = {o["id"]: o["name"] + " · " + o["id"][-6:] for o in self.organizations}
        self.org_select.configure(values=list(self.org_labels.values()))
        if self.org_id not in self.org_labels:
            self.org_id = self.organizations[0]["id"] if self.organizations else None
        self.org_select.set(self.org_labels.get(self.org_id, ""))
        self.update_native_request()
        self.render_records()
        if self.receipt:
            self.root.update_idletasks()
            self.receipt.write_text(json.dumps({"status": "opened", "pid": os.getpid(),
                "title": self.root.title(), "visible": bool(self.root.winfo_viewable()),
                "dpi": self.dpi, "scale": self.scale,
                "dpi_mode": getattr(self, "dpi_mode", "unknown"),
                "pixel_size": [self.root.winfo_width(), self.root.winfo_height()],
                "left_pane_pixels": self.split.sashpos(0),
                "session_count": len(self.sessions), "catalog": discovery.get("catalog") if discovery else None}), encoding="utf-8")
            self.receipt = None

    def busy_members(self):
        return {m for o in self.organizations if o["status"] == "active" for m in o["members"]}

    def render_sessions(self):
        focused = self.tree.focus()
        self.tree.delete(*self.tree.get_children())
        busy = self.busy_members()
        valid = {s["id"] for s in self.sessions if not s.get("archived") and s["id"] not in busy}
        self.chosen.intersection_update(valid)
        visible = matching_sessions(self.sessions, self.query.get(), self.workspace.get(), self.selected_only.get(), self.chosen)
        for s in visible:
            unavailable = s.get("archived") or s["id"] in busy
            state = "已归档" if s.get("archived") else "已入组织" if s["id"] in busy else "可选择"
            self.tree.insert("", "end", iid=s["id"], values=("✓" if s["id"] in self.chosen else "○",
                " ".join(s["title"].split()), s.get("cwd", ""), state), tags=("unavailable",) if unavailable else ())
        if self.tree.exists(focused):
            self.tree.focus(focused)
            self.tree.selection_set(focused)
        self.selection_summary.set(f"显示 {len(visible)} / {len(self.sessions)} 个聊天 · 已选 {len(self.chosen)} 位成员")
        self.render_selection()

    def render_selection(self):
        old = self.leader.get()
        self.leader_labels = {s["id"]: session_label(s) for s in self.sessions if s["id"] in self.chosen}
        values = list(self.leader_labels.values())
        self.leader.configure(values=values)
        self.leader.set(old if old in values else values[0] if values else "")
        self.chosen_list.delete(0, "end")
        for label in values:
            self.chosen_list.insert("end", label)

    def toggle_session(self, session_id):
        session = next((s for s in self.sessions if s["id"] == session_id), None)
        if not session or session.get("archived") or session_id in self.busy_members():
            return "break"
        if session_id in self.chosen:
            self.chosen.remove(session_id)
        else:
            self.chosen.add(session_id)
        self.render_sessions()
        return "break"

    def click_session(self, event):
        if self.tree.identify_column(event.x) == "#1":
            return self.toggle_session(self.tree.identify_row(event.y))

    def double_session(self, event):
        if self.tree.identify_column(event.x) != "#1":
            return self.toggle_session(self.tree.identify_row(event.y))
        return "break"

    def show_session(self, event=None):
        session = next((s for s in self.sessions if s["id"] == self.tree.focus()), None)
        self.session_detail.set((session["title"] + "\n" + session.get("cwd", "") + "\n" + session["id"]) if session else "")

    def clear_selection(self):
        self.chosen.clear()
        self.render_sessions()

    def runtime_changed(self, event=None):
        native = self.runtime.current() == 1
        self.quiet_option.configure(state="disabled" if native else "normal")
        self.delivery_default.configure(state="disabled" if native else "readonly")
        self.new_member_label.configure(text="原生子成员数量" if native else "直接创建新成员")
        self.new_member_hint.configure(text="选择一个根聊天；未选择时使用列表中的当前聊天" if native else "各自新 workspace；不选已有聊天时，首位新成员负责")
        self.chosen_heading.configure(text="本次根聊天 · 仅选择一位" if native else "本次选择的成员 · 每个组织 1–24 位")
        self.runtime_hint.configure(text=("根聊天调用原生 collaboration 工具创建成员。保留反思，由成员根据经历形成协议。根聊天接入后显示组织；宿主接受请求不表示工作完成。" if native else
                                         "启动后，成员可以互相发消息、召开文字会议、共享工作，并讨论和修订 protocol。"))

    def native_requested(self, result):
        self.native_request = result
        state = result["status"]
        if state == "accepted":
            self.status.set("宿主已接受原生组建请求 · 等待根聊天接入，尚未确认成员创建或任务完成 · " + result["request_id"])
        else:
            self.status.set(("组建请求被拒绝" if state == "rejected" else "组建请求结果未知；不会自动重发") + " · " + result.get("reason", state))
        self.update_native_request()

    def update_native_request(self):
        if not self.native_request:
            return
        request = self.native_request
        # Enrollment belongs to the root's authenticated formation call, not the window.
        org = next((o for o in self.organizations if o.get("runtime") == "native_subagents" and
                    o.get("native", {}).get("formation_request_id") == request["request_id"] and
                    o.get("native", {}).get("root_thread_id") == request["root_id"]), None)
        if not org:
            return
        org_id = org["id"]
        with self.service.store.connect() as db:
            request.update(status="enrolled", org_id=org_id)
            db.execute("UPDATE native_window_requests SET body=? WHERE root_id=?", (json.dumps(request, ensure_ascii=False), request["root_id"]))
        self.org_id = org_id
        self.org_select.set(self.org_labels[org_id])
        self.chosen.clear()
        self.right_tabs.select(1)
        self.status.set("原生组织已记录 · 成员接入及工作结果请查看共同组织空间。")
        self.native_request = None

    def create(self):
        try:
            count = int(self.new_members.get())
        except ValueError:
            messagebox.showinfo("组建组织", "新成员数量应为 0–12 的整数。", parent=self.root)
            return
        native = self.runtime.current() == 1
        if not self.name.get().strip() or not 0 <= count <= 12 or (not native and not (self.chosen or count)):
            messagebox.showinfo("组建组织", "填写组织名称，选择已有聊天或创建新成员。", parent=self.root)
            return
        task = self.task_brief.get("1.0", "end").strip()
        if (count or native) and not task:
            messagebox.showinfo("组建组织", "填写具体任务，新成员就能在组建后开始协作。", parent=self.root)
            return
        if native:
            root_id = next(iter(self.chosen)) if len(self.chosen) == 1 else self.service.actor if not self.chosen else None
            root_session = next((s for s in self.sessions if s["id"] == root_id and not s.get("archived") and
                                 s.get("hostId", "local") == "local" and s.get("kind", "codex") == "codex"), None)
            if not root_session or root_id in self.busy_members():
                messagebox.showinfo("原生 SubAgent 组织", "请选择恰好一个可用根聊天；未选择时，当前聊天必须在可用列表中。", parent=self.root)
                return
            data = {"runtime": "native_subagents", "execution_mode": "native", "name": self.name.get().strip(),
                    "task": task, "new_members": count,
                    "governance": "leader_with_peer" if self.governance.current() == 0 else "majority"}
            self.submit(lambda: request_native_organization(self.service, root_session, data), self.native_requested)
            return
        leader = next((i for i, label in self.leader_labels.items() if label == self.leader.get()), None)
        if self.chosen and not leader:
            return
        data = {"name": self.name.get().strip(), "members": list(self.chosen),
                "governance": "leader_with_peer" if self.governance.current() == 0 else "majority",
                "execution_mode": "quiet" if self.quiet.get() else "desktop",
                "delivery_mode": "after_turn" if self.delivery_default.current() == 0 else "immediate"}
        if count or task:
            import uuid
            data.update(task=task, new_members=count, include_current=False)
            if leader:
                data["leader"] = leader
            request_id = str(uuid.uuid4())
            self.submit(lambda: self.service.call("org_organize", {"operation":"start", "request_id":request_id, "data":data}), self.formed)
        else:
            data["leader"] = leader
            self.submit(lambda: self.service.create(data), self.created)

    def formed(self, result):
        if result["status"] != "complete":
            messagebox.showerror("组织组建未完成", "请求 " + result["request_id"] + "\n" + result.get("reason", result["status"]) + "\n已创建成员保留，不能盲目重试。", parent=self.root)
            self.refresh(True)
            return
        self.created({"id": result["org_id"]})
        self.refresh(True)

    def created(self, org):
        self.org_id = org["id"]
        self.chosen.clear()
        self.right_tabs.select(1)
        self.refresh(False)

    def org(self):
        return next((o for o in self.organizations if o["id"] == self.org_id), None)

    def development_task(self):
        if not self.org():return
        org_id=self.org_id
        self.submit(lambda:self.service.development_task(org_id),lambda result:self.refresh(False))

    def organizationbench_task(self):
        if not self.org():return
        source=simpledialog.askstring('OrganizationBench','本地 OrganizationBench 仓库路径（不会修改原有实验）：',
            initialvalue=os.getenv('RELIC_ORGANIZATIONBENCH_PATH',''),parent=self.root)
        if not source:return
        epochs=simpledialog.askinteger('经营期限','软件经营期数（5–8），以实际利润结算：',initialvalue=6,minvalue=5,maxvalue=8,parent=self.root)
        if epochs is None:return
        org_id=self.org_id
        self.submit(lambda:self.service.organizationbench_task(org_id,source,epochs),lambda result:self.refresh(False))

    def choose_org(self, event=None):
        self.org_id = next((i for i, label in self.org_labels.items() if label == self.org_select.get()), None)
        self.render_records()

    def execution_mode(self):
        o = self.org()
        if not o or o.get("runtime") == "native_subagents":
            return
        mode = "desktop" if o.get("execution_mode", "desktop") == "quiet" else "quiet"
        org_id = o["id"]
        def change():
            result = self.service.store.human_control(org_id, "execution_mode", mode)
            if mode == "quiet":
                from .quiet import wake
                wake(self.service.store.path, self.service.actor)
            return result
        self.submit(change, lambda result: self.refresh(False))

    def confirm_notifications(self):
        from .quiet import confirm_notifications_off, wake
        def change():
            receipt = confirm_notifications_off()
            wake(self.service.store.path, self.service.actor)
            return receipt
        self.submit(change, lambda result: self.refresh(False))

    def render_records(self):
        o = self.org()
        selected = self.records.curselection()
        old_id = self.record_items[selected[0]][0] if selected and selected[0] < len(getattr(self, "record_items", [])) else None
        self.record_items = []
        self.records.delete(0, "end")
        if not o:
            self.write_detail("启动组织后，共享记录会显示在这里。")
            return
        quiet = o.get("execution_mode", "desktop") == "quiet"
        native = o.get("runtime") == "native_subagents"
        self.org_summary.set(f"{o['name']} · {len(o['members'])} 位成员 · " + ("运行中" if o["status"] == "active" else "已暂停") + (" · 原生 SubAgent" if native else " · 后台静默" if quiet else " · 桌面聊天运行"))
        self.mode_button.configure(text="原生 collaboration 投递" if native else "当前合并投递 · 切到逐条投递" if quiet else "启用消息合并", state="disabled" if native else "normal")
        self.notifications_button.configure(state="disabled" if native else "normal")
        self.delivery_button.configure(state="disabled" if native else "normal")
        self.pause_button.configure(text="暂停组织" if o["status"] == "active" else "恢复组织")
        category = self.category.get()
        if native and category == "后台进度":
            self.write_detail("原生 SubAgent 由根聊天及成员使用 collaboration 工具运行。\n消息的 native_outbox 需要实际宿主投递；收件人成员亲自 ack 后才确认收取。\n成员加入、消息收取和任务完成分别记录。这里不启动桌面聊天队列。")
            return
        if category == "后台进度":
            from .quiet import status
            progress = status(self.service.store)
            progress["jobs"] = [j for j in progress["jobs"] if j["org_id"] == o["id"]]
            progress["recent_completions"] = [j for j in progress["recent_completions"] if j["org_id"] == o["id"]]
            notice = "完成通知：已由你确认关闭（全局）" if progress["completion_notifications"]["disabled"] else "请在 Codex 设置关闭完成通知，再点上方确认。"
            lines = [notice, "消息在成员空闲后合并投递，保留原聊天和 workspace。", "", f"正在处理：{len(progress['jobs'])} 位成员 · 排队：{progress['queued']} 条投递"]
            if progress.get("error"):
                lines.extend(["", "通信暂不可用："+progress["error"]])
            for issue in progress.get('attention_required', []):
                if issue.get('org_id') != o['id']:
                    continue
                title = o['members'].get(issue['recipient'], {}).get('title', issue['recipient'])
                lines.extend(['', title+' · 原生回合失败，需要处理',
                              str(issue.get('error', {}).get('message', issue.get('native_status'))),
                              issue.get('recovery', '')])
            for job in progress["jobs"]:
                member = o["members"].get(job["recipient"],{})
                count = sum(o["messages"][m]["deliveries"][job["recipient"]]["status"]=="acknowledged" for m in job["message_ids"])
                lines.extend(["", member.get("title",job["recipient"]), f"本批 {len(job['message_ids'])} 条消息 · 已确认 {count} 条", "开始："+job["started_at"]])
            recent = [j for j in progress["recent_completions"] if j.get("transport")=="desktop_batch" and j["state"]!="running"]
            if recent:
                lines.extend(["", "最近处理记录（工作结果请看共享文档或任务）："])
                for job in recent[:5]:
                    title = o["members"].get(job["recipient"],{}).get("title",job["recipient"])
                    lines.append(title+" · "+("本批已确认" if job["state"]=="completed" else "需要检查投递"))
            self.write_detail("\n".join(lines))
            return
        field = {"成员": "members", "消息": "messages", "文档": "documents", "任务": "tasks", "Episodes": "episodes", "Protocols": "protocols", "开发验收":"benchmarks"}.get(category)
        if category=='OrganizationBench':
            binding=o.get('organizationbench')
            self.write_detail(json.dumps(binding or {'notice':'尚未连接软件经营任务'},ensure_ascii=False,indent=2))
            if binding:
                org_id=o['id']
                def fetched(status):
                    if self.org_id==org_id and self.category.get()=='OrganizationBench':
                        self.write_detail(json.dumps({'connection':binding,'live_status':status},ensure_ascii=False,indent=2))
                self.submit(lambda:self.service.call('org_benchmark',{'org_id':org_id,'operation':'upstream_status','data':{}},actor='human'),fetched)
            return
        if field:
            entries = list(o.get(field,{}).items())
            if field in ("messages", "episodes", "protocols"):
                entries.reverse()
            for key, item in entries:
                label = item.get("title") or item.get("key") or item.get("body", key)[:70]
                if field == "members" and key == o["leader"]:
                    label = "负责人 · " + label
                if field == "protocols":
                    label = ("弱协议 · " if item.get("strength", "strong") == "weak" else "强协议 · ") + label
                    label += " · 使用记录 " + str(len(item.get("uses", {})))
                if item.get("status"):
                    label += " · " + item["status"]
                self.record_items.append((key, item))
                self.records.insert("end", " ".join(label.split()))
        else:
            for event in self.service.store.events(o["id"])[-200:]:
                self.record_items.append((event["id"], event))
                self.records.insert("end", event["kind"] + " · " + event["at"])
        if self.record_items:
            row = next((i for i, item in enumerate(self.record_items) if item[0] == old_id), 0)
            self.records.selection_set(row)
            self.show_record()
        else:
            self.write_detail("暂无这一类记录。")

    def write_detail(self, body):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", body)
        self.details.configure(state="disabled")

    def selected_record(self):
        selection = self.records.curselection()
        return self.record_items[selection[0]][1] if selection else None

    def show_record(self, event=None):
        record = self.selected_record()
        if not record:
            self.write_detail("")
            return
        o = self.org()
        member_name = lambda i: "人类" if i == "human" else o["members"].get(i, {}).get("title", i)
        category = self.category.get()
        if category == "成员":
            body = record["title"] + "\n\nWorkspace：" + str(record.get("workspace", "")) + "\nSession：" + record["thread_id"]
        elif category == "消息":
            body = member_name(record["sender"]) + "\n" + record["created_at"] + "\n\n" + record["body"] + "\n\n投递状态：\n" + "\n".join(member_name(i) + "：" + d["status"] for i, d in record["deliveries"].items())
        elif category == "文档":
            body = record["key"] + " · v" + str(record["revision"]) + "\n\n" + record["body"]
        elif category == "任务":
            body = record["title"] + "\n负责人：" + member_name(record["owner"]) + "\n状态：" + record["status"] + "\n\n结果证据：\n" + "\n".join(record["evidence"])
        elif category == "Episodes":
            body = record["title"] + "\n状态：" + record["status"] + "\n结果：" + str(record.get("outcome") or "尚未结算") + "\n\n" + (record.get("summary") or "经历正在进行") + "\n\n反思：\n" + "\n\n".join(member_name(i) + "：\n" + r["body"] for i, r in record["reflections"].items()) + "\n\n证据：\n" + "\n".join(record["evidence"])
        elif category == "Protocols":
            body = record["title"] + " · v" + str(record["version"]) + " · " + record["status"] + "\n\n" + record["rationale"] + "\n\n执行规则：\n" + json.dumps(record["rules"], ensure_ascii=False, indent=2) + "\n\n讨论：\n" + "\n".join(member_name(c["author"]) + "：" + c["body"] for c in record["comments"]) + "\n\n投票：\n" + "\n".join(member_name(i) + "：" + v["vote"] + " · " + v["reason"] for i, v in record["votes"].items())
        elif category=='开发验收':
            body=json.dumps(record,ensure_ascii=False,indent=2)
        else:
            body = record["kind"] + "\n" + record["at"] + "\n\n" + json.dumps(record["body"], ensure_ascii=False, indent=2)
        self.write_detail(body)

    def control(self, operation, value=None):
        o = self.org()
        if o:
            def change():
                result = self.service.store.human_control(o["id"], operation, value)
                if operation == "resume" and result.get("execution_mode") == "quiet":
                    from .quiet import wake
                    wake(self.service.store.path, self.service.actor)
                return result
            self.submit(change, lambda _: self.refresh(False))

    def pause(self):
        o = self.org()
        if o:
            self.control("pause" if o["status"] == "active" else "resume")

    def popup(self, title):
        top = tk.Toplevel(self.root)
        top.title(title)
        top.geometry(f"{round(650*self.scale)}x{round(480*self.scale)}")
        top.transient(self.root)
        body = ttk.Frame(top, padding=18)
        body.pack(fill="both", expand=True)
        return top, body

    def change_leader(self):
        o = self.org()
        if not o:
            return
        top, body = self.popup("更换负责人")
        labels = {i: session_label(dict(m, id=i)) for i, m in o["members"].items()}
        select = ttk.Combobox(body, values=list(labels.values()), state="readonly")
        select.set(labels[o["leader"]])
        select.pack(fill="x", pady=12)
        def save():
            self.control("leader", next(i for i, label in labels.items() if label == select.get()))
            top.destroy()
        ttk.Button(body, text="设为负责人", command=save).pack(anchor="w")

    def message(self):
        o = self.org()
        if not o:
            return
        top, body = self.popup("发送组织消息")
        to = ttk.Combobox(body, values=["负责人", "全部组织成员"], state="readonly")
        to.current(0)
        to.pack(fill="x", pady=(0, 10))
        mode = ttk.Combobox(body, values=["采用组织默认方式", "当前轮结束后投递", "尽快插入当前工作流 · 工具边界"], state="readonly")
        mode.current(0)
        native = o.get("runtime") == "native_subagents"
        if native:
            mode.configure(state="disabled")
        mode.pack(fill="x", pady=(0, 8))
        ttk.Label(body, text=("消息保存到组织收件箱；等待原生成员实际投递，收件人 ack 后确认收取。" if native else
                             "尽快插入依赖可信 hooks；在下一次本地工具边界处理，不中断正在执行的工具。"), wraplength=560, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        text = tk.Text(body, wrap="word", font=("Microsoft YaHei UI", 11))
        text.pack(fill="both", expand=True)
        def send():
            content = text.get("1.0", "end-1c").strip()
            if not content:
                return
            recipients = [o["leader"]] if to.current() == 0 else list(o["members"])
            data = {"body": content, "recipients": recipients, "idempotency_key": str(uuid.uuid4())}
            if mode.current():
                data["delivery_mode"] = "after_turn" if mode.current() == 1 else "immediate"
            def action():
                m = self.service.store.execute(o["id"], "human", "message_send", data)
                return self.service.deliver(o["id"], m["id"])
            button.configure(state="disabled")
            def done(result):
                top.destroy()
                self.category.set("消息")
                self.refresh(False)
                if o.get("runtime") == "native_subagents":
                    self.status.set("消息已保存，等待原生成员读取并实际投递 native_outbox；收件人 ack 后才确认收取。")
            self.submit(action, done)
        button = ttk.Button(body, text="发送", style="Accent.TButton", command=send)
        button.pack(anchor="e", pady=(10, 0))

    def delivery_mode(self):
        o = self.org()
        if not o:
            return
        top, body = self.popup("组织消息默认方式")
        choose = ttk.Combobox(body, values=["当前轮结束后", "尽快插入当前工作流 · 工具边界"], state="readonly")
        choose.current(1 if o.get("delivery_mode") == "immediate" else 0)
        choose.pack(fill="x", pady=8)
        def save():
            self.control("delivery_mode", "immediate" if choose.current() == 1 else "after_turn")
            top.destroy()
        ttk.Button(body, text="保存默认方式", command=save).pack(anchor="w", pady=10)

    def document(self):
        o = self.org()
        if not o:
            return
        current = self.selected_record() if self.category.get() == "文档" else None
        top, body = self.popup("编辑共享文档")
        key = tk.StringVar(value=current["key"] if current else "")
        ttk.Label(body, text="文档名称").pack(anchor="w")
        ttk.Entry(body, textvariable=key).pack(fill="x", pady=(5, 10))
        text = tk.Text(body, wrap="word", font=("Microsoft YaHei UI", 11))
        text.pack(fill="both", expand=True)
        if current:
            text.insert("1.0", current["body"])
        # Keep the revision seen when the editor opened, including zero for a new key.
        revisions = {k: d["revision"] for k, d in o["documents"].items()}
        def save():
            data = {"key": key.get().strip(), "body": text.get("1.0", "end-1c"),
                    "expected_revision": revisions.get(key.get().strip(), 0)}
            self.submit(lambda: self.service.store.execute(o["id"], "human", "document_write", data),
                        lambda _: (top.destroy(), self.category.set("文档"), self.refresh(False)))
        ttk.Button(body, text="保存文档", command=save).pack(anchor="e", pady=(10, 0))

    def retire(self):
        record = self.selected_record()
        if self.category.get() != "Protocols" or not record or record.get("status") != "active":
            messagebox.showinfo("废止协议", "在 Protocols 中选择一个正在使用的协议。", parent=self.root)
            return
        self.control("retire", record["id"])

    def close(self):
        self.closed = True
        self.jobs.put(None)
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()


def run(receipt=None):
    dpi_mode = enable_high_dpi()
    instance = WindowInstance()
    try:
        if instance.existing:
            if receipt:
                receipt.write_text(json.dumps({"status": "focused", "title": "Relic Organization"}), encoding="utf-8")
            return
        root = tk.Tk()
        app = OrganizationWindow(root, Service(), instance, receipt)
        app.dpi_mode = dpi_mode
        root.mainloop()
    finally:
        instance.close()
