#import <AppKit/AppKit.h>

NS_ASSUME_NONNULL_BEGIN
/// Read the actual informal or formal AppKit accessibility implementation.
/// SwiftUI's virtual AX nodes need not declare NSAccessibilityProtocol conformance.
FOUNDATION_EXPORT NSDictionary<NSString *, id> *RelicAXRead(id object);
/// Read only role; safe to use while a native control is enumerating children.
FOUNDATION_EXPORT NSString * _Nullable RelicAXRole(id object);
FOUNDATION_EXPORT NSArray *RelicAXChildren(id object);
/// Objects and order evidence from the same getter invocation; do not serialize
/// the objects. Only the evidence dictionary is a JSON-safe capture receipt.
FOUNDATION_EXPORT NSDictionary<NSString *, id> *RelicAXChildSnapshot(id object);
FOUNDATION_EXPORT id _Nullable RelicAXHitTest(id object, NSPoint screenPoint);
FOUNDATION_EXPORT id _Nullable RelicAXParent(id object);
FOUNDATION_EXPORT NSAttributedString * _Nullable RelicAXText(id object, NSRange range);
/// Actual process counters for the CI responsiveness watchdog, without walking UI.
FOUNDATION_EXPORT NSDictionary<NSString *, NSNumber *> *RelicProcessStats(void);
NS_ASSUME_NONNULL_END
