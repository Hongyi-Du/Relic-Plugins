namespace Relic.Core;

// A native scroll notification is not itself proof of a new input. WinUI can
// deliver DirectManipulationStarted while applying a programmatic list seek.
public sealed class ScrollInputIntent
{
    private long? manipulationSeekGeneration;
    public long Generation { get; private set; }

    // Raw input alone includes single-finger cursor movement. It is a pan
    // cancellation only when paired with an uncompleted native DM start.
    public bool RecordInput()
    {
        Generation++;
        return manipulationSeekGeneration is { } requested && requested != Generation;
    }

    public long BeginSeek()
    {
        CompleteDirectManipulation();
        return Generation;
    }

    public bool BeginDirectManipulation(long? pendingSeekGeneration, bool inputObservationAvailable)
    {
        var programmatic = IsProgrammaticDirectManipulation(pendingSeekGeneration, inputObservationAvailable);
        manipulationSeekGeneration = programmatic ? pendingSeekGeneration : null;
        return !programmatic;
    }

    public void CompleteDirectManipulation() => manipulationSeekGeneration = null;

    public bool IsProgrammaticDirectManipulation(long? pendingSeekGeneration, bool inputObservationAvailable)
        => inputObservationAvailable && pendingSeekGeneration is { } requested && requested == Generation;
}
