"""Pair anonymous elements inside already identified semantic boundaries.

This is correspondence only: no coordinates, styles or states influence it,
and no property or mismatch is rewritten. Ambiguous unequal groups are left
for the caller's sequence alignment rather than dropping an unmatched node.
"""
from collections import defaultdict


def descendant_anchor_pairs(reference, native, pairs, remaining_reference, remaining_native):
    """Identify an anonymous container by its complete already-paired subtree.

    Require a unique signature on both sides and at least two independent
    descendant anchors. A button and its own icon are one independent anchor,
    not two. Extra painted wrappers remain separate elements; neither style
    nor geometry participates in deciding which container owns the anchors.
    """
    groups = []
    for side, elements, remaining in ((0, reference, remaining_reference), (1, native, remaining_native)):
        ids = [element.get("id") for element in elements]
        if any(not isinstance(eid, str) or not eid for eid in ids) or len(set(ids)) != len(ids):
            return []  # No reliable parent graph with duplicate/missing ids.
        by_id = {eid: index for index, eid in enumerate(ids)}
        anchors = {pair[side]: token for token, pair in enumerate(pairs)}
        paths = {}
        for index, element in enumerate(elements):
            path, seen, parent = [], {index}, element.get("parent")
            while parent is not None:
                ancestor = by_id.get(parent)
                if ancestor is None or ancestor in seen:
                    path = None
                    break
                path.append(ancestor); seen.add(ancestor)
                parent = elements[ancestor].get("parent")
            paths[index] = path
        grouped = defaultdict(list)
        for index in remaining:
            element = elements[index]
            if element.get("text") or element.get("name") or paths[index] is None:
                continue
            descendants = {anchor for anchor in anchors if paths[anchor] is not None and index in paths[anchor]}
            # Only anchors without another paired ancestor below this owner
            # provide independent structural support for this correspondence.
            independent = {anchor for anchor in descendants
                           if not any(parent in descendants for parent in paths[anchor][:paths[anchor].index(index)])}
            if len(independent) < 2:
                continue
            parent_anchor = next((anchors[parent] for parent in paths[index] if parent in anchors), None)
            signature = (element.get("region"), element.get("kind"), parent_anchor,
                         frozenset(anchors[anchor] for anchor in descendants))
            grouped[signature].append(index)
        groups.append(grouped)
    result = []
    for signature, refs in groups[0].items():
        natives = groups[1].get(signature, [])
        if len(refs) == len(natives) == 1:
            result.append((refs[0], natives[0]))
    return sorted(result)


def anonymous_anchor_pairs(reference, native, pairs, remaining_reference, remaining_native):
    """Return one-to-one pairs sharing region, kind, anchors and known parent."""
    descendant_pairs = descendant_anchor_pairs(reference, native, pairs, remaining_reference, remaining_native)
    remaining_reference = set(remaining_reference) - {r for r, _ in descendant_pairs}
    remaining_native = set(remaining_native) - {n for _, n in descendant_pairs}
    pairs = [*pairs, *descendant_pairs]
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
    result = list(descendant_pairs)
    for key, refs in groups[0].items():
        natives = groups[1].get(key, [])
        if len(refs) == len(natives):
            result.extend(zip(refs, natives))
    return result
