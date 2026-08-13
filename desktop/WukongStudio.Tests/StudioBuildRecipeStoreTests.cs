using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class StudioBuildRecipeStoreTests
{
    [Fact]
    public void SaveListLockAndDeleteRespectRecipeLock()
    {
        using var workspace = new TestWorkspace();
        var store = new StudioBuildRecipeStore(workspace.Layout);
        var profile = StudioBuildProfile.Create(
            "Plus daily",
            "ColorOS_16.0.8",
            "resume",
            ["WK_Manager"],
            [],
            ["apply_mod", "package_zip"],
            true);

        var saved = store.Save("Plus daily", profile);
        Assert.Single(store.List());

        var locked = store.SetLocked(saved.Id, true);
        Assert.True(locked.Locked);
        Assert.Throws<InvalidOperationException>(() => store.Save("Changed", profile, saved.Id));
        Assert.Throws<InvalidOperationException>(() => store.Delete(saved.Id));

        store.SetLocked(saved.Id, false);
        store.Delete(saved.Id);
        Assert.Empty(store.List());
    }

    [Fact]
    public void ImportAcceptsLegacyBuildProfile()
    {
        using var workspace = new TestWorkspace();
        var store = new StudioBuildRecipeStore(workspace.Layout);
        var source = Path.Combine(workspace.Layout.DataRoot, "profile.json");
        File.WriteAllText(source, StudioBuildProfile.Create(
            "Imported",
            "ColorOS_16.0.7",
            "lite",
            [],
            [],
            ["package_zip"],
            false).ToJson());

        var imported = store.Import(source);

        Assert.Equal("Imported", imported.Name);
        Assert.Equal("lite", imported.Profile.Preset);
        Assert.Single(store.List());
    }

    [Fact]
    public void ExportAndImportFullRecipePreserveProfileAndLock()
    {
        using var sourceWorkspace = new TestWorkspace();
        using var destinationWorkspace = new TestWorkspace();
        var sourceStore = new StudioBuildRecipeStore(sourceWorkspace.Layout);
        var destinationStore = new StudioBuildRecipeStore(destinationWorkspace.Layout);
        var profile = StudioBuildProfile.Create(
            "Custom release",
            "ColorOS_16.0.8",
            "custom",
            ["WK_Manager", "Theme_cr"],
            ["my_stock\\app\\AIUnit"],
            ["apply_mod", "package_zip"],
            true);
        var saved = sourceStore.Save("Custom release", profile);
        sourceStore.SetLocked(saved.Id, true);
        var exportedPath = Path.Combine(sourceWorkspace.Layout.DataRoot, "recipe-export.json");

        sourceStore.Export(saved.Id, exportedPath);
        var imported = destinationStore.Import(exportedPath);

        Assert.NotEqual(saved.Id, imported.Id);
        Assert.True(imported.Locked);
        Assert.Equal(saved.Name, imported.Name);
        Assert.Equal(saved.Profile.ModVersion, imported.Profile.ModVersion);
        Assert.Equal(saved.Profile.Preset, imported.Profile.Preset);
        Assert.Equal(saved.Profile.ModNames, imported.Profile.ModNames);
        Assert.Equal(saved.Profile.DebloatPaths, imported.Profile.DebloatPaths);
        Assert.Equal(saved.Profile.EnabledSteps, imported.Profile.EnabledSteps);
        Assert.Equal(saved.Profile.NotifyTelegram, imported.Profile.NotifyTelegram);
        Assert.Throws<InvalidOperationException>(() => destinationStore.Save("Changed", profile, imported.Id));
    }
}
