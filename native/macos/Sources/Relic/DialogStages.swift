import SwiftUI

/// A dialog opens cold: its view types, native labels, icons and controls are
/// created for the first time in that transaction. Building a large dialog in
/// one display turn blocks the window for 250-350 ms. Its parts are admitted
/// in separate turns of the shared row queue instead; once open, the dialog
/// is exactly the same. The CI harness waits for the ticket before settling.
@MainActor enum DialogStages {
    static func admit(_ stages: Int, label: String, advance: @MainActor (Int) -> Void) async {
        let ticket = PerformanceRendering.beginSurface()
        defer { PerformanceRendering.endSurface(ticket) }
        for stage in 1...stages {
            let turn = UUID()
            guard await RowMountQueue.shared.acquire(turn, label: label + "-" + String(stage), priority: 30) else { return }
            guard !Task.isCancelled else { RowMountQueue.shared.release(turn); return }
            advance(stage)
            // Let this part reach the display before the next one is built.
            do { try await Task.sleep(for: .milliseconds(32)) } catch { RowMountQueue.shared.release(turn); return }
            RowMountQueue.shared.release(turn)
        }
    }
}
