import copy
import unittest

from windows_automation_identity import NATIVE_SOURCE, OWNER_SOURCE, TRANSPORT_SOURCE, bind_automation_identities, measured_id


def array(values, lower=0):
    return {"status": "measured", "dimensions": 1, "vartype": 3, "element_size": 4,
            "dimension_bounds": [{"dimension": 1, "lower": lower, "upper": lower + len(values) - 1}],
            "element_count": len(values), "values": values}


def actual_pair():
    return [{"id": "xaml-17", "automation_identity_evidence": {
        "source": OWNER_SOURCE, "status": "measured", "owner_id": "xaml-17", "peer_owner_id": "xaml-17",
        "same_owner_object": True, "peer_same_object_after": True, "metadata_modified": False,
        "peer_is_null": False, "process_id": 1234, "events_source_is_null": True,
        "events_source_same_peer": False, "events_source_type": None,
        "events_source_same_object_after": True,
        "apartment_transport": {"source": TRANSPORT_SOURCE, "status": "measured", "failures": [],
            "returned_to_origin_thread": True, "worker_read_completed": True,
            "stream_consumed_by_unmarshal": True, "stream_consumption_unknown": False},
        "native": {"source": NATIVE_SOURCE, "status": "measured", "failures": [], "core_runtime_id_stable": True,
                   "fragment_runtime_id": array([3, 7]), "core_runtime_id": array([42, 91, 4, 7]),
                   "core_runtime_id_recheck": array([42, 91, 4, 7])}}}], {
        "pid": 1234, "raw_nodes": [{"id": "uia-92", "runtime_id": "42.91.4.7", "name": "Different actual name"}]}


class AutomationIdentityTests(unittest.TestCase):
    def test_complete_identity_is_joined_without_name_or_box(self):
        raw, uia = actual_pair()
        receipt = bind_automation_identities(raw, uia)
        self.assertEqual(receipt["pairs"][0]["uia_id"], "uia-92")
        self.assertEqual(receipt["unresolved"], [])

    def test_partial_id_suffix_never_joins(self):
        raw, uia = actual_pair()
        uia["raw_nodes"][0]["runtime_id"] = "42.999.4.7"
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_other_process_changed_peer_redirect_and_modified_metadata_are_unknown(self):
        for key, value in (("process_id", 999), ("same_owner_object", False), ("peer_same_object_after", False),
                           ("owner_id", "different"), ("peer_owner_id", "different"), ("peer_is_null", True),
                           ("metadata_modified", True), ("events_source_is_null", False), ("status", "unknown")):
            with self.subTest(key=key):
                raw, uia = actual_pair()
                raw[0]["automation_identity_evidence"][key] = value
                self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_native_failure_and_unstable_id_remain_unknown(self):
        for key, value in (("failures", ["actual failed API"]), ("status", "unknown"),
                           ("core_runtime_id_stable", False), ("core_runtime_id_recheck", array([42, 91, 4, 9]))):
            raw, uia = actual_pair()
            raw[0]["automation_identity_evidence"]["native"][key] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_missing_or_conflicting_events_source_fields_are_not_proof(self):
        for key in ("events_source_type", "events_source_same_peer", "events_source_is_null"):
            raw, uia = actual_pair()
            del raw[0]["automation_identity_evidence"][key]
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        evidence = raw[0]["automation_identity_evidence"]
        evidence["events_source_same_peer"] = True
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        evidence.update(events_source_is_null=False, events_source_type="ActualPeer")
        self.assertEqual(len(bind_automation_identities(raw, uia)["pairs"]), 1)

    def test_unfinished_apartment_transfer_cannot_prove_binding(self):
        for key, value in (("status", "unknown"), ("failures", ["release failed"]),
                           ("returned_to_origin_thread", False), ("worker_read_completed", False),
                           ("stream_consumed_by_unmarshal", False), ("stream_consumption_unknown", True)):
            raw, uia = actual_pair()
            raw[0]["automation_identity_evidence"]["apartment_transport"][key] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_duplicate_owner_or_provider_is_not_arbitrarily_selected(self):
        for side in ("owner", "provider"):
            raw, uia = actual_pair()
            if side == "owner":
                other = copy.deepcopy(raw[0]); other["id"] = "xaml-18"
                other["automation_identity_evidence"].update(owner_id="xaml-18", peer_owner_id="xaml-18")
                raw.append(other)
            else:
                uia["raw_nodes"].append(dict(uia["raw_nodes"][0], id="uia-93"))
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_array_shape_count_types_and_signed_values_are_measured_exactly(self):
        self.assertEqual(measured_id(array([42, -9, 0], lower=-2)), (42, -9, 0))
        for key, value in (("dimensions", True), ("vartype", 8), ("element_size", 8), ("element_count", 9),
                           ("values", [42, True]), ("values", [2 ** 31]), ("values", []), ("dimension_bounds", [])):
            item = array([42, 7]); item[key] = value
            self.assertIsNone(measured_id(item))


if __name__ == "__main__":
    unittest.main()
