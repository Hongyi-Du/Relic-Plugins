namespace Relic;

// The production walker is independent of WinUI so CI can exercise actual
// endpoint operations with in-memory providers. It never synthesizes bounds or
// UTF16 offsets; the caller observes each resulting provider range separately.
internal enum ProbeRangeEndpoint { Start, End }

internal interface IProbeFormatRange
{
    IProbeFormatRange Clone();
    int CompareEndpoints(ProbeRangeEndpoint endpoint, IProbeFormatRange other, ProbeRangeEndpoint otherEndpoint);
    void MoveEndpointByRange(ProbeRangeEndpoint endpoint, IProbeFormatRange other, ProbeRangeEndpoint otherEndpoint);
    int MoveEndByOneFormat();
}

internal sealed record ProbeFormatStep(int Index, int UnitsMoved, int EndVsParentEndBeforeClamp,
    int StartVsPreviousStart, int EndVsPreviousEnd, int StartVsEnd, int EndVsParentEndAfterClamp);

internal static class TextRangeFormatEnumeration
{
    internal static int Capture(IProbeFormatRange parent,
        Action<IProbeFormatRange, ProbeFormatStep> observe, int maximumRuns = 10000)
    {
        if (maximumRuns <= 0) throw new ArgumentOutOfRangeException(nameof(maximumRuns));
        if (parent.CompareEndpoints(ProbeRangeEndpoint.Start, parent, ProbeRangeEndpoint.End) > 0)
            throw new InvalidOperationException("WinRT parent text range has reversed endpoints.");
        var cursor = parent.Clone();
        cursor.MoveEndpointByRange(ProbeRangeEndpoint.End, cursor, ProbeRangeEndpoint.Start);
        var count = 0;
        while (true)
        {
            var remaining = cursor.CompareEndpoints(ProbeRangeEndpoint.Start, parent, ProbeRangeEndpoint.End);
            if (remaining == 0) return count;
            if (remaining > 0)
                throw new InvalidOperationException("WinRT format cursor advanced beyond its parent range.");
            if (count >= maximumRuns)
                throw new InvalidOperationException($"WinRT format range enumeration exceeded {maximumRuns} runs; coverage is incomplete.");
            var previous = cursor.Clone();
            var moved = cursor.MoveEndByOneFormat();
            var beyond = cursor.CompareEndpoints(ProbeRangeEndpoint.End, parent, ProbeRangeEndpoint.End);
            if (beyond > 0)
                cursor.MoveEndpointByRange(ProbeRangeEndpoint.End, parent, ProbeRangeEndpoint.End);
            var step = new ProbeFormatStep(count, moved, beyond,
                cursor.CompareEndpoints(ProbeRangeEndpoint.Start, previous, ProbeRangeEndpoint.Start),
                cursor.CompareEndpoints(ProbeRangeEndpoint.End, previous, ProbeRangeEndpoint.End),
                cursor.CompareEndpoints(ProbeRangeEndpoint.Start, cursor, ProbeRangeEndpoint.End),
                cursor.CompareEndpoints(ProbeRangeEndpoint.End, parent, ProbeRangeEndpoint.End));
            // Preserve the actual problematic range as well as its operation
            // journal before reporting a nonadvancing/otherwise invalid step.
            observe(cursor, step);
            count++;
            if (step.UnitsMoved <= 0 || step.StartVsPreviousStart != 0 || step.EndVsPreviousEnd <= 0
                || step.StartVsEnd >= 0 || step.EndVsParentEndAfterClamp > 0)
                throw new InvalidOperationException("WinRT format endpoint did not produce one advancing, nondegenerate range with the unchanged start endpoint inside its parent.");
            cursor.MoveEndpointByRange(ProbeRangeEndpoint.Start, cursor, ProbeRangeEndpoint.End);
        }
    }
}
