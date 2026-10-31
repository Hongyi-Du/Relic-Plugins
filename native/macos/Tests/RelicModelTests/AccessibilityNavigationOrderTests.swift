import XCTest
import AppKit
import RelicAX

@MainActor final class AccessibilityNavigationOrderTests: XCTestCase {
    private final class Owner: NSObject {
        var children: [Any] = [], navigation: [Any] = []
        @objc func accessibilityChildren() -> [Any] { children }
        @objc func accessibilityChildrenInNavigationOrder() -> [Any] { navigation }
    }
    func testNativeNavigationOrderRequiresTheExactOrdinaryChildInventory() throws {
        let first = NSObject(), second = NSObject(), unrelated = NSObject(), owner = Owner()
        owner.children = [first, second]; owner.navigation = [second, first]
        func ids() -> [ObjectIdentifier] { RelicAXChildren(owner).map { ObjectIdentifier($0 as AnyObject) } }
        XCTAssertEqual(ids(), [ObjectIdentifier(second), ObjectIdentifier(first)])
        let evidence = try XCTUnwrap(RelicAXRead(owner)["child_order"] as? [String: Any])
        XCTAssertEqual(evidence["source"] as? String, "accessibilityChildrenInNavigationOrder")
        XCTAssertEqual(evidence["same_object_inventory"] as? Bool, true)
        let snapshot = RelicAXChildSnapshot(owner)
        XCTAssertEqual((snapshot["children"] as? [Any])?.map { ObjectIdentifier($0 as AnyObject) }, [ObjectIdentifier(second), ObjectIdentifier(first)])
        XCTAssertEqual((snapshot["evidence"] as? [String: Any])?["source"] as? String, "accessibilityChildrenInNavigationOrder")
        for invalid in [[second], [second, second], [second, unrelated], [second, first, unrelated]] {
            owner.navigation = invalid
            XCTAssertEqual(ids(), [ObjectIdentifier(first), ObjectIdentifier(second)], "An incomplete or foreign navigation list must never remove an actual child")
            XCTAssertEqual((RelicAXRead(owner)["child_order"] as? [String: Any])?["same_object_inventory"] as? Bool, false)
        }
        owner.children = []; owner.navigation = [first]
        XCTAssertEqual(ids(), [ObjectIdentifier(first)])
    }
}
