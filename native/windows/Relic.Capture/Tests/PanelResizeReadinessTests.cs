using System.Text.Json.Nodes;
using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class PanelResizeReadinessTests
{
    // Minimal observer-shape fixtures, not recorded screenshots or UI proof.
    private static JsonObject Closed() => JsonNode.Parse("""
        {"owned_tooltip":{"same_tooltip_instance":true,"attached_same_tooltip_object":true,
          "is_open":false,"is_loaded":false,"visibility":"Visible","opacity":1,
          "actual_popup_indices":[],"bounds":null},"open_popups":[]}
        """)!.AsObject();

    private static JsonObject Open() => JsonNode.Parse("""
        {"owned_tooltip":{"same_tooltip_instance":true,"attached_same_tooltip_object":true,
          "is_open":true,"is_loaded":true,"visibility":"Visible","opacity":1,
          "actual_popup_indices":[0],"bounds":{"x":1056,"y":418,"width":92,"height":32}},
         "open_popups":[{"capture_popup_index":0,"child_same_owned_tooltip_object":true,"is_open":true}]}
        """)!.AsObject();

    [Fact]
    public void AnObservedClosedTipDoesNotRequireAnOpeningOrMutateItsReceipt()
    {
        var state = Closed(); var original = state.DeepClone();
        Assert.Equal("closed", PanelResizeToolTipReadiness.Observe(state));
        Assert.True(JsonNode.DeepEquals(original, state));
        state["owned_tooltip"]!["is_loaded"] = true;
        Assert.Equal("closed", PanelResizeToolTipReadiness.Observe(state));
    }

    [Fact]
    public void AnObservedOpenTipRetainsItsActualPopupAndOpeningDoesChangeContinuityState()
    {
        var state = Open(); var original = state.DeepClone();
        Assert.Equal("open", PanelResizeToolTipReadiness.Observe(state));
        Assert.True(JsonNode.DeepEquals(original, state));
        Assert.False(JsonNode.DeepEquals(Closed(), state));
        Assert.Single(state["open_popups"]!.AsArray());
    }

    [Theory]
    [InlineData("same_tooltip_instance")]
    [InlineData("attached_same_tooltip_object")]
    [InlineData("is_open")]
    public void MissingOrConflictingIdentityAndUnknownOpenStateAreNotReadiness(string field)
    {
        foreach (var state in new[] { Closed(), Open() })
        {
            state["owned_tooltip"]!.AsObject().Remove(field);
            Assert.Null(PanelResizeToolTipReadiness.Observe(state));
            if (field != "is_open")
            {
                state["owned_tooltip"]![field] = false;
                Assert.Null(PanelResizeToolTipReadiness.Observe(state));
            }
        }
    }

    [Fact]
    public void ClosedFlagCannotHideAnActuallyOwnedOpenPopup()
    {
        var state = Open(); state["owned_tooltip"]!["is_open"] = false;
        Assert.Null(PanelResizeToolTipReadiness.Observe(state));
        state["owned_tooltip"]!["actual_popup_indices"] = new JsonArray();
        Assert.Null(PanelResizeToolTipReadiness.Observe(state));
    }

    [Theory]
    [InlineData("popup-index")]
    [InlineData("popup-identity")]
    [InlineData("popup-open")]
    [InlineData("popup-missing")]
    [InlineData("bounds")]
    [InlineData("loaded")]
    [InlineData("opacity")]
    [InlineData("visibility")]
    public void OpenFlagRequiresMeasuredVisiblePopupWithMatchingIdentity(string failure)
    {
        var state = Open(); var tip = state["owned_tooltip"]!.AsObject();
        var popup = state["open_popups"]![0]!.AsObject();
        switch (failure)
        {
            case "popup-index": popup["capture_popup_index"] = 1; break;
            case "popup-identity": popup["child_same_owned_tooltip_object"] = false; break;
            case "popup-open": popup["is_open"] = false; break;
            case "popup-missing": state.Remove("open_popups"); break;
            case "bounds": tip["bounds"] = null; break;
            case "loaded": tip["is_loaded"] = false; break;
            case "opacity": tip["opacity"] = 0; break;
            case "visibility": tip["visibility"] = "Collapsed"; break;
        }
        Assert.Null(PanelResizeToolTipReadiness.Observe(state));
    }

    [Fact]
    public void AnUnrelatedActualPopupDoesNotClaimTheClosedOwnedTip()
    {
        var state = Closed();
        state["open_popups"]!.AsArray().Add(new JsonObject
        {
            ["capture_popup_index"] = 0, ["child_same_owned_tooltip_object"] = false, ["is_open"] = true
        });
        Assert.Equal("closed", PanelResizeToolTipReadiness.Observe(state));
        Assert.Single(state["open_popups"]!.AsArray());
    }

    private static void AddObserver(JsonObject state, int revision = 0, bool initialOpen = false)
    {
        var tip = state["owned_tooltip"]!;
        tip["open_change_observer_active"] = true;
        tip["initial_is_open"] = initialOpen;
        tip["last_observed_is_open"] = tip["is_open"]!.DeepClone();
        tip["open_change_revision"] = revision;
    }

    private static JsonObject DeliveredEvent(string kind, int revision) => new()
    {
        ["kind"] = kind, ["sender_same_tooltip_object"] = true, ["same_thumb_object"] = true,
        ["production_map_same_tooltip_object"] = true, ["attached_same_tooltip_object"] = true,
        ["is_open"] = kind == "opened", ["is_loaded"] = kind == "opened", ["open_change_revision"] = revision
    };

    [Fact]
    public void ActualOpenLoadedPopupIsNotEvidenceThatOpenedWasDelivered()
    {
        // The 2f4bd19 race: these visible properties already agreed at the two
        // checkpoints; only the real Opened delivery changed between them.
        // Synthetic receipt, deliberately not described as a recorded capture.
        var state = Open(); AddObserver(state, 1); var events = new JsonArray();
        var original = state.DeepClone();
        Assert.Equal("open", PanelResizeToolTipReadiness.Observe(state));
        Assert.Equal("waiting-for-owned-tooltip-opened-event", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        events.Add(DeliveredEvent("opened", 1));
        Assert.Equal("delivered-open", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        Assert.Single(events);
        Assert.True(JsonNode.DeepEquals(original, state));
    }

    [Fact]
    public void InitiallyClosedTipNeedsNoManufacturedOpenedOrClosedEvent()
    {
        var state = Closed(); AddObserver(state); var events = new JsonArray();
        Assert.Equal("delivered-closed-initial", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        Assert.Empty(events);
    }

    [Fact]
    public void ReopenedTipCannotBorrowAnEarlierOpening()
    {
        var state = Open(); AddObserver(state, 3);
        var events = new JsonArray(DeliveredEvent("opened", 1), DeliveredEvent("closed", 2));
        Assert.Equal("waiting-for-owned-tooltip-opened-event", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        events.Add(DeliveredEvent("opened", 3));
        Assert.Equal("delivered-open", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        Assert.Equal(3, events.Count);
    }

    [Fact]
    public void ActualClosureWaitsForTheCurrentClosedEvent()
    {
        var state = Closed(); AddObserver(state, 2);
        var events = new JsonArray(DeliveredEvent("opened", 1));
        Assert.Equal("waiting-for-owned-tooltip-closed-event", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        events.Add(DeliveredEvent("closed", 2));
        Assert.Equal("delivered-closed", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        Assert.Equal(2, events.Count);
    }

    [Theory]
    [InlineData("sender_same_tooltip_object")]
    [InlineData("same_thumb_object")]
    [InlineData("production_map_same_tooltip_object")]
    [InlineData("attached_same_tooltip_object")]
    public void ForeignOrReboundEventCannotSatisfyCurrentDelivery(string flag)
    {
        var state = Open(); AddObserver(state, 1); var delivered = DeliveredEvent("opened", 1);
        delivered[flag] = false; var events = new JsonArray(delivered);
        Assert.Equal("conflicting-tooltip-event-identity", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        Assert.Single(events);
    }

    [Fact]
    public void MissingObserverAndPendingPropertyObservationStayUnknown()
    {
        var state = Open(); var events = new JsonArray(DeliveredEvent("opened", 1));
        Assert.Equal("unknown-tooltip-event-observer", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
        AddObserver(state, 1); state["owned_tooltip"]!["last_observed_is_open"] = false;
        Assert.Equal("waiting-for-owned-tooltip-property-observation", PanelResizeToolTipReadiness.DeliveryStatus(state, events));
    }
}
