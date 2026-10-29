using System.Diagnostics;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace Relic.Core;

public static class Json
{
    public static string Text(this JsonNode? node, string key = "") =>
        (key.Length == 0 ? node : node?[key])?.ToString() ?? "";
    public static JsonArray Rows(this JsonNode? node, string key = "") =>
        (key.Length == 0 ? node : node?[key]) as JsonArray ?? new();
    public static bool Flag(this JsonNode? node, string key) => node?[key]?.ToString() == "true";
}

public sealed class Client : IDisposable
{
    private readonly HttpClient http;
    public Client(int port, string token, HttpMessageHandler? handler = null)
    {
        if (port is < 1 or > 65535 || string.IsNullOrWhiteSpace(token)) throw new ArgumentException("Invalid server record");
        http = new HttpClient(handler ?? new SocketsHttpHandler { UseProxy = false })
        { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(30) };
        http.DefaultRequestHeaders.Add("X-Relic-Token", token);
    }
    public static string Segment(string value) => Uri.EscapeDataString(value);
    public static string Org(string id, string action = "") => "/api/org/" + Segment(id) + action;
    public async Task<JsonNode> Get(string path, CancellationToken ct = default)
    {
        using var response = await http.GetAsync(path, ct);
        return await Decode(response, ct);
    }
    public async Task<JsonNode> Post(string path, object body, CancellationToken ct = default)
    {
        using var response = await http.PostAsJsonAsync(path, body, ct);
        return await Decode(response, ct);
    }
    private static async Task<JsonNode> Decode(HttpResponseMessage response, CancellationToken ct)
    {
        var value = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct)) ?? new JsonObject();
        if (!response.IsSuccessStatusCode) throw new HttpRequestException(value.Text("error"), null, response.StatusCode);
        return value;
    }
    public async Task Events(Func<JsonNode, Task> receive, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var response = await http.GetAsync("/api/events", HttpCompletionOption.ResponseHeadersRead, ct);
                response.EnsureSuccessStatusCode();
                using var stream = await response.Content.ReadAsStreamAsync(ct);
                using var reader = new StreamReader(stream);
                var frame = new List<string>();
                while (await reader.ReadLineAsync(ct) is { } line)
                {
                    if (line.StartsWith("data:")) frame.Add(line[5..].TrimStart());
                    if (line.Length == 0 && frame.Count > 0)
                    {
                        var item = JsonNode.Parse(string.Join("\n", frame)); frame.Clear();
                        if (item != null) await receive(item);
                    }
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (Exception error) when (error is HttpRequestException or IOException or System.Text.Json.JsonException) { }
            await Task.Delay(1500, ct);
            // SSE is a hint, not a durable log. Refetch after every reconnect.
            await receive(new JsonObject { ["type"] = "reconnect" });
        }
    }
    public void Dispose() => http.Dispose();
}

public sealed class Words
{
    public string Language { get; private set; } = "en-US";
    private JsonNode strings = new JsonObject();
    public static string Normalize(string? language) => (language ?? "").StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-CN" : "en-US";
    public void Load(JsonNode response) { Language = Normalize(response.Text("lang")); strings = response["strings"]?.DeepClone() ?? new JsonObject(); }
    public string T(string key, params (string, object)[] args)
    {
        var value = strings[key];
        if (value is JsonObject)
        {
            var one = Language == "en-US" && args.Any(a => a.Item1 == "n" && a.Item2.ToString() == "1");
            value = value[one ? "one" : "other"];
        }
        var text = value?.ToString() ?? key;
        foreach (var (name, arg) in args) text = text.Replace("{" + name + "}", arg.ToString());
        return text;
    }
}

public static class Composer
{
    public static object Message(string body, string member, IEnumerable<string> selected, JsonArray members)
    {
        var to = selected.ToArray();
        if (member.Length > 0) to = [member];
        else if (to.Length == 0 || to.Contains("all"))
        {
            to = members.Where(m => body.Contains("@" + m.Text("name")) ||
                (m.Text("display").Length > 0 && body.Contains("@" + m.Text("display"))))
                .Select(m => m.Text("name")).ToArray();
            if (to.Length == 0) to = ["all"];
        }
        return new { body, to, channel = member.Length == 0 ? "group" : "private" };
    }
}

public sealed class ServerHost : IAsyncDisposable
{
    private Process? process;
    private Task<string>? errors;
    public async Task<Client> Start(string root, string python)
    {
        var entry = Path.Combine(root, "plugins", "relic", "scripts", "native_host.py");
        if (!File.Exists(entry)) throw new FileNotFoundException("Relic engine not found", entry);
        var start = new ProcessStartInfo(python)
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
          RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = root };
        foreach (var arg in new[] { "-X", "utf8", entry }) start.ArgumentList.Add(arg);
        process = Process.Start(start) ?? throw new IOException("Could not start Relic");
        errors = process.StandardError.ReadToEndAsync();
        try
        {
            var line = await process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(35));
            if (line == null) throw new IOException(await errors);
            var info = JsonNode.Parse(line)!;
            var client = new Client(int.Parse(info.Text("port")), info.Text("token"));
            var live = await client.Get("/api/lifecycle");
            if (live.Text("instance") != info.Text("instance") || live.Text("pid") != info.Text("pid"))
            { client.Dispose(); throw new IOException("Relic instance changed during startup"); }
            return client;
        }
        catch { await DisposeAsync(); throw; }
    }
    public async ValueTask DisposeAsync()
    {
        if (process == null) return;
        process.StandardInput.Close();
        try { await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(30)); }
        catch (TimeoutException) { /* Host retains ownership until engine cleanup completes. */ }
        process.Dispose(); process = null;
    }
}
