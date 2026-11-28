using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Relic;
using Xunit;

public sealed class AutomationIdentityAbiTests
{
    internal sealed class ArrayFixture(int[] values, int lower = 0, uint dimensions = 1, ushort type = 3)
    {
        public int[] Values = values;
        public int Lower = lower;
        public uint Dimensions = dimensions;
        public ushort Type = type;
    }
    internal sealed class FakeApi : AutomationIdentityNative.IApi
    {
        public readonly Dictionary<IntPtr, ArrayFixture> Arrays = new()
        {
            [new IntPtr(101)] = new([3, 114], 5),
            [new IntPtr(102)] = new([42, 1048658, 4, 114], -2),
            [new IntPtr(103)] = new([42, 1048658, 4, 114], -2)
        };
        public readonly List<IntPtr> Destroyed = [];
        public readonly List<IntPtr> Released = [];
        public readonly List<IntPtr> NodesReleased = [];
        public Guid? FailedQuery;
        public bool FailNodeRelease;
        public bool FailArrayDestroy;
        public bool FailElementRead;
        public bool FailCoreRead;
        public int CoreReads;
        public int Query(IntPtr value, Guid iid, out IntPtr result)
        {
            if (FailedQuery == iid) { result = IntPtr.Zero; return unchecked((int)0x80004002); }
            Assert.Equal(iid == AutomationIdentityNative.FragmentId ? new IntPtr(1) : new IntPtr(2), value);
            result = iid == AutomationIdentityNative.FragmentId ? new IntPtr(2) : new IntPtr(3); return 0;
        }
        public int FragmentIdRead(IntPtr fragment, out IntPtr array)
        { Assert.Equal(new IntPtr(2), fragment); array = new IntPtr(101); return 0; }
        public int NodeFromProvider(IntPtr simple, out IntPtr node)
        { Assert.Equal(new IntPtr(3), simple); node = new IntPtr(4); return 0; }
        public int RuntimeIdRead(IntPtr node, out IntPtr array)
        { Assert.Equal(new IntPtr(4), node); array = new IntPtr(102 + CoreReads++); return FailCoreRead ? unchecked((int)0x8000FFFF) : 0; }
        public uint ArrayDimensions(IntPtr array) => Arrays[array].Dimensions;
        public uint ArrayElementSize(IntPtr array) => 4;
        public int ArrayType(IntPtr array, out ushort type) { type = Arrays[array].Type; return 0; }
        public int ArrayLower(IntPtr array, uint dimension, out int lower) { lower = Arrays[array].Lower; return 0; }
        public int ArrayUpper(IntPtr array, uint dimension, out int upper) { upper = Arrays[array].Lower + Arrays[array].Values.Length - 1; return 0; }
        public int ArrayElement(IntPtr array, ref int index, out int value)
        { value = Arrays[array].Values[index - Arrays[array].Lower]; return FailElementRead ? unchecked((int)0x8000FFFF) : 0; }
        public int ArrayDestroy(IntPtr array) { Destroyed.Add(array); return FailArrayDestroy ? unchecked((int)0x8000FFFF) : 0; }
        public bool NodeRelease(IntPtr node) { NodesReleased.Add(node); return !FailNodeRelease; }
        public int Release(IntPtr value) { Released.Add(value); return 1; }
    }

    [Fact]
    public void ProductionFragmentAbiUsesHresultSelfAndSafeArrayOutputAtSlotFour()
    {
        var type = typeof(AutomationIdentityNative.FragmentRuntimeId);
        var invoke = type.GetMethod("Invoke")!;
        Assert.Equal(typeof(int), invoke.ReturnType);
        Assert.Equal(CallingConvention.StdCall, type.GetCustomAttribute<UnmanagedFunctionPointerAttribute>()!.CallingConvention);
        var parameters = invoke.GetParameters(); Assert.Equal(2, parameters.Length);
        Assert.Equal(typeof(IntPtr), parameters[0].ParameterType);
        Assert.Equal(typeof(IntPtr).MakeByRefType(), parameters[1].ParameterType); Assert.True(parameters[1].IsOut);
        Assert.Equal(4, AutomationIdentityNative.FragmentRuntimeIdSlot);
        var vtable = Marshal.AllocHGlobal(5 * IntPtr.Size); var instance = Marshal.AllocHGlobal(IntPtr.Size);
        IntPtr calledSelf = IntPtr.Zero;
        AutomationIdentityNative.FragmentRuntimeId callback = (IntPtr self, out IntPtr output) =>
        { calledSelf = self; output = new IntPtr(0x1234); return unchecked((int)0x8000FFFF); };
        try
        {
            for (var i = 0; i < 5; i++) Marshal.WriteIntPtr(vtable, i * IntPtr.Size, IntPtr.Zero);
            Marshal.WriteIntPtr(vtable, 4 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(callback));
            Marshal.WriteIntPtr(instance, vtable);
            var hr = AutomationIdentityNative.Method<AutomationIdentityNative.FragmentRuntimeId>(instance, AutomationIdentityNative.FragmentRuntimeIdSlot)(instance, out var output);
            Assert.Equal(instance, calledSelf); Assert.Equal(new IntPtr(0x1234), output); Assert.Equal(unchecked((int)0x8000FFFF), hr);
        }
        finally { GC.KeepAlive(callback); Marshal.FreeHGlobal(instance); Marshal.FreeHGlobal(vtable); }
    }

    [Theory]
    [InlineData("UiaNodeFromProvider", typeof(int))]
    [InlineData("UiaGetRuntimeId", typeof(int))]
    [InlineData("UiaNodeRelease", typeof(bool))]
    public void PublicCorePInvokeContractsHaveExplicitOutputsAndWin32Boolean(string name, Type returnType)
    {
        var method = typeof(AutomationIdentityNative).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!;
        Assert.Equal(returnType, method.ReturnType);
        Assert.Equal("UIAutomationCore.dll", method.GetCustomAttribute<DllImportAttribute>()!.Value);
        Assert.Equal(typeof(IntPtr), method.GetParameters()[0].ParameterType);
        if (name == "UiaNodeRelease") Assert.Equal(UnmanagedType.Bool, method.ReturnParameter.GetCustomAttribute<MarshalAsAttribute>()!.Value);
        else { Assert.True(method.GetParameters()[1].IsOut); Assert.Equal(typeof(IntPtr).MakeByRefType(), method.GetParameters()[1].ParameterType); }
    }

    [Fact]
    public void ActualCoreOpaqueArrayIsPreservedAndAllOwnedResultsAreReleased()
    {
        var api = new FakeApi(); var progress = new List<JsonObject>();
        var receipt = AutomationIdentityNative.Read(new IntPtr(1), api, entry => progress.Add(entry.DeepClone().AsObject()));
        Assert.Equal("measured", receipt["status"]!.GetValue<string>());
        Assert.Equal("[42,1048658,4,114]", receipt["core_runtime_id"]!["values"]!.ToJsonString());
        Assert.Equal("[3,114]", receipt["fragment_runtime_id"]!["values"]!.ToJsonString());
        Assert.Equal(-2, receipt["core_runtime_id"]!["dimension_bounds"]![0]!["lower"]!.GetValue<int>());
        Assert.Equal(new[] { new IntPtr(101), new IntPtr(102), new IntPtr(103) }, api.Destroyed);
        Assert.Equal(new[] { new IntPtr(3), new IntPtr(2) }, api.Released);
        Assert.Equal(new[] { new IntPtr(4) }, api.NodesReleased);
        Assert.DoesNotContain(new IntPtr(1), api.Released); // borrowed inspectable belongs to the WinUI caller.
        Assert.Contains(progress, item => item["api"]!.GetValue<string>() == "UiaNodeFromProvider" && item["status"]!.GetValue<string>() == "pending");
    }

    [Theory]
    [InlineData(2, 3)]
    [InlineData(1, 8)]
    public void WrongArrayShapeOrTypeStaysUnknownAndStillDestroysTheArray(int dimensions, int type)
    {
        var api = new FakeApi(); api.Arrays[new IntPtr(101)].Dimensions = (uint)dimensions; api.Arrays[new IntPtr(101)].Type = (ushort)type;
        var receipt = AutomationIdentityNative.Read(new IntPtr(1), api);
        Assert.Equal("unknown", receipt["status"]!.GetValue<string>());
        Assert.Equal(dimensions, receipt["fragment_runtime_id"]!["dimension_bounds"]!.AsArray().Count);
        Assert.Equal(new[] { new IntPtr(101) }, api.Destroyed);
        Assert.Equal(new[] { new IntPtr(2) }, api.Released);
        Assert.Empty(api.NodesReleased); Assert.Equal(0, api.CoreReads);
    }

    [Fact]
    public void FailedSecondQueryReleasesPreviouslyAcquiredFragmentWithoutFabricatingFullId()
    {
        var api = new FakeApi { FailedQuery = AutomationIdentityNative.SimpleId };
        var receipt = AutomationIdentityNative.Read(new IntPtr(1), api);
        Assert.Equal("unknown", receipt["status"]!.GetValue<string>());
        Assert.Null(receipt["core_runtime_id"]);
        Assert.Equal(new[] { new IntPtr(101) }, api.Destroyed);
        Assert.Equal(new[] { new IntPtr(2) }, api.Released);
    }

    [Fact]
    public void CoreReadFailureRetainsHresultAndDestroysAnyReturnedArray()
    {
        var api = new FakeApi { FailCoreRead = true };
        var receipt = AutomationIdentityNative.Read(new IntPtr(1), api);
        Assert.Equal("unknown", receipt["status"]!.GetValue<string>());
        Assert.Contains(receipt["steps"]!.AsArray(), item => item?["hresult_hex"]?.GetValue<string>() == "0x8000FFFF");
        Assert.Equal(new[] { new IntPtr(101), new IntPtr(102) }, api.Destroyed);
        Assert.Single(api.NodesReleased); Assert.Equal(2, api.Released.Count);
        Assert.Null(receipt["core_runtime_id"]!["values"]);
    }

    [Fact]
    public void ChangedFullIdCannotBeRepairedFromMatchingFragmentSuffix()
    {
        var api = new FakeApi(); api.Arrays[new IntPtr(103)].Values = [42, 999, 4, 114];
        var receipt = AutomationIdentityNative.Read(new IntPtr(1), api);
        Assert.Equal("unknown", receipt["status"]!.GetValue<string>());
        Assert.False(receipt["core_runtime_id_stable"]!.GetValue<bool>());
        Assert.Equal("[42,1048658,4,114]", receipt["core_runtime_id"]!["values"]!.ToJsonString());
        Assert.Equal("[42,999,4,114]", receipt["core_runtime_id_recheck"]!["values"]!.ToJsonString());
        Assert.Equal(3, api.Destroyed.Count);
    }

    [Fact]
    public void FailedReleaseOrJournalCannotProduceCompleteIdentity()
    {
        foreach (var mode in new[] { "array", "node", "journal", "element" })
        {
            var api = new FakeApi { FailArrayDestroy = mode == "array", FailNodeRelease = mode == "node", FailElementRead = mode == "element" };
            var receipt = AutomationIdentityNative.Read(new IntPtr(1), api,
                _ => { if (mode == "journal") throw new System.IO.IOException("synthetic journal write fault"); });
            Assert.Equal("unknown", receipt["status"]!.GetValue<string>());
            Assert.NotEmpty(receipt["failures"]!.AsArray()); Assert.NotEmpty(api.Destroyed); Assert.NotEmpty(api.Released);
        }
    }
}
