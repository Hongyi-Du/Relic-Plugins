import AppKit
import SwiftUI

@MainActor enum PerformancePointer {
    static var bounds: [String: CGRect] = [:]
    static var clicks: [String: Int] = [:]
    // Invoked only by the real production Button action, not by the injector.
    static func observed(_ target: String) {
        guard ResponsivenessCapture.enabled, let event = NSApp.currentEvent,
              event.type == .leftMouseUp || event.type == .leftMouseDown else { return }
        clicks[target, default: 0] += 1
    }
}

struct PerformancePointerTarget: ViewModifier {
    let identity: String
    func body(content: Content) -> some View {
        content.background {
            if ResponsivenessCapture.enabled {
                GeometryReader { proxy in
                    let rect = proxy.frame(in: .named("relic-window"))
                    Color.clear.onAppear { PerformancePointer.bounds[identity] = rect }
                        .onChange(of: rect) { PerformancePointer.bounds[identity] = rect }
                }.allowsHitTesting(false)
            }
        }
    }
}
