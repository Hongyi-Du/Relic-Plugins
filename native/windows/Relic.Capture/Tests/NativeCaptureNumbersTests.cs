using System.Text.Json.Nodes;
using Relic;
using Xunit;

public sealed class NativeCaptureNumbersTests
{
    [Fact]
    public void NestedNonfiniteMeasurementsRetainExactBitsAndFailWithoutMutatingOriginal()
    {
        var nan = BitConverter.UInt64BitsToDouble(0x7FF800000000002A);
        var source = new JsonObject { ["a/b~c"] = new JsonArray(double.PositiveInfinity, double.NegativeInfinity, nan) };
        var result = NativeCaptureNumbers.Prepare(source, "actual frame");
        Assert.NotNull(JsonNode.Parse(result.ToJsonString()));
        var invalid = result["nonfinite_measurements"]!.AsArray();
        Assert.Equal(3, invalid.Count);
        Assert.Equal("/a~1b~0c/0", invalid[0]!["path"]!.GetValue<string>());
        Assert.Equal("FFF0000000000000", invalid[1]!["ieee754_bits"]!.GetValue<string>());
        Assert.Equal("7FF800000000002A", invalid[2]!["ieee754_bits"]!.GetValue<string>());
        Assert.Equal(3, result["errors"]!.AsArray().Count);
        Assert.Contains("non-finite", result["failure"]!.GetValue<string>());
        Assert.True(double.IsPositiveInfinity(source["a/b~c"]![0]!.GetValue<double>()));
        Assert.Null(source["failure"]);
    }

    [Fact]
    public void SinglePrecisionRetainsItsActualFormat()
    {
        var source = new JsonObject { ["value"] = float.NegativeInfinity };
        var result = NativeCaptureNumbers.Prepare(source, "actual float");
        var value = result["value"]!["nonfinite_measurement"]!;
        Assert.Equal("binary32", value["ieee754_format"]!.GetValue<string>());
        Assert.Equal("FF800000", value["ieee754_bits"]!.GetValue<string>());
    }

    [Fact]
    public void FiniteDataNullsAndExistingErrorsArePreserved()
    {
        var source = new JsonObject { ["n"] = -0.125, ["float"] = 0.4f, ["id"] = 71,
            ["unknown"] = null, ["text"] = "Infinity", ["errors"] = new JsonArray("earlier error") };
        var result = NativeCaptureNumbers.Prepare(source, "actual frame");
        Assert.True(JsonNode.DeepEquals(source, result));
        Assert.Null(result["nonfinite_measurements"]);
    }

    [Fact]
    public void ExistingFailureAndErrorsAreNotReplaced()
    {
        var source = new JsonObject { ["bad"] = double.NaN, ["failure"] = "original failure",
            ["errors"] = new JsonArray("original error") };
        var result = NativeCaptureNumbers.Prepare(source, "actual frame");
        Assert.StartsWith("original failure\n", result["failure"]!.GetValue<string>());
        Assert.Equal("original error", result["errors"]![0]!.GetValue<string>());
        Assert.Equal(2, result["errors"]!.AsArray().Count);
    }
}
