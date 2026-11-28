import AppKit

/// A read-only passage participates in its parent's layout; resizing that
/// passage must not scroll the page to the text view's dormant insertion point.
/// Explicit selection, keyboard navigation and accessibility scrolling still
/// use NSTextView's normal implementation outside the frame assignment.
class ReadOnlyTextView: NSTextView {
    private var frameAssignmentDepth = 0

    override func setFrameSize(_ newSize: NSSize) {
        frameAssignmentDepth += 1
        defer { frameAssignmentDepth -= 1 }
        super.setFrameSize(newSize)
    }

    override func scrollToVisible(_ rect: NSRect) -> Bool {
        guard isEditable || frameAssignmentDepth == 0 else { return false }
        return super.scrollToVisible(rect)
    }
}
