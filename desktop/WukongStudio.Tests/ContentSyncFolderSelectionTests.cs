using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class ContentSyncFolderSelectionTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"wukong-folder-sync-{Guid.NewGuid():N}");

    [Theory]
    [InlineData("WK_Manager")]
    [InlineData("com")]
    public void ResolvesStarkChildToCompleteContentStarkPack(string child)
    {
        var packRoot = Path.Combine(_root, "Content", "STARK");
        var selected = Path.Combine(packRoot, child);
        Directory.CreateDirectory(selected);

        var result = ContentSyncFolderResolver.Resolve(_root, selected);

        Assert.Equal("STARK/common", result.PackId);
        Assert.Equal(Path.GetFullPath(packRoot), result.PackRoot);
        Assert.Equal(Path.GetFullPath(selected), result.SelectedFolder);
    }

    [Fact]
    public void RejectsRuntimeStarkAsNonCanonical()
    {
        var selected = Path.Combine(_root, "Runtime", "STARK", "WK_Manager");
        Directory.CreateDirectory(selected);

        var error = Assert.Throws<InvalidOperationException>(
            () => ContentSyncFolderResolver.Resolve(_root, selected));

        Assert.Contains("Content\\STARK", error.Message);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }
}
