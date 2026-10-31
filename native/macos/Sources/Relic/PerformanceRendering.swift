import Foundation

/// CI observation only. This never controls product rendering or bypasses work.
@MainActor enum PerformanceRendering {
    private static var markdown: Set<UUID> = []
    private static var surfaces: Set<UUID> = []
    private static var mountedRows: [String: Int] = [:]
    private(set) static var streamVersion = -1
    static var pendingMarkdown: Int { markdown.count }
    static var pendingSurfaces: Int { surfaces.count }
    static func beginSurface() -> UUID? {
        guard ResponsivenessCapture.enabled else { return nil }
        let ticket = UUID(); surfaces.insert(ticket); return ticket
    }
    static func endSurface(_ ticket: UUID?) {
        if let ticket { surfaces.remove(ticket) }
    }
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
    static func rowAppeared(_ kind: String = "message") {
        guard ResponsivenessCapture.enabled else { return }
        mountedRows[kind, default: 0] += 1; UIWorkTrace.gauge("mounted_\(kind)_rows", mountedRows[kind, default: 0])
    }
    static func rowDisappeared(_ kind: String = "message") {
        guard ResponsivenessCapture.enabled else { return }
        mountedRows[kind, default: 0] -= 1; UIWorkTrace.gauge("mounted_\(kind)_rows", mountedRows[kind, default: 0])
    }
}
