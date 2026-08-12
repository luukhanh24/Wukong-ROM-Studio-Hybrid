using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class LegacyMigrationServiceTests
{
    [Fact]
    public async Task ImportsThroughStagingAndKeepsLegacyByDefault()
    {
        using var workspace = new TestWorkspace();
        var legacy = Path.Combine(workspace.Root, "legacy");
        var source = Path.Combine(legacy, "MOD", "ColorOS_Test");
        Directory.CreateDirectory(source);
        File.WriteAllText(Path.Combine(source, "mod.txt"), "test");
        var service = new LegacyMigrationService(workspace.Layout);

        var result = await service.ImportAsync(
            legacy,
            [new LegacyMigrationItem("MOD", "MOD")]);

        Assert.Single(result.ImportedTargets);
        Assert.True(File.Exists(Path.Combine(workspace.Layout.ContentRoot, "MOD", "ColorOS_Test", "mod.txt")));
        Assert.True(File.Exists(Path.Combine(source, "mod.txt")));
    }
}
