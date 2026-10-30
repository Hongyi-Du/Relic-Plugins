"""CI-only synthetic source/paint receipts; no native layout or process starts."""
from copy import deepcopy
import unittest

from element_parity import native_path_failure_owners
from native_path_source import native_path_source_contract
from test_windows_native_path import synthetic, project_fixture
from windows_elements import native_path_binding


def utf16_length(text):
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def utf16_slice(text, first, last):
    return text.encode("utf-16-le", "surrogatepass")[first * 2:last * 2].decode("utf-16-le", "surrogatepass")


def iterator(text):
    # Controlled boundary fixture, not a measurement from an installed ICU.
    boundaries, position = [0], 0
    for character in text:
        position += utf16_length(character)
        boundaries.append(position)
    return {"source": "Actual system ICU ubrk iterators over the unchanged production source", "source_text": text,
            "iterators": [{"type": typ, "open_status": 0, "boundaries_utf16": list(boundaries)} for typ in (0, 2)]}


def mapped_fixture(source=" \tab \t x\r\n😀cd ", paint=" ab x 😀cd ",
                   source_ranges=((0, 2), (2, 3), (3, 4), (4, 7), (7, 8), (8, 10),
                                  (10, 11), (11, 12), (12, 13), (13, 14), (14, 15)),
                   line_ranges=((1, 5), (6, 10)), normal=True):
    """Explicit source spans with authentic schema, never recorded UI evidence."""
    raw, elements, providers, pairs = synthetic()
    owner = raw["path"]
    owner["accessible_name"] = providers[0]["name"] = source
    receipt = owner["native_path_evidence"]
    mapping = {"source": "Actual production UTF16 source-to-paint mapping", "source_text": source,
               "paint_text": paint, "normal_whitespace": normal,
               "spans": [{"paint_start_utf16": i, "paint_end_utf16": i + 1, "source_start_utf16": first, "source_end_utf16": last}
                         for i, (first, last) in enumerate(source_ranges)]}
    style = {"kind": "notice" if normal else "path", "configured_family_list": "Synthetic actual configured UI family",
             "size": 12, "weight": 400, "line_height": 19.2, "alignment": "center" if normal else "left",
             "white_space": "normal" if normal else "preserve-source",
             "wrap_policy": "normal-boundaries-with-word-overflow" if normal else "normal-then-emergency",
             "strut_family": None, "strut_size": 0, "strut_line_height": 0}
    clusters, position = [], 0
    for character in paint:
        length = utf16_length(character)
        clusters.append({"start_utf16": position, "length_utf16": length, "width": length * 6, "raw_flags": 0})
        position += length
    measurement = {"source": "Production unwrapped DirectWrite layout used to choose source line ranges",
                   "source_text": paint, "layout_com_identity_at_measurement": "123456", "clusters": clusters,
                   "configured_family_list": style["configured_family_list"], "configured_size": 12, "configured_weight": 400,
                   "natural_height": 15, "baseline": 12}
    receipt.update(source_text=source, source_utf16_length=utf16_length(source), source_to_paint=mapping,
                   text_style=style, arranged_lines=[])
    receipt["layout"].update(text_style=deepcopy(style), icu=iterator(source), paint_icu=iterator(paint),
                             source_measurement=measurement, parent_strut_measurement=None)
    for index, (first, last) in enumerate(line_ranges):
        binding = receipt["actual_line_bindings"][index]
        source_first, source_last = source_ranges[first][0], source_ranges[last - 1][1]
        original = utf16_slice(source, source_first, source_last)
        painted = utf16_slice(paint, first, last)
        fields = {"start_utf16": source_first, "end_utf16": source_last, "paint_start_utf16": first, "paint_end_utf16": last}
        binding.update(**fields, complete_source_text=source, actual_label_text=painted,
                       source_slice_matches=original == painted, paint_slice_matches=True,
                       same_production_source_to_paint_map=True,
                       source_to_paint=deepcopy(mapping), text_style=deepcopy(style), actual_line_x=3)
        receipt["layout"]["lines"][index].update(**fields, source_text=original, paint_text=painted,
                                                actual_line_baseline=12, actual_line_desired_width=30,
                                                actual_line_desired_height=14)
        receipt["arranged_lines"].append({**fields, "actual_line_x": 3, "actual_line_y": index * 20,
                                         "actual_label_width": 30, "actual_label_height": 14})
        line = raw["line-" + str(index)]
        line.update(text=painted, local_bounds={"x": 0, "y": 0, "width": 30, "height": 14},
                    native_path_line_evidence=deepcopy(binding))
        elements[index]["text"] = painted
        elements[index]["style"]["font_size"] = style["size"]
        elements[index]["style"]["rendered_fonts"][0]["glyph_count"] = len(painted)
        elements[index]["evidence"]["font_weight_quantities"]["resolved"]["faces"][0]["glyph_count"] = len(painted)
        metric = elements[index]["evidence"]["native_label_geometry"]["font_metric_advance"][0]
        metric["description"].update(text=painted, text_length_utf16=utf16_length(painted))
    return raw, elements, providers, pairs


def sync_line_receipts(raw):
    for binding in raw["path"]["native_path_evidence"]["actual_line_bindings"]:
        raw[binding["line_id"]]["native_path_line_evidence"] = deepcopy(binding)


class NativePathSourceTests(unittest.TestCase):
    def test_normal_mapping_preserves_original_and_distinguishes_shaping_and_actual_line_inputs(self):
        raw, elements, providers, pairs = mapped_fixture()
        receipt = raw["path"]["native_path_evidence"]
        original = deepcopy((raw, elements, providers, pairs))
        contract, error = native_path_source_contract(receipt)
        self.assertIsNone(error)
        self.assertEqual(contract["paint_text"], " ab x 😀cd ")
        self.assertEqual(contract["source_text"], " \tab \t x\r\n😀cd ")
        self.assertFalse(receipt["actual_line_bindings"][0]["source_slice_matches"])
        self.assertEqual([(item["start_utf16"], item["end_utf16"]) for item in contract["omitted_paint_ranges"]],
                         [(0, 1), (5, 6), (10, 11)])
        bound, error = native_path_binding(raw["path"], raw)
        self.assertIsNone(error)
        self.assertEqual([line["id"] for line in bound], ["line-0", "line-1"])
        prior = {"id": "line-0", "property": "pixel.presentation", "reason": "Actual final PNG attribution is unmeasured"}
        result, used, _, issues = project_fixture(raw, elements, providers, pairs, [deepcopy(prior)])
        item = result[0]
        self.assertEqual(item["text"], contract["source_text"])
        self.assertEqual(item["name"], receipt["source_text"], "The actual UIA name is an independent quantity")
        self.assertEqual(item["layout"]["normal_break_strategy"], "word")
        self.assertEqual(item["layout"]["emergency_break_strategy"], "none")
        self.assertEqual(item["layout"]["line_count"], 2)
        self.assertEqual(item["evidence"]["native_path_projection"]["source_receipt"], receipt)
        self.assertEqual(item["evidence"]["native_path_projection"]["independent_line_elements"], elements)
        quantity = item["evidence"]["text_quantity"]
        self.assertEqual(quantity["source_text"], contract["source_text"])
        self.assertEqual(quantity["shaping_input"], contract["paint_text"])
        self.assertEqual([line["text"] for line in quantity["line_inputs"]], ["ab x", "😀cd"])
        self.assertNotEqual("".join(line["text"] for line in quantity["line_inputs"]), quantity["shaping_input"])
        self.assertIsNone(quantity["visible_text"])
        self.assertTrue(any(issue["property"] == "native_path.visible_text" for issue in issues))
        self.assertEqual(issues[0], {**prior, "projected_owner_id": "path"})
        self.assertTrue(any(issue["property"] == "native_path.font_weight.resolved" for issue in issues))
        self.assertEqual(used, {"uia-path"})
        self.assertEqual((raw, elements, providers, pairs), original)

    def test_failure_owner_reuses_actual_mapping_and_full_object_proof(self):
        raw, elements, providers, pairs = mapped_fixture()
        result, _, _, _ = project_fixture(raw, elements, providers, pairs)
        found = native_path_failure_owners(result)
        self.assertEqual(set(found), {"line-0", "line-1"})
        self.assertTrue(all(item["owner"] == "path" for item in found.values()))
        changed = deepcopy(result)
        changed[0]["text"] = raw["path"]["native_path_evidence"]["source_to_paint"]["paint_text"]
        self.assertEqual(native_path_failure_owners(changed), {}, "Source and paint are not interchangeable quantities")
        changed = deepcopy(result)
        changed[0]["evidence"]["native_path_projection"]["raw_lines"][0]["parent"] = "other"
        self.assertEqual(native_path_failure_owners(changed), {})

    def test_new_path_map_keeps_unchanged_source_and_emergency_policy(self):
        args = ("ab😀cd", "ab😀cd", tuple((i, i + 1) for i in range(6)), ((0, 2), (2, 6)))
        raw, elements, providers, pairs = mapped_fixture(*args, normal=False)
        result, _, _, _ = project_fixture(raw, elements, providers, pairs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "ab😀cd")
        self.assertEqual(result[0]["layout"]["emergency_break_strategy"], "break-unbreakable")

    def test_recorded_reference_soft_wrap_separator_is_not_the_concatenated_drawn_line_string(self):
        # Actual reference receipt: parity-7df43bd-full/reference-en-US-dark-1024x700/
        # en-US-dark-1024x700-group.dom.json, node216/backend225/layout182.
        # layout.text contains all 23 UTF-16 units; the two actual textBoxes
        # cover [0,16) and [17,23), excluding the soft-wrap separator at16.
        reference = {"source": "Native interface review", "transformed": "Native interface review",
                     "fragments": [{"start": 0, "length": 16}, {"start": 17, "length": 6}]}
        text = reference["source"]
        # Native receipts below remain explicitly synthetic. This checks the
        # quantities; it does not claim a Windows rendering of this reference.
        raw, elements, providers, pairs = mapped_fixture(text, text, tuple((i, i + 1) for i in range(23)),
                                                         ((0, 16), (17, 23)))
        result, _, _, issues = project_fixture(raw, elements, providers, pairs)
        self.assertEqual(result[0]["text"], reference["transformed"])
        quantity = result[0]["evidence"]["text_quantity"]
        fragments = [text[part["start"]:part["start"] + part["length"]] for part in reference["fragments"]]
        self.assertEqual([part["text"] for part in quantity["line_inputs"]], fragments)
        self.assertNotEqual("".join(fragments), result[0]["text"])
        self.assertIsNone(quantity["visible_text"])
        self.assertTrue(any(issue["property"] == "native_path.visible_text" for issue in issues))

    def test_old_unmapped_receipt_keeps_its_original_strict_contract(self):
        raw, elements, providers, pairs = synthetic()
        contract, error = native_path_source_contract(raw["path"]["native_path_evidence"])
        self.assertIsNone(error)
        self.assertFalse(contract["mapped"])
        self.assertEqual(contract["paint_text"], "ab😀cd")
        result, _, _, _ = project_fixture(raw, elements, providers, pairs)
        self.assertEqual(result[0]["layout"]["emergency_break_strategy"], "break-unbreakable")

    def test_partial_new_schema_cannot_fall_back_to_old_contract(self):
        for key, value in (("source_to_paint", {}), ("text_style", {}), ("arranged_lines", [])):
            with self.subTest(key=key):
                raw, _, _, _ = synthetic()
                raw["path"]["native_path_evidence"][key] = value
                self.assertIsNotNone(native_path_source_contract(raw["path"]["native_path_evidence"])[1])
        raw, _, _, _ = synthetic()
        raw["path"]["native_path_evidence"]["layout"]["lines"][0]["paint_start_utf16"] = 0
        self.assertIsNotNone(native_path_source_contract(raw["path"]["native_path_evidence"])[1])

    def test_source_map_missing_changed_duplicate_cross_owner_and_boolean_fields_fail(self):
        changes = ("missing", "source", "paint", "policy", "length", "duplicate", "missing-unit", "offset", "bool-offset",
                   "source-slice-flag", "paint-slice-flag", "same-map", "line-map", "line-style", "style-mode")
        for change in changes:
            with self.subTest(change=change):
                raw, elements, providers, pairs = mapped_fixture()
                receipt = raw["path"]["native_path_evidence"]
                mapping, binding = receipt["source_to_paint"], receipt["actual_line_bindings"][0]
                if change == "missing": receipt.pop("source_to_paint")
                elif change == "source": mapping["source_text"] = "other-owner"
                elif change == "paint": mapping["paint_text"] = "changed"
                elif change == "policy": mapping["normal_whitespace"] = False
                elif change == "length": receipt["source_utf16_length"] = len(receipt["source_text"])
                elif change == "duplicate": mapping["spans"].append(deepcopy(mapping["spans"][0]))
                elif change == "missing-unit": mapping["spans"].pop()
                elif change == "offset": mapping["spans"][3]["source_end_utf16"] -= 1
                elif change == "bool-offset": mapping["spans"][0]["paint_start_utf16"] = False
                elif change == "source-slice-flag": binding["source_slice_matches"] = True
                elif change == "paint-slice-flag": binding["paint_slice_matches"] = False
                elif change == "same-map": binding["same_production_source_to_paint_map"] = False
                elif change == "line-map": binding["source_to_paint"]["source_text"] = "other-owner"
                elif change == "line-style": binding["text_style"]["size"] = 13
                elif change == "style-mode": receipt["text_style"]["wrap_policy"] = "unknown"
                sync_line_receipts(raw)
                result, used, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertEqual([item["id"] for item in result], ["line-0", "line-1"])
                self.assertFalse(used)
                self.assertTrue(any(issue["property"] == "native_path.ownership" for issue in issues))

    def test_shaping_icu_and_measured_line_records_cannot_be_supplied_by_other_sources(self):
        changes = ("shape-source", "shape-identity", "shape-font", "shape-size", "shape-weight", "shape-clusters", "shape-gap",
                   "shape-width", "shape-surrogate", "paint-icu-source", "paint-icu-end", "source-icu", "arranged-x", "arranged-y",
                   "arranged-span", "local-size", "line-height", "line-text", "paint-overlap", "emergency")
        for change in changes:
            with self.subTest(change=change):
                raw, elements, providers, pairs = mapped_fixture()
                receipt = raw["path"]["native_path_evidence"]
                shape = receipt["layout"]["source_measurement"]
                if change == "shape-source": shape["source_text"] = receipt["source_text"]
                elif change == "shape-identity": shape["layout_com_identity_at_measurement"] = "0"
                elif change == "shape-font": shape["configured_family_list"] = "other actual font"
                elif change == "shape-size": shape["configured_size"] += 1
                elif change == "shape-weight": shape["configured_weight"] = 600
                elif change == "shape-clusters": shape["clusters"].pop()
                elif change == "shape-gap": shape["clusters"][1]["start_utf16"] += 1
                elif change == "shape-width": shape["clusters"][0]["width"] = float("nan")
                elif change == "shape-surrogate": shape["clusters"][6]["length_utf16"] = 1
                elif change == "paint-icu-source": receipt["layout"]["paint_icu"]["source_text"] = receipt["source_text"]
                elif change == "paint-icu-end": receipt["layout"]["paint_icu"]["iterators"][0]["boundaries_utf16"].pop()
                elif change == "source-icu": receipt["layout"]["icu"]["iterators"] = []
                elif change == "arranged-x": receipt["arranged_lines"][0]["actual_line_x"] += 1
                elif change == "arranged-y": receipt["arranged_lines"][0]["actual_line_y"] += 1
                elif change == "arranged-span": receipt["arranged_lines"][0]["paint_end_utf16"] += 1
                elif change == "local-size": raw["line-0"]["local_bounds"]["width"] += 1
                elif change == "line-height": receipt["layout"]["lines"][0]["line_height"] += 1
                elif change == "line-text": raw["line-0"]["text"] = "different"
                elif change == "paint-overlap": receipt["layout"]["lines"][1]["paint_start_utf16"] = 1
                elif change == "emergency": receipt["layout"]["lines"][0]["emergency"] = True
                result, used, _, issues = project_fixture(raw, elements, providers, pairs)
                self.assertEqual([item["id"] for item in result], ["line-0", "line-1"])
                self.assertFalse(used)
                self.assertTrue(any(issue["property"] == "native_path.ownership" for issue in issues))

    def test_line_gaps_cannot_hide_visible_source_characters(self):
        # 'x' is deliberately omitted between the two otherwise valid lines.
        args = ("abx😀cd", "abx😀cd", tuple((i, i + 1) for i in range(7)), ((0, 2), (3, 7)))
        raw, _, _, _ = mapped_fixture(*args)
        contract, error = native_path_source_contract(raw["path"]["native_path_evidence"])
        self.assertIsNone(contract)
        self.assertIn("omit paint units", error)

    def test_zwsp_segment_break_gap_is_validated_without_inventing_glyphs(self):
        source, paint = "a\u200b\r\n b", "a\u200bb"
        raw, _, _, _ = mapped_fixture(source, paint, ((0, 1), (1, 2), (5, 6)), ((0, 2), (2, 3)))
        contract, error = native_path_source_contract(raw["path"]["native_path_evidence"])
        self.assertIsNone(error)
        self.assertEqual(contract["removed_source_ranges"], [{"start_utf16": 2, "end_utf16": 5,
            "reason": "Recorded normal whitespace segment break adjacent to ZWSP"}])
        self.assertEqual(contract["paint_text"], paint)
        changed = deepcopy(raw["path"]["native_path_evidence"])
        changed["source_text"] = changed["source_text"].replace("\u200b", "z")
        changed["source_to_paint"]["source_text"] = changed["source_text"]
        self.assertIsNotNone(native_path_source_contract(changed)[1])

    def test_ff_nbsp_and_supplementary_characters_are_not_normalized(self):
        source = "A\fB\u00a0😀"
        raw, _, _, _ = mapped_fixture(source, source, tuple((i, i + 1) for i in range(6)), ((0, 3), (3, 6)))
        contract, error = native_path_source_contract(raw["path"]["native_path_evidence"])
        self.assertIsNone(error)
        self.assertEqual(contract["paint_text"], source)
        changed = deepcopy(raw["path"]["native_path_evidence"])
        changed["source_to_paint"]["paint_text"] = source.replace("\f", " ")
        self.assertIsNotNone(native_path_source_contract(changed)[1])

    def test_held_identity_and_parent_edges_remain_required_for_mapped_text(self):
        for key in ("same_retained_label_reference", "same_current_body_parent", "same_content_body", "label_is_loaded",
                    "line_in_actual_visual_walk", "reaches_same_owner_object", "all_captured_edges_match"):
            with self.subTest(key=key):
                raw, _, _, _ = mapped_fixture()
                raw["path"]["native_path_evidence"]["actual_line_bindings"][0][key] = False
                sync_line_receipts(raw)
                self.assertIsNotNone(native_path_binding(raw["path"], raw)[1])

    def test_final_pixel_and_outline_unknowns_are_not_resolved_by_source_mapping(self):
        raw, elements, providers, pairs = mapped_fixture()
        elements[1]["style"]["outline"] = None
        elements[1]["evidence"]["native_label_geometry"]["font_metric_advance"] = []
        previous = {"id": "line-1", "property": "presentation", "reason": "Actual final pixels are unknown"}
        result, _, _, issues = project_fixture(raw, elements, providers, pairs, [deepcopy(previous)])
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0]["bounds"])
        self.assertIsNone(result[0]["style"]["outline"])
        self.assertEqual(issues[0], {**previous, "projected_owner_id": "path"})
        self.assertTrue(any(item["property"] == "native_path.text_bounds" for item in issues))


if __name__ == "__main__":
    unittest.main()
