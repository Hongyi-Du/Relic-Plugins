import copy
import unittest

from windows_automation_identity import (COLLECTION_PHASE, NATIVE_SOURCE, OWNER_SOURCE, TRANSPORT_SOURCE,
                                         bind_automation_identities, measured_id)


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
        "collection_phase": COLLECTION_PHASE,
        "observer": {"case_id": "synthetic-case", "app_pid": 1234, "observer_pid": 5678},
        "apartment_transport": {"source": TRANSPORT_SOURCE, "status": "measured", "failures": [],
            "returned_to_origin_thread": True, "worker_read_completed": True,
            "stream_consumed_by_unmarshal": True, "stream_consumption_unknown": False},
        "native": {"source": NATIVE_SOURCE, "status": "measured", "failures": [], "core_runtime_id_stable": True,
                   "fragment_runtime_id": array([3, 7]), "core_runtime_id": array([42, 91, 4, 7]),
                   "core_runtime_id_recheck": array([42, 91, 4, 7])}}}], {
        "case_id": "synthetic-case", "pid": 1234,
        "observer_hold": {"schema_version": 1, "status": "released", "case_id": "synthetic-case",
            "app_pid": 1234, "observer_pid": 5678, "capture_exit_code": 0, "exit_code": 0,
            "errors": [], "release": {"action": "release", "status": "observed",
                "case_id": "synthetic-case", "observer_pid": 5678},
            "retained_owners": {"capture_instance_retained": True, "retention_requested": True,
                "primary_root_retained": True, "native_text_evidence_retained": True,
                "retained_element_reference_count": 2}},
        "raw_nodes": [{"id": "uia-92", "runtime_id": "42.91.4.7", "name": "Different actual name"}]}


class AutomationIdentityTests(unittest.TestCase):
    def test_complete_identity_is_joined_without_name_or_box(self):
        raw, uia = actual_pair()
        receipt = bind_automation_identities(raw, uia)
        self.assertEqual(receipt["pairs"][0]["uia_id"], "uia-92")
        self.assertEqual(receipt["pairs"][0]["collection_phase"], COLLECTION_PHASE)
        self.assertEqual(receipt["pairs"][0]["observer"], raw[0]["automation_identity_evidence"]["observer"])
        self.assertEqual(receipt["unresolved"], [])

    def test_missing_or_wrong_collection_phase_never_uses_matching_id(self):
        for value in (None, "", "before-independent-uia", "after-independent-uia", True):
            with self.subTest(value=value):
                raw, uia = actual_pair()
                raw[0]["automation_identity_evidence"]["collection_phase"] = value
                receipt = bind_automation_identities(raw, uia)
                self.assertEqual(receipt["pairs"], [])
                self.assertIn("collected while", receipt["unresolved"][0]["reason"])
        raw, uia = actual_pair()
        del raw[0]["automation_identity_evidence"]["collection_phase"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_missing_hold_or_owner_observer_is_not_retention_proof(self):
        for target, key in (("owner", "observer"), ("uia", "observer_hold")):
            for value in (None, [], "held"):
                with self.subTest(target=target, value=value):
                    raw, uia = actual_pair()
                    container = raw[0]["automation_identity_evidence"] if target == "owner" else uia
                    container[key] = value
                    self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
            raw, uia = actual_pair()
            container = raw[0]["automation_identity_evidence"] if target == "owner" else uia
            del container[key]
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_foreign_case_app_and_observer_processes_never_join(self):
        for target in ("owner_observer", "hold"):
            for key, values in (("case_id", ("foreign-case", None, True)),
                                ("app_pid", (9999, None, True, "1234")),
                                ("observer_pid", (9999, None, True, 0, -1, "5678"))):
                for value in values:
                    with self.subTest(target=target, key=key, value=value):
                        raw, uia = actual_pair()
                        observed = (raw[0]["automation_identity_evidence"]["observer"]
                                    if target == "owner_observer" else uia["observer_hold"])
                        observed[key] = value
                        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
                raw, uia = actual_pair()
                observed = (raw[0]["automation_identity_evidence"]["observer"]
                            if target == "owner_observer" else uia["observer_hold"])
                del observed[key]
                self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        for key, value in (("case_id", "foreign-case"), ("case_id", None), ("case_id", ""),
                           ("pid", 9999), ("pid", True), ("pid", 0)):
            raw, uia = actual_pair()
            uia[key] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_incomplete_or_unreleased_hold_never_joins(self):
        for status in ("ready", "waiting", "timed-out", "failed", None):
            raw, uia = actual_pair()
            uia["observer_hold"]["status"] = status
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        del uia["observer_hold"]["status"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        for value in (None, [], {}):
            raw, uia = actual_pair()
            uia["observer_hold"]["retained_owners"] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        del uia["observer_hold"]["retained_owners"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_each_actual_retention_flag_and_positive_reference_count_is_required(self):
        flags = ("capture_instance_retained", "retention_requested", "primary_root_retained",
                 "native_text_evidence_retained")
        for key in flags:
            for value in (False, None, 1, "true"):
                with self.subTest(key=key, value=value):
                    raw, uia = actual_pair()
                    uia["observer_hold"]["retained_owners"][key] = value
                    self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
            raw, uia = actual_pair()
            del uia["observer_hold"]["retained_owners"][key]
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        for value in (0, -1, True, None, 1.0, "2"):
            raw, uia = actual_pair()
            uia["observer_hold"]["retained_owners"]["retained_element_reference_count"] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        del uia["observer_hold"]["retained_owners"]["retained_element_reference_count"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_released_status_does_not_accept_failed_cleanup_or_foreign_release(self):
        for key, values in (("action", ("cancel", None, True)),
                            ("status", ("failed", "cleanup", None, True)),
                            ("case_id", ("foreign-case", None, True)),
                            ("observer_pid", (9999, None, True, "5678"))):
            for value in values:
                with self.subTest(key=key, value=value):
                    raw, uia = actual_pair()
                    # The observer process acknowledged release, but this does
                    # not prove that the native observation finished normally.
                    uia["observer_hold"]["release"][key] = value
                    receipt = bind_automation_identities(raw, uia)
                    self.assertEqual(receipt["pairs"], [])
                    self.assertIn("release", receipt["unresolved"][0]["reason"])
            raw, uia = actual_pair()
            del uia["observer_hold"]["release"][key]
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        for value in (None, [], "observed"):
            raw, uia = actual_pair()
            uia["observer_hold"]["release"] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        del uia["observer_hold"]["release"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_hold_errors_are_independent_of_capture_exit_code(self):
        for value in (["actual hold acknowledgement error"], None, {}, False):
            raw, uia = actual_pair()
            uia["observer_hold"]["errors"] = value
            self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])
        raw, uia = actual_pair()
        del uia["observer_hold"]["errors"]
        self.assertEqual(bind_automation_identities(raw, uia)["pairs"], [])

    def test_capture_exit_one_keeps_identity_diagnostic_without_erasing_original_errors(self):
        raw, uia = actual_pair()
        uia["observer_hold"].update(capture_exit_code=1, exit_code=1)
        uia["extraction_errors"] = [
            "uia-92: COM text rectangle 0 is zero-area; original values retained."]
        uia["raw_extraction_errors"] = ["uia-92: original provider measurement failed"]
        uia["raw_nodes"][0]["measurement_errors"] = ["unmeasured original provider attribute"]
        uia["nonfinite_measurements"] = [{"owner": "uia-92", "value": "original raw sentinel"}]
        before_raw, before_uia = copy.deepcopy(raw), copy.deepcopy(uia)
        receipt = bind_automation_identities(raw, uia)
        self.assertEqual(len(receipt["pairs"]), 1)
        self.assertEqual(receipt["unresolved"], [])
        self.assertIn("provider failures remain independent", receipt["does_not_resolve"])
        self.assertEqual(uia, before_uia)
        self.assertEqual(raw, before_raw)

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
