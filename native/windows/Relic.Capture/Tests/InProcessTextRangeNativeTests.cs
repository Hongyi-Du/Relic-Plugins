using System.Text.Json.Nodes;
using Relic;
using Xunit;

public sealed class InProcessTextRangeNativeTests
{
    // Synthetic provider memory and calls only: no peer, window, COM server or
    // application is created by these tests. Fractional values are fixtures,
    // not a claim that the new in-process diagnostic has already run in CI.
    private sealed class Api : InProcessTextRangeNative.IApi
    {
        public readonly List<IntPtr> Released = [], Destroyed = [];
        public readonly List<(IntPtr source, Guid iid)> Queries = [];
        private readonly Dictionary<IntPtr, (int start, int end)> ranges = new() { [(IntPtr)8] = (0, 3), [(IntPtr)9] = (1, 3) };
        private readonly Dictionary<IntPtr, string> strings = [];
        private int nextRange = 100, nextString = 1000;
        public readonly double[] Values = [475.125, 127, 251.783203125, 0.8499908447265625];
        public bool PatternUnavailable, FailProviderQuery, WrongArrayType, FailRectangles, FailDestroy;
        public bool DirectSimpleAvailable, FailFragmentQuery, FailFragmentSimpleQuery;
        public int TextQueries, DoubleReads;
        private const string DocumentText = "A\uD800B";
        public int Query(IntPtr source, Guid iid, out IntPtr result)
        {
            Queries.Add((source, iid));
            if (iid == AutomationIdentityNative.FragmentId)
            {
                Assert.Equal((IntPtr)1, source); result = FailFragmentQuery ? IntPtr.Zero : (IntPtr)50;
                return FailFragmentQuery ? unchecked((int)0x80004002) : 0;
            }
            if (iid == AutomationIdentityNative.SimpleId)
            {
                if (source == (IntPtr)1)
                { result = DirectSimpleAvailable ? (IntPtr)70 : IntPtr.Zero; return DirectSimpleAvailable ? 0 : unchecked((int)0x80004002); }
                Assert.Equal((IntPtr)50, source); result = FailFragmentSimpleQuery ? IntPtr.Zero : (IntPtr)60;
                return FailFragmentSimpleQuery ? unchecked((int)0x80004002) : 0;
            }
            if (iid == InProcessTextRangeNative.TextProviderId)
            { result = FailProviderQuery ? IntPtr.Zero : (IntPtr)4; return FailProviderQuery ? unchecked((int)0x80004002) : 0; }
            Assert.Equal(InProcessTextRangeNative.TextRangeProviderId, iid); result = source; return 0;
        }
        public int Pattern(IntPtr simple, out IntPtr result) { result = PatternUnavailable ? IntPtr.Zero : (IntPtr)2; return 0; }
        public int Document(IntPtr provider, out IntPtr result) { result = (IntPtr)8; return 0; }
        public int Visible(IntPtr provider, out IntPtr array) { array = (IntPtr)20; return 0; }
        public int Clone(IntPtr range, out IntPtr result) { result = (IntPtr)nextRange++; ranges[result] = ranges[range]; return 0; }
        public int Text(IntPtr range, out IntPtr bstr)
        { TextQueries++; var (s, e) = ranges[range]; bstr = (IntPtr)nextString++; strings[bstr] = DocumentText.Substring(s, e - s); return 0; }
        public int Rectangles(IntPtr range, out IntPtr array)
        { array = FailRectangles ? IntPtr.Zero : range == (IntPtr)8 ? (IntPtr)30 : (IntPtr)31; return FailRectangles ? unchecked((int)0x8000FFFF) : 0; }
        public int Move(IntPtr range, int endpoint, IntPtr target, int targetEndpoint)
        {
            Assert.Equal(1, endpoint); var current = ranges[range]; var to = ranges[target];
            ranges[range] = (current.start, targetEndpoint == 0 ? to.start : to.end); return 0;
        }
        public int Compare(IntPtr range, int endpoint, IntPtr target, int targetEndpoint, out int comparison)
        { var from = ranges[range]; var to = ranges[target]; comparison = (endpoint == 0 ? from.start : from.end) - (targetEndpoint == 0 ? to.start : to.end); return 0; }
        public uint Dimensions(IntPtr array) => 1;
        public uint ElementSize(IntPtr array) => array == (IntPtr)20 ? (uint)IntPtr.Size : 8;
        public int ArrayType(IntPtr array, out ushort type) { type = array == (IntPtr)20 ? (ushort)13 : WrongArrayType ? (ushort)3 : (ushort)5; return 0; }
        public int Lower(IntPtr array, out int lower) { lower = array == (IntPtr)20 ? -2 : 5; return 0; }
        public int Upper(IntPtr array, out int upper) { upper = array == (IntPtr)20 ? -2 : 8; return 0; }
        public int Double(IntPtr array, int index, out double value) { DoubleReads++; value = Values[index - 5]; return 0; }
        public int Unknown(IntPtr array, int index, out IntPtr value) { Assert.Equal(-2, index); value = (IntPtr)9; return 0; }
        public int Destroy(IntPtr array) { Destroyed.Add(array); return FailDestroy ? unchecked((int)0x8000FFFF) : 0; }
        public string? String(IntPtr bstr) => strings[bstr];
        public void FreeString(IntPtr bstr) { Assert.True(strings.Remove(bstr)); }
        public int Release(IntPtr value) { Released.Add(value); return 1; }
    }

    [Fact]
    public void PreservesSubpixelRawDoublesBitsAndNonzeroSafeArrayLowerBounds()
    {
        var api = new Api(); var receipt = InProcessTextRangeNative.Read((IntPtr)1, api);
        Assert.Equal("observed", receipt["status"]!.ToString());
        var range = receipt["document_range"]!;
        Assert.Equal(5, range["safearray"]!["lower_bound"]!.GetValue<int>());
        Assert.Equal(api.Values, range["bounding_rectangle_values"]!.AsArray().Select(v => v!.GetValue<double>()));
        Assert.Equal(api.Values.Select(v => unchecked((ulong)BitConverter.DoubleToInt64Bits(v)).ToString("X16")),
            range["bounding_rectangle_value_bits_hex"]!.AsArray().Select(v => v!.ToString()));
        Assert.Equal(-2L, receipt["visible_ranges"]![0]!["safearray_index"]!.GetValue<long>());
        Assert.False(receipt["canonical_geometry_supplied"]!.GetValue<bool>());
        Assert.False(receipt["provider_errors_resolved"]!.GetValue<bool>());
        Assert.Equal(new[] { (IntPtr)30, (IntPtr)31, (IntPtr)20 }, api.Destroyed);
        // One copied IUnknown and its QI reference are released separately.
        Assert.Equal(2, api.Released.Count(value => value == (IntPtr)9));
        Assert.Contains((IntPtr)8, api.Released); Assert.Contains((IntPtr)4, api.Released); Assert.Contains((IntPtr)2, api.Released);
    }

    [Fact]
    public void ActualEndpointCallsPreserveSourceSpanAndUnpairedUtf16()
    {
        var receipt = InProcessTextRangeNative.Read((IntPtr)1, new Api());
        var range = receipt["visible_ranges"]![0]!;
        Assert.Equal(1, range["start"]!["verified_prefix_utf16_length"]!.GetValue<int>());
        Assert.Equal(3, range["end"]!["verified_prefix_utf16_length"]!.GetValue<int>());
        Assert.True(range["text_matches_document_snapshot_slice"]!.GetValue<bool>());
        Assert.Equal(new byte[] { 0, 0xD8, 0x42, 0 }, Convert.FromBase64String(range["text"]!["utf16_le_base64"]!.ToString()));
    }

    [Fact]
    public void UnavailablePatternNeverConstructsTextRange()
    {
        var api = new Api { PatternUnavailable = true }; var receipt = InProcessTextRangeNative.Read((IntPtr)1, api);
        Assert.Equal("unavailable", receipt["status"]!.ToString()); Assert.Null(receipt["document_range"]);
        Assert.Equal(0, api.TextQueries); Assert.Empty(api.Destroyed); Assert.Empty(api.Released);
    }

    [Fact]
    public void PublicQiFailureRetainsHresultAndReleasesOnlyOwnedPattern()
    {
        var api = new Api { FailProviderQuery = true }; var receipt = InProcessTextRangeNative.Read((IntPtr)1, api);
        Assert.Equal("unavailable", receipt["status"]!.ToString()); Assert.Null(receipt["document_range"]);
        Assert.Contains(receipt["calls"]!.AsArray(), item => item?["hresult"]?.GetValue<int>() == unchecked((int)0x80004002));
        Assert.Equal(new[] { (IntPtr)2 }, api.Released);
    }

    [Fact]
    public void WrongSafeArrayTypeIsNotReinterpretedAsDoubles()
    {
        var api = new Api { WrongArrayType = true }; var receipt = InProcessTextRangeNative.Read((IntPtr)1, api);
        Assert.Equal("observed-with-errors", receipt["status"]!.ToString()); Assert.Equal(0, api.DoubleReads);
        Assert.Null(receipt["document_range"]!["bounding_rectangle_values"]); Assert.NotEmpty(receipt["errors"]!.AsArray());
        Assert.Contains((IntPtr)30, api.Destroyed); Assert.Contains((IntPtr)31, api.Destroyed);
    }

    [Fact]
    public void ProviderBoundsFailureRemainsMissingAndRetainsUnexpectedHresult()
    {
        var receipt = InProcessTextRangeNative.Read((IntPtr)1, new Api { FailRectangles = true });
        Assert.Equal("observed-with-errors", receipt["status"]!.ToString());
        Assert.Null(receipt["document_range"]!["bounding_rectangle_values"]);
        Assert.Contains(receipt["errors"]!.AsArray(), item => item?["hresult"]?.GetValue<int>() == unchecked((int)0x8000FFFF));
    }

    [Fact]
    public void ArrayCleanupFailureRemainsAnErrorAfterValuesWereObserved()
    {
        var receipt = InProcessTextRangeNative.Read((IntPtr)1, new Api { FailDestroy = true });
        Assert.Equal("observed-with-errors", receipt["status"]!.ToString());
        Assert.NotNull(receipt["document_range"]!["bounding_rectangle_values"]); Assert.NotEmpty(receipt["errors"]!.AsArray());
    }

    [Fact]
    public void ActualPublicFragmentRouteRetainsDirectQiFailureAndTransfersOnlySimpleReference()
    {
        var api = new Api(); var receipt = new JsonObject();
        var simple = InProcessTextRangeNative.AcquireSimpleThroughFragment((IntPtr)1, api, receipt);
        Assert.Equal((IntPtr)60, simple);
        Assert.Equal(new[] { ((IntPtr)1, AutomationIdentityNative.SimpleId), ((IntPtr)1, AutomationIdentityNative.FragmentId),
            ((IntPtr)50, AutomationIdentityNative.SimpleId) }, api.Queries);
        Assert.Equal("acquired-through-actual-fragment", receipt["status"]!.ToString());
        Assert.Single(receipt["errors"]!.AsArray());
        Assert.Equal(unchecked((int)0x80004002), receipt["calls"]![0]!["hresult"]!.GetValue<int>());
        Assert.Equal(new[] { (IntPtr)50 }, api.Released); // Caller still owns 60.
        Assert.True(receipt["simple_reference_transferred_to_caller"]!.GetValue<bool>());
    }

    [Fact]
    public void SuccessfulDirectDiagnosticReferenceIsReleasedWithoutReplacingFragmentRoute()
    {
        var api = new Api { DirectSimpleAvailable = true }; var receipt = new JsonObject();
        Assert.Equal((IntPtr)60, InProcessTextRangeNative.AcquireSimpleThroughFragment((IntPtr)1, api, receipt));
        Assert.Equal(new[] { (IntPtr)50, (IntPtr)70 }, api.Released);
        Assert.Empty(receipt["errors"]!.AsArray());
        Assert.DoesNotContain((IntPtr)60, api.Released);
    }

    [Fact]
    public void UnavailableFragmentRemainsUnavailableWithoutTryingAnotherPeerOrInterface()
    {
        var api = new Api { FailFragmentQuery = true }; var receipt = new JsonObject();
        Assert.Equal(IntPtr.Zero, InProcessTextRangeNative.AcquireSimpleThroughFragment((IntPtr)1, api, receipt));
        Assert.Equal(2, api.Queries.Count); Assert.Empty(api.Released);
        Assert.Equal("unavailable", receipt["status"]!.ToString());
        Assert.Equal(2, receipt["errors"]!.AsArray().Count);
    }

    [Fact]
    public void FragmentSimpleFailureReleasesTheRealIntermediateAndDoesNotManufactureAProvider()
    {
        var api = new Api { FailFragmentSimpleQuery = true }; var receipt = new JsonObject();
        Assert.Equal(IntPtr.Zero, InProcessTextRangeNative.AcquireSimpleThroughFragment((IntPtr)1, api, receipt));
        Assert.Equal(new[] { (IntPtr)50 }, api.Released);
        Assert.Null(receipt["simple_reference_transferred_to_caller"]);
        Assert.Equal("unavailable", receipt["status"]!.ToString());
        Assert.Equal(2, receipt["errors"]!.AsArray().Count);
    }
}
