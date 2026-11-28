using System.Text.Json.Nodes;

namespace Relic;

// Receipt policy only. Tests supply mock observations; the WinUI observer supplies
// values read from the actual retained Run, Binding and unmounted target objects.
internal sealed class RunTextBindingJournal
{
    private readonly Action changed;
    private readonly Action<string> error;
    private readonly JsonArray callbacks = [], failures = [];
    private readonly HashSet<string> reportedFailures = [];
    private bool installationFinished, installationValid, cleaningUp;
    private long callbackCount;
    internal JsonObject Receipt { get; }

    internal RunTextBindingJournal(int objectId, long startedQpc, Action changed, Action<string> error)
    {
        this.changed = changed; this.error = error;
        Receipt = new JsonObject
        {
            ["source"] = "OneWay Binding from the retained production Run to an observer-owned unmounted TextBlock",
            ["source_object_id"] = objectId, ["started_qpc"] = startedQpc,
            ["callbacks"] = callbacks, ["errors"] = failures,
            ["production_source_assigned_by_observer"] = false,
            ["canonical_geometry_supplied"] = false, ["frame_continuity_supplied"] = false,
            ["scope"] = "Run.Text notification channel only; no InlineCollection, glyph, paint or presentation proof"
        };
    }

    internal void Callback(JsonObject? state, bool sameTarget, bool sameProperty, long qpc)
    {
        callbackCount++;
        var phase = cleaningUp ? "cleanup" : installationFinished ? "observing" : "installation";
        // Every post-installation notification advances the real source object's
        // revision, even if the value was restored or this receipt is invalid.
        if (installationFinished && !cleaningUp) changed();
        if (callbacks.Count < 4096)
            callbacks.Add(new JsonObject
            {
                ["index"] = callbackCount - 1, ["phase"] = phase, ["qpc"] = qpc,
                ["sender_same_target"] = sameTarget, ["property_same_text_property"] = sameProperty,
                ["state"] = state?.DeepClone()
            });
        else Fail("Run.Text callback journal overflow", phase, qpc);
        Receipt["callback_count"] = callbackCount;
        if (!sameTarget || !sameProperty) Fail("Callback sender or property identity differs", phase, qpc);
        if (cleaningUp) Fail("Callback occurred during observer cleanup", phase, qpc);
        else Validate(state, phase, qpc, requireExpression: installationFinished);
    }

    internal void Installed(JsonObject state, long qpc)
    {
        Validate(state, "installation_complete", qpc, requireExpression: true);
        installationFinished = true; installationValid = failures.Count == 0;
        Receipt["installed_qpc"] = qpc;
        Receipt["initialization_callback_count"] = callbackCount;
        Receipt["installation_state"] = state.DeepClone();
        Receipt["installation_valid"] = installationValid;
    }

    internal bool Check(JsonObject state, long qpc)
    {
        Validate(state, "checkpoint", qpc, requireExpression: true);
        return installationFinished && installationValid && !cleaningUp && failures.Count == 0;
    }

    internal void BeginCleanup(JsonObject? state, long qpc)
    {
        if (installationFinished) Validate(state, "before_cleanup", qpc, requireExpression: true);
        cleaningUp = true;
        Receipt["cleanup_started_qpc"] = qpc;
        Receipt["cleanup_before"] = state?.DeepClone();
    }

    internal void Fail(string reason, string stage, long qpc)
    {
        if (!reportedFailures.Add(reason)) return;
        failures.Add(new JsonObject { ["stage"] = stage, ["qpc"] = qpc, ["reason"] = reason });
        error(reason);
    }

    private void Validate(JsonObject? state, string stage, long qpc, bool requireExpression)
    {
        if (state == null) { Fail("No binding state was measured", stage, qpc); return; }
        foreach (var field in new[] { "source_has_ui_thread_access", "target_has_ui_thread_access",
            "target_xaml_root_is_null", "target_visual_parent_is_null", "binding_source_same_run",
            "binding_mode_one_way", "binding_path_text", "callback_registered", "source_target_utf16_equal" })
            if (!Flag(state, field, true)) Fail("Binding state did not measure " + field + "=true", stage, qpc);
        if (!Flag(state, "target_is_loaded", false)) Fail("Binding target was mounted or loading state was unknown", stage, qpc);
        if (requireExpression)
            foreach (var field in new[] { "binding_expression_present", "expression_data_item_same_run", "expression_parent_binding_same_object" })
                if (!Flag(state, field, true)) Fail("Binding state did not measure " + field + "=true", stage, qpc);
        var source = state["source_text"] as JsonObject; var target = state["target_text"] as JsonObject;
        if (source == null || target == null || !ValidText(source) || !ValidText(target)
            || source["utf16_length"]!.GetValue<int>() != target["utf16_length"]!.GetValue<int>()
            || source["utf16_le_base64"]!.GetValue<string>() != target["utf16_le_base64"]!.GetValue<string>())
            Fail("Source and target raw UTF-16 were missing, invalid or different", stage, qpc);
        if (state["error"] != null) Fail("Reading actual binding state failed: " + state["error"], stage, qpc);
    }

    private static bool Flag(JsonObject state, string name, bool expected) =>
        state[name] is JsonValue value && value.TryGetValue<bool>(out var actual) && actual == expected;

    private static bool ValidText(JsonObject? text)
    {
        if (text == null || text["utf16_length"] is not JsonValue lengthValue || !lengthValue.TryGetValue<int>(out var length) || length < 0
            || text["utf16_le_base64"] is not JsonValue bytesValue || !bytesValue.TryGetValue<string>(out var encoded) || encoded == null) return false;
        try { return Convert.FromBase64String(encoded).LongLength == (long)length * 2; }
        catch (FormatException) { return false; }
    }

    internal static JsonObject Text(string value)
    {
        // Encoding.Unicode replaces unpaired surrogates. Preserve actual .NET
        // UTF-16 code units, including unpaired ones, independently of JSON text.
        var bytes = new byte[value.Length * 2];
        for (var i = 0; i < value.Length; i++) { bytes[2 * i] = (byte)value[i]; bytes[2 * i + 1] = (byte)(value[i] >> 8); }
        return new JsonObject { ["value"] = value, ["utf16_length"] = value.Length, ["utf16_le_base64"] = Convert.ToBase64String(bytes) };
    }
}
