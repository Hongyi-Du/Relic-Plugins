using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Xunit;

public sealed class TextRangeEvidenceTests
{
    [Fact]
    public void FailedBoundsPreserveActualIdentityAndHresultWithoutSuccessfulEmptyValue()
    {
        var range = new JsonObject
        {
            ["text"] = "\r", ["range_identity"] = new JsonObject { ["start_utf16"] = 123, ["end_utf16"] = 124 }
        };
        var errors = new JsonArray();
        var read = TextRangeEvidence.TryReadBounds<double[]>(
            () => throw new COMException("Provider failed", unchecked((int)0x8000FFFF)),
            range, "mock bounds", errors, out var value);

        Assert.False(read); Assert.Null(value); Assert.Single(errors);
        Assert.Equal("\r", range["text"]!.GetValue<string>());
        Assert.Equal(123, range["range_identity"]!["start_utf16"]!.GetValue<int>());
        Assert.Equal("error", range["bounds_status"]!.GetValue<string>());
        Assert.Equal("0x8000FFFF", range["bounds_error"]!["hresult_hex"]!.GetValue<string>());
        Assert.Equal(unchecked((int)0x8000FFFF), range["bounds_error"]!["hresult"]!.GetValue<int>());
    }

    [Fact]
    public void SuccessfulEmptyArrayRemainsDistinctFromFailedRead()
    {
        var range = new JsonObject(); var errors = new JsonArray(); var actual = Array.Empty<double>();
        Assert.True(TextRangeEvidence.TryReadBounds(() => actual, range, "mock bounds", errors, out var value));
        Assert.Same(actual, value); Assert.Empty(errors); Assert.False(range.ContainsKey("bounds_error"));
    }

    [Fact]
    public void ProviderZeroAreaAndNonfiniteValuesAreNotChangedByObservation()
    {
        var range = new JsonObject(); var errors = new JsonArray();
        var actual = new[] { 8.0, 31.0, 0.0, 0.0, double.NaN, double.PositiveInfinity, -1.0, 10.0 };
        Assert.True(TextRangeEvidence.TryReadBounds(() => actual, range, "mock bounds", errors, out var value));
        Assert.Same(actual, value); Assert.Equal(0, value![2]); Assert.True(double.IsNaN(value[4]));
        // Geometry validation still happens in the caller; measurement does not
        // replace invalid provider data with guessed or empty rectangles.
    }

    [Theory]
    [InlineData(0, 0, 0, 0)]
    [InlineData(-1, 0, -1, 0)]
    [InlineData(1, 1, 1, -1)]
    [InlineData(1, 0, 0, 0)]
    [InlineData(1, 0, 1, 0)]
    public void InvalidFormatStepFailsInsteadOfBeingNormalized(int moved, int start, int end, int order) =>
        Assert.Throws<InvalidOperationException>(() => TextRangeEvidence.ValidateFormatStep(moved, start, end, order));

    [Fact]
    public void EndpointComparisonUsesOnlyOrderingNotCharacterDistance() =>
        TextRangeEvidence.ValidateFormatStep(1, 0, 27, -300);
}
