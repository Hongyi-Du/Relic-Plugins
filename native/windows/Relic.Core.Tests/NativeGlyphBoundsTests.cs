using System.Text.Json.Nodes;
using Xunit;

namespace Relic.Core.Tests;

public sealed class NativeGlyphBoundsTests
{
    private static JsonObject EmptyOutline() => new()
    {
        ["source"] = "Actual same-run IDWriteFontFace.GetGlyphRunOutline into ID2D1PathGeometry",
        ["failure"] = null, ["color_font"] = false, ["figure_count"] = 0u, ["segment_count"] = 0u,
        ["create_path_hresult"] = 0, ["open_hresult"] = 0, ["outline_hresult"] = 0,
        ["close_hresult"] = 0, ["segment_count_hresult"] = 0, ["figure_count_hresult"] = 0
    };
    private static NativeGlyphBounds.Bounds RecordedAbnormal() => new(float.PositiveInfinity, float.PositiveInfinity, float.MaxValue, float.MaxValue);

    [Fact]
    public void FiniteOrderedBoundsDoNotQueryOutline()
    {
        var result = NativeGlyphBounds.Classify(0, new(1, 2, 3, 4), () => throw new Exception("Must not query"));
        Assert.Equal("finite", result["classification"]!.GetValue<string>());
        Assert.Null(result["outline"]);
        Assert.Null(result["failure"]);
    }

    [Fact]
    public void FailedHresultDoesNotTreatOutBufferAsGeometryOrQueryOutline()
    {
        var result = NativeGlyphBounds.Classify(unchecked((int)0x80070057), new(0, 0, 0, 0), () => throw new Exception("Must not query"));
        Assert.Equal("api-failed", result["classification"]!.GetValue<string>());
        Assert.Equal("0x80070057", result["bounds_hresult_hex"]!.GetValue<string>());
        Assert.Null(result["outline"]);
    }

    [Fact]
    public void RecordedNonfiniteValuesKeepExactBitsWithoutPuttingInfinityInJsonNumbers()
    {
        // db91b1b group label 23/run 7 and five other space runs. This tests
        // transport/classification only; the synthetic outline is not CI proof.
        var result = NativeGlyphBounds.Classify(0, RecordedAbnormal(), EmptyOutline);
        Assert.Equal("outline-empty", result["classification"]!.GetValue<string>());
        Assert.Equal("7F800000", result["raw_bounds"]!["left"]!["ieee754_bits"]!.GetValue<string>());
        Assert.Equal("7F7FFFFF", result["raw_bounds"]!["right"]!["ieee754_bits"]!.GetValue<string>());
        Assert.Null(result["raw_bounds"]!["left"]!["value"]);
        Assert.Contains("Infinity", result.ToJsonString());
        Assert.Null(result["failure"]);
    }

    [Fact]
    public void InfinityAloneNeverProvesEmpty()
    {
        var proof = EmptyOutline(); proof["figure_count"] = 1u; proof["segment_count"] = 4u;
        var result = NativeGlyphBounds.Classify(0, new(float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity, float.PositiveInfinity), () => proof);
        Assert.Equal("unclassified", result["classification"]!.GetValue<string>());
        Assert.NotNull(result["failure"]);
    }

    [Fact]
    public void ReversedFiniteRectangleStillRequiresActualOutlineObservation()
    {
        var called = 0;
        var result = NativeGlyphBounds.Classify(0, new(10, 20, -10, -20), () => { called++; return EmptyOutline(); });
        Assert.Equal(1, called);
        Assert.Equal("reversed", result["raw_bounds_classification"]!.GetValue<string>());
        Assert.Equal("outline-empty", result["classification"]!.GetValue<string>());
    }

    [Fact]
    public void EveryNativeFailureOrMissingCountRetainsUnknown()
    {
        foreach (var key in new[] { "create_path_hresult", "open_hresult", "outline_hresult", "close_hresult", "segment_count_hresult", "figure_count_hresult" })
        {
            var proof = EmptyOutline(); proof[key] = -1;
            var result = NativeGlyphBounds.Classify(0, RecordedAbnormal(), () => proof);
            Assert.Equal("unclassified", result["classification"]!.GetValue<string>());
            Assert.NotNull(result["failure"]);
        }
        var missing = EmptyOutline(); missing["figure_count"] = null;
        Assert.False(NativeGlyphBounds.OutlineEmpty(missing));
    }

    [Fact]
    public void FailedObservationOrUnknownColorStatusCannotProveAllPaintAbsent()
    {
        var result = NativeGlyphBounds.Classify(0, RecordedAbnormal(), () => throw new InvalidOperationException("Actual outline failed"));
        Assert.Equal("unclassified", result["classification"]!.GetValue<string>());
        Assert.Contains("Actual outline failed", result["failure"]!.GetValue<string>());
        var proof = EmptyOutline(); proof["color_font"] = null;
        Assert.False(NativeGlyphBounds.OutlineEmpty(proof));
        proof["color_font"] = true;
        Assert.False(NativeGlyphBounds.OutlineEmpty(proof));
    }

    [Fact]
    public void FiniteZeroAreaDoesNotInventEmptyOutlineOrDiscardRawSignedZero()
    {
        var result = NativeGlyphBounds.Classify(0, new(-0f, 0, 0, 0), () => throw new Exception("Must not query"));
        Assert.Equal("finite", result["classification"]!.GetValue<string>());
        Assert.Equal("80000000", result["raw_bounds"]!["left"]!["ieee754_bits"]!.GetValue<string>());
    }
}
