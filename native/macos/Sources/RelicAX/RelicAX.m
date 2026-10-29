#import "RelicAX.h"
#import <objc/message.h>

static id Attribute(id object, NSString *selector, NSString *legacy) {
    SEL sel = NSSelectorFromString(selector);
    if ([object respondsToSelector:sel]) {
        id value = ((id (*)(id, SEL))objc_msgSend)(object, sel);
        if (value) return value;
    }
    if (legacy && [object respondsToSelector:@selector(accessibilityAttributeValue:)])
        return [object accessibilityAttributeValue:legacy];
    return nil;
}
static id Flag(id object, NSString *selector, NSString *legacy) {
    SEL sel = NSSelectorFromString(selector);
    if ([object respondsToSelector:sel])
        return @(((BOOL (*)(id, SEL))objc_msgSend)(object, sel));
    return legacy ? Attribute(object, @"relicNoSuchGetter", legacy) : nil;
}
NSArray *RelicAXChildren(id object) {
    @try {
        id children = Attribute(object, @"accessibilityChildren", NSAccessibilityChildrenAttribute);
        return [children isKindOfClass:NSArray.class] ? children : @[];
    } @catch (NSException *exception) { return @[]; }
}
NSAttributedString *RelicAXText(id object, NSRange range) {
    @try {
        SEL sel = NSSelectorFromString(@"accessibilityAttributedStringForRange:");
        id result = nil;
        if ([object respondsToSelector:sel])
            result = ((id (*)(id, SEL, NSRange))objc_msgSend)(object, sel, range);
        else if ([object respondsToSelector:@selector(accessibilityAttributeValue:forParameter:)])
            result = [object accessibilityAttributeValue:NSAccessibilityAttributedStringForRangeParameterizedAttribute forParameter:[NSValue valueWithRange:range]];
        return [result isKindOfClass:NSAttributedString.class] ? result : nil;
    } @catch (NSException *exception) { return nil; }
}
NSDictionary<NSString *, id> *RelicAXRead(id object) {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    NSMutableArray *errors = [NSMutableArray array];
    NSDictionary *attributes = @{
        @"role": @[@"accessibilityRole", NSAccessibilityRoleAttribute],
        @"subrole": @[@"accessibilitySubrole", NSAccessibilitySubroleAttribute],
        @"label": @[@"accessibilityLabel", NSAccessibilityDescriptionAttribute],
        @"title": @[@"accessibilityTitle", NSAccessibilityTitleAttribute],
        @"value": @[@"accessibilityValue", NSAccessibilityValueAttribute],
        @"identifier": @[@"accessibilityIdentifier", NSAccessibilityIdentifierAttribute],
        @"help": @[@"accessibilityHelp", NSAccessibilityHelpAttribute],
        @"placeholder": @[@"accessibilityPlaceholderValue", NSAccessibilityPlaceholderValueAttribute]
    };
    for (NSString *key in attributes) {
        @try { NSArray *names = attributes[key]; result[key] = Attribute(object, names[0], names[1]) ?: NSNull.null; }
        @catch (NSException *exception) { [errors addObject:[NSString stringWithFormat:@"%@: %@", key, exception.reason]]; }
    }
    NSDictionary *flags = @{
        @"enabled": @[@"isAccessibilityEnabled", NSAccessibilityEnabledAttribute],
        @"focused": @[@"isAccessibilityFocused", NSAccessibilityFocusedAttribute],
        @"selected": @[@"isAccessibilitySelected", NSAccessibilitySelectedAttribute],
        @"expanded": @[@"isAccessibilityExpanded", NSAccessibilityExpandedAttribute],
        @"hidden": @[@"isAccessibilityHidden", @"AXHidden"],
        @"element": @[@"isAccessibilityElement", @""]
    };
    for (NSString *key in flags) {
        @try { NSArray *names = flags[key]; result[key] = Flag(object, names[0], [names[1] length] ? names[1] : nil) ?: NSNull.null; }
        @catch (NSException *exception) { [errors addObject:[NSString stringWithFormat:@"%@: %@", key, exception.reason]]; }
    }
    @try {
        if ([object respondsToSelector:@selector(accessibilityFrame)])
            result[@"frame"] = [NSValue valueWithRect:[(id<NSAccessibility>)object accessibilityFrame]];
        else {
            NSValue *position = Attribute(object, @"relicNoSuchGetter", NSAccessibilityPositionAttribute);
            NSValue *size = Attribute(object, @"relicNoSuchGetter", NSAccessibilitySizeAttribute);
            if (position && size) result[@"frame"] = [NSValue valueWithRect:(NSRect){position.pointValue, size.sizeValue}];
        }
    } @catch (NSException *exception) { [errors addObject:[@"frame: " stringByAppendingString:exception.reason]]; }
    @try {
        NSArray *children = RelicAXChildren(object);
        result[@"child_count"] = @(children.count);
        NSMutableArray *classes = [NSMutableArray array];
        for (id child in children) [classes addObject:NSStringFromClass([child class])];
        result[@"child_classes"] = classes;
        if (result[@"element"] == NSNull.null && [object respondsToSelector:@selector(accessibilityIsIgnored)])
            result[@"element"] = @(![object accessibilityIsIgnored]);
    } @catch (NSException *exception) { [errors addObject:[@"children: " stringByAppendingString:exception.reason]]; }
    result[@"errors"] = errors;
    return result;
}
