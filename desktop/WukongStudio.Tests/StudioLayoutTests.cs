using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class StudioLayoutTests
{
    [Fact]
    public void ManagedPathRejectsSiblingPrefix()
    {
        using var workspace = new TestWorkspace();
        Assert.True(workspace.Layout.IsManagedPath(Path.Combine(workspace.Layout.DataRoot, "settings.json")));
        Assert.False(workspace.Layout.IsManagedPath(workspace.Layout.InstallRoot + "-other"));
    }

    [Fact]
    public void EnsureWritableDirectoriesCreatesRequiredTree()
    {
        using var workspace = new TestWorkspace();
        Assert.True(Directory.Exists(workspace.Layout.JobsRoot));
        Assert.True(Directory.Exists(workspace.Layout.RecipesRoot));
        Assert.True(Directory.Exists(workspace.Layout.WorkspaceRoot));
        Assert.True(Directory.Exists(workspace.Layout.OutputRoot));
        Assert.True(Directory.Exists(workspace.Layout.BackupsRoot));
    }
}
