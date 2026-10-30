using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class PanelResizeSettlingTests
{
    // Synthetic clock/API-result fixtures only, with no UI or system calls.
    [Theory]
    [InlineData(0, "waiting-for-measured-delay")]
    [InlineData(799.99, "waiting-for-measured-delay")]
    [InlineData(800, "waiting-for-dispatcher")]
    public void InitialMouseDelayUsesActualSpiValueBeforeDispatcherCanSettle(double elapsed, string expected)
        => Assert.Equal(expected, PanelResizeSettling.Status(elapsed, 400, false, true, true));

    [Theory]
    [InlineData(800)]
    [InlineData(999.9)]
    [InlineData(1000)]
    public void ObservedStateOnlyBecomesReadyWithinUnchangedBudgetAfterActualDispatcherTurn(double elapsed)
        => Assert.Equal("ready", PanelResizeSettling.Status(elapsed, 400, true, true, true));

    [Fact]
    public void DispatcherOverrunCannotTurnIntoReadiness()
        => Assert.Equal("deadline-exceeded", PanelResizeSettling.Status(1000.001, 400, true, true, true));

    [Fact]
    public void SpiFailureIsNotReplacedByAnAssumedDefault()
        => Assert.Equal("unknown-system-hover-delay", PanelResizeSettling.Status(900, null, true, true, true));

    [Fact]
    public void LongerActualSystemDelayDoesNotExtendTheDeadline()
        => Assert.Equal("system-delay-exceeds-deadline", PanelResizeSettling.Status(0, 501, false, true, true));

    [Fact]
    public void ActualZeroSystemDelayStillNeedsDispatcherAndObservedStates()
    {
        Assert.Equal("waiting-for-dispatcher", PanelResizeSettling.Status(0, 0, false, true, true));
        Assert.Equal("waiting-for-idle-hover", PanelResizeSettling.Status(0, 0, true, false, true));
        Assert.Equal("waiting-for-measured-tooltip-state", PanelResizeSettling.Status(0, 0, true, true, false));
        Assert.Equal("ready", PanelResizeSettling.Status(0, 0, true, true, true));
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void InvalidClockMeasurementsNeverClaimReadiness(double elapsed)
        => Assert.Equal("invalid-elapsed-time", PanelResizeSettling.Status(elapsed, 400, true, true, true));
}
