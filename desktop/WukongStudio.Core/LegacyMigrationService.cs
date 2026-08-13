using System.Security.Cryptography;

namespace WukongStudio.Core;

public sealed record LegacyMigrationItem(string SourceName, string TargetRelativePath);

public sealed record LegacyMigrationProgress(string Item, long FilesCompleted, long TotalFiles);

public sealed record LegacyMigrationResult(IReadOnlyList<string> ImportedTargets, IReadOnlyList<string> Backups);

public sealed class LegacyMigrationService(StudioLayout layout)
{
    public static IReadOnlyList<LegacyMigrationItem> DefaultItems { get; } =
    [
        new("MOD", "MOD"),
        new("TWRP", "TWRP"),
        new("OFX", "OFX"),
        new("copy-image", "copy-image"),
    ];

    public async Task<LegacyMigrationResult> ImportAsync(
        string legacyRoot,
        IEnumerable<LegacyMigrationItem> items,
        bool deleteSourceAfterImport = false,
        IProgress<LegacyMigrationProgress>? progress = null,
        CancellationToken cancellationToken = default)
    {
        layout.EnsureWritableDirectories();
        var sourceRoot = Path.GetFullPath(legacyRoot);
        if (!Directory.Exists(sourceRoot))
        {
            throw new DirectoryNotFoundException($"Legacy project was not found: {sourceRoot}");
        }

        var selected = items.ToArray();
        if (selected.Length == 0)
        {
            return new LegacyMigrationResult([], []);
        }

        var staging = Path.Combine(layout.ExtractionRoot, $"migration-{Guid.NewGuid():N}");
        Directory.CreateDirectory(staging);
        var imported = new List<string>();
        var backups = new List<string>();
        try
        {
            foreach (var item in selected)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var source = SafeLegacyChild(sourceRoot, item.SourceName);
                if (!Directory.Exists(source))
                {
                    continue;
                }
                RejectReparsePoints(source);
                var staged = ContentPackService.SafeCombine(staging, item.TargetRelativePath);
                var sourceFiles = Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories).ToArray();
                await CopyAndVerifyAsync(source, staged, sourceFiles, item.SourceName, progress, cancellationToken);
            }

            foreach (var item in selected)
            {
                var staged = ContentPackService.SafeCombine(staging, item.TargetRelativePath);
                if (!Directory.Exists(staged))
                {
                    continue;
                }
                var target = ContentPackService.SafeCombine(layout.ContentRoot, item.TargetRelativePath);
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                string? backup = null;
                if (Directory.Exists(target))
                {
                    backup = Path.Combine(
                        layout.BackupsRoot,
                        "LegacyMigration",
                        item.SourceName,
                        DateTime.UtcNow.ToString("yyyyMMdd-HHmmssfff"));
                    Directory.CreateDirectory(Path.GetDirectoryName(backup)!);
                    Directory.Move(target, backup);
                }
                try
                {
                    Directory.Move(staged, target);
                    imported.Add(target);
                    if (backup is not null)
                    {
                        backups.Add(backup);
                    }
                }
                catch
                {
                    if (Directory.Exists(target))
                    {
                        Directory.Delete(target, recursive: true);
                    }
                    if (backup is not null && Directory.Exists(backup))
                    {
                        Directory.Move(backup, target);
                    }
                    throw;
                }
            }

            if (deleteSourceAfterImport)
            {
                foreach (var item in selected)
                {
                    var source = SafeLegacyChild(sourceRoot, item.SourceName);
                    if (Directory.Exists(source) && imported.Any(path =>
                        path.Equals(ContentPackService.SafeCombine(layout.ContentRoot, item.TargetRelativePath), StringComparison.OrdinalIgnoreCase)))
                    {
                        Directory.Delete(source, recursive: true);
                    }
                }
            }
            return new LegacyMigrationResult(imported, backups);
        }
        finally
        {
            if (Directory.Exists(staging))
            {
                Directory.Delete(staging, recursive: true);
            }
        }
    }

    private static async Task CopyAndVerifyAsync(
        string sourceRoot,
        string targetRoot,
        IReadOnlyList<string> sourceFiles,
        string itemName,
        IProgress<LegacyMigrationProgress>? progress,
        CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(targetRoot);
        long completed = 0;
        foreach (var source in sourceFiles)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var relative = Path.GetRelativePath(sourceRoot, source);
            var target = ContentPackService.SafeCombine(targetRoot, relative.Replace('\\', '/'));
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(source, target, overwrite: false);
            var sourceInfo = new FileInfo(source);
            var targetInfo = new FileInfo(target);
            if (sourceInfo.Length != targetInfo.Length
                || !await FilesMatchAsync(source, target, cancellationToken))
            {
                throw new IOException($"Migration validation failed: {relative}");
            }
            completed++;
            progress?.Report(new LegacyMigrationProgress(itemName, completed, sourceFiles.Count));
        }
    }

    private static async Task<bool> FilesMatchAsync(string source, string target, CancellationToken cancellationToken)
    {
        await using var sourceStream = File.OpenRead(source);
        await using var targetStream = File.OpenRead(target);
        var sourceHash = await SHA256.HashDataAsync(sourceStream, cancellationToken);
        var targetHash = await SHA256.HashDataAsync(targetStream, cancellationToken);
        return sourceHash.AsSpan().SequenceEqual(targetHash);
    }

    private static string SafeLegacyChild(string root, string relative)
    {
        if (Path.IsPathRooted(relative) || relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Any(part => part == ".."))
        {
            throw new InvalidDataException($"Unsafe migration path: {relative}");
        }
        var rootFull = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var candidate = Path.GetFullPath(Path.Combine(rootFull, relative));
        if (!candidate.StartsWith(rootFull + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"Migration path escapes legacy root: {relative}");
        }
        return candidate;
    }

    private static void RejectReparsePoints(string root)
    {
        foreach (var path in Directory.EnumerateFileSystemEntries(root, "*", SearchOption.AllDirectories).Prepend(root))
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException($"Legacy content contains a junction or symbolic link: {path}");
            }
        }
    }
}
