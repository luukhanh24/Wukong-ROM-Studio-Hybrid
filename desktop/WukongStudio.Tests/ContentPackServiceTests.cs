using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class ContentPackServiceTests
{
    [Fact]
    public async Task InstallsValidatedPackAndRecordsRegistry()
    {
        using var workspace = new TestWorkspace();
        var content = "hello pack"u8.ToArray();
        var package = CreatePack(workspace.Root, "MOD/Test/data.txt", content);
        var service = new ContentPackService(workspace.Layout);

        var result = await service.InstallAsync(package, new Version(1, 0, 0));

        Assert.Equal("hello pack", File.ReadAllText(Path.Combine(result.TargetPath, "data.txt")));
        Assert.Single(service.LoadRegistry());
    }

    [Fact]
    public async Task RejectsTraversalEntry()
    {
        using var workspace = new TestWorkspace();
        var package = CreatePack(workspace.Root, "MOD/Test/data.txt", "ok"u8.ToArray(), archive =>
        {
            using var writer = new StreamWriter(archive.CreateEntry("../escape.txt").Open());
            writer.Write("blocked");
        });
        var service = new ContentPackService(workspace.Layout);
        await Assert.ThrowsAsync<InvalidDataException>(() => service.InstallAsync(package, new Version(1, 0, 0)));
        Assert.False(File.Exists(Path.Combine(workspace.Root, "escape.txt")));
    }

    [Fact]
    public async Task RejectsHashMismatchWithoutActivatingTarget()
    {
        using var workspace = new TestWorkspace();
        var package = CreatePack(workspace.Root, "MOD/Test/data.txt", "actual"u8.ToArray(), declaredHash: new string('0', 64));
        var service = new ContentPackService(workspace.Layout);
        await Assert.ThrowsAsync<InvalidDataException>(() => service.InstallAsync(package, new Version(1, 0, 0)));
        Assert.False(Directory.Exists(Path.Combine(workspace.Layout.ContentRoot, "MOD", "Test")));
    }

    private static string CreatePack(
        string root,
        string path,
        byte[] content,
        Action<ZipArchive>? append = null,
        string? declaredHash = null)
    {
        var package = Path.Combine(root, $"pack-{Guid.NewGuid():N}.zip");
        using var archive = ZipFile.Open(package, ZipArchiveMode.Create);
        var file = archive.CreateEntry(path);
        using (var stream = file.Open())
        {
            stream.Write(content);
        }
        var manifest = new ContentPackManifest(
            1,
            "test-pack",
            "Test Pack",
            "2026.07.1",
            "1.0.0",
            "mod-version",
            "MOD/Test",
            [new ContentPackFile(path, content.Length, declaredHash ?? Convert.ToHexString(SHA256.HashData(content)).ToLowerInvariant())]);
        using (var writer = new StreamWriter(archive.CreateEntry(ContentPackService.ManifestName).Open()))
        {
            writer.Write(JsonSerializer.Serialize(manifest, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            }));
        }
        append?.Invoke(archive);
        return package;
    }
}
