import AppKit
import SwiftUI
import Speech
import AVFoundation
import RelicCore

struct MentionEditor: NSViewRepresentable {
    @Binding var text: String
    let members: [Node]
    let onMention: (String) -> Void
    let send: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true
        let editor = ComposerTextView()
        editor.drawsBackground = false; scroll.drawsBackground = false; editor.textColor = NSColor.labelColor; editor.insertionPointColor = NSColor.labelColor
        editor.isRichText = false; editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false; editor.isVerticallyResizable = true
        editor.autoresizingMask = [.width]; editor.textContainer?.widthTracksTextView = true
        editor.textContainerInset = NSSize(width: 6, height: 6); editor.font = .systemFont(ofSize: 14)
        editor.delegate = context.coordinator; editor.string = text; editor.send = send
        editor.members = members; editor.onMention = onMention
        scroll.documentView = editor; return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let editor = scroll.documentView as? ComposerTextView else { return }
        if editor.string != text && !editor.hasMarkedText() { editor.string = text }
        editor.members = members; editor.onMention = onMention; editor.send = send
    }
    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MentionEditor
        init(_ parent: MentionEditor) { self.parent = parent }
        func textDidChange(_ notification: Notification) { if let editor = notification.object as? NSTextView { parent.text = editor.string } }
        func textView(_ textView: NSTextView, completions words: [String], forPartialWordRange range: NSRange, indexOfSelectedItem index: UnsafeMutablePointer<Int>?) -> [String] {
            guard let editor = textView as? ComposerTextView else { return [] }
            let query = (editor.string as NSString).substring(with: range).dropFirst().lowercased()
            return editor.members.filter { $0.display.lowercased().hasPrefix(query) || $0["name"].text.lowercased().hasPrefix(query) }.prefix(8).map { "@" + $0.display }
        }
    }
}

final class ComposerTextView: NSTextView {
    var send: (() -> Void)?
    var onMention: ((String) -> Void)?
    var members: [Node] = []
    private var completing = false
    override var rangeForUserCompletion: NSRange {
        let cursor = selectedRange().location
        guard cursor != NSNotFound, cursor <= (string as NSString).length else { return NSRange(location: NSNotFound, length: 0) }
        let prefix = (string as NSString).substring(to: cursor)
        if let range = prefix.range(of: #"@[^\s@]*$"#, options: .regularExpression) { return NSRange(range, in: prefix) }
        return NSRange(location: NSNotFound, length: 0)
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 36 && Composer.sendsReturn(shift: event.modifierFlags.contains(.shift), composing: hasMarkedText(), completing: completing) { send?(); return }
        super.keyDown(with: event)
        if event.keyCode == 53 || rangeForUserCompletion.location == NSNotFound { completing = false }
        if event.characters == "@", !members.isEmpty, !hasMarkedText() { completing = true; complete(nil) }
    }
    override func insertCompletion(_ word: String, forPartialWordRange range: NSRange, movement: Int, isFinal: Bool) {
        super.insertCompletion(word, forPartialWordRange: range, movement: movement, isFinal: isFinal)
        if isFinal { completing = false; if let member = members.first(where: { "@" + $0.display == word }) { onMention?(member["name"].text) } }
    }
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
    @StateObject private var voice = SpeechInput()
    var body: some View {
        if m.preferences["voice"].text != "off" {
            Button(action: toggle) {
                Label(m.t("common.voice_input"), systemImage: voice.recording ? "stop.circle.fill" : "mic")
            }.buttonStyle(.borderless).controlSize(.small).disabled(voice.starting).tint(voice.recording ? .red : nil).help(m.t("composer.voice_title")).onDisappear { voice.stop() }
        } else {
            Image(systemName: "mic.slash").foregroundStyle(.secondary).help(m.t("composer.voice_off"))
        }
    }
    private func toggle() {
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
