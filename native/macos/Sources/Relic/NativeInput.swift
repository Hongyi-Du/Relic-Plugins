import AppKit
import SwiftUI
import Speech
import AVFoundation
import RelicCore

struct MentionEditor: NSViewRepresentable {
    @EnvironmentObject var m: Model
    @Binding var text: String
    var contextID = "main"
    var placeholder = ""
    var focusChanged: (Bool) -> Void = { _ in }
    var pointSize: CGFloat? = nil
    var sendsOnReturn = true
    let members: [Node]
    let onMention: (String) -> Void
    let send: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true
        let editor = ComposerTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 26.4))
        editor.drawsBackground = false; scroll.drawsBackground = false; editor.textColor = NSColor(RelicStyle.ink); editor.insertionPointColor = NSColor(RelicStyle.ink)
        editor.isRichText = false; editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false; editor.isVerticallyResizable = true
        editor.autoresizingMask = [.width]; editor.textContainer?.widthTracksTextView = true
        editor.textContainerInset = NSSize(width: 0, height: 2); editor.textContainer?.lineFragmentPadding = 0; editor.font = RelicStyle.nativeFont(14, weight: 400)
        editor.delegate = context.coordinator; editor.string = text; editor.send = send
        editor.members = members; editor.onMention = onMention
        editor.presentationModel = m; editor.composerID = contextID; editor.setAccessibilityIdentifier("relic-composer/" + contextID)
        editor.placeholder = placeholder; editor.focusChanged = focusChanged
        editor.sendsOnReturn = sendsOnReturn
        scroll.documentView = editor; return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let editor = scroll.documentView as? ComposerTextView else { return }
        if editor.string != text && !editor.hasMarkedText() { editor.closeMentions(); editor.string = text }
        editor.members = members; editor.onMention = onMention; editor.send = send
        editor.presentationModel = m; editor.composerID = contextID
        editor.placeholder = placeholder; editor.focusChanged = focusChanged
        editor.sendsOnReturn = sendsOnReturn
        let size: CGFloat = pointSize ?? (m.preferences["font"].text == "large" ? 15.5 : m.preferences["font"].text == "small" ? 13 : 14)
        let paragraph = NSMutableParagraphStyle(); paragraph.minimumLineHeight = size * 1.6; paragraph.maximumLineHeight = size * 1.6
        editor.font = RelicStyle.nativeFont(size, weight: 400); editor.defaultParagraphStyle = paragraph
        editor.typingAttributes[.tracking] = 0
        editor.textStorage?.addAttributes([.paragraphStyle: paragraph, .tracking: 0], range: NSRange(location: 0, length: (editor.string as NSString).length))
        editor.needsDisplay = true
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSScrollView, context: Context) -> CGSize? {
        guard let editor = nsView.documentView as? ComposerTextView else { return nil }
        let width = max(1, proposal.width ?? 400), font = editor.font ?? RelicStyle.nativeFont(14, weight: 400)
        let storage = NSTextStorage(string: editor.string.isEmpty ? " " : editor.string, attributes: [.font: font, .paragraphStyle: editor.defaultParagraphStyle ?? NSParagraphStyle.default, .tracking: 0])
        let layout = NSLayoutManager(), container = NSTextContainer(containerSize: NSSize(width: width, height: CGFloat.greatestFiniteMagnitude))
        container.lineFragmentPadding = 0; storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
        return CGSize(width: width, height: min(260, max(26, layout.usedRect(for: container).height + 4)))
    }
    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) { (scroll.documentView as? ComposerTextView)?.closeMentions() }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MentionEditor
        init(_ parent: MentionEditor) { self.parent = parent }
        func textDidChange(_ notification: Notification) { if let editor = notification.object as? NSTextView { parent.text = editor.string } }
    }
}

final class ComposerTextView: NSTextView {
    weak var presentationModel: Model?
    var composerID = "main"
    var sendsOnReturn = true
    var placeholder = ""
    var focusChanged: (Bool) -> Void = { _ in }
    override func accessibilityPlaceholderValue() -> String? { placeholder }
    override func becomeFirstResponder() -> Bool { let accepted = super.becomeFirstResponder(); if accepted { focusChanged(true) }; return accepted }
    override func resignFirstResponder() -> Bool { let accepted = super.resignFirstResponder(); if accepted { focusChanged(false) }; return accepted }
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        if string.isEmpty {
            let paragraph = defaultParagraphStyle ?? NSParagraphStyle.default
        NSAttributedString(string: placeholder, attributes: [.font: font ?? RelicStyle.nativeFont(14, weight: 400), .foregroundColor: NSColor(RelicStyle.muted), .paragraphStyle: paragraph, .tracking: 0])
                .draw(in: NSRect(x: textContainerInset.width, y: textContainerInset.height, width: bounds.width - textContainerInset.width * 2, height: bounds.height - textContainerInset.height * 2))
        }
    }
    var send: (() -> Void)?
    var onMention: ((String) -> Void)?
    var members: [Node] = []
    private var completing = false
    private var mentionMouseMonitor: Any?
    private var suggestions: [Node] = []
    private var suggestionIndex = 0
    var mentionSuggestionsVisible: Bool { presentationModel?.mentionEditor === self && presentationModel?.mentionVisible == true }
    override var rangeForUserCompletion: NSRange {
        let cursor = selectedRange().location
        guard cursor != NSNotFound, cursor <= (string as NSString).length else { return NSRange(location: NSNotFound, length: 0) }
        let prefix = (string as NSString).substring(to: cursor)
        if let range = prefix.range(of: #"@[^\s@]*$"#, options: .regularExpression) { return NSRange(range, in: prefix) }
        return NSRange(location: NSNotFound, length: 0)
    }
    override func keyDown(with event: NSEvent) {
        if completing {
            if event.keyCode == 53 { closeMentions(); return }
            if event.keyCode == 125 || event.keyCode == 126 {
                suggestionIndex = Self.nextSuggestion(suggestionIndex, direction: event.keyCode == 125 ? 1 : -1, count: suggestions.count); renderMentions(); return
            }
            if event.keyCode == 36 || event.keyCode == 48 { chooseMention(suggestionIndex); return }
        }
        if sendsOnReturn && event.keyCode == 36 && Composer.sendsReturn(shift: event.modifierFlags.contains(.shift), composing: hasMarkedText(), completing: completing) { send?(); return }
        super.keyDown(with: event)
        if rangeForUserCompletion.location == NSNotFound || hasMarkedText() { closeMentions() }
        else if !members.isEmpty { showMentionSuggestions() }
    }
    func showMentionSuggestions() {
        let range = rangeForUserCompletion
        guard range.location != NSNotFound, window != nil, presentationModel != nil else { closeMentions(); return }
        suggestions = mentionCandidates()
        guard !suggestions.isEmpty else { closeMentions(); return }
        completing = true; suggestionIndex = 0
        if mentionMouseMonitor == nil {
            mentionMouseMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] event in
                guard let self, let model = self.presentationModel, let window = self.window, let content = window.contentView else { return event }
                if event.window !== window { self.closeMentions(); return event }
                let screen = window.convertPoint(toScreen: event.locationInWindow)
                let canvas = window.convertToScreen(content.convert(content.bounds, to: nil))
                let point = CGPoint(x: screen.x - canvas.minX, y: canvas.maxY - screen.y)
                if !model.mentionMenuBounds.contains(point) && !model.mentionAnchor.contains(point) { self.closeMentions() }
                return event
            }
        }
        renderMentions()
    }
    func mentionAnchorRect() -> NSRect {
        let range = rangeForUserCompletion
        guard range.location != NSNotFound, let manager = layoutManager, let container = textContainer else { return NSRect(origin: textContainerOrigin, size: NSSize(width: 1, height: 18)) }
        // Keep the anchor in this text view's coordinates. Screen-coordinate
        // input-method rectangles can lag a moved/resized SwiftUI hosting window.
        manager.ensureLayout(for: container)
        let glyphs = manager.glyphRange(forCharacterRange: NSRange(location: range.location, length: 1), actualCharacterRange: nil)
        return manager.boundingRect(forGlyphRange: glyphs, in: container).offsetBy(dx: textContainerOrigin.x, dy: textContainerOrigin.y)
    }
    func mentionCandidates() -> [Node] {
        let range = rangeForUserCompletion
        guard range.location != NSNotFound else { return [] }
        let query = String((string as NSString).substring(with: range).dropFirst()).lowercased()
        return Array(members.filter { query.isEmpty || $0.display.lowercased().hasPrefix(query) || $0["name"].text.lowercased().hasPrefix(query) }.prefix(8))
    }
    static func nextSuggestion(_ index: Int, direction: Int, count: Int) -> Int { count > 0 ? (index + direction + count) % count : 0 }
    private func renderMentions() {
        guard let model = presentationModel, let window, let content = window.contentView else { return }
        let source: NSView = enclosingScrollView ?? self
        let screen = window.convertToScreen(source.convert(source.bounds, to: nil))
        let canvas = window.convertToScreen(content.convert(content.bounds, to: nil))
        model.mentionAnchor = CGRect(x: screen.minX - canvas.minX, y: canvas.maxY - screen.maxY, width: screen.width, height: screen.height)
        model.mentionEditor = self; model.mentionIndex = suggestionIndex; model.mentionItems = suggestions
    }
    func chooseMention(_ index: Int) {
        guard suggestions.indices.contains(index) else { closeMentions(); return }
        acceptMention(suggestions[index])
    }
    func acceptMention(_ member: Node) {
        let range = rangeForUserCompletion
        guard range.location != NSNotFound else { closeMentions(); return }
        insertText("@" + member.display + " ", replacementRange: range)
        onMention?(member["name"].text); closeMentions(); window?.makeFirstResponder(self)
    }
    func closeMentions() {
        completing = false; suggestions = []; suggestionIndex = 0
        if let mentionMouseMonitor { NSEvent.removeMonitor(mentionMouseMonitor); self.mentionMouseMonitor = nil }
        if let model = presentationModel, model.mentionEditor === self { model.mentionItems = []; model.mentionEditor = nil; model.mentionVisible = false }
    }
}

// The native completion menu shares the application's coordinate space. It has
// no system-popover arrow, separate window chrome or unrelated role subtitle.
struct MentionSuggestions: View {
    @EnvironmentObject var m: Model
    private var width: CGFloat {
        max(220, m.mentionItems.map {
            74 + ($0.display as NSString).size(withAttributes: [.font: RelicStyle.nativeFont(13, weight: 400), .tracking: 0]).width
                + ($0["name"].text as NSString).size(withAttributes: [.font: RelicStyle.monoFont(11.96), .tracking: 0]).width
        }.max() ?? 220)
    }
    private var height: CGFloat { min(m.windowSize.height * 0.6, CGFloat(m.mentionItems.count) * 34.8 + 14) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(m.mentionItems.enumerated()), id: \.offset) { index, member in
                        Button { m.mentionEditor?.chooseMention(index) } label: {
                            HStack(spacing: 10) {
                                Avatar(member: member["name"].text, size: 20)
                                ReferenceLabel(member.display, size: 13)
                                ReferenceLabel(member["name"].text, size: 11.96, color: RelicStyle.muted, monospaced: true)
                                Spacer(minLength: 0)
                            }.padding(.horizontal, 10).frame(height: 34.8)
                        }.buttonStyle(MenuItemStyle(selected: index == m.mentionIndex)).accessibilityIdentifier("relic-menu-item/mention/" + member["name"].text)
                    }
                }.padding(7)
            }.frame(width: width, height: height)
                .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 12, kind: "region", shadows: SurfaceShadow.dialog))
                .background(GeometryReader { proxy in Color.clear.preference(key: MentionMenuBounds.self, value: proxy.frame(in: .named("relic-window"))) })
                .offset(x: m.mentionAnchor.minX, y: m.mentionAnchor.minY - 8 - height)
                .measuredRegion("menu")
                .onPreferenceChange(MentionMenuBounds.self) { m.mentionMenuBounds = $0 }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .onAppear { m.mentionVisible = true }.onDisappear { m.mentionVisible = false }
            .onExitCommand { m.mentionEditor?.closeMentions() }
    }
}

private struct MentionMenuBounds: PreferenceKey {
    static var defaultValue = CGRect.zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}

@MainActor final class SpeechInput: ObservableObject {
    @Published var recording = false
    @Published var starting = false
    private let audio = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapInstalled = false
    private var requestID = UUID()
    private var ended: (() -> Void)?
    func start(language: String, model: Model, ended: @escaping () -> Void = {}, update: @escaping (String) -> Void) async throws {
        guard !starting && !recording else { return }; stop(); starting = true
        if model.activeSpeech !== self { model.activeSpeech?.stop() }; model.activeSpeech = self
        self.ended = ended
        let id = UUID(); requestID = id
        defer { starting = false }
        // Shared packaging supplies the privacy keys; never trigger Apple's fatal missing-key path.
        guard Bundle.main.object(forInfoDictionaryKey: "NSSpeechRecognitionUsageDescription") != nil,
              Bundle.main.object(forInfoDictionaryKey: "NSMicrophoneUsageDescription") != nil else { throw RelicError.message(model.t("native.speech_unavailable")) }
        let speech = await withCheckedContinuation { continuation in SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) } }
        guard requestID == id && !Task.isCancelled else { return }
        guard speech else { throw RelicError.message(model.t("native.speech_permission")) }
        let microphone = await AVCaptureDevice.requestAccess(for: .audio)
        guard requestID == id && !Task.isCancelled else { return }
        guard microphone else { throw RelicError.message(model.t("native.microphone_permission")) }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: language)), recognizer.isAvailable else { throw RelicError.message(model.t("native.speech_unavailable")) }
        let request = SFSpeechAudioBufferRecognitionRequest(); request.shouldReportPartialResults = true; self.request = request
        let input = audio.inputNode, format = audio.inputNode.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { throw RelicError.message(model.t("composer.voice_no_mic")) }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }; tapInstalled = true
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                guard self?.requestID == id else { return }
                if let result { update(result.bestTranscription.formattedString) }
                if let error {
                    let ns = error as NSError
                    if ns.domain == NSURLErrorDomain { model.error = model.t("composer.voice_network") }
                    else if ns.code == 1110 { model.notice = model.t("composer.voice_no_speech") }
                    else if ns.code != 216 { model.error = model.t("composer.voice_start_failed", ["error": error.localizedDescription]) }
                }
                if error != nil || result?.isFinal == true { self?.stop() }
            }
        }
        do { audio.prepare(); try audio.start(); recording = true } catch { stop(); throw error }
    }
    func stop() {
        requestID = UUID(); audio.stop()
        if tapInstalled { audio.inputNode.removeTap(onBus: 0); tapInstalled = false }
        request?.endAudio(); task?.cancel(); task = nil; request = nil; recording = false
        let completion = ended; ended = nil; completion?()
    }
}

struct VoiceButton: View {
    @EnvironmentObject var m: Model
    @Binding var text: String
    var size: CGFloat = 26
    @StateObject private var voice = SpeechInput()
    var body: some View {
        if m.preferences["voice"].text != "off" {
            IconButton(title: m.t("common.voice_input"), icon: voice.recording ? "stop" : "mic", size: 17, height: size, width: size, action: toggle)
                .disabled(voice.starting).tint(voice.recording ? .red : nil).help(m.t("composer.voice_title")).onDisappear { voice.stop() }
        }
    }
    private func toggle() {
        guard m.preferences["voice"].text != "off" else { m.notice = m.t("composer.voice_off"); return }
        if voice.recording { voice.stop(); return }
        let focused = NSApp.keyWindow?.firstResponder as? NSTextView
        let editor = focused?.string == text ? focused : nil
        let insertion = DictationInsertion(text: text, selection: editor?.selectedRange())
        m.run {
            do {
                try await voice.start(language: m.words.language, model: m, ended: { [weak editor] in
                    if let editor, let window = editor.window, window.isKeyWindow { window.makeFirstResponder(editor) }
                }) { [weak editor] transcription in
                    let result = insertion.applying(transcription)
                    text = result.text
                    if let editor, editor.window != nil {
                        editor.string = result.text
                        editor.setSelectedRange(NSRange(location: result.caret, length: 0))
                        editor.didChangeText()
                    }
                }
            } catch { voice.stop(); throw error }
        }
    }
}

extension View {
    func dictation(_ text: Binding<String>) -> some View { HStack(alignment: .top) { self; VoiceButton(text: text).labelStyle(.iconOnly) } }
}

@MainActor func pickAvatar(_ model: Model, member: String? = nil) async throws {
    let panel = NSOpenPanel(); panel.allowedContentTypes = [.png, .jpeg, .heic, .gif]; panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
    guard await panel.begin() == .OK, let url = panel.url, let source = NSImage(contentsOf: url) else { return }
    guard ((try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) <= 2 * 1024 * 1024 else { throw RelicError.message(model.t("card.image_too_large")) }
    let size = NSSize(width: 256, height: 256), resized = NSImage(size: size)
    resized.lockFocus(); source.draw(in: NSRect(origin: .zero, size: size)); resized.unlockFocus()
    guard let tiff = resized.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff), let data = bitmap.representation(using: .png, properties: [:]) else { return }
    var body: [String: Any] = ["data": "data:image/png;base64," + data.base64EncodedString()]
    if let member { body["org"] = model.organization; body["member"] = member }
    let result = try await model.post("/api/avatar", body)
    model.notice = model.t("card.avatar_changed")
    if member == nil { model.preferences = Node(model.preferences.object.merging(["avatar": result["avatar"].raw]) { _, new in new }) }
    try await model.refresh()
}
