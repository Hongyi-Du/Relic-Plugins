using Relic.Core;
using Xunit;

namespace Relic.Core.Tests;

public sealed class ScrollInputIntentTests
{
    [Fact]
    public void LateNotificationFromPreviousInputDoesNotCancelNewProgrammaticSeek()
    {
        var input = new ScrollInputIntent();
        input.RecordInput(); // Upward wheel, then an older page is inserted.
        var readingSeek = input.Generation;
        Assert.True(input.IsProgrammaticDirectManipulation(readingSeek, true));
        // More than one queued native state transition can arrive for the seek.
        Assert.True(input.IsProgrammaticDirectManipulation(readingSeek, true));
    }

    [Fact]
    public void NewTouchpadOrRoutedInputCancelsAnUnfinishedSeek()
    {
        var input = new ScrollInputIntent();
        var latestSeek = input.Generation;
        input.RecordInput();
        Assert.False(input.IsProgrammaticDirectManipulation(latestSeek, true));
        // A later explicit End can establish a new intent after that input.
        Assert.True(input.IsProgrammaticDirectManipulation(input.Generation, true));
    }

    [Fact]
    public void SettledOrCancelledSeekDoesNotSuppressNativePanning()
    {
        var input = new ScrollInputIntent();
        Assert.False(input.IsProgrammaticDirectManipulation(null, true));
    }

    [Fact]
    public void MissingRegistrationOrInputReadErrorPreservesNativePanning()
    {
        var input = new ScrollInputIntent();
        Assert.False(input.IsProgrammaticDirectManipulation(input.Generation, false));
        input.RecordInput();
        Assert.False(input.IsProgrammaticDirectManipulation(input.Generation - 1, false));
    }

    [Fact]
    public void RawInputBeforeNativePanCancelsButCursorMovementAloneDoesNot()
    {
        var input = new ScrollInputIntent();
        var seek = input.BeginSeek();
        Assert.False(input.RecordInput());
        Assert.True(input.BeginDirectManipulation(seek, true));
    }

    [Fact]
    public void NativePanBeforeRawInputCancelsWhenTheInputArrives()
    {
        var input = new ScrollInputIntent();
        var seek = input.BeginSeek();
        Assert.False(input.BeginDirectManipulation(seek, true));
        Assert.True(input.RecordInput());
    }

    [Fact]
    public void CompletedManipulationCannotCombineWithLaterPointerMotion()
    {
        var input = new ScrollInputIntent();
        Assert.False(input.BeginDirectManipulation(input.BeginSeek(), true));
        input.CompleteDirectManipulation();
        Assert.False(input.RecordInput());
    }

    [Fact]
    public void NewSeekCannotInheritThePreviousManipulationCandidate()
    {
        var input = new ScrollInputIntent();
        Assert.False(input.BeginDirectManipulation(input.BeginSeek(), true));
        var nextChat = input.BeginSeek();
        Assert.False(input.RecordInput());
        Assert.True(input.BeginDirectManipulation(nextChat, true));
    }

    [Fact]
    public void ConsumedNativePanDoesNotCancelAgainForEveryRawReport()
    {
        var input = new ScrollInputIntent();
        Assert.False(input.BeginDirectManipulation(input.BeginSeek(), true));
        Assert.True(input.RecordInput());
        input.CompleteDirectManipulation(); // Production LeaveLatest consumes it.
        Assert.False(input.RecordInput());
        Assert.False(input.RecordInput());
    }
}
