import SwiftUI
import AppKit
import RelicCore

struct WorkspaceView: View {
    @EnvironmentObject var m: Model
    @State private var who = ""
    @State private var workspace = Node()
    @State private var error = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Picker(m.t("work.whose"), selection: $who) { Rows(m.members.filter { $0["surface"].text != "chat" }) { Text($0.display).tag($0["name"].text) } }
                if who.isEmpty { Text(m.t("work.no_members")) }
                else if workspace["folder"].text.isEmpty { Text(m.t("work.no_folder", ["name": m.name(who)])) }
                else {
                    Text(workspace["folder"].text).textSelection(.enabled)
                    Button(m.t("work.open_in_finder")) { m.run { try await m.post("/api/fs/open", ["path": workspace["folder"].text]) } }
                    if !workspace["exists"].flag { Text(m.t("work.folder_missing")) }
                    else {
                        Text(m.t("work.git_changes") + " · " + workspace["git"]["branch"].text).font(.headline)
                        Text(m.t("work.file_count", ["n": String(workspace["git"]["changes"].rows.count)])).font(.caption)
                        if workspace["git"]["changes"].rows.isEmpty { Text(m.t("work.no_changes")) }
                        Rows(workspace["git"]["changes"].rows) { file in Button(file["status"].text + " " + file["path"].text) { m.run { try await m.openFile(file["path"].text) } }.disabled(file["status"].text.contains("D")) }
                        Text(m.t("work.recent_files")).font(.headline)
                        Rows(workspace["recent"].rows) { file in Button(file["path"].text + " · " + file["at"].text) { m.run { try await m.openFile(file["path"].text) } } }
                        Text(m.t("work.files")).font(.headline)
                        FileTree(path: workspace["folder"].text, ancestors: [])
                    }
                }
                if !error.isEmpty { Text(error).foregroundStyle(.red) }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.onAppear { who = m.member.isEmpty ? m.members.first(where: { $0["surface"].text != "chat" })?["name"].text ?? "" : m.member }
        .onChange(of: m.selection) { who = m.member.isEmpty ? m.members.first(where: { $0["surface"].text != "chat" })?["name"].text ?? "" : m.member }
        .task(id: m.organization + "/" + who) {
            let org = m.organization, member = who; workspace = Node(); error = ""
            guard !member.isEmpty else { return }
            do { let result = try await m.get(Client.org(org, "/workspace?member=" + Client.segment(member))); try Task.checkCancellation(); if org == m.organization && member == who { workspace = result } }
            catch is CancellationError {} catch { self.error = error.localizedDescription }
        }
    }
}

struct FileTree: View {
    @EnvironmentObject var m: Model
    let path: String
    let ancestors: Set<String>
    @State private var data = Node()
    @State private var expanded: Set<String> = []
    @State private var error = ""
    private let hidden: Set<String> = [".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"]
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Rows(data["entries"].rows.filter { !($0["dir"].flag && hidden.contains($0["name"].text)) }) { entry in
                if entry["dir"].flag {
                    DisclosureGroup(isExpanded: Binding(get: { expanded.contains(entry["path"].text) }, set: { if $0 { expanded.insert(entry["path"].text) } else { expanded.remove(entry["path"].text) } })) {
                        if expanded.contains(entry["path"].text), !ancestors.union([path]).contains(entry["path"].text) {
                            AnyView(FileTree(path: entry["path"].text, ancestors: ancestors.union([path])).padding(.leading, 10))
                        }
                    } label: { Label(entry["name"].text, systemImage: "folder") }
                } else { Button { m.run { try await m.openFile(entry["path"].text) } } label: { Label(entry["name"].text, systemImage: "doc") }.buttonStyle(.plain) }
            }
            if data["entries"].rows.isEmpty { Text(m.t("work.empty_dir")).foregroundStyle(.secondary) }
            if data["more"].flag { Text(m.t("work.list_limit")) }
            if !error.isEmpty { Text(error).foregroundStyle(.red) }
        }.task(id: path) { do { data = try await m.get("/api/fs/list?path=" + Client.segment(path)) } catch { self.error = error.localizedDescription } }
    }
}

struct FilePreview: View {
    @EnvironmentObject var m: Model
    @State private var source = false
    @State private var jump = ""
    private var lines: [String] {
        let text = m.file["text"].text
        if m.file["kind"].text == "json", let data = text.data(using: .utf8), let json = try? JSONSerialization.jsonObject(with: data) { return pretty(Node(json)).components(separatedBy: "\n") }
        return text.components(separatedBy: "\n")
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if m.file["path"].text.isEmpty { Text(m.t("file.empty")); Spacer() }
            else {
                Text(m.file["name"].text).font(.headline)
                Text(m.file["path"].text).font(.caption).textSelection(.enabled)
                HStack {
                    Button(m.t("file.copy_path")) { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(m.file["path"].text, forType: .string) }
                    Button(m.t("file.open_default")) { m.run { try await m.post("/api/fs/open", ["path": m.file["path"].text]) } }
                }
                Text(ByteCountFormatter.string(fromByteCount: Int64(m.file["size"].integer), countStyle: .file) + " · " + m.t("file.modified", ["when": m.file["mtime"].text])).font(.caption)
                if m.file["truncated"].flag { Text(m.t("file.truncated")).foregroundStyle(.orange) }
                if m.file["kind"].text == "image", let image = m.fileImage { ScrollView([.horizontal, .vertical]) { Image(nsImage: image).resizable().scaledToFit().frame(maxWidth: 1200) } }
                else if m.file["kind"].text == "binary" { Text(m.t("file.binary")); Spacer() }
                else {
                    if m.file["kind"].text == "markdown" { Picker("", selection: $source) { Text(m.t("file.preview")).tag(false); Text(m.t("file.source")).tag(true) }.pickerStyle(.segmented) }
                    if m.file["kind"].text == "markdown" && !source { ScrollView { RichText(m.file["text"].text) } }
                    else {
                        ScrollViewReader { proxy in
                            HStack { TextField("#", text: $jump).frame(width: 70).onSubmit { if let line = Int(jump) { m.fileLine = line; proxy.scrollTo(line, anchor: .center) } }; Button(m.t("common.open")) { if let line = Int(jump) { m.fileLine = line; proxy.scrollTo(line, anchor: .center) } } }
                            ScrollView([.vertical, .horizontal]) {
                                LazyVStack(alignment: .leading, spacing: 0) {
                                    ForEach(Array(lines.prefix(6000).enumerated()), id: \.offset) { index, line in
                                        HStack(alignment: .top) { Text(String(index + 1)).foregroundStyle(.secondary).frame(width: 50, alignment: .trailing); Text(line.isEmpty ? " " : line).textSelection(.enabled) }
                                            .font(.system(.caption, design: .monospaced)).padding(.vertical, 2).background(m.fileLine == index + 1 ? Color.accentColor.opacity(0.15) : .clear).id(index + 1)
                                    }
                                }
                            }.onAppear { proxy.scrollTo(m.fileLine, anchor: .center) }.onChange(of: m.fileLine) { proxy.scrollTo(m.fileLine, anchor: .center) }
                            if lines.count > 6000 { Text(m.t("file.lines_shown", ["max": "6000", "total": String(lines.count)])).font(.caption) }
                        }
                    }
                }
            }
        }.onChange(of: m.file["path"].text) { source = false; jump = m.fileLine == 0 ? "" : String(m.fileLine) }
    }
}
