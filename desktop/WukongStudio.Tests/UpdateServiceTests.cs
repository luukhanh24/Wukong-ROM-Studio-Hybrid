using System.Security.Cryptography;
using System.Net;
using System.Text;
using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class UpdateServiceTests
{
    [Fact]
    public void ManifestRequiresHttps()
    {
        const string json = """
        {"version":"1.1.0","url":"http://example.com/update.exe","size":10,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        """;
        Assert.Throws<InvalidDataException>(() => UpdateService.ParseManifest(json));
    }

    [Fact]
    public async Task PackageValidationChecksSizeAndHash()
    {
        using var workspace = new TestWorkspace();
        var path = Path.Combine(workspace.Root, "update.exe");
        var bytes = "update"u8.ToArray();
        await File.WriteAllBytesAsync(path, bytes);
        var manifest = new StudioUpdateManifest(
            "1.1.0",
            "https://example.com/update.exe",
            bytes.Length,
            Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant());
        await UpdateService.ValidatePackageAsync(path, manifest);
    }

    [Fact]
    public async Task DownloadsManifestOnlyFromHttps()
    {
        using var workspace = new TestWorkspace();
        var json = """
        {"version":"1.1.0","url":"https://example.com/update.exe","size":10,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
        """;
        using var client = new HttpClient(new StaticResponseHandler(json));
        using var service = new UpdateService(workspace.Layout, client);
        var manifest = await service.GetManifestAsync(new Uri("https://example.com/update.json"));
        Assert.Equal("1.1.0", manifest.Version);
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            service.GetManifestAsync(new Uri("http://example.com/update.json")));
    }

    private sealed class StaticResponseHandler(string content) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(content, Encoding.UTF8, "application/json"),
        });
    }
}
