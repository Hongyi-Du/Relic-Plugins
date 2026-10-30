"""Pure CDP receipts for real-node font collection; no browser/process starts."""
import copy
import unittest
from unittest.mock import Mock

import capture


class TextNodeFontCaptureTests(unittest.TestCase):
    def snapshot(self):
        # Topology recorded in 6db group: P owns two direct text siblings and
        # a B element whose own Text is a distinct shaping/attribution source.
        return {"strings": ["", "收到。我会按 ", "聊天、概况、工作区、设置", " 的顺序整理验收记录。"],
                "documents": [{"nodes": {"nodeType": [1, 3, 1, 3, 3],
                    "backendNodeId": [360, 361, 362, 363, 364],
                    "parentIndex": [-1, 0, 0, 2, 0], "nodeValue": [0, 1, 0, 2, 3]},
                    "layout": {"nodeIndex": [1, 3, 4], "text": [1, 2, 3]}}]}

    def font(self, face, count):
        return {"familyName": "fixture family", "postScriptName": face,
                "isCustomFont": False, "glyphCount": count}

    def cdp(self, replies, node_ids=None):
        client = Mock()
        mapping = {}

        def send(method, parameters):
            if method == "CSS.enable":
                self.assertEqual(parameters, {})
                return {}
            if method == "DOM.pushNodesByBackendIdsToFrontend":
                ids = node_ids if node_ids is not None else [backend + 1000 for backend in parameters["backendNodeIds"]]
                mapping.update(zip(ids, parameters["backendNodeIds"]))
                return {"nodeIds": ids}
            self.assertEqual(method, "CSS.getPlatformFontsForNode", "Collection is read-only and never clones or modifies DOM")
            response = replies.get(mapping[parameters["nodeId"]], {"fonts": [self.font("raw-parent-aggregate", 99)]})
            if isinstance(response, Exception):
                raise response
            return copy.deepcopy(response)

        client.send.side_effect = send
        return client

    def test_actual_text_siblings_are_queried_separately_from_parent_and_nested_bold(self):
        replies = {361: {"fonts": [self.font("regular-first", 8)]},
                   363: {"fonts": [self.font("bold-child", 12)]},
                   364: {"fonts": [self.font("regular-last", 10)]}}
        cdp = self.cdp(replies)
        result = capture.font_evidence(cdp, self.snapshot(), {"inputs": {}})
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["setup"][1]["parameters"], {"backendNodeIds": [360, 361, 362, 363, 364]})
        for backend in (361, 363, 364):
            query = result["queries"][str(backend)]
            self.assertEqual(query["node_type"], 3)
            self.assertEqual(query["scope"], "text-node-layout")
            self.assertTrue(query["request_sent"])
            self.assertEqual(query["request"], {"method": "CSS.getPlatformFontsForNode", "parameters": {"nodeId": backend + 1000}})
            self.assertEqual(query["result"], replies[backend])
            self.assertEqual(result["by_backend_node"][str(backend)], replies[backend]["fonts"])
        self.assertEqual(result["queries"]["360"]["scope"], "descendant-layout-aggregate")
        self.assertEqual(result["by_backend_node"]["360"][0]["glyphCount"], 99, "Raw parent data is retained unchanged, never subtracted")

    def test_one_failed_text_node_does_not_fall_back_to_successful_parent(self):
        cdp = self.cdp({361: RuntimeError("actual text-node query failed")})
        result = capture.font_evidence(cdp, self.snapshot(), {"inputs": {}})
        self.assertIn("360", result["by_backend_node"])
        self.assertNotIn("361", result["by_backend_node"])
        self.assertEqual(result["queries"]["361"]["error"], "actual text-node query failed")
        self.assertIsNone(result["queries"]["361"]["result"])
        self.assertEqual(result["errors"][0]["backend_node_id"], 361)
        self.assertIn("364", result["by_backend_node"], "One failure must not discard other actual queries")

    def test_empty_actual_reply_is_retained_but_remains_unknown(self):
        result = capture.font_evidence(self.cdp({361: {"fonts": []}}), self.snapshot(), {"inputs": {}})
        self.assertEqual(result["queries"]["361"]["result"], {"fonts": []})
        self.assertNotIn("361", result["by_backend_node"])
        self.assertIn("no platform font usage", result["queries"]["361"]["error"])

    def test_short_frontend_mapping_retains_a_failure_for_every_unmapped_node(self):
        result = capture.font_evidence(self.cdp({}, node_ids=[1360]), self.snapshot(), {"inputs": {}})
        self.assertEqual(len(result["queries"]), 5)
        self.assertEqual(len(result["errors"]), 4)
        self.assertIsNone(result["queries"]["364"]["frontend_node_id"])
        self.assertIsNone(result["queries"]["364"]["result"])
        self.assertFalse(result["queries"]["364"]["request_sent"])

    def test_setup_failure_is_not_lost_or_converted_into_success(self):
        cdp = Mock()
        cdp.send.side_effect = [RuntimeError("CSS domain unavailable"), {"nodeIds": [1360, 1361, 1362, 1363, 1364]}]
        result = capture.font_evidence(cdp, self.snapshot(), {"inputs": {}})
        self.assertEqual(cdp.send.call_count, 2)
        self.assertEqual(result["by_backend_node"], {})
        self.assertEqual(result["setup"][0]["error"], "CSS domain unavailable")
        self.assertEqual(len(result["queries"]), 5)
        self.assertTrue(all(query["error"] for query in result["queries"].values()))
        self.assertTrue(all(query["request_sent"] is False for query in result["queries"].values()))

    def test_ua_input_queries_actual_pierced_text_node_not_only_its_parent(self):
        input_text = {"inputs": {"500": {"text_nodes": [{"backend_node_id": 502,
            "font_owner_backend_node_id": 501, "text": "actual value", "boxes": [{"width": 20}]}]}},
            "raw_document": {"root": {"backendNodeId": 500, "nodeType": 1,
                "shadowRoots": [{"nodeType": 11, "children": [{"backendNodeId": 501, "nodeType": 1,
                    "children": [{"backendNodeId": 502, "nodeType": 3, "nodeValue": "actual value"}]}]}]}}}
        result = capture.font_evidence(self.cdp({502: {"fonts": [self.font("actual-input-face", 12)]}}), self.snapshot(), input_text)
        self.assertEqual(result["queries"]["502"]["node_type"], 3)
        self.assertEqual(result["queries"]["502"]["scope"], "text-node-layout")
        self.assertEqual(result["queries"]["502"]["identities"][0]["node_value"], "actual value")
        self.assertEqual(result["queries"]["501"]["scope"], "descendant-layout-aggregate")


if __name__ == "__main__":
    unittest.main()
