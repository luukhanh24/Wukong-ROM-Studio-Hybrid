using WukongStudio.Core;

namespace WukongStudio.Tests;

internal sealed class TestWorkspace : IDisposable
{
    public TestWorkspace()
    {
        Root = Path.Combine(Path.GetTempPath(), "WukongStudio.Tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Root);
        Layout = new StudioLayout(Path.Combine(Root, "Studio"));
        Layout.EnsureWritableDirectories();
    }

    public string Root { get; }
    public StudioLayout Layout { get; }

    public void Dispose()
    {
        if (Directory.Exists(Root))
        {
            Directory.Delete(Root, recursive: true);
        }
    }
}
