using System.Text.Json.Nodes;

namespace Relic.Core;

// GET /api/cc owns the unread total. Its returned cards can omit copies whose
// organization or protocol is unavailable, so counting Items changes the badge.
public sealed class CopyInbox
{
    public JsonArray Items { get; private set; } = new();
    public int Unread { get; private set; }
    public bool Loaded { get; private set; }

    public JsonNode? Update(JsonNode response)
    {
        var previous = Loaded ? Unread : (int?)null;
        Items = response.Rows("items");
        Unread = response["unread"]?.GetValue<int>() ?? 0;
        Loaded = true;
        // Same production rule as loadCc(): an increase after the initial load
        // can notify about the first returned unread copy, if one is available.
        return previous.HasValue && Unread > previous.Value
            ? Items.FirstOrDefault(copy => !copy.Flag("read")) : null;
    }
}
