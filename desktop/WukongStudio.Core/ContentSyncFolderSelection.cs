namespace WukongStudio.Core;

public sealed record ContentSyncFolderSelection(
    string SelectedFolder,
    string PackRoot,
    string PackId);

public static class ContentSyncFolderResolver
{
    private static readonly System.Text.RegularExpressions.Regex ReleaseLabel = new(
        "^[^/\\\\\\x00-\\x1f]{1,64}$",
        System.Text.RegularExpressions.RegexOptions.CultureInvariant);
    private static readonly (string RelativePath, string PackId)[] FixedPacks =
    [
        (Path.Combine("Content", "STARK"), "STARK/common"),
        (Path.Combine("Content", "Flash_script"), "Flash_script/common"),
        (Path.Combine("Content", "copy-image"), "copy-image/v1"),
        (Path.Combine("Content", "OFX"), "OFX/v1"),
        (Path.Combine("Content", "TWRP"), "TWRP/v1"),
    ];

    public static ContentSyncFolderSelection Resolve(string installRoot, string selectedFolder)
    {
        var install = Path.GetFullPath(installRoot);
        var selected = Path.GetFullPath(selectedFolder);
        if (!Directory.Exists(selected))
        {
            throw new DirectoryNotFoundException($"Selected sync folder does not exist: {selected}");
        }

        foreach (var (relativePath, packId) in FixedPacks)
        {
            var packRoot = Path.GetFullPath(Path.Combine(install, relativePath));
            if (Directory.Exists(packRoot) && IsWithin(selected, packRoot))
            {
                return new ContentSyncFolderSelection(selected, packRoot, packId);
            }
        }

        var modRoot = Path.GetFullPath(Path.Combine(install, "Content", "MOD"));
        if (Directory.Exists(modRoot) && IsWithin(selected, modRoot) && !PathsEqual(selected, modRoot))
        {
            var relative = Path.GetRelativePath(modRoot, selected);
            var version = relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)[0];
            var packRoot = Path.Combine(modRoot, version);
            if (Directory.Exists(packRoot))
            {
                return new ContentSyncFolderSelection(selected, packRoot, $"MOD/{version}");
            }
        }

        throw new InvalidOperationException(
            "Folder is not managed by content sync. Choose Content\\STARK, Content\\Flash_script, " +
            "Content\\MOD\\<version>, Content\\copy-image, Content\\OFX, or Content\\TWRP.");
    }

    /// <summary>
    /// Validates a human-facing MOD release label. It is intentionally separate
    /// from a MOD pack directory name: labels such as V5.0 or a custom name
    /// must never rename Content/MOD/ColorOS_* folders.
    /// </summary>
    public static bool IsValidReleaseLabel(string? value) =>
        !string.IsNullOrWhiteSpace(value) && ReleaseLabel.IsMatch(value.Trim());

    private static bool IsWithin(string path, string root) =>
        PathsEqual(path, root)
        || path.StartsWith(Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar,
            StringComparison.OrdinalIgnoreCase);

    private static bool PathsEqual(string left, string right) =>
        string.Equals(
            Path.TrimEndingDirectorySeparator(left),
            Path.TrimEndingDirectorySeparator(right),
            StringComparison.OrdinalIgnoreCase);
}
