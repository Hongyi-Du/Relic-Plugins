using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;

namespace Relic;

// Independent CI feasibility experiment. Neither object is inserted in the
// application's scene. Results never supply frame continuity or canonical data.
internal static class RunTextBindingProbe
{
    internal static void Capture(string directory, IReadOnlyList<string> caseIds)
    {
        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true"
            || string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))) return;
        var path = Path.Combine(directory, "run-text-binding-probe.json");
        var callbacks = new JsonArray(); var steps = new JsonArray(); var errors = new JsonArray();
        var receipt = new JsonObject
        {
            ["source"] = "Actual SDK OneWay Binding from a newly allocated Run to an unmounted TextBlock",
            ["app_pid"] = Environment.ProcessId, ["started_qpc"] = Stopwatch.GetTimestamp(),
            ["qpc_frequency"] = Stopwatch.Frequency, ["managed_thread_id"] = Environment.CurrentManagedThreadId,
            ["case_ids"] = new JsonArray(caseIds.Select(id => (JsonNode?)JsonValue.Create(id)).ToArray()),
            ["scope"] = "Independent probe-owned objects; no production scene Run is read or modified",
            ["canonical_geometry_supplied"] = false, ["frame_continuity_supplied"] = false,
            ["resolver_success_supplied"] = false, ["completed"] = false, ["status"] = "pending",
            ["callbacks"] = callbacks, ["steps"] = steps, ["errors"] = errors
        };
        Run? source = null; TextBlock? target = null; Binding? binding = null;
        long? token = null; string phase = "allocate";

        void Save()
        {
            // Each completed operation remains inspectable if a later native
            // operation fails. A failed write is logged, never promoted to data.
            try
            {
                File.WriteAllText(path + ".tmp", receipt.ToJsonString(), new UTF8Encoding(false));
                File.Move(path + ".tmp", path, true);
            }
            catch (Exception error)
            {
                errors.Add(new JsonObject { ["phase"] = "write_diagnostic", ["qpc"] = Stopwatch.GetTimestamp(),
                    ["path"] = path, ["error"] = error.ToString(), ["hresult"] = error.HResult });
                Console.Error.WriteLine("RunTextBindingProbe write: " + error);
            }
        }
        void Error(Exception error)
        {
            errors.Add(new JsonObject { ["phase"] = phase, ["qpc"] = Stopwatch.GetTimestamp(),
                ["exception_type"] = error.GetType().FullName, ["hresult"] = error.HResult,
                ["hresult_hex"] = "0x" + unchecked((uint)error.HResult).ToString("X8"), ["error"] = error.ToString() });
        }
        JsonObject State()
        {
            var expression = target!.GetBindingExpression(TextBlock.TextProperty);
            return new JsonObject
            {
                ["qpc"] = Stopwatch.GetTimestamp(), ["source_text"] = Text(source!.Text), ["target_text"] = Text(target.Text),
                ["source_has_ui_thread_access"] = source.DispatcherQueue.HasThreadAccess,
                ["target_has_ui_thread_access"] = target.DispatcherQueue.HasThreadAccess,
                ["target_is_loaded"] = target.IsLoaded, ["target_xaml_root_is_null"] = target.XamlRoot == null,
                ["target_visual_parent_is_null"] = VisualTreeHelper.GetParent(target) == null,
                ["binding_source_same_run"] = binding != null && ReferenceEquals(binding.Source, source),
                ["binding_expression_present"] = expression != null,
                ["expression_data_item_same_run"] = expression == null ? null : ReferenceEquals(expression.DataItem, source),
                ["expression_parent_binding_same_object"] = expression == null ? null : ReferenceEquals(expression.ParentBinding, binding),
                ["callback_count"] = callbacks.Count
            };
        }
        void Step(string name, Action action, string? requestedText = null)
        {
            phase = name;
            var step = new JsonObject { ["name"] = name, ["started_qpc"] = Stopwatch.GetTimestamp(),
                ["managed_thread_id"] = Environment.CurrentManagedThreadId, ["before"] = State(),
                ["status"] = "pending", ["requested_source_text"] = requestedText == null ? null : Text(requestedText) };
            steps.Add(step); Save();
            try { action(); step["after"] = State(); step["status"] = "returned"; }
            catch (Exception error) { Error(error); step["status"] = "failed"; }
            finally { step["completed_qpc"] = Stopwatch.GetTimestamp(); Save(); }
        }
        Save();
        try
        {
            source = new Run { Text = "initial 中" };
            target = new TextBlock();
            if (!source.DispatcherQueue.HasThreadAccess || !target.DispatcherQueue.HasThreadAccess)
                throw new InvalidOperationException("Run binding probe must execute on its objects' UI thread.");
            binding = new Binding { Source = source, Path = new PropertyPath("Text"), Mode = BindingMode.OneWay };
            receipt["binding_mode"] = binding.Mode.ToString(); receipt["binding_path"] = binding.Path.Path;
            receipt["objects_created_by_probe"] = true;
            token = target.RegisterPropertyChangedCallback(TextBlock.TextProperty, (sender, property) =>
            {
                try
                {
                    callbacks.Add(new JsonObject { ["index"] = callbacks.Count, ["phase"] = phase,
                        ["qpc"] = Stopwatch.GetTimestamp(), ["managed_thread_id"] = Environment.CurrentManagedThreadId,
                        ["sender_same_target"] = ReferenceEquals(sender, target),
                        ["property_same_text_property"] = ReferenceEquals(property, TextBlock.TextProperty),
                        ["source_text"] = Text(source.Text), ["target_text"] = Text(target.Text),
                        ["binding_source_same_run"] = ReferenceEquals(binding.Source, source) });
                }
                catch (Exception error) { Error(error); }
            });
            receipt["callback_token"] = token.Value;
            Step("initialize_binding", () => target.SetBinding(TextBlock.TextProperty, binding));
            Step("ordinary_change", () => source.Text = "ordinary 改变", "ordinary 改变");

            // No await, dispatch enqueue, or event pumping between these writes.
            // The callback journal must reveal an intermediate value itself;
            // the final restored value is not evidence that both were observed.
            var restore = source.Text;
            receipt["same_dispatch_pair_started_qpc"] = Stopwatch.GetTimestamp();
            Step("same_dispatch_change", () => source.Text = "temporary 瞬时", "temporary 瞬时");
            Step("same_dispatch_restore", () => source.Text = restore, restore);
            receipt["same_dispatch_pair_completed_qpc"] = Stopwatch.GetTimestamp();
            Step("empty_text", () => source.Text = "", "");
            const string surrogate = "甲\U0001F600\U00010437乙";
            Step("surrogate_pairs", () => source.Text = surrogate, surrogate);
            Step("unregister_callback", () =>
            {
                target.UnregisterPropertyChangedCallback(TextBlock.TextProperty, token!.Value);
                token = null;
            });
            var detachedCount = callbacks.Count;
            Step("change_after_callback_unregistered", () => source.Text = "after unregister", "after unregister");
            receipt["callbacks_after_unregister"] = callbacks.Count - detachedCount;
            Step("clear_binding", () => target.ClearValue(TextBlock.TextProperty));
            Step("change_after_binding_cleared", () => source.Text = "after binding cleared", "after binding cleared");

            var observations = new JsonArray();
            var boundStates = true;
            foreach (var step in steps.OfType<JsonObject>().Where(value => new[] { "initialize_binding", "ordinary_change",
                "same_dispatch_change", "same_dispatch_restore", "empty_text", "surrogate_pairs" }.Contains(value["name"]!.ToString())))
            {
                var name = step["name"]!.ToString();
                var afterText = step["after"]?["source_text"]?["utf16_le_base64"]?.ToString();
                var state = step["after"];
                var bound = step["status"]?.ToString() == "returned"
                    && state?["binding_source_same_run"]?.GetValue<bool>() == true
                    && state?["expression_data_item_same_run"]?.GetValue<bool>() == true
                    && state?["expression_parent_binding_same_object"]?.GetValue<bool>() == true
                    && state?["target_is_loaded"]?.GetValue<bool>() == false
                    && state?["target_xaml_root_is_null"]?.GetValue<bool>() == true
                    && state?["target_visual_parent_is_null"]?.GetValue<bool>() == true;
                boundStates &= bound;
                var matching = callbacks.OfType<JsonObject>().Count(value => value["phase"]?.ToString() == name
                    && afterText != null && value["source_text"]?["utf16_le_base64"]?.ToString() == afterText
                    && value["target_text"]?["utf16_le_base64"]?.ToString() == afterText
                    && value["sender_same_target"]?.GetValue<bool>() == true
                    && value["binding_source_same_run"]?.GetValue<bool>() == true);
                observations.Add(new JsonObject { ["step"] = name, ["actual_matching_callbacks"] = matching,
                    ["actual_source_identity_and_unmounted_target_observed"] = bound });
            }
            receipt["step_callback_observations"] = observations;
            var allObserved = observations.Count == 6 && observations.OfType<JsonObject>()
                .All(value => value["actual_matching_callbacks"]!.GetValue<int>() > 0);
            receipt["all_requested_changes_observed"] = allObserved;
            receipt["status"] = errors.Count == 0 && allObserved && boundStates && callbacks.Count == detachedCount
                ? "candidate-observed" : "candidate-not-demonstrated";
            receipt["completed"] = true;
        }
        catch (Exception error) { Error(error); receipt["status"] = "failed"; }
        finally
        {
            phase = "cleanup";
            try { if (target != null && token.HasValue) target.UnregisterPropertyChangedCallback(TextBlock.TextProperty, token.Value); }
            catch (Exception error) { Error(error); }
            try { target?.ClearValue(TextBlock.TextProperty); }
            catch (Exception error) { Error(error); }
            receipt["completed_qpc"] = Stopwatch.GetTimestamp(); receipt["error_count"] = errors.Count;
            if (errors.Count != 0 && receipt["status"]?.ToString() == "candidate-observed") receipt["status"] = "candidate-not-demonstrated";
            Save(); GC.KeepAlive(source); GC.KeepAlive(target); GC.KeepAlive(binding);
        }
    }

    private static JsonObject Text(string value)
    {
        var bytes = new byte[value.Length * 2];
        for (var index = 0; index < value.Length; index++)
        { bytes[index * 2] = (byte)value[index]; bytes[index * 2 + 1] = (byte)(value[index] >> 8); }
        return new JsonObject { ["value"] = value, ["utf16_length"] = value.Length, ["utf16_le_base64"] = Convert.ToBase64String(bytes) };
    }
}
