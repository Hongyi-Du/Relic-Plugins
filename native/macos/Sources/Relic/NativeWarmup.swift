import SwiftUI

/// Shown, invisibly, only while the first organization loads. Creating one
/// native List row with a label and a selectable passage moves AppKit's
/// one-time table, TextKit and font setup into launch, instead of blocking
/// the first chat that appears after the data arrives.
struct NativeWarmup: View {
    var body: some View {
        List {
            ReferenceLabel("Relic 组织 Organization", size: 13.3, weight: 600)
            SelectableText(value: AttributedString("原生界面准备中。 Preparing native text."), pointSize: 14, lineHeight: 23.1)
        }
        .listStyle(.plain)
        .frame(width: 360, height: 120)
        .opacity(0)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
