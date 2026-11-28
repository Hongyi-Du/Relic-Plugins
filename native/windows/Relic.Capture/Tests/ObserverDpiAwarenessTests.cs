using System.Runtime.InteropServices;
using Xunit;

public sealed class ObserverDpiAwarenessTests
{
    [Fact]
    public void OpaqueContextUsesNativeEqualityAndPreservesActualValues()
    {
        var api = new FakeApi { Context = new nint(0x654321), Awareness = 2, Equal = true };
        var receipt = ObserverDpiAwareness.Read("before-first-uia", api);
        Assert.Equal("measured-per-monitor-v2", receipt["status"]!.GetValue<string>());
        Assert.Equal("0x654321", receipt["thread_context"]!.GetValue<string>());
        Assert.Equal(2, receipt["awareness"]!.GetValue<int>());
        Assert.True(receipt["equals_per_monitor_v2"]!.GetValue<bool>());
        Assert.Equal((api.Context, ObserverDpiAwareness.PerMonitorV2), api.Compared);
        Assert.Empty(receipt["errors"]!.AsArray());
    }

    [Theory]
    [InlineData(2)] // PMv1 and PMv2 share the same broad DPI_AWARENESS value.
    [InlineData(1)]
    [InlineData(0)]
    public void NonPmv2IsRecordedAndFailsWithoutSettingAnyContext(int awareness)
    {
        var api = new FakeApi { Awareness = awareness, Equal = false };
        var receipt = ObserverDpiAwareness.Read("actual-stage", api);
        Assert.Equal("failed", receipt["status"]!.GetValue<string>());
        Assert.Equal(awareness, receipt["awareness"]!.GetValue<int>());
        Assert.False(receipt["equals_per_monitor_v2"]!.GetValue<bool>());
        Assert.Contains("not confirmed PerMonitorV2", receipt["errors"]!.ToJsonString());
        Assert.Equal(1, api.ContextReads);
    }

    [Fact]
    public void FailedAwarenessApiDoesNotTurnDefaultIntoAnObservedUnawareValue()
    {
        var api = new FakeApi { AwarenessFailure = new COMException("actual test failure", unchecked((int)0x80004005)) };
        var receipt = ObserverDpiAwareness.Read("failed-awareness", api);
        Assert.Null(receipt["awareness"]);
        Assert.Equal("failed", receipt["status"]!.GetValue<string>());
        Assert.Contains("0x80004005", receipt["calls"]!.ToJsonString());
        Assert.Contains("actual test failure", receipt["errors"]!.ToJsonString());
        Assert.True(receipt["equals_per_monitor_v2"]!.GetValue<bool>());
    }

    [Fact]
    public void FailedEqualityDoesNotBecomeObservedFalse()
    {
        var api = new FakeApi { EqualityFailure = new EntryPointNotFoundException("actual unavailable API") };
        var receipt = ObserverDpiAwareness.Read("failed-equality", api);
        Assert.Equal(2, receipt["awareness"]!.GetValue<int>());
        Assert.Null(receipt["equals_per_monitor_v2"]);
        Assert.Contains("EntryPointNotFoundException", receipt["errors"]!.ToJsonString());
        Assert.Equal("failed", receipt["status"]!.GetValue<string>());
    }

    [Fact]
    public void MissingContextRemainsUnknownWithoutQueryingDependentApis()
    {
        var api = new FakeApi { Context = 0 };
        var receipt = ObserverDpiAwareness.Read("null-context", api);
        Assert.Null(receipt["thread_context"]);
        Assert.Null(receipt["awareness"]);
        Assert.Null(receipt["equals_per_monitor_v2"]);
        Assert.Null(api.Compared);
        Assert.Equal(0, api.AwarenessReads);
        Assert.Equal("failed", receipt["status"]!.GetValue<string>());
    }

    [Fact]
    public void ContextApiFailurePreservesExceptionAndUnknownDependentValues()
    {
        var api = new FakeApi { ContextFailure = new DllNotFoundException("test API unavailable") };
        var receipt = ObserverDpiAwareness.Read("failed-context", api);
        Assert.Null(receipt["thread_context"]);
        Assert.Null(receipt["awareness"]);
        Assert.Null(receipt["equals_per_monitor_v2"]);
        Assert.Contains("DllNotFoundException", receipt["calls"]!.ToJsonString());
        Assert.Contains("test API unavailable", receipt["errors"]!.ToJsonString());
        Assert.Null(api.Compared);
        Assert.Equal(0, api.AwarenessReads);
    }

    [Fact]
    public void InvalidAwarenessIsRetainedEvenIfEqualityClaimsPmv2()
    {
        var receipt = ObserverDpiAwareness.Read("invalid-awareness", new FakeApi { Awareness = -1 });
        Assert.Equal(-1, receipt["awareness"]!.GetValue<int>());
        Assert.True(receipt["equals_per_monitor_v2"]!.GetValue<bool>());
        Assert.Equal("failed", receipt["status"]!.GetValue<string>());
    }

    [Fact]
    public void LaterObservationDoesNotReuseEarlierContext()
    {
        var api = new FakeApi();
        var before = ObserverDpiAwareness.Read("before", api);
        api.Context = new nint(0x765432); api.Awareness = 0; api.Equal = false;
        var after = ObserverDpiAwareness.Read("after", api);
        Assert.Equal("measured-per-monitor-v2", before["status"]!.GetValue<string>());
        Assert.Equal("failed", after["status"]!.GetValue<string>());
        Assert.Equal("0x765432", after["thread_context"]!.GetValue<string>());
        Assert.Equal(2, api.ContextReads);
    }

    private sealed class FakeApi : ObserverDpiAwareness.IApi
    {
        public nint Context = new(0x123456);
        public int Awareness = 2;
        public bool Equal = true;
        public Exception? ContextFailure, AwarenessFailure, EqualityFailure;
        public int ContextReads, AwarenessReads;
        public (nint First, nint Second)? Compared;
        public uint GetCurrentThreadId() => 123;
        public nint GetThreadDpiAwarenessContext()
        {
            ContextReads++;
            if (ContextFailure != null) throw ContextFailure;
            return Context;
        }
        public int GetAwarenessFromDpiAwarenessContext(nint context)
        {
            AwarenessReads++; Assert.Equal(Context, context);
            if (AwarenessFailure != null) throw AwarenessFailure;
            return Awareness;
        }
        public bool AreDpiAwarenessContextsEqual(nint first, nint second)
        {
            Compared = (first, second);
            if (EqualityFailure != null) throw EqualityFailure;
            return Equal;
        }
    }
}
