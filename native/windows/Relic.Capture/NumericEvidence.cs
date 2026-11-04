using System.Globalization;
using System.Text.Json.Nodes;

/// <summary>Keep JSON strict while retaining actual invalid measurement reasons.</summary>
internal static class NumericEvidence
{
    public static void Sanitize(JsonObject result, JsonArray errors)
    {
        var invalid = new JsonArray();
        void Missing(JsonNode parent, string key, JsonValue value, string path)
        {
            var raw = value.TryGetValue<double>(out var number) ? number.ToString("R", CultureInfo.InvariantCulture)
                : value.TryGetValue<float>(out var single) ? single.ToString("R", CultureInfo.InvariantCulture) : "non-finite number";
            if (parent is JsonObject obj) obj[key] = null;
            else ((JsonArray)parent)[int.Parse(key, CultureInfo.InvariantCulture)] = null;
            invalid.Add(new JsonObject { ["path"] = path, ["raw_value"] = raw, ["reason"] = "Actual UIA measurement is not a finite JSON number" });
            errors.Add(path + ": non-finite actual UIA measurement " + raw);
        }
        bool Invalid(JsonNode? value) => value is JsonValue scalar &&
            (scalar.TryGetValue<double>(out var number) && !double.IsFinite(number) ||
             scalar.TryGetValue<float>(out var single) && !float.IsFinite(single));
        void Walk(JsonNode? value, string path)
        {
            if (value is JsonObject obj)
            {
                foreach (var field in obj.ToArray())
                {
                    var next = path + "/" + field.Key.Replace("~", "~0").Replace("/", "~1");
                    if (Invalid(field.Value)) Missing(obj, field.Key, (JsonValue)field.Value!, next);
                    else Walk(field.Value, next);
                }
            }
            else if (value is JsonArray array)
            {
                for (var index = 0; index < array.Count; index++)
                {
                    var key = index.ToString(CultureInfo.InvariantCulture); var next = path + "/" + key;
                    if (Invalid(array[index])) Missing(array, key, (JsonValue)array[index]!, next);
                    else Walk(array[index], next);
                }
            }
        }
        Walk(result, "");
        result["nonfinite_measurements"] = invalid;
    }
}
