using System.Diagnostics;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;

namespace Relic;

// d7b164c's 19 actual CI processes observed all six requested changes, including
// change/restore in one dispatch, through this SDK binding route. That experiment
// used independent objects. This observer instead retains the actual scene Run;
// it never assigns its Text and never inserts the observation target in a tree.
internal sealed class RunTextBindingObserver : IDisposable
{
    private readonly Run source;
    private readonly RunTextBindingJournal journal;
    private TextBlock? target;
    private Binding? binding;
    private long? token;
    private bool disposed;
    internal JsonObject Receipt => journal.Receipt;

    internal RunTextBindingObserver(Run source, int objectId, Action changed, Action<string> error)
    {
        this.source = source;
        journal = new RunTextBindingJournal(objectId, Stopwatch.GetTimestamp(), changed, error);
        Receipt["source_runtime_type"] = source.GetType().FullName;
        Receipt["managed_thread_id"] = Environment.CurrentManagedThreadId;
        Receipt["qpc_frequency"] = Stopwatch.Frequency;
    }

    internal void Install()
    {
        try
        {
            if (!source.DispatcherQueue.HasThreadAccess)
                throw new InvalidOperationException("Run.Text observer installation requires the retained Run's UI thread");
            target = new TextBlock();
            binding = new Binding { Source = source, Path = new PropertyPath("Text"), Mode = BindingMode.OneWay };
            token = target.RegisterPropertyChangedCallback(TextBlock.TextProperty, Callback);
            Receipt["callback_token"] = token.Value;
            Receipt["callback_registration_source"] = "Actual RegisterPropertyChangedCallback returned token; no callback-list enumeration API is claimed";
            target.SetBinding(TextBlock.TextProperty, binding);
            journal.Installed(ReadState(), Stopwatch.GetTimestamp());
        }
        catch (Exception ex) { Failed("installation", ex); }
    }

    private void Callback(DependencyObject sender, DependencyProperty property)
    {
        var qpc = Stopwatch.GetTimestamp(); JsonObject? state = null;
        try { state = ReadState(); }
        catch (Exception ex) { Failed("callback_read", ex); }
        // A failed state read still records the callback and advances the actual
        // Run revision after initialization; it cannot silently hide a mutation.
        journal.Callback(state, ReferenceEquals(sender, target), ReferenceEquals(property, TextBlock.TextProperty), qpc);
    }

    private JsonObject ReadState()
    {
        if (target == null || binding == null) throw new InvalidOperationException("Run.Text observer objects were not installed");
        var expression = target.GetBindingExpression(TextBlock.TextProperty);
        var sourceText = source.Text; var targetText = target.Text;
        return new JsonObject
        {
            ["source_text"] = RunTextBindingJournal.Text(sourceText), ["target_text"] = RunTextBindingJournal.Text(targetText),
            ["source_target_utf16_equal"] = string.Equals(sourceText, targetText, StringComparison.Ordinal),
            ["source_has_ui_thread_access"] = source.DispatcherQueue.HasThreadAccess,
            ["target_has_ui_thread_access"] = target.DispatcherQueue.HasThreadAccess,
            ["target_is_loaded"] = target.IsLoaded, ["target_xaml_root_is_null"] = target.XamlRoot == null,
            ["target_visual_parent_is_null"] = VisualTreeHelper.GetParent(target) == null,
            ["binding_source_same_run"] = ReferenceEquals(binding.Source, source),
            ["binding_mode_one_way"] = binding.Mode == BindingMode.OneWay,
            ["binding_path_text"] = binding.Path?.Path == "Text", ["callback_registered"] = token.HasValue,
            ["binding_expression_present"] = expression != null,
            ["expression_data_item_same_run"] = expression == null ? null : ReferenceEquals(expression.DataItem, source),
            ["expression_parent_binding_same_object"] = expression == null ? null : ReferenceEquals(expression.ParentBinding, binding)
        };
    }

    internal JsonObject Inspect()
    {
        try
        {
            // No timestamp enters the input signature. Each checkpoint still
            // reads the actual objects; observation time is recorded by its caller.
            var state = ReadState();
            state["channel_available"] = !disposed && journal.Check(state, Stopwatch.GetTimestamp());
            return state;
        }
        catch (Exception ex)
        {
            Failed("checkpoint", ex);
            return new JsonObject { ["channel_available"] = false, ["error"] = ex.ToString() };
        }
    }

    private void Failed(string phase, Exception ex) => journal.Fail(
        "Run.Text " + phase + ": " + ex, phase, Stopwatch.GetTimestamp());

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        JsonObject? before = null;
        try { before = ReadState(); } catch (Exception ex) { Failed("cleanup_read", ex); }
        journal.BeginCleanup(before, Stopwatch.GetTimestamp());
        var cleanup = new JsonObject { ["started_qpc"] = Stopwatch.GetTimestamp() };
        Receipt["cleanup"] = cleanup;
        try
        {
            cleanup["registered_token_before"] = token.HasValue ? JsonValue.Create(token.Value) : null;
            if (target != null && token.HasValue)
            {
                target.UnregisterPropertyChangedCallback(TextBlock.TextProperty, token.Value);
                token = null; cleanup["unregister_returned"] = true;
            }
            else cleanup["unregister_returned"] = false;
        }
        catch (Exception ex) { cleanup["unregister_error"] = ex.ToString(); Failed("unregister", ex); }
        cleanup["unregister_completed_qpc"] = Stopwatch.GetTimestamp();
        try
        {
            if (target != null)
            {
                target.ClearValue(TextBlock.TextProperty);
                cleanup["clear_value_returned"] = true;
                cleanup["binding_expression_absent"] = target.GetBindingExpression(TextBlock.TextProperty) == null;
                cleanup["after"] = ReadState();
                if (cleanup["binding_expression_absent"]?.GetValue<bool>() != true)
                    journal.Fail("Observer target retained a binding expression after ClearValue", "cleanup", Stopwatch.GetTimestamp());
            }
            else cleanup["clear_value_returned"] = false;
        }
        catch (Exception ex) { cleanup["clear_value_error"] = ex.ToString(); Failed("clear_binding", ex); }
        cleanup["completed_qpc"] = Stopwatch.GetTimestamp();
        cleanup["callback_registered_after"] = token.HasValue;
        Receipt["disposed"] = true;
        GC.KeepAlive(source); GC.KeepAlive(target); GC.KeepAlive(binding);
    }
}
