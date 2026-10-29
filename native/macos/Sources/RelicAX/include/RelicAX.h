#import <AppKit/AppKit.h>

NS_ASSUME_NONNULL_BEGIN
/// Read the actual informal or formal AppKit accessibility implementation.
/// SwiftUI's virtual AX nodes need not declare NSAccessibilityProtocol conformance.
FOUNDATION_EXPORT NSDictionary<NSString *, id> *RelicAXRead(id object);
FOUNDATION_EXPORT NSArray *RelicAXChildren(id object);
FOUNDATION_EXPORT NSAttributedString * _Nullable RelicAXText(id object, NSRange range);
NS_ASSUME_NONNULL_END
