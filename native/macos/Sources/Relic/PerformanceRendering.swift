import Foundation
import AppKit
import RelicCore

/// CI observation only. This never controls product rendering or bypasses work.
@MainActor enum PerformanceRendering {
    private static var observing: Bool { ResponsivenessCapture.enabled || VisualCapture.enabled || TitlebarCapture.enabled }
    private static var markdown: Set<UUID> = []
    private static var surfaces: Set<UUID> = []
    private static var mountedRows: [String: Int] = [:]
    private(set) static var streamVersion = -1
    static var pendingMarkdown: Int { markdown.count }
    static var pendingSurfaces: Int { surfaces.count }
    static func beginSurface() -> UUID? {
        guard observing else { return nil }
        let ticket = UUID(); surfaces.insert(ticket); return ticket
    }
    static func endSurface(_ ticket: UUID?) {
        if let ticket { surfaces.remove(ticket) }
    }
    static func beginMarkdown() -> UUID? {
        guard observing else { return nil }
        let ticket = UUID(); markdown.insert(ticket); return ticket
    }
    static func endMarkdown(_ ticket: UUID?) {
        if let ticket { markdown.remove(ticket) }
    }
    static func observed(streamVersion: Int) {
        if observing { self.streamVersion = streamVersion }
    }
    static func rowAppeared(_ kind: String = "message") {
        guard ResponsivenessCapture.enabled else { return }
        mountedRows[kind, default: 0] += 1; UIWorkTrace.gauge("mounted_\(kind)_rows", mountedRows[kind, default: 0])
    }
    static func rowDisappeared(_ kind: String = "message") {
        guard ResponsivenessCapture.enabled else { return }
        mountedRows[kind, default: 0] -= 1; UIWorkTrace.gauge("mounted_\(kind)_rows", mountedRows[kind, default: 0])
    }
    static func waitForContent(_ model: Model, window: NSWindow) async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + 15
        var quietPasses = 0
        repeat {
            try await Task.sleep(for: .milliseconds(100))
            let visible = RenderReadiness.observation(in: window, expectInspector: model.panelOpen && !model.organization.isEmpty, expectDialog: model.sheet != nil)
            if visible.ready, !model.isPreparingConversation, (model.organization.isEmpty || streamVersion == model.streamVersion),
               (model.streamRows.isEmpty || visible.conversationRows > 0),
               pendingSurfaces == 0, pendingMarkdown == 0 { quietPasses += 1 }
            else { quietPasses = 0 }
            if quietPasses >= 3 { return }
        } while ProcessInfo.processInfo.systemUptime < deadline
        throw RelicCore.RelicError.message("Native panes and visible Markdown did not finish preparing")
    }
}
