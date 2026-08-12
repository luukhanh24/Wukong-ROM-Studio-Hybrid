using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class StudioBuildProfileTests
{
    [Fact]
    public void RoundTripKeepsBuildConfigurationWithoutRomPath()
    {
        var profile = StudioBuildProfile.Create(
            "ColorOS Plus",
            "ColorOS_16.0.8",
            "custom",
            ["WK_Manager", "Fake_lock", "WK_Manager"],
            [@"my_stock\app\Browser"],
            ["apply_mod", "package_zip"],
            notifyTelegram: true);

        var json = profile.ToJson();
        var loaded = StudioBuildProfile.Parse(json);

        Assert.Equal(profile.Name, loaded.Name);
        Assert.Equal(profile.ModVersion, loaded.ModVersion);
        Assert.Equal(profile.Preset, loaded.Preset);
        Assert.Equal(profile.DebloatPaths, loaded.DebloatPaths);
        Assert.Equal(profile.EnabledSteps, loaded.EnabledSteps);
        Assert.Equal(profile.NotifyTelegram, loaded.NotifyTelegram);
        Assert.DoesNotContain("romPath", json, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(["Fake_lock", "WK_Manager"], loaded.ModNames);
    }

    [Fact]
    public void FutureSchemaIsRejected()
    {
        const string json = """
            {
              "schemaVersion": 99,
              "name": "future",
              "modVersion": "ColorOS_16.0.8",
              "preset": "custom",
              "modNames": [],
              "debloatPaths": [],
              "enabledSteps": [],
              "notifyTelegram": false
            }
            """;

        Assert.Throws<InvalidDataException>(() => StudioBuildProfile.Parse(json));
    }
}
