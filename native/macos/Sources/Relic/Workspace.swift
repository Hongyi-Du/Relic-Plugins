import SwiftUI
import AppKit
import RelicCore

struct WorkspaceView: View {
    @EnvironmentObject var m: Model
    @State private var workspace = Node()
    @State private var error = ""
    @State private var loading = true
    private var people: [Node] { m.members.filter { $0["surface"].text != "chat" } }
    private var base: String { workspace["git"]["root"].text.isEmpty ? workspace["folder"].text : workspace["git"]["root"].text }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                OverviewBlock {
                    heading(m.t("work.whose"))
                    FlowLayout(spacing: 5) { Rows(people) { member in
                        WorkspaceMemberChip(member: member, selected: m.workspaceMember == member["name"].text) { m.workspaceMember = member["name"].text }
                    } }
                }
                if m.workspaceMember.isEmpty { empty(m.t("work.no_members")) }
                else if !error.isEmpty { empty(error) }
                else if loading { empty(m.t("common.loading")) }
                else if workspace["folder"].text.isEmpty { empty(m.t("work.no_folder", ["name": m.name(m.workspaceMember)])) }
                else {
                    OverviewBlock {
                        HStack(spacing: 8) {
                            heading(m.t("common.work_folder")); Spacer(minLength: 0)
                            Button { m.run { try await m.post("/api/fs/open", ["path": workspace["folder"].text]) } } label: {
                                HStack(spacing: 4) { ReferenceIcon(name: "open", size: 12, color: RelicStyle.muted); ReferenceLabel(m.t("work.open_in_finder"), size: 12, color: RelicStyle.muted) }
                            }.buttonStyle(.plain)
                        }
                        ReferenceLabel(workspace["folder"].text, size: 12, color: RelicStyle.secondary, lineHeight: 18.6, lines: 0, monospaced: true).textSelection(.enabled)
                        if !workspace["exists"].flag { hint(m.t("work.folder_missing")) }
                    }
                    if workspace["exists"].flag {
                        if !workspace["git"].isNull { git }
                        if !workspace["recent"].rows.isEmpty { recent }
                        OverviewBlock { heading(m.t("work.files")); FileTree(path: workspace["folder"].text, ancestors: []).padding(.horizontal, -6) }
                    }
                }
            }
        }.onAppear { selectMember() }.onChange(of: m.selection) { selectMember() }
            .task(id: m.organization + "/" + m.workspaceMember) {
                let org = m.organization, member = m.workspaceMember; workspace = Node(); error = ""; loading = true
                guard !member.isEmpty else { loading = false; return }
                do {
                    let result = try await m.get(Client.org(org, "/workspace?member=" + Client.segment(member)))
                    try Task.checkCancellation()
                    if org == m.organization && member == m.workspaceMember { workspace = result; loading = false }
                } catch is CancellationError {} catch { self.error = m.t("common.load_failed", ["error": error.localizedDescription]); loading = false }
            }
    }
    private func selectMember() {
        guard !m.members.contains(where: { $0["name"].text == m.workspaceMember }) else { return }
        m.workspaceMember = people.contains(where: { $0["name"].text == m.member }) ? m.member : people.first?["name"].text ?? ""
    }
    private func heading(_ text: String) -> some View { ReferenceLabel(text, size: 12, color: RelicStyle.muted) }
    private func hint(_ text: String) -> some View { ReferenceLabel(text, size: 12.5, color: RelicStyle.muted, lines: 0).padding(.vertical, 6) }
    private func empty(_ text: String) -> some View { OverviewBlock { hint(text) } }
    private var git: some View {
        OverviewBlock {
            HStack(spacing: 8) {
                heading(m.t("work.git_changes") + (workspace["git"]["branch"].text.isEmpty ? "" : " · " + workspace["git"]["branch"].text)); Spacer(minLength: 0)
                if !workspace["git"]["changes"].rows.isEmpty { heading(m.t("work.file_count", ["n": String(workspace["git"]["changes"].rows.count)])) }
            }
            if workspace["git"]["changes"].rows.isEmpty { hint(m.t("work.no_changes")) }
            Rows(Array(workspace["git"]["changes"].rows.prefix(60))) { file in
                let status = FilePresentation.status(file["status"].text)
                WorkspaceFileRow(path: file["path"].text, disabled: file["status"].text.contains("D")) {
                    ReferenceLabel(status, size: 11, weight: 600, color: ["M", "R"].contains(status) ? RelicStyle.amber : ["A", "U"].contains(status) ? RelicStyle.green : status == "D" ? RelicStyle.red : RelicStyle.ink, monospaced: true).frame(width: 18)
                    Text(FilePresentation.relative(file["path"].text, root: base)).font(RelicStyle.font(12.5, weight: 400)).lineLimit(1).strikethrough(file["status"].text.contains("D"))
                }
            }
            if workspace["git"]["changes"].rows.count > 60 { hint(m.t("common.more_items", ["n": String(workspace["git"]["changes"].rows.count - 60)])) }
        }
    }
    private var recent: some View {
        OverviewBlock {
            heading(m.t("work.recent_files"))
            Rows(Array(workspace["recent"].rows.prefix(15))) { file in
                let shown = FilePresentation.relative(file["path"].text, root: base).replacingOccurrences(of: "\\", with: "/")
                let name = FilePresentation.name(shown), folder = String(shown.dropLast(name.count)).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                WorkspaceFileRow(path: file["path"].text) {
                    ReferenceIcon(name: "file", size: 14, color: RelicStyle.muted)
                    (Text(name) + Text(folder.isEmpty ? "" : "  " + folder).foregroundColor(RelicStyle.muted)).font(RelicStyle.font(12.5, weight: 400)).lineLimit(1)
                    Spacer(minLength: 0)
                    ReferenceLabel(m.ago(file["at"]), size: 11, color: RelicStyle.muted).fixedSize().padding(.leading, 8)
                }
            }
        }
    }
}

private struct WorkspaceMemberChip: View {
    let member: Node, selected: Bool
    let action: () -> Void
    @State private var hovered = false
    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Avatar(member: member["name"].text, size: 20)
                ReferenceLabel(member.display, size: 12.5, weight: selected ? 600 : 400, color: selected || hovered ? RelicStyle.ink : RelicStyle.secondary)
            }.padding(.leading, 4).padding(.trailing, 11).frame(height: 28)
                .modifier(RecordedSurface(background: selected ? RelicStyle.mix(RelicStyle.accent, RelicStyle.card, fraction: 0.1) : RelicStyle.card,
                    border: selected ? RelicStyle.accent.opacity(0.5) : RelicStyle.border, borderWidth: 1, radius: 14, hovered: hovered, selected: selected))
        }.buttonStyle(.plain).onHover { hovered = $0 }.help(member["name"].text + (member["role"].text.isEmpty ? "" : " · " + member["role"].text))
    }
}

private struct WorkspaceFileRow<Content: View>: View {
    @EnvironmentObject var m: Model
    let path: String
    var disabled = false
    @ViewBuilder let content: () -> Content
    var body: some View {
        Button { m.run { try await m.openFile(path) } } label: {
            HStack(spacing: 6) { content(); Spacer(minLength: 0) }.padding(.horizontal, 6).frame(height: 26)
        }.buttonStyle(FileRowStyle()).help(path).disabled(disabled)
    }
}

struct FileRowStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { StyledContent(configuration: configuration) }
    private struct StyledContent: View {
        let configuration: Configuration
        @State private var hovered = false
        @Environment(\.isEnabled) private var enabled
        var body: some View {
            configuration.label.contentShape(RoundedRectangle(cornerRadius: 6))
                .foregroundStyle(enabled ? RelicStyle.ink : RelicStyle.muted)
                .modifier(RecordedSurface(background: enabled && (hovered || configuration.isPressed) ? RelicStyle.hover : .clear, radius: 6, hovered: hovered))
                .onHover { hovered = $0 }
        }
    }
}

struct FileTree: View {
    @EnvironmentObject var m: Model
    let path: String
    let ancestors: Set<String>
    var depth = 0
    @State private var data = Node()
    @State private var error = ""
    @State private var expanded: Set<String> = []
    private let hidden: Set<String> = [".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"]
    private var entries: [Node] { data["entries"].rows.filter { !($0["dir"].flag && hidden.contains($0["name"].text)) } }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Rows(entries) { entry in
                let open = expanded.contains(entry["path"].text)
                Button {
                    if entry["dir"].flag { if open { expanded.remove(entry["path"].text) } else { expanded.insert(entry["path"].text) } }
                    else { m.run { try await m.openFile(entry["path"].text) } }
                } label: {
                    HStack(spacing: 6) {
                        if entry["dir"].flag { ReferenceIcon(name: "chev", size: 12, color: RelicStyle.muted).rotationEffect(.degrees(open ? 90 : 0)) }
                        else { Color.clear.frame(width: 12).accessibilityHidden(true) }
                        ReferenceIcon(name: entry["dir"].flag ? "folder" : "file", size: 14, color: RelicStyle.muted)
                        ReferenceLabel(entry["name"].text, size: 12.5); Spacer(minLength: 0)
                    }.padding(.leading, CGFloat(depth * 14 + 4)).padding(.trailing, 6).frame(height: 26)
                        .modifier(RecordedSurface(background: .clear, radius: 6, expanded: entry["dir"].flag ? open : nil))
                }.buttonStyle(FileRowStyle()).help(entry["path"].text)
                if entry["dir"].flag && open && !ancestors.union([path]).contains(entry["path"].text) {
                    AnyView(FileTree(path: entry["path"].text, ancestors: ancestors.union([path]), depth: depth + 1))
                }
            }
            if !data.isNull && entries.isEmpty { note(m.t("work.empty_dir")) }
            if data["more"].flag { note(m.t("work.list_limit")) }
            if !error.isEmpty { note(error) }
        }.task(id: path) { do { data = try await m.get("/api/fs/list?path=" + Client.segment(path)) } catch { self.error = error.localizedDescription } }
    }
    private func note(_ text: String) -> some View { ReferenceLabel(text, size: 12.5, color: RelicStyle.muted, lines: 0).padding(.leading, CGFloat(depth * 14 + 26)).padding(.vertical, 6) }
}

struct FilePreview: View {
    @EnvironmentObject var m: Model
    @State private var mode = "preview"
    @State private var codeWidth: CGFloat = 0
    private var lines: [String] { FilePresentation.lines(m.file["kind"].text == "json" && !m.file["display_text"].isNull ? m.file["display_text"].text : m.file["text"].text) }
    var body: some View {
        if m.file["path"].text.isEmpty { OverviewBlock { ReferenceLabel(m.t("file.empty"), size: 12.5, color: RelicStyle.muted, lines: 0) }; Spacer() }
        else {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                        Section { contents } header: { header }
                    }
                }.onAppear { if m.fileLine > 0 { proxy.scrollTo(m.fileLine, anchor: .center) } }
                    .onChange(of: m.fileLine) { if m.fileLine > 0 { proxy.scrollTo(m.fileLine, anchor: .center) } }
                    .onChange(of: mode) { if mode == "source" && m.fileLine > 0 { proxy.scrollTo(m.fileLine, anchor: .center) } }
            }.onChange(of: m.file["path"].text) { mode = "preview" }
        }
    }
    private var header: some View {
        HStack(spacing: 8) {
            ReferenceIcon(name: "file", size: 16, color: RelicStyle.muted)
            VStack(alignment: .leading, spacing: 0) {
                ReferenceLabel(FilePresentation.name(m.file["path"].text), size: 13, weight: 650, lineHeight: 17.55)
                ReferenceLabel(m.file["path"].text, size: 11, color: RelicStyle.muted, lineHeight: 13, monospaced: true).help(m.file["path"].text)
            }.frame(maxWidth: .infinity, alignment: .leading)
            IconButton(title: m.t("file.copy_path"), icon: "copy", size: 15) { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(m.file["path"].text, forType: .string) }
            IconButton(title: m.t("file.open_default"), icon: "open", size: 15) { m.run { try await m.post("/api/fs/open", ["path": m.file["path"].text]) } }
        }.padding(.leading, 14).padding(.trailing, 8).padding(.top, 10).padding(.bottom, 10)
            .modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "region"))
    }
    @ViewBuilder private var contents: some View {
        if !m.file["error"].text.isEmpty { OverviewBlock { ReferenceLabel(m.t("file.open_failed", ["error": m.file["error"].text]), size: 12.5, color: RelicStyle.muted, lines: 0) } }
        else if m.file["kind"].isNull { OverviewBlock { ReferenceLabel(m.t("common.loading"), size: 12.5, color: RelicStyle.muted) } }
        else {
            HStack(spacing: 10) {
                ReferenceLabel(FilePresentation.size(m.file["size"].integer), size: 11.5, color: RelicStyle.muted).fixedSize()
                ReferenceLabel(m.t("file.modified", ["when": m.ago(m.file["mtime"])]), size: 11.5, color: RelicStyle.muted).fixedSize()
                if m.file["truncated"].flag { ReferenceLabel(m.t("file.truncated"), size: 11.5, color: RelicStyle.muted) }
                Spacer(minLength: 0)
                if m.file["kind"].text == "markdown" { SettingsSegments(options: [("preview", m.t("file.preview")), ("source", m.t("file.source"))], selection: $mode) }
            }.padding(.horizontal, 14).padding(.vertical, 6)
            if m.file["kind"].text == "image", let image = m.fileImage { FileImagePreview(image: image, name: FilePresentation.name(m.file["path"].text)).padding(16) }
            else if m.file["kind"].text == "binary" { OverviewBlock { ReferenceLabel(m.t("file.binary"), size: 12.5, color: RelicStyle.muted, lines: 0) } }
            else if m.file["kind"].text == "markdown" && mode == "preview" {
                RichText(m.file["text"].text, document: true).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 18).padding(.top, 13).padding(.bottom, 24)
                    .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "region"))
            } else { code }
        }
    }
    private var code: some View {
        VStack(spacing: 0) {
            ScrollView(.horizontal) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(lines.prefix(6000).enumerated()), id: \.offset) { index, line in
                        HStack(alignment: .top, spacing: 0) {
                            ReferenceLabel(String(index + 1), size: 12, color: RelicStyle.faint, lineHeight: 19.2, alignment: .right, monospaced: true).frame(width: 46).padding(.trailing, 14)
                            SelectableText(value: AttributedString(line.isEmpty ? " " : line), pointSize: 12, lineHeight: 19.2, monospaced: true).fixedSize(horizontal: true, vertical: true)
                            Spacer(minLength: 16)
                        }.frame(minHeight: 19.2).frame(maxWidth: .infinity, alignment: .leading)
                            .modifier(FileLineHighlight(selected: m.fileLine == index + 1))
                            .id(index + 1)
                    }
                }.padding(.top, 7).padding(.bottom, 18).frame(minWidth: codeWidth, alignment: .leading)
            }.fixedSize(horizontal: false, vertical: true).background(GeometryReader { proxy in Color.clear.onAppear { codeWidth = proxy.size.width }.onChange(of: proxy.size.width) { codeWidth = proxy.size.width } })
                .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "code"))
            if lines.count > 6000 { ReferenceLabel(m.t("file.lines_shown", ["max": "6000", "total": String(lines.count)]), size: 11.5, color: RelicStyle.muted).padding(.horizontal, 14).padding(.vertical, 6) }
        }
    }
}

private struct FileImagePreview: View {
    let image: NSImage, name: String
    var body: some View {
        Image(nsImage: image).resizable().aspectRatio(contentMode: .fit).frame(maxWidth: image.size.width)
            .background {
                Canvas { context, size in
                    for y in stride(from: CGFloat.zero, to: size.height, by: 8) {
                        for x in stride(from: CGFloat.zero, to: size.width, by: 8) where (Int(x / 8) + Int(y / 8)) % 2 == 0 {
                            context.fill(Path(CGRect(x: x, y: y, width: 8, height: 8)), with: .color(RelicStyle.ink.opacity(0.06)))
                        }
                    }
                }
            }.clipShape(RoundedRectangle(cornerRadius: 8))
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, borderWidth: 1, radius: 8))
            .accessibilityLabel(name).frame(maxWidth: .infinity)
    }
}

private struct FileLineHighlight: ViewModifier {
    let selected: Bool
    func body(content: Content) -> some View {
        if selected { content.modifier(RecordedSurface(background: RelicStyle.accent.opacity(0.15), kind: "card")) }
        else { content }
    }
}
