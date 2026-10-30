"""Pair anonymous elements inside already identified semantic boundaries.

This is correspondence only: no coordinates, styles or states influence it,
and no property or mismatch is rewritten. Ambiguous unequal groups are left
for the caller's sequence alignment rather than dropping an unmatched node.
"""
from collections import defaultdict


def anonymous_anchor_pairs(reference, native, pairs, remaining_reference, remaining_native):
    """Return one-to-one pairs sharing region, kind, anchors and known parent."""
    maps = ({r: pair for pair, (r, _) in enumerate(pairs)},
            {n: pair for pair, (_, n) in enumerate(pairs)})
    groups = []
    for elements, anchors, remaining in zip((reference, native), maps,
                                            (remaining_reference, remaining_native)):
        by_id = {element.get("id"): index for index, element in enumerate(elements)}
        region_order = defaultdict(list)
        for index, element in enumerate(elements):
            region_order[element.get("region")].append(index)
        context = {}
        for region, indices in region_order.items():
            indices.sort(key=lambda index: (elements[index].get("order", index), index))
            before = None
            for index in indices:
                context[index] = [before, None]
                if index in anchors:
                    before = anchors[index]
            after = None
            for index in reversed(indices):
                context[index][1] = after
                if index in anchors:
                    after = anchors[index]
        grouped = defaultdict(list)
        for index in sorted(remaining, key=lambda index: (elements[index].get("order", index), index)):
            element = elements[index]
            if element.get("text") or element.get("name"):
                continue
            before, after = context[index]
            parent = anchors.get(by_id.get(element.get("parent")))
            if before is None and after is None and parent is None:
                continue
            grouped[(element.get("region"), element.get("kind"), before, after, parent)].append(index)
        groups.append(grouped)
    result = []
    for key, refs in groups[0].items():
        natives = groups[1].get(key, [])
        if len(refs) == len(natives):
            result.extend(zip(refs, natives))
    return result
