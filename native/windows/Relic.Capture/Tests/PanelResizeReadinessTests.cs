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
}
