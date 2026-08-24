namespace WukongStudio.Core;

public sealed record ContentSyncFolderSelection(
    string SelectedFolder,
    string PackRoot,
    string PackId);

public static class ContentSyncFolderResolver
{
    private static readonly System.Text.RegularExpressions.Regex ModPackName = new(
        "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
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

    public static bool IsValidModPackName(string? value) =>
        !string.IsNullOrWhiteSpace(value) && ModPackName.IsMatch(value.Trim());

    /// <summary>Renames only a direct Content/MOD pack, never an arbitrary selected child.</summary>
    public static ContentSyncFolderSelection RenameModPack(
        string installRoot,
        ContentSyncFolderSelection selection,
        string requestedName)
    {
        if (!selection.PackId.StartsWith("MOD/", StringComparison.Ordinal)
            || !IsValidModPackName(requestedName))
        {
            throw new InvalidOperationException("MOD pack name must contain only letters, digits, dot, dash, or underscore.");
        }
        var targetName = requestedName.Trim();
        var currentName = selection.PackId[4..];
        if (string.Equals(currentName, targetName, StringComparison.OrdinalIgnoreCase))
        {
            return selection;
        }
        var modRoot = Path.GetFullPath(Path.Combine(Path.GetFullPath(installRoot), "Content", "MOD"));
        var target = Path.GetFullPath(Path.Combine(modRoot, targetName));
        if (!IsWithin(target, modRoot) || Directory.Exists(target) || File.Exists(target))
        {
            throw new IOException($"MOD pack already exists: {targetName}");
        }
        Directory.Move(selection.PackRoot, target);
        return Resolve(installRoot, target);
    }

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
