using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Relic;
using Xunit;

public sealed class AutomationIdentityMarshalTests
{
    private static JsonObject? RunWorker(AutomationIdentityMarshal transport, AutomationIdentityNative.IApi api)
    {
        JsonObject? result = null; Exception? failure = null;
        // Dedicated mock thread avoids Task.Wait inlining the queued operation
        // onto this test's origin thread. No COM APIs or UI are created here.
        var thread = new Thread(() => { try { result = transport.ReadWorker(api); } catch (Exception ex) { failure = ex; } });
        thread.Start(); thread.Join();
        if (failure != null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(failure).Throw();
        return result;
    }
    private sealed class FakeMarshalApi : AutomationIdentityMarshal.IApi
    {
        public int InitializeResult, MarshalResult, UnmarshalResult;
        public bool ThrowUnmarshal, FailPacketRelease;
        public readonly List<(string Api, IntPtr Pointer, int Thread)> Calls = [];
        private void Record(string name, IntPtr pointer = default) => Calls.Add((name, pointer, Environment.CurrentManagedThreadId));
        public int QueryFragment(IntPtr peer, out IntPtr fragment)
        { Assert.Equal(new IntPtr(77), peer); Record("Query", peer); fragment = new IntPtr(22); return 0; }
        public int MarshalFragment(IntPtr fragment, out IntPtr stream)
        { Assert.Equal(new IntPtr(22), fragment); Record("Marshal", fragment); stream = new IntPtr(33); return MarshalResult; }
        public int InitializeMta() { Record("Initialize"); return InitializeResult; }
        public int UnmarshalFragmentAndReleaseStream(IntPtr stream, out IntPtr fragment)
        {
            Assert.Equal(new IntPtr(33), stream); Record("UnmarshalAndReleaseStream", stream);
            if (ThrowUnmarshal) throw new EntryPointNotFoundException("Synthetic interop boundary failure before a return receipt");
            fragment = UnmarshalResult < 0 ? IntPtr.Zero : new IntPtr(1); return UnmarshalResult;
        }
        public void Uninitialize() => Record("Uninitialize");
        public int ReleaseMarshalData(IntPtr stream)
        { Assert.Equal(new IntPtr(33), stream); Record("ReleaseMarshalData", stream); return FailPacketRelease ? unchecked((int)0x8000FFFF) : 0; }
        public int Release(IntPtr pointer) { Record("Release", pointer); return 1; }
    }

    [Theory]
    [InlineData("CoMarshalInterThreadInterfaceInStream", typeof(int))]
    [InlineData("CoGetInterfaceAndReleaseStream", typeof(int))]
    [InlineData("CoInitializeEx", typeof(int))]
    [InlineData("CoUninitialize", typeof(void))]
    [InlineData("CoReleaseMarshalData", typeof(int))]
    public void PublicComPInvokesRetainHresultsGuidReferencesAndOwnedOutputs(string name, Type returnType)
    {
        var method = typeof(AutomationIdentityMarshal).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!;
        Assert.Equal(returnType, method.ReturnType);
        Assert.Equal("ole32.dll", method.GetCustomAttribute<DllImportAttribute>()!.Value);
        var parameters = method.GetParameters();
        if (name is "CoMarshalInterThreadInterfaceInStream" or "CoGetInterfaceAndReleaseStream")
        {
            Assert.Equal(3, parameters.Length);
            var guidPosition = name == "CoMarshalInterThreadInterfaceInStream" ? 0 : 1;
            Assert.Equal(typeof(Guid).MakeByRefType(), parameters[guidPosition].ParameterType);
            Assert.Equal(typeof(IntPtr), parameters[1 - guidPosition].ParameterType);
            Assert.Equal(typeof(IntPtr).MakeByRefType(), parameters[2].ParameterType); Assert.True(parameters[2].IsOut);
        }
        else if (name == "CoInitializeEx")
        {
            Assert.Equal(typeof(IntPtr), parameters[0].ParameterType); Assert.Equal(typeof(uint), parameters[1].ParameterType);
        }
        else if (name == "CoReleaseMarshalData") Assert.Equal(typeof(IntPtr), parameters.Single().ParameterType);
        else Assert.Empty(parameters);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void WorkerUsesOnlyUnmarshaledProxyAndBalancesBothSuccessfulInitializeResults(int initialized)
    {
        var origin = Environment.CurrentManagedThreadId;
        var api = new FakeMarshalApi { InitializeResult = initialized };
        var transport = new AutomationIdentityMarshal(api);
        var nativeApi = new AutomationIdentityAbiTests.FakeApi();
        Assert.True(transport.Prepare(new IntPtr(77)));
        // Pure mocks only: synchronously joining a worker is safe in this test.
        // The production UI caller awaits instead, so its STA remains available.
        var native = RunWorker(transport, nativeApi);
        transport.FinishOnOrigin();
        Assert.Equal("measured", transport.Receipt["status"]!.GetValue<string>());
        Assert.Equal("measured", native!["status"]!.GetValue<string>());
        Assert.True(transport.Receipt["stream_consumed_by_unmarshal"]!.GetValue<bool>());
        Assert.True(transport.Receipt["returned_to_origin_thread"]!.GetValue<bool>());
        Assert.Empty(transport.Receipt["failures"]!.AsArray());
        Assert.All(api.Calls.Where(call => call.Api is "Query" or "Marshal"), call => Assert.Equal(origin, call.Thread));
        Assert.All(api.Calls.Where(call => call.Api is "Initialize" or "UnmarshalAndReleaseStream" or "Uninitialize"),
            call => Assert.NotEqual(origin, call.Thread));
        Assert.Equal(new[] { new IntPtr(22), new IntPtr(1) }, api.Calls.Where(call => call.Api == "Release").Select(call => call.Pointer));
        Assert.DoesNotContain(api.Calls, call => call.Api == "ReleaseMarshalData" || (call.Api == "Release" && call.Pointer == new IntPtr(33)));
        Assert.Single(api.Calls.Where(call => call.Api == "Uninitialize"));
        Assert.Equal(new[] { new IntPtr(3), new IntPtr(2) }, nativeApi.Released);
    }

    [Fact]
    public void FailedMtaInitializationReclaimsUnusedPacketOnlyOnOriginWithoutCallingProvider()
    {
        var origin = Environment.CurrentManagedThreadId;
        var api = new FakeMarshalApi { InitializeResult = unchecked((int)0x80010106) }; // RPC_E_CHANGED_MODE
        var transport = new AutomationIdentityMarshal(api); var nativeApi = new AutomationIdentityAbiTests.FakeApi();
        Assert.True(transport.Prepare(new IntPtr(77)));
        Assert.Null(RunWorker(transport, nativeApi));
        transport.FinishOnOrigin();
        Assert.Equal("unknown", transport.Receipt["status"]!.GetValue<string>());
        Assert.Equal(0, nativeApi.CoreReads);
        Assert.DoesNotContain(api.Calls, call => call.Api is "UnmarshalAndReleaseStream" or "Uninitialize");
        Assert.Contains(api.Calls, call => call.Api == "ReleaseMarshalData" && call.Thread == origin);
        Assert.Contains(api.Calls, call => call.Api == "Release" && call.Pointer == new IntPtr(33) && call.Thread == origin);
    }

    [Fact]
    public void UnmarshalHresultFailureConsumesStreamExactlyOnceAndNeverReadsProvider()
    {
        var api = new FakeMarshalApi { UnmarshalResult = unchecked((int)0x80004002) };
        var transport = new AutomationIdentityMarshal(api); var nativeApi = new AutomationIdentityAbiTests.FakeApi();
        Assert.True(transport.Prepare(new IntPtr(77)));
        Assert.Null(RunWorker(transport, nativeApi));
        transport.FinishOnOrigin();
        Assert.Equal("unknown", transport.Receipt["status"]!.GetValue<string>());
        Assert.True(transport.Receipt["stream_consumed_by_unmarshal"]!.GetValue<bool>());
        Assert.Equal(0, nativeApi.CoreReads); Assert.Single(api.Calls.Where(call => call.Api == "Uninitialize"));
        Assert.DoesNotContain(api.Calls, call => call.Api == "ReleaseMarshalData" || (call.Api == "Release" && call.Pointer == new IntPtr(33)));
        Assert.Contains(transport.Receipt["steps"]!.AsArray(), item => item?["hresult_hex"]?.GetValue<string>() == "0x80004002");
    }

    [Fact]
    public void MissingUnmarshalReturnKeepsConsumptionUnknownRatherThanDoubleReleasing()
    {
        var api = new FakeMarshalApi { ThrowUnmarshal = true };
        var transport = new AutomationIdentityMarshal(api);
        Assert.True(transport.Prepare(new IntPtr(77)));
        Assert.Null(RunWorker(transport, new AutomationIdentityAbiTests.FakeApi()));
        transport.FinishOnOrigin();
        Assert.Equal("unknown", transport.Receipt["status"]!.GetValue<string>());
        Assert.True(transport.Receipt["stream_consumption_unknown"]!.GetValue<bool>());
        Assert.Equal("0x21", transport.Receipt["unresolved_stream_pointer"]!.GetValue<string>());
        Assert.DoesNotContain(api.Calls, call => call.Api == "ReleaseMarshalData" || (call.Api == "Release" && call.Pointer == new IntPtr(33)));
    }

    [Fact]
    public void NativeReadFailureStillReleasesProxyAndUninitializesMta()
    {
        var api = new FakeMarshalApi(); var transport = new AutomationIdentityMarshal(api);
        Assert.True(transport.Prepare(new IntPtr(77)));
        var native = RunWorker(transport, new AutomationIdentityAbiTests.FakeApi { FailCoreRead = true });
        transport.FinishOnOrigin();
        Assert.Equal("unknown", native!["status"]!.GetValue<string>());
        Assert.Contains(api.Calls, call => call.Api == "Release" && call.Pointer == new IntPtr(1));
        Assert.Single(api.Calls.Where(call => call.Api == "Uninitialize"));
    }

    [Fact]
    public void UnscheduledWorkerReleasesPacketOnOriginAndRetainsCleanupFailure()
    {
        var api = new FakeMarshalApi { FailPacketRelease = true }; var transport = new AutomationIdentityMarshal(api);
        Assert.True(transport.Prepare(new IntPtr(77)));
        transport.FinishOnOrigin(); transport.FinishOnOrigin();
        Assert.Equal("unknown", transport.Receipt["status"]!.GetValue<string>());
        Assert.Single(api.Calls.Where(call => call.Api == "ReleaseMarshalData"));
        Assert.Single(api.Calls.Where(call => call.Api == "Release" && call.Pointer == new IntPtr(33)));
        Assert.Contains(transport.Receipt["lifecycle"]!.AsArray(), item => item?["hresult_hex"]?.GetValue<string>() == "0x8000FFFF");
    }

    [Fact]
    public void FailedMarshalDoesNotClaimAPacketButReleasesAnyReturnedStream()
    {
        var api = new FakeMarshalApi { MarshalResult = unchecked((int)0x8007000E) }; var transport = new AutomationIdentityMarshal(api);
        Assert.False(transport.Prepare(new IntPtr(77)));
        transport.FinishOnOrigin();
        Assert.Equal("unknown", transport.Receipt["status"]!.GetValue<string>());
        Assert.DoesNotContain(api.Calls, call => call.Api == "ReleaseMarshalData");
        Assert.Equal(new[] { new IntPtr(22), new IntPtr(33) }, api.Calls.Where(call => call.Api == "Release").Select(call => call.Pointer));
    }
}
