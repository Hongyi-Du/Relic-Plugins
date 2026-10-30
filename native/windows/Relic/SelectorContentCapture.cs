using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    // Read the current production template/content objects. Neither tab.Text,
    // AutomationProperties.Name nor a template-part name establishes a label.
    private static void CaptureSelectorContentBindings(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> records)
    {
        foreach (var (value, record) in records)
        {
            if (value.GetType() != typeof(SelectorBarItem) || value is not SelectorBarItem owner
                || owner.Tag is not UIElement tag) continue;
            var receipt = new JsonObject
            {
                ["contract"] = "selectorbar-current-content-label-v1",
                ["source"] = "Actual SelectorBarItem.Tag and current ContentPresenter.Content object identity",
                ["owner_id"] = ids[owner], ["owner_runtime_type"] = owner.GetType().FullName,
                ["tag_content_id"] = ids.GetValueOrDefault(tag),
                ["ui_thread_access"] = owner.DispatcherQueue.HasThreadAccess,
                ["template_present"] = owner.Template != null,
                ["status"] = "incomplete"
            };
            record["selector_content_evidence"] = receipt;
            var errors = new JsonArray(); receipt["errors"] = errors;
            try
            {
                var template = owner.Template;
                List<(DependencyObject Value, DependencyObject? Parent, int Index)> Snapshot()
                {
                    var result = new List<(DependencyObject, DependencyObject?, int)>();
                    void Walk(DependencyObject current, DependencyObject? parent, int index)
                    {
                        result.Add((current, parent, index));
                        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(current); i++)
                            Walk(VisualTreeHelper.GetChild(current, i), current, i);
                    }
                    Walk(owner, null, 0); return result;
                }
                var before = Snapshot();
                var presenters = before.Select(entry => entry.Value).OfType<ContentPresenter>()
                    .Where(presenter => ReferenceEquals(presenter.Content, tag)).ToArray();
                receipt["presenter_ids"] = new JsonArray(presenters.Select(p => (JsonNode?)JsonValue.Create(ids.GetValueOrDefault(p))).ToArray());
                var tree = new JsonArray(); var textSources = new JsonArray();
                var complete = true;
                foreach (var entry in before)
                {
                    var found = ids.TryGetValue(entry.Value, out var id) && records.TryGetValue(entry.Value, out _);
                    var parentId = entry.Parent == null ? null : ids.GetValueOrDefault(entry.Parent);
                    var parentMatches = entry.Parent == null || found && parentId != null
                        && records[entry.Value]["parent"]?.GetValue<string>() == parentId
                        && ReferenceEquals(VisualTreeHelper.GetParent(entry.Value), entry.Parent);
                    complete &= found && parentMatches;
                    tree.Add(new JsonObject
                    {
                        ["id"] = id, ["parent_id"] = parentId, ["child_index"] = entry.Index,
                        ["runtime_type"] = entry.Value.GetType().FullName,
                        ["captured_parent_matches"] = parentMatches
                    });
                    if (entry.Value is FrameworkElement text && text is TextBlock or RichTextBlock or NativeLabel)
                    {
                        var actual = CaptureText(text);
                        var same = found && records[entry.Value]["text"]?.GetValue<string>() == actual;
                        complete &= same;
                        textSources.Add(new JsonObject { ["id"] = id, ["text"] = actual,
                            ["captured_text_matches"] = same, ["runtime_type"] = text.GetType().FullName });
                    }
                }
                receipt["actual_subtree"] = tree;
                receipt["text_sources"] = textSources;
                var after = Snapshot();
                var sameTree = before.Count == after.Count && before.Zip(after).All(pair =>
                    ReferenceEquals(pair.First.Value, pair.Second.Value)
                    && ReferenceEquals(pair.First.Parent, pair.Second.Parent) && pair.First.Index == pair.Second.Index);
                var sameTag = ReferenceEquals(owner.Tag, tag);
                var sameTemplate = ReferenceEquals(owner.Template, template);
                var sameContent = presenters.Length == 1 && ReferenceEquals(presenters[0].Content, tag);
                var tagInTree = before.Any(entry => ReferenceEquals(entry.Value, tag));
                receipt["same_subtree_after"] = sameTree;
                receipt["same_tag_after"] = sameTag;
                receipt["same_template_after"] = sameTemplate;
                receipt["same_presenter_content_after"] = sameContent;
                receipt["tag_in_actual_subtree"] = tagInTree;
                receipt["captured_subtree_complete"] = complete;
                complete &= sameTree && sameTag && sameTemplate && sameContent && tagInTree
                    && owner.DispatcherQueue.HasThreadAccess && template != null;
                if (!complete) errors.Add("Current template, Tag/Content reference, text source or visual-tree binding is incomplete or changed");
                receipt["status"] = complete ? "measured" : "incomplete";
            }
            catch (Exception error)
            {
                errors.Add(error.GetType().FullName + ": " + error.Message);
            }
        }
    }
}
