import Foundation

/// CI observation only. This never controls product rendering or bypasses work.
@MainActor enum PerformanceRendering {
    private static var markdown: Set<UUID> = []
    private(set) static var streamVersion = -1
    static var pendingMarkdown: Int { markdown.count }
    static func beginMarkdown() -> UUID? {
        guard ResponsivenessCapture.enabled else { return nil }
        let ticket = UUID(); markdown.insert(ticket); return ticket
    }
    static func endMarkdown(_ ticket: UUID?) {
        if let ticket { markdown.remove(ticket) }
    }
    static func observed(streamVersion: Int) {
        if ResponsivenessCapture.enabled { self.streamVersion = streamVersion }
    }
}
