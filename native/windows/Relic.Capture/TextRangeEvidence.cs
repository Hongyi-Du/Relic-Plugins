using System.Globalization;
using System.Text.Json.Nodes;

// A failed provider field is unknown, not an empty successful measurement.
// Keep the already measured range identity and let independent observations
// continue, while retaining the original failure in the extraction gate.
internal static class TextRangeEvidence
{
    public static bool TryReadBounds<T>(Func<T> read, JsonObject range, string api,
        JsonArray errors, out T? value)
    {
        try
        {
            value = read();
            return true;
        }
        catch (Exception error)
        {
            value = default;
            range["bounds_status"] = "error";
            range["bounds_error"] = new JsonObject
            {
                ["api"] = api, ["exception_type"] = error.GetType().FullName,
                ["hresult"] = error.HResult,
                ["hresult_hex"] = "0x" + unchecked((uint)error.HResult).ToString("X8", CultureInfo.InvariantCulture),
                ["message"] = error.Message, ["exception"] = error.ToString()
            };
            errors.Add(api + ": " + range["bounds_error"]!["hresult_hex"] + " " + error.GetType().Name + ": " + error.Message);
            return false;
        }
    }

    public static void ValidateFormatStep(int moved, int startFromPreviousStart,
        int endFromPreviousEnd, int startFromEnd)
    {
        // CompareEndpoints establishes order only; its magnitude is not a
        // portable character offset. Do not normalize an invalid provider run.
        if (moved <= 0 || startFromPreviousStart != 0 || endFromPreviousEnd <= 0 || startFromEnd >= 0)
            throw new InvalidOperationException("UIA format endpoint did not produce one advancing, nondegenerate range with the unchanged start endpoint.");
    }
}
