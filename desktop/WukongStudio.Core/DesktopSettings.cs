using System.Text.Json;

namespace WukongStudio.Core;

public sealed record DesktopSettings
{
    private const int WindowsMinimizedCoordinateThreshold = -30000;

    public int WindowWidth { get; init; } = 1280;
    public int WindowHeight { get; init; } = 820;
    public int? WindowX { get; init; }
    public int? WindowY { get; init; }
    public bool Maximized { get; init; }
    public string? UpdateManifestUrl { get; init; }
    public bool MinimizeToTrayWhileBuilding { get; init; } = true;
    public string Locale { get; init; } = "vi";
    public string Theme { get; init; } = "system";
    public int ConsoleMaxCharacters { get; init; } = 100_000;
    public int LogPollIntervalMs { get; init; } = 750;
    public bool AutoScrollLogs { get; init; } = true;
    public bool NavigationPaneOpen { get; init; } = true;
    public bool ExpandModOptions { get; init; } = true;
    public bool ExpandPipelineSteps { get; init; }
    public string? LastModVersion { get; init; }
    public string? LastRecipeId { get; init; }

    public static DesktopSettings Load(StudioLayout layout)
    {
        if (!File.Exists(layout.DesktopSettingsPath))
        {
            return new DesktopSettings();
        }

        try
        {
            var settings = JsonSerializer.Deserialize<DesktopSettings>(
                File.ReadAllText(layout.DesktopSettingsPath),
                JsonOptions) ?? new DesktopSettings();
            return settings.Normalize();
        }
        catch (JsonException)
        {
            var corrupt = layout.DesktopSettingsPath + $".corrupt-{DateTime.UtcNow:yyyyMMddHHmmss}";
            File.Move(layout.DesktopSettingsPath, corrupt, overwrite: false);
            return new DesktopSettings();
        }
    }

    public void Save(StudioLayout layout)
    {
        layout.EnsureWritableDirectories();
        var temporary = layout.DesktopSettingsPath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(this, JsonOptions));
        File.Move(temporary, layout.DesktopSettingsPath, overwrite: true);
    }

    private DesktopSettings NormalizeWindowPosition()
    {
        if (WindowX is null && WindowY is null)
        {
            return this;
        }
        if (WindowX is not int x
            || WindowY is not int y
            || x <= WindowsMinimizedCoordinateThreshold
            || y <= WindowsMinimizedCoordinateThreshold)
        {
            return this with { WindowX = null, WindowY = null };
        }
        return this;
    }

    private DesktopSettings Normalize()
    {
        var settings = NormalizeWindowPosition();
        return settings with
        {
            ConsoleMaxCharacters = Math.Clamp(settings.ConsoleMaxCharacters, 50_000, 500_000),
            LogPollIntervalMs = Math.Clamp(settings.LogPollIntervalMs, 750, 2_000),
            Locale = string.Equals(settings.Locale, "en", StringComparison.OrdinalIgnoreCase) ? "en" : "vi",
            Theme = (settings.Theme ?? string.Empty).Trim().ToLowerInvariant() switch
            {
                "dark" => "dark",
                "light" => "light",
                _ => "system",
            },
        };
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
    };
}
