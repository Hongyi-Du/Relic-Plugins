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
NSString *RelicAXRole(id object) {
    @try {
        id role = Attribute(object, @"accessibilityRole", NSAccessibilityRoleAttribute);
        return [role isKindOfClass:NSString.class] ? role : nil;
    } @catch (NSException *exception) { return nil; }
}
static NSDictionary *ChildrenObservation(id object) {
    id raw = Attribute(object, @"accessibilityChildren", NSAccessibilityChildrenAttribute);
    id ordered = Attribute(object, @"accessibilityChildrenInNavigationOrder", @"AXChildrenInNavigationOrder");
    NSArray *children = [raw isKindOfClass:NSArray.class] ? raw : @[];
    NSArray *navigation = [ordered isKindOfClass:NSArray.class] ? ordered : @[];
    NSHashTable *remaining = [NSHashTable hashTableWithOptions:NSPointerFunctionsObjectPointerPersonality];
    for (id child in children) [remaining addObject:child];
    BOOL permutation = children.count > 0 && navigation.count == children.count && remaining.count == children.count;
    if (permutation) for (id child in navigation) {
        if (![remaining containsObject:child]) { permutation = NO; break; }
        [remaining removeObject:child];
    }
    permutation = permutation && remaining.count == 0;
    // Navigation order is authoritative only when it contains exactly the
    // same actual objects. A partial navigation array must not hide siblings.
    NSArray *selected = permutation || !children.count ? navigation : children;
    NSMutableArray *rawIDs = [NSMutableArray array], *navigationIDs = [NSMutableArray array];
    for (id child in children) [rawIDs addObject:[NSString stringWithFormat:@"%p", (__bridge void *)child]];
    for (id child in navigation) [navigationIDs addObject:[NSString stringWithFormat:@"%p", (__bridge void *)child]];
    return @{@"children": selected, @"ordinary": children,
        @"evidence": @{@"source": permutation ? @"accessibilityChildrenInNavigationOrder" : !children.count ? @"navigation-only fallback" : @"accessibilityChildren",
            @"same_object_inventory": @(permutation), @"ordinary_identities": rawIDs, @"navigation_identities": navigationIDs,
            @"navigation_available": @([ordered isKindOfClass:NSArray.class])}};
}
NSArray *RelicAXChildren(id object) {
    return RelicAXChildSnapshot(object)[@"children"];
}
NSDictionary<NSString *, id> *RelicAXChildSnapshot(id object) {
    @try { return ChildrenObservation(object); }
    @catch (NSException *exception) {
        return @{@"children": @[], @"ordinary": @[],
            @"evidence": @{@"source": @"unmeasured", @"error": exception.reason ?: @"Native child getter failed"}};
    }
}
id RelicAXHitTest(id object, NSPoint screenPoint) {
    @try {
        SEL selector = @selector(accessibilityHitTest:);
        if ([object respondsToSelector:selector])
            return ((id (*)(id, SEL, NSPoint))objc_msgSend)(object, selector, screenPoint);
        return nil;
    } @catch (NSException *exception) { return nil; }
}
id RelicAXParent(id object) {
    @try { return Attribute(object, @"accessibilityParent", NSAccessibilityParentAttribute); }
    @catch (NSException *exception) { return nil; }
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
    // Read capabilities without invoking them. Current focused=false and a
    // generic AXGroup role cannot prove that a node is noninteractive.
    NSMutableDictionary *interaction = [NSMutableDictionary dictionary];
    @try {
        id actions = Attribute(object, @"accessibilityActionNames", nil);
        interaction[@"legacy_action_names"] = [actions isKindOfClass:NSArray.class] ? actions : NSNull.null;
        id custom = Attribute(object, @"accessibilityCustomActions", nil);
        NSMutableArray *names = [NSMutableArray array];
        if ([custom isKindOfClass:NSArray.class]) {
            for (id action in custom) [names addObject:Attribute(action, @"name", nil) ?: NSNull.null];
            interaction[@"custom_action_names"] = names;
        } else interaction[@"custom_action_names"] = NSNull.null;
        interaction[@"accepts_first_responder"] = Flag(object, @"acceptsFirstResponder", nil) ?: NSNull.null;
        SEL settable = NSSelectorFromString(@"accessibilityIsAttributeSettable:");
        interaction[@"legacy_focus_settable"] = [object respondsToSelector:settable]
            ? @(((BOOL (*)(id, SEL, NSString *))objc_msgSend)(object, settable, NSAccessibilityFocusedAttribute)) : NSNull.null;
    } @catch (NSException *exception) { [errors addObject:[@"interaction: " stringByAppendingString:exception.reason]]; }
    NSMutableDictionary *selectors = [NSMutableDictionary dictionary];
    SEL permission = @selector(isAccessibilitySelectorAllowed:);
    for (NSString *name in @[@"accessibilityPerformPress", @"accessibilityPerformShowMenu", @"accessibilityPerformPick",
                            @"accessibilityPerformIncrement", @"accessibilityPerformDecrement", @"accessibilityPerformConfirm",
                            @"accessibilityPerformCancel", @"accessibilityPerformDelete", @"accessibilityPerformRaise",
                            @"setAccessibilityFocused:", @"setAccessibilityValue:", @"setAccessibilityExpanded:"]) {
        @try {
            SEL selector = NSSelectorFromString(name);
            selectors[name] = @{@"responds": @([object respondsToSelector:selector]),
                                @"allowed": [object respondsToSelector:permission]
                                    ? @(((BOOL (*)(id, SEL, SEL))objc_msgSend)(object, permission, selector)) : NSNull.null};
        } @catch (NSException *exception) { [errors addObject:[NSString stringWithFormat:@"interaction.%@: %@", name, exception.reason]]; }
    }
    interaction[@"selectors"] = selectors;
    interaction[@"source"] = @"Live NSAccessibility action names, selector permissions and responder capability; no actions performed";
    result[@"interaction"] = interaction;
    NSDictionary *attributes = @{
        @"role": @[@"accessibilityRole", NSAccessibilityRoleAttribute],
        @"subrole": @[@"accessibilitySubrole", NSAccessibilitySubroleAttribute],
        @"label": @[@"accessibilityLabel", NSAccessibilityDescriptionAttribute],
        @"title": @[@"accessibilityTitle", NSAccessibilityTitleAttribute],
        @"value": @[@"accessibilityValue", NSAccessibilityValueAttribute],
        @"minimum": @[@"accessibilityMinValue", NSAccessibilityMinValueAttribute],
        @"maximum": @[@"accessibilityMaxValue", NSAccessibilityMaxValueAttribute],
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
        NSDictionary *observation = ChildrenObservation(object);
        NSArray *children = observation[@"ordinary"];
        result[@"child_count"] = @(children.count);
        NSMutableArray *classes = [NSMutableArray array];
        for (id child in children) [classes addObject:NSStringFromClass([child class])];
        result[@"child_classes"] = classes;
        result[@"child_order"] = observation[@"evidence"];
        result[@"navigation_child_count"] = [observation[@"evidence"][@"navigation_available"] boolValue]
            ? @([observation[@"evidence"][@"navigation_identities"] count]) : NSNull.null;
        if (result[@"element"] == NSNull.null && [object respondsToSelector:@selector(accessibilityIsIgnored)])
            result[@"element"] = @(![object accessibilityIsIgnored]);
    } @catch (NSException *exception) { [errors addObject:[@"children: " stringByAppendingString:exception.reason]]; }
    result[@"errors"] = errors;
    return result;
}
