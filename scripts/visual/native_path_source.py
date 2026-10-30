"""Validate retained selectable-text source/paint receipts, without rendering.

The mapping is a recorded production quantity. Recomputing its documented
whitespace transformation here only checks that record; it never supplies a
missing map, a glyph measurement, a font face or a screenshot contribution.
"""
import math
import re


ICU_SOURCE = "Actual system ICU ubrk iterators over the unchanged production source"
MAP_SOURCE = "Actual production UTF16 source-to-paint mapping"
SHAPING_SOURCE = "Production unwrapped DirectWrite layout used to choose source line ranges"
COLLAPSIBLE = {9, 10, 13, 32}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _units(text):
    encoded = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]


def _slice(text, first, last):
    return text.encode("utf-16-le", "surrogatepass")[first * 2:last * 2].decode("utf-16-le", "surrogatepass")


def _boundary(units, position):
    return (type(position) is int and 0 <= position <= len(units)
            and not (0 < position < len(units) and 0xD800 <= units[position - 1] <= 0xDBFF
                     and 0xDC00 <= units[position] <= 0xDFFF))


def native_path_iterator(icu, text, typ):
    """Return one complete actual ICU boundary list, otherwise no measurement."""
    if (not isinstance(icu, dict) or icu.get("source") != ICU_SOURCE or icu.get("source_text") != text
            or not isinstance(icu.get("iterators"), list)):
        return None
    rows = [row for row in icu["iterators"] if isinstance(row, dict)
            and type(row.get("type")) is int and row["type"] == typ]
    if len(rows) != 1:
        return None
    row = rows[0]
    positions = row.get("boundaries_utf16")
    units = _units(text)
    if (type(row.get("open_status")) is not int or row["open_status"] > 0
            or not isinstance(positions, list) or len(positions) < 2
            or any(not _boundary(units, position) for position in positions)
            or positions[0] != 0 or positions[-1] != len(units)
            or any(left >= right for left, right in zip(positions, positions[1:]))):
        return None
    return positions


def native_path_source_contract(receipt):
    """Validate original source, shaping input and retained line source intervals.

Old receipts without any new mapping fields retain their unchanged-source
contract. Partially supplied new receipts never fall back to that old contract.
Object/visual-parent identity is separately required by native_path_binding.
    In particular, paint_text is the whole unwrapped shaping input. Its line-edge
    whitespace need not reach any NativeLabel; it is not a measured visible string.
"""
    if not isinstance(receipt, dict):
        return None, "Actual complete selectable-text source receipt is missing"
    source = receipt.get("source_text")
    if not isinstance(source, str) or not source:
        return None, "Actual complete selectable-text source is missing"
    source_units = _units(source)
    if type(receipt.get("source_utf16_length")) is not int or receipt["source_utf16_length"] != len(source_units):
        return None, "Actual selectable-text UTF-16 length differs from its retained source"
    layout = receipt.get("layout")
    line_rows = layout.get("lines") if isinstance(layout, dict) else None
    bindings = receipt.get("actual_line_bindings")
    mapped = any(key in receipt for key in ("source_to_paint", "text_style", "arranged_lines"))
    mapped |= isinstance(layout, dict) and any(key in layout for key in ("paint_icu", "text_style"))
    mapped |= any(isinstance(row, dict) and any(key in row for key in ("paint_start_utf16", "paint_end_utf16", "paint_text", "source_to_paint"))
                  for rows in (line_rows, bindings) if isinstance(rows, list) for row in rows)
    if not mapped:
        return {"mapped": False, "source_text": source, "paint_text": source, "normal_whitespace": False}, None
    mapping, style = receipt.get("source_to_paint"), receipt.get("text_style")
    if (not isinstance(mapping, dict) or mapping.get("source") != MAP_SOURCE or mapping.get("source_text") != source
            or not isinstance(mapping.get("paint_text"), str) or not mapping["paint_text"]
            or type(mapping.get("normal_whitespace")) is not bool or not isinstance(mapping.get("spans"), list)
            or not isinstance(style, dict) or not isinstance(layout, dict) or layout.get("text_style") != style):
        return None, "Actual source-to-paint mapping or current style receipt is missing or inconsistent"
    normal = mapping["normal_whitespace"]
    if (style.get("kind") not in ("path", "notice") or (style["kind"] == "notice") != normal
            or style.get("white_space") != ("normal" if normal else "preserve-source")
            or style.get("wrap_policy") != ("normal-boundaries-with-word-overflow" if normal else "normal-then-emergency")
            or style.get("alignment") not in ("left", "center")
            or not isinstance(style.get("configured_family_list"), str) or not style["configured_family_list"]
            or any(not _finite(style.get(key)) or style[key] <= 0 for key in ("size", "line_height"))
            or type(style.get("weight")) is not int or not 1 <= style["weight"] <= 1000):
        return None, "Actual selectable-text normal/emergency policy or configured style is incomplete"
    paint = mapping["paint_text"]
    paint_units, spans = _units(paint), mapping["spans"]
    expected_units, expected_spans, removed_source_ranges = [], [], []
    position = 0
    while position < len(source_units):
        first = position
        if normal and source_units[position] in COLLAPSIBLE:
            while position < len(source_units) and source_units[position] in COLLAPSIBLE:
                position += 1
            newline = any(unit in (10, 13) for unit in source_units[first:position])
            adjacent_zwsp = (first > 0 and source_units[first - 1] == 0x200B
                             or position < len(source_units) and source_units[position] == 0x200B)
            if newline and adjacent_zwsp:
                removed_source_ranges.append({"start_utf16": first, "end_utf16": position,
                                              "reason": "Recorded normal whitespace segment break adjacent to ZWSP"})
                continue
            unit = 32
        else:
            unit = source_units[position]
            position += 1
        expected_spans.append({"paint_start_utf16": len(expected_units), "paint_end_utf16": len(expected_units) + 1,
                               "source_start_utf16": first, "source_end_utf16": position})
        expected_units.append(unit)
    if (paint_units != expected_units or len(spans) != len(expected_spans)
            or any(not isinstance(span, dict) or set(span) != set(expected)
                   or any(type(span.get(key)) is not int or span[key] != value for key, value in expected.items())
                   for span, expected in zip(spans, expected_spans))):
        return None, "Recorded source-to-paint UTF-16 spans omit, alter, duplicate or reorder actual source units"
    measure = layout.get("source_measurement")
    if (not isinstance(measure, dict) or measure.get("source") != SHAPING_SOURCE or measure.get("source_text") != paint
            or not isinstance(measure.get("layout_com_identity_at_measurement"), str)
            or re.fullmatch(r"[0-9a-fA-F]+", measure["layout_com_identity_at_measurement"]) is None
            or int(measure["layout_com_identity_at_measurement"], 16) == 0
            or measure.get("configured_family_list") != style["configured_family_list"]
            or not _finite(measure.get("configured_size")) or measure["configured_size"] != style["size"]
            or type(measure.get("configured_weight")) is not int or measure["configured_weight"] != style["weight"]
            or any(not _finite(measure.get(key)) or measure[key] <= 0 for key in ("natural_height", "baseline"))
            or not isinstance(measure.get("clusters"), list) or not measure["clusters"]):
        return None, "Actual unwrapped DirectWrite shaping is not bound to the current paint string/style/layout"
    cluster_boundaries, position = {0}, 0
    for cluster in measure["clusters"]:
        if (not isinstance(cluster, dict) or type(cluster.get("start_utf16")) is not int or cluster["start_utf16"] != position
                or type(cluster.get("length_utf16")) is not int or cluster["length_utf16"] <= 0
                or not _finite(cluster.get("width")) or cluster["width"] < 0
                or type(cluster.get("raw_flags")) is not int or not 0 <= cluster["raw_flags"] <= 65535):
            return None, "Actual DirectWrite clusters are incomplete, overlapping or malformed"
        position += cluster["length_utf16"]
        if not _boundary(paint_units, position):
            return None, "Actual DirectWrite clusters exceed paint text or split a UTF-16 surrogate pair"
        cluster_boundaries.add(position)
    if position != len(paint_units):
        return None, "Actual DirectWrite clusters do not cover the complete paint string"
    source_iterators = {typ: native_path_iterator(layout.get("icu"), source, typ) for typ in (0, 2)}
    paint_iterators = {typ: native_path_iterator(layout.get("paint_icu"), paint, typ) for typ in (0, 2)}
    if any(value is None for value in (*source_iterators.values(), *paint_iterators.values())):
        return None, "Actual source and paint ICU iterators lack complete independently bound boundaries"
    arranged = receipt.get("arranged_lines")
    if (not isinstance(line_rows, list) or not line_rows or not isinstance(arranged, list)
            or len(arranged) != len(line_rows) or not isinstance(bindings, list) or len(bindings) != len(line_rows)):
        return None, "Actual source/paint line layouts, arrangements and retained bindings are incomplete"
    paint_position, line_contracts, omitted_paint_ranges = 0, [], []
    for line, arrangement, binding in zip(line_rows, arranged, bindings):
        if not all(isinstance(row, dict) for row in (line, arrangement, binding)):
            return None, "An actual source/paint line receipt is malformed"
        first, last = line.get("paint_start_utf16"), line.get("paint_end_utf16")
        if (not _boundary(paint_units, first) or not _boundary(paint_units, last) or first < paint_position or last <= first
                or first not in cluster_boundaries or last not in cluster_boundaries
                or first not in paint_iterators[0] or last not in paint_iterators[0]):
            return None, "Actual line paint intervals overlap, reorder or split a measured cluster/character"
        gap_units = paint_units[paint_position:first]
        if gap_units and (not normal or any(unit != 32 for unit in gap_units)):
            return None, "Actual drawn lines omit paint units other than normal line-edge spaces"
        if gap_units:
            omitted_paint_ranges.append({"start_utf16": paint_position, "end_utf16": first,
                                         "reason": "Recorded normal whitespace at a production line edge"})
        original_first = spans[first]["source_start_utf16"]
        original_last = spans[last - 1]["source_end_utf16"]
        source_slice, paint_slice = _slice(source, original_first, original_last), _slice(paint, first, last)
        fields = {"start_utf16": original_first, "end_utf16": original_last,
                  "paint_start_utf16": first, "paint_end_utf16": last}
        if (any(type(row.get(key)) is not int or row[key] != value for row in (line, arrangement, binding) for key, value in fields.items())
                or line.get("source_text") != source_slice or line.get("paint_text") != paint_slice
                or binding.get("complete_source_text") != source or binding.get("actual_label_text") != paint_slice
                or binding.get("source_slice_matches") is not (source_slice == paint_slice)
                or binding.get("paint_slice_matches") is not True or binding.get("source_to_paint") != mapping
                or binding.get("text_style") != style or binding.get("same_production_source_to_paint_map") is not True):
            return None, "Actual retained line's original source and paint mapping disagree across receipts"
        if (any(not _finite(row.get(key)) for row, key in ((binding, "actual_line_x"), (binding, "actual_line_y"),
                                                          (line, "label_y"), (arrangement, "actual_line_x"), (arrangement, "actual_line_y")))
                or binding["actual_line_x"] != arrangement["actual_line_x"]
                or binding["actual_line_y"] != arrangement["actual_line_y"] or binding["actual_line_y"] != line["label_y"]
                or any(not _finite(row.get(key)) or row[key] <= 0 for row, key in
                       ((binding, "actual_line_height"), (line, "line_height"), (line, "actual_line_baseline"),
                        (line, "actual_line_desired_width"), (line, "actual_line_desired_height"),
                        (arrangement, "actual_label_width"), (arrangement, "actual_label_height")))
                or binding["actual_line_height"] != line["line_height"]):
            return None, "Actual retained line measurements/arrangement disagree or are unmeasured"
        if type(line.get("emergency")) is not bool or normal and line["emergency"]:
            return None, "Actual normal-only selectable text reports an unknown or emergency line break"
        if normal:
            consume = last
            while consume < len(paint_units) and paint_units[consume] == 32:
                consume += 1
            # Normal line ends may be before the whitespace consumed at that
            # actual ICU boundary. This verifies a boundary; it predicts none.
            if not any(end in cluster_boundaries and end in paint_iterators[0] and end in paint_iterators[2]
                       for end in range(last, consume + 1)):
                return None, "Actual normal line end has no measured normal boundary after its trailing spaces"
        line_contracts.append({**fields, "paint_text": paint_slice, "source_text": source_slice})
        paint_position = last
    tail = paint_units[paint_position:]
    if tail and (not normal or any(unit != 32 for unit in tail)):
        return None, "Actual drawn lines omit non-whitespace trailing paint units"
    if tail:
        omitted_paint_ranges.append({"start_utf16": paint_position, "end_utf16": len(paint_units),
                                     "reason": "Recorded normal whitespace at the final production line edge"})
    return {"mapped": True, "source_text": source, "paint_text": paint, "normal_whitespace": normal,
            "line_contracts": line_contracts, "removed_source_ranges": removed_source_ranges,
            "omitted_paint_ranges": omitted_paint_ranges}, None
