using System.Globalization;
using System.Text.Json.Nodes;

namespace Relic;

// Keep actual invalid measurements inspectable without accepting them as a
// finite coordinate, substituting zero, or mutating the live observer record.
internal static class NativeCaptureNumbers
{
    internal static JsonObject Prepare(JsonObject original, string source)
    {
        var result = original.DeepClone().AsObject();
        var invalid = new JsonArray();
        JsonNode? Visit(JsonNode? node, string path)
        {
            if (node is JsonValue value)
            {
                string? raw = null, bits = null, type = null;
                if (value.TryGetValue<double>(out var number) && !double.IsFinite(number))
                {
                    raw = number.ToString("R", CultureInfo.InvariantCulture);
                    bits = BitConverter.DoubleToUInt64Bits(number).ToString("X16", CultureInfo.InvariantCulture); type = "binary64";
                }
                else if (value.TryGetValue<float>(out var single) && !float.IsFinite(single))
                {
                    raw = single.ToString("R", CultureInfo.InvariantCulture);
                    bits = BitConverter.SingleToUInt32Bits(single).ToString("X8", CultureInfo.InvariantCulture); type = "binary32";
                }
                if (raw != null)
                {
                    var observation = new JsonObject { ["source"] = source, ["path"] = path,
                        ["raw_value"] = raw, ["ieee754_format"] = type, ["ieee754_bits"] = bits,
                        ["reason"] = "Actual value is not a finite JSON number; no replacement measurement is inferred" };
                    invalid.Add(observation.DeepClone());
                    return new JsonObject { ["nonfinite_measurement"] = observation };
                }
            }
            else if (node is JsonObject obj)
            {
                foreach (var field in obj.ToArray())
                {
                    var child = Visit(field.Value, path + "/" + field.Key.Replace("~", "~0").Replace("/", "~1"));
                    if (!ReferenceEquals(child, field.Value)) obj[field.Key] = child;
                }
            }
            else if (node is JsonArray array)
            {
                for (var index = 0; index < array.Count; index++)
                {
                    var child = Visit(array[index], path + "/" + index.ToString(CultureInfo.InvariantCulture));
                    if (!ReferenceEquals(child, array[index])) array[index] = child;
                }
            }
            return node;
        }
        Visit(result, "");
        if (invalid.Count == 0) return result;
        result["nonfinite_measurements"] = invalid;
        if (result["errors"] is not JsonArray errors) result["errors"] = errors = new JsonArray();
        foreach (var value in invalid)
            errors.Add(source + value!["path"] + ": actual non-finite measurement " + value["raw_value"]);
        // Frame observers use failure; the XAML extractor also retains errors.
        // Both remain failed, while all other raw evidence can now be written.
        result["failure"] = (result["failure"]?.ToString() is { Length: > 0 } prior ? prior + "\n" : "")
            + source + ": non-finite actual measurements; see nonfinite_measurements";
        return result;
    }
}
