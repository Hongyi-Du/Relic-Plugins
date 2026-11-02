import XCTest
@testable import Relic

@MainActor final class RowMountQueueTests: XCTestCase {
    func testLatestContentGetsTheNextTurnWithoutReorderingPeersOrStrandingOtherPanes() async {
        let queue = RowMountQueue(), active = UUID()
        let acquired = await queue.acquire(active); XCTAssertTrue(acquired)
        var order: [String] = []
        var tasks: [Task<Void, Never>] = []
        for (name, priority) in [("inspector", 0), ("visible-1", 10), ("visible-2", 10), ("latest", 20)] {
            let id = UUID(), count = tasks.count + 1
            tasks.append(Task {
                if await queue.acquire(id, priority: priority) { order.append(name); queue.release(id) }
            })
            while queue.waitingCount < count { await Task.yield() }
        }
        queue.release(active)
        for task in tasks { await task.value }
        XCTAssertEqual(order, ["latest", "visible-1", "visible-2", "inspector"])
        XCTAssertTrue(queue.isIdle)
    }
    func testOneRowAtATimeAndCancellationDoesNotStrandFollowingRows() async {
        let queue = RowMountQueue(), first = UUID(), removed = UUID(), last = UUID()
        let acquired = await queue.acquire(first)
        XCTAssertTrue(acquired)
        var order: [String] = []
        let cancelled = Task { let granted = await queue.acquire(removed); if granted { order.append("removed"); queue.release(removed) }; return granted }
        let next = Task { let granted = await queue.acquire(last); if granted { order.append("last"); queue.release(last) }; return granted }
        while queue.waitingCount < 2 { await Task.yield() }
        XCTAssertTrue(order.isEmpty)
        cancelled.cancel()
        let removedAcquired = await cancelled.value
        XCTAssertFalse(removedAcquired)
        queue.release(first)
        let lastAcquired = await next.value
        XCTAssertTrue(lastAcquired); XCTAssertEqual(order, ["last"])
        XCTAssertEqual(queue.waitingCount, 0)
    }
    func testCancelledOwnerReleasesTheNextTurn() async {
        let queue = RowMountQueue(), first = UUID(), second = UUID()
        let acquired = await queue.acquire(first); XCTAssertTrue(acquired)
        let next = Task { await queue.acquire(second) }
        while queue.waitingCount == 0 { await Task.yield() }
        queue.release(UUID()) // A stale row cannot release another row's turn.
        XCTAssertEqual(queue.waitingCount, 1)
        queue.release(first)
        let nextAcquired = await next.value; XCTAssertTrue(nextAcquired)
        queue.release(second); XCTAssertEqual(queue.waitingCount, 0)
    }
}
