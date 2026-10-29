using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using Relic.Core;
using Xunit;

public class HttpFramingTests
{
    [Fact]
    public async Task JsonPostThenGetShareOneCorrectlyFramedConnection()
    {
        // CI only in this workspace. No Relic server or child program is started.
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        var server = Task.Run(async () =>
        {
            using var peer = await listener.AcceptTcpClientAsync(timeout.Token);
            using var stream = peer.GetStream();
            async Task<string> Line()
            {
                var bytes = new List<byte>(); var one = new byte[1];
                while (await stream.ReadAsync(one, timeout.Token) == 1)
                {
                    if (one[0] == '\n') return Encoding.ASCII.GetString(bytes.ToArray()).TrimEnd('\r');
                    bytes.Add(one[0]);
                }
                throw new EndOfStreamException();
            }
            for (var request = 0; request < 2; request++)
            {
                Assert.Equal(request == 0 ? "POST /api/prefs HTTP/1.1" : "GET /api/prefs HTTP/1.1", await Line());
                var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                for (var line = await Line(); line.Length > 0; line = await Line())
                {
                    var split = line.IndexOf(':'); headers[line[..split]] = line[(split + 1)..].Trim();
                }
                Assert.Equal("fixture-token", headers["X-Relic-Token"]);
                Assert.False(headers.ContainsKey("Transfer-Encoding"));
                if (request == 0)
                {
                    Assert.StartsWith("application/json", headers["Content-Type"]);
                    var bytes = new byte[int.Parse(headers["Content-Length"])];
                    await stream.ReadExactlyAsync(bytes, timeout.Token);
                    var body = JsonNode.Parse(bytes)!;
                    Assert.Equal("zh-CN", body.Text("lang")); Assert.Equal("你好", body.Text("personName"));
                }
                var response = Encoding.UTF8.GetBytes("{\"lang\":\"zh-CN\"}");
                await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {response.Length}\r\n\r\n"), timeout.Token);
                await stream.WriteAsync(response, timeout.Token);
            }
        }, timeout.Token);
        using var client = new Client(port, "fixture-token");
        var requests = Task.Run(async () =>
        {
            Assert.Equal("zh-CN", (await client.Post("/api/prefs", new { Lang = "zh-CN", PersonName = "你好" }, timeout.Token)).Text("lang"));
            Assert.Equal("zh-CN", (await client.Get("/api/prefs", timeout.Token)).Text("lang"));
        }, timeout.Token);
        await Task.WhenAll(server, requests);
    }
}
