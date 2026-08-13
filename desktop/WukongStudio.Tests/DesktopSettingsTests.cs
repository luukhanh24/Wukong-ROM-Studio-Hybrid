using WukongStudio.Core;

namespace WukongStudio.Tests;

public sealed class DesktopSettingsTests
{
    [Fact]
    public void SaveAndLoadRoundTrips()
    {
        using var workspace = new TestWorkspace();
        var expected = new DesktopSettings { WindowWidth = 1111, WindowHeight = 777, Locale = "en" };
        expected.Save(workspace.Layout);
        Assert.Equal(expected, DesktopSettings.Load(workspace.Layout));
        Assert.False(File.Exists(workspace.Layout.DesktopSettingsPath + ".tmp"));
    }

    [Fact]
    public void CorruptSettingsArePreserved()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(workspace.Layout.DesktopSettingsPath, "{");
        var loaded = DesktopSettings.Load(workspace.Layout);
        Assert.Equal("vi", loaded.Locale);
        Assert.Single(Directory.GetFiles(workspace.Layout.DataRoot, "desktop-settings.json.corrupt-*"));
    }

    [Fact]
    public void LoadDiscardsWindowsMinimizedCoordinates()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(
            workspace.Layout.DesktopSettingsPath,
            """
            {
              "windowWidth": 900,
              "windowHeight": 600,
              "windowX": -32000,
              "windowY": -32000,
              "maximized": false,
              "locale": "vi"
            }
            """);

        var loaded = DesktopSettings.Load(workspace.Layout);

        Assert.Null(loaded.WindowX);
        Assert.Null(loaded.WindowY);
        Assert.Equal(900, loaded.WindowWidth);
        Assert.Equal(600, loaded.WindowHeight);
    }

    [Fact]
    public void ConsolePreferencesAreNormalized()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(
            workspace.Layout.DesktopSettingsPath,
            """{"consoleMaxCharacters":10,"logPollIntervalMs":9999,"autoScrollLogs":false}""");

        var loaded = DesktopSettings.Load(workspace.Layout);

        Assert.Equal(50_000, loaded.ConsoleMaxCharacters);
        Assert.Equal(2_000, loaded.LogPollIntervalMs);
        Assert.False(loaded.AutoScrollLogs);
    }

    [Fact]
    public void LogPollingCannotBeConfiguredBelowUiSafeMinimum()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(workspace.Layout.DesktopSettingsPath, """{"logPollIntervalMs":250}""");

        var loaded = DesktopSettings.Load(workspace.Layout);

        Assert.Equal(750, loaded.LogPollIntervalMs);
    }

    [Fact]
    public void LocaleAndThemeAreNormalized()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(
            workspace.Layout.DesktopSettingsPath,
            """{"locale":"EN","theme":"DARK"}""");

        var loaded = DesktopSettings.Load(workspace.Layout);

        Assert.Equal("en", loaded.Locale);
        Assert.Equal("dark", loaded.Theme);
    }

    [Fact]
    public void SystemThemeIsPreservedAndUsedForLegacySettings()
    {
        using var workspace = new TestWorkspace();
        File.WriteAllText(workspace.Layout.DesktopSettingsPath, """{"theme":"SYSTEM"}""");
        Assert.Equal("system", DesktopSettings.Load(workspace.Layout).Theme);

        File.WriteAllText(workspace.Layout.DesktopSettingsPath, """{"locale":"vi"}""");
        Assert.Equal("system", DesktopSettings.Load(workspace.Layout).Theme);

        File.WriteAllText(workspace.Layout.DesktopSettingsPath, """{"theme":null}""");
        Assert.Equal("system", DesktopSettings.Load(workspace.Layout).Theme);
    }
}
