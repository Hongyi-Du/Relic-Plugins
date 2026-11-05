using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Globalization;
using System.Text.Json.Nodes;
using Windows.ApplicationModel.DataTransfer;

namespace Relic;

// Settings > Slack (relic_core/slack.py). The person connects a read-only Slack app of their own and chooses what each
// organization may read. The token goes from the password box to the local Relic App service once and is never shown
// again: every answer from the service carries the connection only. A choice is saved as soon as it changes.
public sealed partial class MainWindow
{
    // Errors the service answers with as word-list keys; anything else is Slack's own text.
    private static readonly string[] SlackErrorKeys =
        ["slack.error.bot_token", "slack.error.not_user_token", "slack.error.invalid_token", "slack.error.unreachable", "slack.error.not_connected"];
    private static readonly Dictionary<string, string> SlackModeKeys = new()
        { ["inherit"] = "slack.mode.inherit", ["all"] = "slack.mode.all", ["list"] = "slack.mode.list", ["none"] = "slack.mode.none" };
    private static readonly Dictionary<string, string> SlackKindKeys = new()
        { ["public"] = "slack.kind.public", ["private"] = "slack.kind.private", ["mpim"] = "slack.kind.mpim", ["im"] = "slack.kind.im" };
    private static readonly Dictionary<string, string> SlackOpKeys = new()
        { ["search"] = "slack.op.search", ["history"] = "slack.op.history", ["thread"] = "slack.op.thread", ["channels"] = "slack.op.channels" };
    private JsonArray? slackConversations;

    private string SlackError(Exception error) => SlackErrorKeys.Contains(error.Message) ? T(error.Message) : error.Message;
    // An unknown value from a newer service shows as itself rather than disappearing.
    private string SlackWord(Dictionary<string, string> keys, string value) => keys.TryGetValue(value, out var key) ? T(key) : value;

    private static void SlackCopy(string text)
    {
        try { var package = new DataPackage(); package.SetText(text); Clipboard.SetContent(package); }
        catch (Exception) { }
    }

    private async Task SlackSettings(StackPanel content)
    {
        content.Children.Add(SettingsHeading(T("slack.title")));
        var intro = OverviewText(T("slack.intro"), 12.5, true, lineHeight: 21.25); intro.TextWrapping = TextWrapping.Wrap; intro.Margin = new Thickness(0, 0, 0, 6);
        content.Children.Add(intro);
        // Added before the first await: a page left meanwhile cleared content, so late answers fill a detached panel.
        var body = new StackPanel(); content.Children.Add(body);
        JsonNode state;
        try { state = await api!.Get("/api/slack", lifetime.Token); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            body.Children.Add(OverviewText(T("slack.load_failed", ("error", ex.Message)), 12.5, true)); return;
        }
        slackConversations = null;
        DrawSlack(body, state);
    }

    private void DrawSlack(StackPanel body, JsonNode state)
    {
        body.Children.Clear();
        if (state.Flag("connected")) SlackConnection(body, state); else SlackSetup(body, state);
        var scopes = new StackPanel(); body.Children.Add(scopes);
        var reads = new StackPanel(); body.Children.Add(reads);
        SlackReads(reads, state);
        _ = Run(() => DrawSlackScopes(scopes, state));
    }

    private void SlackSetup(StackPanel body, JsonNode state)
    {
        var manifest = state.Text("manifest"); var createUrl = state.Text("create_url");
        var first = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        first.Children.Add(OverviewAction(T("slack.copy_manifest"), () => { SlackCopy(manifest); Note(T("slack.copied")); return Task.CompletedTask; }));
        first.Children.Add(OverviewAction(T("slack.open_slack"), async () => { if (Uri.TryCreate(createUrl, UriKind.Absolute, out var uri)) await Windows.System.Launcher.LaunchUriAsync(uri); }));
        body.Children.Add(SettingRow(T("slack.step1"), T("slack.step1_hint"), first));
        body.Children.Add(SettingRow(T("slack.step2"), T("slack.step2_hint"), new Border()));
        var token = new PasswordBox
        {
            Width = 260, Height = 37, MinHeight = 0, PlaceholderText = "xoxp-…", FontFamily = new FontFamily("Cascadia Code"), FontSize = 13,
            Padding = new Thickness(10, 7, 10, 7), BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"),
            Background = Paint("FFFFFF", "1F1F1E"), CornerRadius = new CornerRadius(9)
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(token, T("slack.step3"));
        var problem = OverviewText("", 12.5, true); problem.TextWrapping = TextWrapping.Wrap; problem.Foreground = Paint("B3261E", "F2B8B5"); problem.Visibility = Visibility.Collapsed;
        Button? connect = null;
        async Task Connect()
        {
            var value = token.Password.Trim();
            if (value.Length == 0) { token.Focus(FocusState.Programmatic); return; }
            if (connect != null) connect.IsEnabled = false;
            problem.Visibility = Visibility.Collapsed;
            try
            {
                var next = await api!.Post("/api/slack/connect", new { token = value }, lifetime.Token);
                token.Password = ""; slackConversations = null; Note(T("slack.connected_note")); DrawSlack(body, next);
            }
            catch (HttpRequestException ex) { problem.Text = SlackError(ex); problem.Visibility = Visibility.Visible; }
            finally { if (connect != null) connect.IsEnabled = true; }
        }
        connect = OverviewAction(T("slack.connect"), Connect, primary: true);
        token.KeyDown += (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) { e.Handled = true; _ = Run(Connect); } };
        var line = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 }; line.Children.Add(token); line.Children.Add(connect);
        var block = new StackPanel { Spacing = 6 }; block.Children.Add(line); block.Children.Add(problem);
        body.Children.Add(SettingRow(T("slack.step3"), T("slack.step3_hint"), block));
    }

    private void SlackConnection(StackPanel body, JsonNode state)
    {
        var team = state["team"]; var domain = team.Text("domain");
        body.Children.Add(SettingRow(T("slack.workspace"), team.Text("name") + (domain.Length > 0 ? " · " + domain + ".slack.com" : ""), OverviewChip(T("settings.connected"), "ok")));
        body.Children.Add(SettingRow(T("slack.account"), state["user"].Text("name"), new Border()));
        var missing = state.Rows("missing_scopes").Select(scope => scope.Text()).Where(scope => scope.Length > 0).ToList();
        if (missing.Count > 0)
        {
            var manifest = state.Text("manifest");
            body.Children.Add(SettingRow(T("slack.missing"), T("slack.missing_hint", ("scopes", string.Join(", ", missing))),
                OverviewAction(T("slack.copy_manifest"), () => { SlackCopy(manifest); Note(T("slack.copied")); return Task.CompletedTask; })));
        }
        body.Children.Add(SettingRow(T("slack.disconnect"), T("slack.disconnect_hint"), OverviewAction(T("slack.disconnect"), async () =>
        {
            var next = await api!.Post("/api/slack/disconnect", new { }, lifetime.Token);
            slackConversations = null; DrawSlack(body, next);
        })));
    }

    private string SlackDescribe(JsonNode? scope, bool counted = true) => scope.Text("mode") switch
    {
        "list" => counted ? T("slack.scope_list", ("n", scope.Rows("conversations").Count)) : T("slack.scope_list_any"),
        "none" => T("slack.scope_none"),
        _ => scope.Flag("dms") ? T("slack.scope_all_dms") : T("slack.scope_all"),
    };

    private async Task DrawSlackScopes(StackPanel scopes, JsonNode state)
    {
        var connected = state.Flag("connected");
        if (connected && slackConversations == null)
        {
            try { slackConversations = (await api!.Get("/api/slack/conversations", lifetime.Token)).Rows("conversations"); }
            catch (Exception ex) when (ex is not OperationCanceledException) { slackConversations = null; }
        }
        scopes.Children.Clear();
        var heading = OverviewText(T("slack.scopes"), 15, weight: 650); heading.Margin = new Thickness(0, 18, 0, 2); scopes.Children.Add(heading);
        var hint = OverviewText(T("slack.scopes_hint"), 12.5, true); hint.TextWrapping = TextWrapping.Wrap; hint.Margin = new Thickness(0, 0, 0, 4); scopes.Children.Add(hint);
        SlackScopeRow(scopes, connected, "", T("slack.default"), 0, state["default"], state["default"], "", "");
        foreach (var org in state.Rows("orgs"))
        {
            if (org == null) continue;
            _ = int.TryParse(org.Text("depth"), out var depth);
            SlackScopeRow(scopes, connected, org.Text("id"), org.Text("name"), depth + 1, org["own"], org["effective"], org.Text("source"), org.Text("source_name"));
        }
    }

    private void SlackScopeRow(StackPanel scopes, bool connected, string orgId, string name, int depth, JsonNode? own, JsonNode? effective, string source, string sourceName)
    {
        var isDefault = orgId.Length == 0;
        var mode = own.Text("mode") is { Length: > 0 } chosenMode ? chosenMode : "inherit";
        var chosen = new HashSet<string>(own.Rows("conversations").Select(item => item.Text()).Where(id => id.Length > 0));
        var indent = Math.Min(depth, 6) * 18;
        string Describe()
        {
            if (mode != "inherit") return mode == "list" ? T("slack.scope_list", ("n", chosen.Count)) : SlackDescribe(own);
            var what = SlackDescribe(effective, counted: false);
            return source == "default" || sourceName.Length == 0 ? T("slack.from_default", ("what", what)) : T("slack.from_org", ("name", sourceName), ("what", what));
        }
        var choice = new ComboBox
        {
            Width = 150, Height = 34, MinHeight = 0, FontFamily = new FontFamily(FontFamilies.UI), FontSize = 13, Padding = new Thickness(10, 5, 10, 5),
            BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"), Background = Paint("FFFFFF", "1F1F1E"), CornerRadius = new CornerRadius(9)
        };
        foreach (var value in isDefault ? new[] { "all", "list", "none" } : new[] { "inherit", "all", "list", "none" })
            choice.Items.Add(new ComboBoxItem { Content = SlackWord(SlackModeKeys, value), Tag = value });
        SetChoice(choice, mode);
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(choice, name);
        var dms = new CheckBox { Content = T("slack.dms"), IsChecked = own.Flag("dms"), MinWidth = 0, VerticalAlignment = VerticalAlignment.Center,
            Visibility = mode == "all" ? Visibility.Visible : Visibility.Collapsed };
        var controls = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 }; controls.Children.Add(dms); controls.Children.Add(choice);
        var note = OverviewText(Describe(), 12.5, true); note.TextWrapping = TextWrapping.Wrap;
        var labels = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center }; labels.Children.Add(OverviewText(name, 13.5, weight: 600)); labels.Children.Add(note);
        var grid = TwoColumns(labels, controls); grid.ColumnSpacing = 16; controls.VerticalAlignment = VerticalAlignment.Center;
        scopes.Children.Add(new Border { Child = grid, Padding = new Thickness(indent, 10, 0, 10), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line });
        var picker = new StackPanel { Spacing = 6, Margin = new Thickness(indent, 4, 0, 10), Visibility = mode == "list" ? Visibility.Visible : Visibility.Collapsed };
        scopes.Children.Add(picker);
        Task<JsonNode> Save(string value) => api!.Post("/api/slack/scope", new { org = orgId, mode = value, dms = dms.IsChecked == true, conversations = chosen.ToArray() }, lifetime.Token);
        if (mode == "list")
        {
            if (slackConversations == null) picker.Children.Add(OverviewText(T(connected ? "slack.pick_failed" : "slack.pick_needs_connection"), 12.5, true));
            else
            {
                var filter = SettingsInput("", T("slack.filter"), 240, fontSize: 13);
                var list = new StackPanel();
                var scroll = new ScrollViewer { Content = list, MaxHeight = 260, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
                var all = slackConversations;
                void Fill()
                {
                    list.Children.Clear();
                    var query = filter.Text.Trim().TrimStart('#', '@').ToLowerInvariant(); var shown = 0;
                    foreach (var item in all)
                    {
                        if (item == null) continue;
                        var id = item.Text("id"); var label = item.Text("label");
                        if (query.Length > 0 && !label.ToLowerInvariant().Contains(query)) continue;
                        if (++shown > 300) break;
                        var box = new CheckBox { Content = label + " · " + SlackWord(SlackKindKeys, item.Text("kind")), IsChecked = chosen.Contains(id), MinHeight = 0, FontSize = 13 };
                        box.Click += async (_, _) => await Run(async () =>
                        {
                            if (box.IsChecked == true) chosen.Add(id); else chosen.Remove(id);
                            note.Text = Describe(); await Save("list");
                        });
                        list.Children.Add(box);
                    }
                }
                filter.TextChanged += (_, _) => Fill();
                picker.Children.Add(filter); picker.Children.Add(scroll); Fill();
            }
        }
        // Mode and direct messages change what the organizations below follow: draw every row again from the answer.
        choice.SelectionChanged += async (_, _) => await Run(async () => { var next = await Save(Value(choice)); await DrawSlackScopes(scopes, next); });
        dms.Click += async (_, _) => await Run(async () => { var next = await Save(Value(choice)); await DrawSlackScopes(scopes, next); });
    }

    private void SlackReads(StackPanel reads, JsonNode state)
    {
        var heading = OverviewText(T("slack.reads"), 15, weight: 650); heading.Margin = new Thickness(0, 18, 0, 6); reads.Children.Add(heading);
        var rows = state.Rows("reads");
        if (rows.Count == 0) { reads.Children.Add(OverviewText(T("slack.reads_empty"), 12.5, true)); return; }
        foreach (var read in rows)
        {
            if (read == null) continue;
            var at = double.TryParse(read.Text("at"), NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds)
                ? DateTimeOffset.FromUnixTimeMilliseconds((long)(seconds * 1000)).ToLocalTime().ToString("MM-dd HH:mm", CultureInfo.InvariantCulture) : "";
            var what = SlackWord(SlackOpKeys, read.Text("op")) + (read.Text("target").Length > 0 ? " " + read.Text("target") : "");
            var tail = read.Text("error").Length > 0 ? T("slack.read_error", ("error", read.Text("error"))) : T("slack.read_count", ("n", read.Text("count")));
            var text = string.Join(" · ", new[] { at, read.Text("org_name"), read.Text("member"), what, tail }.Where(part => part.Length > 0));
            var line = OverviewText(text, 12.5, true); line.TextWrapping = TextWrapping.Wrap; line.Margin = new Thickness(0, 0, 0, 4); reads.Children.Add(line);
        }
    }
}
