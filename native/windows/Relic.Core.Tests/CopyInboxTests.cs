using System.Text.Json.Nodes;
using Relic.Core;
using Xunit;

public class CopyInboxTests
{
    private static JsonNode Response(int unread, params (string Id, bool Read)[] copies) => new JsonObject
    {
        ["unread"] = unread,
        ["items"] = new JsonArray(copies.Select(copy => (JsonNode)new JsonObject
        {
            ["id"] = copy.Id, ["read"] = copy.Read, ["org_name"] = "Relic 工作室",
            ["protocol_id"] = "P-17", ["title"] = "检查交付"
        }).ToArray())
    };

    [Fact] public void ServerTotalIncludesUnreadCopiesOmittedFromTheCardList()
    {
        var inbox = new CopyInbox();
        Assert.Null(inbox.Update(Response(7, ("visible", false))));
        Assert.Equal(7, inbox.Unread); Assert.Single(inbox.Items); Assert.True(inbox.Loaded);
    }

    [Fact] public void NewReturnedIdWithoutAnIncreaseDoesNotNotify()
    {
        var inbox = new CopyInbox(); inbox.Update(Response(3, ("earlier", false)));
        Assert.Null(inbox.Update(Response(3, ("different", false))));
        Assert.Null(inbox.Update(Response(2, ("different", false))));
    }

    [Fact] public void IncreaseUsesFirstActualUnreadCopyWithItsNotificationFields()
    {
        var inbox = new CopyInbox(); inbox.Update(Response(0));
        var response = Response(4, ("read", true), ("first", false), ("second", false));
        var copy = inbox.Update(response);
        Assert.Same(response["items"]![1], copy);
        Assert.Equal("Relic 工作室", copy.Text("org_name"));
        Assert.Equal("P-17", copy.Text("protocol_id")); Assert.Equal("检查交付", copy.Text("title"));
    }

    [Fact] public void IncreaseWithoutAnAvailableUnreadCardDoesNotInventANotification()
    {
        var inbox = new CopyInbox(); inbox.Update(Response(0));
        Assert.Null(inbox.Update(Response(2))); Assert.Equal(2, inbox.Unread);
        Assert.Null(inbox.Update(Response(3, ("read", true)))); Assert.Equal(3, inbox.Unread);
    }

    [Fact] public void MissingUnreadUsesTheReferenceZeroDefaultInsteadOfCountingItems()
    {
        var inbox = new CopyInbox(); var response = Response(5, ("unread-card", false));
        response.AsObject().Remove("unread");
        Assert.Null(inbox.Update(response)); Assert.Equal(0, inbox.Unread);
    }
}
