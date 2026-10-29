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
    private HttpClient http;
    private readonly HttpMessageHandler? handler;
    private readonly Func<JsonNode?>? serverRecord;
    private readonly SemaphoreSlim renew = new(1, 1);
    private readonly List<HttpClient> retired = new();
    private string identity;
    public Client(int port, string token, HttpMessageHandler? handler = null, Func<JsonNode?>? serverRecord = null)
    {
        this.handler = handler; this.serverRecord = serverRecord; identity = port + ":" + token;
        http = Connection(port, token);
    }
    private HttpClient Connection(int port, string token)
    {
        if (port is < 1 or > 65535 || string.IsNullOrWhiteSpace(token)) throw new ArgumentException("Invalid server record");
        var client = new HttpClient(handler ?? new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false }, handler == null)
        { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(30) };
        client.DefaultRequestHeaders.Add("X-Relic-Token", token); return client;
    }
    private async Task<bool> RefreshRecord(CancellationToken ct)
    {
        if (serverRecord == null) return false;
        await renew.WaitAsync(ct);
        try
        {
            var record = serverRecord();
            if (!int.TryParse(record.Text("port"), out var port) || port is < 1 or > 65535 || record.Text("token").Length == 0
                || !int.TryParse(record.Text("pid"), out var pid) || pid <= 0 || record.Text("instance").Length == 0) return false;
            var next = port + ":" + record.Text("token"); if (next == identity) return false;
            var candidate = Connection(port, record.Text("token"));
            try
            {
                using var response = await candidate.GetAsync("/api/lifecycle", ct); var live = await Decode(response, ct);
                if (live.Text("app") != "relic" || live.Text("state") != "running" || live.Text("pid") != record.Text("pid") || live.Text("instance") != record.Text("instance")) throw new IOException("Relic instance changed");
                retired.Add(http); http = candidate; identity = next; return true;
            }
            catch { candidate.Dispose(); return false; }
        }
        catch (Exception error) when (error is IOException or System.Text.Json.JsonException or UnauthorizedAccessException) { return false; }
        finally { renew.Release(); }
    }
    public static string Segment(string value) => Uri.EscapeDataString(value);
    public static string Org(string id, string action = "") => "/api/org/" + Segment(id) + action;
    public async Task<JsonNode> Get(string path, CancellationToken ct = default)
    {
        var connection = http;
        try { using var response = await connection.GetAsync(path, ct); return await Decode(response, ct); }
        catch (HttpRequestException) { if (!await RefreshRecord(ct) && ReferenceEquals(connection, http)) throw; using var retry = await http.GetAsync(path, ct); return await Decode(retry, ct); }
    }
    public async Task<JsonNode> Post(string path, object body, CancellationToken ct = default)
    {
        var connection = http;
        using var response = await connection.PostAsJsonAsync(path, body, ct);
        try { return await Decode(response, ct); }
        catch (HttpRequestException error) when (error.StatusCode == System.Net.HttpStatusCode.Forbidden && error.Message == "missing token")
        {
            if (!await RefreshRecord(ct) && ReferenceEquals(connection, http)) throw;
            using var retry = await http.PostAsJsonAsync(path, body, ct); return await Decode(retry, ct);
        }
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
            await RefreshRecord(ct);
            // SSE is a hint, not a durable log. Refetch after every reconnect.
            await receive(new JsonObject { ["type"] = "reconnect" });
        }
    }
    public void Dispose() { http.Dispose(); foreach (var client in retired) client.Dispose(); renew.Dispose(); }
}

public sealed class Words
{
    public string Language { get; private set; } = "en-US";
    public JsonArray Languages { get; private set; } = new();
    private JsonNode strings = new JsonObject();
    public static string Normalize(string? language) => (language ?? "").StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh-CN" : "en-US";
    public void Load(JsonNode response) { Language = Normalize(response.Text("lang")); strings = response["strings"]?.DeepClone() ?? new JsonObject(); Languages = response["languages"]?.DeepClone() as JsonArray ?? new JsonArray(); }
    public string T(string key, params (string, object)[] args)
    {
        var value = strings[key];
        if (value is JsonObject)
        {
            var one = Language == "en-US" && args.Any(a => a.Item1 == "n" && a.Item2.ToString() == "1");
            value = value[one ? "one" : "other"];
        }
        // A missing translation must never become a technical key in the UI.
        // CI checks every native key against both shared word lists.
        var text = value?.ToString() ?? "";
        foreach (var (name, arg) in args) text = text.Replace("{" + name + "}", arg.ToString());
        return text;
    }
    public string List(IEnumerable<string> values)
    {
        var items = values.ToArray(); if (items.Length == 0) return ""; if (items.Length == 1) return items[0];
        if (items.Length == 2) return T("list.pair", ("a", items[0]), ("b", items[1]));
        var joined = items[0];
        for (int i = 1; i < items.Length; i++) joined = T(i == items.Length - 1 ? "list.end" : "list.middle", ("a", joined), ("b", items[i]));
        return joined;
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
            JsonNode? SavedRecord()
            {
                var home = Environment.GetEnvironmentVariable("RELIC_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".relic");
                return JsonNode.Parse(File.ReadAllText(Path.Combine(home, "app.json")));
            }
            var client = new Client(int.Parse(info.Text("port")), info.Text("token"), serverRecord: SavedRecord);
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
