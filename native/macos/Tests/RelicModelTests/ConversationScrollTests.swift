import XCTest
@testable import Relic

final class ConversationScrollTests: XCTestCase {
    func testDaySeparatorAndFollowingMessageUseCollapsedMarginsInBothDensities() {
        for (kind, continued, compact, expected) in [("message", false, false, 14.0), ("message", false, true, 8.0), ("message", true, false, 8.0), ("notice", false, false, 8.0), ("acts", false, false, 8.0)] {
            let spacing = ConversationSpacing.separatorBottom(kind: kind, continued: continued, compact: compact)
                + ConversationSpacing.messageTop(kind: kind, continued: continued, compact: compact)
            XCTAssertEqual(spacing, expected, "Day separator followed by \(kind), continued=\(continued), compact=\(compact)")
        }
    }

    func testOpeningExistingToolOutputPreservesPositionThroughIntermediateLayout() {
        var state = ConversationScrollFollowing()
        let viewport = CGSize(width: 824, height: 698)
        _ = state.observe(content: CGSize(width: 784, height: 900), bottom: 900, viewport: viewport)
        _ = state.observe(content: CGSize(width: 784, height: 900), bottom: 698, viewport: viewport)
        state.disclosureChanged()
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 900), bottom: 698, viewport: viewport))
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 996), bottom: 794, viewport: viewport),
            "The clicked disclosure adds height without issuing a bottom-scroll request")
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 998), bottom: 796, viewport: viewport),
            "A second TextKit layout pass for that same disclosure must preserve the reading position too")
        XCTAssertTrue(state.followsBottom, "A later incoming message still uses the reference's 120px follow threshold")
        state.contentChanged()
        XCTAssertTrue(state.observe(content: CGSize(width: 784, height: 1036), bottom: 834, viewport: viewport))
    }

    func testInspectorReflowPreservesPositionButNewLiveContentCanFollow() {
        var state = ConversationScrollFollowing()
        let wide = CGSize(width: 824, height: 698), narrow = CGSize(width: 644, height: 698)
        XCTAssertTrue(state.observe(content: CGSize(width: 784, height: 900), bottom: 900, viewport: wide))
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 900), bottom: 698, viewport: wide))
        // The viewport can publish its width before the content's new height.
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 900), bottom: 698, viewport: narrow))
        XCTAssertFalse(state.observe(content: CGSize(width: 604, height: 970), bottom: 768, viewport: narrow))
        XCTAssertTrue(state.followsBottom, "70px from the bottom remains inside the reference's 120px follow threshold")
        XCTAssertFalse(state.observe(content: CGSize(width: 604, height: 970), bottom: 768, viewport: narrow))
        XCTAssertTrue(state.observe(content: CGSize(width: 604, height: 1010), bottom: 808, viewport: narrow),
            "A new live result at the unchanged viewport can follow")
    }

    func testReadingOlderMessagesAndComposerResizeDoNotJumpToBottom() {
        var state = ConversationScrollFollowing()
        let viewport = CGSize(width: 824, height: 698)
        _ = state.observe(content: CGSize(width: 784, height: 900), bottom: 900, viewport: viewport)
        _ = state.observe(content: CGSize(width: 784, height: 900), bottom: 818, viewport: viewport)
        XCTAssertFalse(state.followsBottom, "The reference uses a strict distance less than 120px")
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 1000), bottom: 918, viewport: viewport))
        _ = state.observe(content: CGSize(width: 784, height: 1000), bottom: 698, viewport: viewport)
        XCTAssertTrue(state.followsBottom)
        XCTAssertFalse(state.observe(content: CGSize(width: 784, height: 1000), bottom: 698,
            viewport: CGSize(width: 824, height: 620)), "Growing the composer preserves the current message position")
    }
}
