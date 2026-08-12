using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;

namespace WukongStudio.Core;

public sealed record ContentPackFile(string Path, long Size, string Sha256);

public sealed record ContentPackManifest(
    int SchemaVersion,
    string Id,
    string DisplayName,
    string Version,
    string MinStudioVersion,
    string Type,
    string Target,
    IReadOnlyList<ContentPackFile> Files);

public sealed record InstalledContentPack(
    string Id,
    string DisplayName,
    string Version,
    string Target,
    DateTimeOffset InstalledAt,
    string SourceSha256);

public sealed record ContentPackInstallResult(ContentPackManifest Manifest, string TargetPath, string? BackupPath);

public sealed class ContentPackService(StudioLayout layout)
{
    public const string ManifestName = "content-pack.json";
    private readonly string _registryPath = layout.ContentPacksPath;

    public async Task<ContentPackInstallResult> InstallAsync(
        string packagePath,
        Version studioVersion,
        CancellationToken cancellationToken = default)
    {
        layout.EnsureWritableDirectories();
        var package = Path.GetFullPath(packagePath);
        if (!File.Exists(package))
        {
            throw new FileNotFoundException("Content pack ZIP was not found.", package);
        }

        var stagingRoot = Path.Combine(layout.ExtractionRoot, $"pack-{Guid.NewGuid():N}");
        Directory.CreateDirectory(stagingRoot);
        string? backupPath = null;
        string? activatedPath = null;
        try
        {
            using var archive = ZipFile.OpenRead(package);
            var manifest = ReadManifest(archive);
            ValidateManifest(manifest, studioVersion);
            EnsureTargetOwnership(manifest);
            ExtractValidated(archive, stagingRoot, cancellationToken);
            await ValidateExtractedFilesAsync(manifest, stagingRoot, cancellationToken);

            var stagedTarget = SafeCombine(stagingRoot, NormalizeRelativePath(manifest.Target));
            var targetPath = SafeCombine(layout.ContentRoot, NormalizeRelativePath(manifest.Target));
            if (!Directory.Exists(stagedTarget))
            {
                throw new InvalidDataException($"Content pack target is missing: {manifest.Target}");
            }

            Directory.CreateDirectory(Path.GetDirectoryName(targetPath)!);
            if (Directory.Exists(targetPath))
            {
                backupPath = Path.Combine(
                    layout.BackupsRoot,
                    "ContentPacks",
                    manifest.Id,
                    DateTime.UtcNow.ToString("yyyyMMdd-HHmmssfff"));
                Directory.CreateDirectory(Path.GetDirectoryName(backupPath)!);
                Directory.Move(targetPath, backupPath);
            }

            try
            {
                Directory.Move(stagedTarget, targetPath);
                activatedPath = targetPath;
                var installed = LoadRegistry()
                    .Where(item => !item.Id.Equals(manifest.Id, StringComparison.OrdinalIgnoreCase))
                    .ToList();
                installed.Add(new InstalledContentPack(
                    manifest.Id,
                    manifest.DisplayName,
                    manifest.Version,
                    manifest.Target,
                    DateTimeOffset.UtcNow,
                    await ComputeSha256Async(package, cancellationToken)));
                AtomicFile.WriteJson(_registryPath, installed.OrderBy(item => item.Id).ToArray());
            }
            catch
            {
                if (activatedPath is not null && Directory.Exists(activatedPath))
                {
                    Directory.Delete(activatedPath, recursive: true);
                }
                if (backupPath is not null && Directory.Exists(backupPath))
                {
                    Directory.Move(backupPath, targetPath);
                }
                throw;
            }

            return new ContentPackInstallResult(manifest, targetPath, backupPath);
        }
        finally
        {
            if (Directory.Exists(stagingRoot))
            {
                Directory.Delete(stagingRoot, recursive: true);
            }
        }
    }

    public IReadOnlyList<InstalledContentPack> LoadRegistry()
    {
        if (!File.Exists(_registryPath))
        {
            return [];
        }
        try
        {
            return JsonSerializer.Deserialize<List<InstalledContentPack>>(
                File.ReadAllText(_registryPath),
                JsonOptions) ?? [];
        }
        catch (JsonException)
        {
            var corrupt = _registryPath + $".corrupt-{DateTime.UtcNow:yyyyMMddHHmmss}";
            File.Move(_registryPath, corrupt, overwrite: false);
            return [];
        }
    }

    private ContentPackManifest ReadManifest(ZipArchive archive)
    {
        var entries = archive.Entries.Where(entry =>
            NormalizeRelativePath(entry.FullName).Equals(ManifestName, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (entries.Length != 1)
        {
            throw new InvalidDataException($"Content pack must contain exactly one root {ManifestName}.");
        }
        using var stream = entries[0].Open();
        return JsonSerializer.Deserialize<ContentPackManifest>(stream, JsonOptions)
            ?? throw new InvalidDataException("Content pack manifest is empty.");
    }

    private static void ValidateManifest(ContentPackManifest manifest, Version studioVersion)
    {
        if (manifest.SchemaVersion != 1)
        {
            throw new InvalidDataException($"Unsupported content pack schema: {manifest.SchemaVersion}");
        }
        if (string.IsNullOrWhiteSpace(manifest.Id)
            || manifest.Id.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not '-' and not '_'))
        {
            throw new InvalidDataException("Content pack ID is invalid.");
        }
        if (!Version.TryParse(manifest.MinStudioVersion, out var minimum) || studioVersion < minimum)
        {
            throw new InvalidDataException($"Content pack requires Wukong Studio {manifest.MinStudioVersion} or newer.");
        }
        var target = NormalizeRelativePath(manifest.Target);
        if (target.Length == 0 || target.Equals(".", StringComparison.Ordinal))
        {
            throw new InvalidDataException("Content pack target is invalid.");
        }
        if (manifest.Files.Count == 0)
        {
            throw new InvalidDataException("Content pack does not contain any declared files.");
        }

        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in manifest.Files)
        {
            var relative = NormalizeRelativePath(file.Path);
            if (!IsPathWithin(relative, target))
            {
                throw new InvalidDataException($"Content pack file is outside target '{target}': {file.Path}");
            }
            if (!paths.Add(relative))
            {
                throw new InvalidDataException($"Content pack declares a duplicate file: {file.Path}");
            }
            if (file.Size < 0 || file.Sha256.Length != 64 || !file.Sha256.All(Uri.IsHexDigit))
            {
                throw new InvalidDataException($"Content pack metadata is invalid for: {file.Path}");
            }
        }
    }

    private void EnsureTargetOwnership(ContentPackManifest manifest)
    {
        var target = NormalizeRelativePath(manifest.Target);
        foreach (var installed in LoadRegistry())
        {
            if (installed.Id.Equals(manifest.Id, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            var owned = NormalizeRelativePath(installed.Target);
            if (IsPathWithin(target, owned) || IsPathWithin(owned, target))
            {
                throw new InvalidDataException(
                    $"Content pack target conflicts with installed pack '{installed.DisplayName}'.");
            }
        }
    }

    private static void ExtractValidated(ZipArchive archive, string stagingRoot, CancellationToken cancellationToken)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in archive.Entries)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var relative = NormalizeRelativePath(entry.FullName);
            if (relative.Equals(ManifestName, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            if (relative.Length == 0)
            {
                continue;
            }
            if (IsUnixSymlink(entry))
            {
                throw new InvalidDataException($"Content pack contains a symbolic link: {entry.FullName}");
            }
            if (!seen.Add(relative))
            {
                throw new InvalidDataException($"Content pack contains a duplicate path: {entry.FullName}");
            }

            var destination = SafeCombine(stagingRoot, relative);
            if (entry.FullName.EndsWith('/') || entry.FullName.EndsWith('\\'))
            {
                Directory.CreateDirectory(destination);
                continue;
            }
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            using var input = entry.Open();
            using var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            input.CopyTo(output);
        }
    }

    private static async Task ValidateExtractedFilesAsync(
        ContentPackManifest manifest,
        string stagingRoot,
        CancellationToken cancellationToken)
    {
        var expected = manifest.Files.ToDictionary(
            file => NormalizeRelativePath(file.Path),
            StringComparer.OrdinalIgnoreCase);
        var actualFiles = Directory.EnumerateFiles(stagingRoot, "*", SearchOption.AllDirectories)
            .Select(path => Path.GetRelativePath(stagingRoot, path).Replace('\\', '/'))
            .ToArray();
        if (actualFiles.Length != expected.Count || actualFiles.Any(path => !expected.ContainsKey(path)))
        {
            throw new InvalidDataException("Content pack files do not match the manifest.");
        }

        foreach (var pair in expected)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var path = SafeCombine(stagingRoot, pair.Key);
            var info = new FileInfo(path);
            if (info.Length != pair.Value.Size)
            {
                throw new InvalidDataException($"Content pack size mismatch: {pair.Key}");
            }
            var hash = await ComputeSha256Async(path, cancellationToken);
            if (!hash.Equals(pair.Value.Sha256, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"Content pack SHA-256 mismatch: {pair.Key}");
            }
        }
    }

    internal static string NormalizeRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Path.IsPathRooted(path))
        {
            throw new InvalidDataException($"Absolute or empty archive path is not allowed: {path}");
        }
        var normalized = path.Replace('\\', '/').Trim('/');
        var parts = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Any(part => part is "." or ".." || part.Contains(':')))
        {
            throw new InvalidDataException($"Unsafe archive path: {path}");
        }
        return string.Join('/', parts);
    }

    internal static string SafeCombine(string root, string relative)
    {
        var rootFull = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var candidate = Path.GetFullPath(Path.Combine(rootFull, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!candidate.StartsWith(rootFull + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"Path escapes managed root: {relative}");
        }
        return candidate;
    }

    private static bool IsPathWithin(string candidate, string root) =>
        candidate.Equals(root, StringComparison.OrdinalIgnoreCase)
        || candidate.StartsWith(root.TrimEnd('/') + '/', StringComparison.OrdinalIgnoreCase);

    private static bool IsUnixSymlink(ZipArchiveEntry entry) =>
        ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000;

    internal static async Task<string> ComputeSha256Async(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024, true);
        var hash = await SHA256.HashDataAsync(stream, cancellationToken);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };
}
