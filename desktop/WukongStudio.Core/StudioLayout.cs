namespace WukongStudio.Core;

public sealed record StudioLayout(string InstallRoot)
{
    public static StudioLayout Default { get; } = new(
        Environment.GetEnvironmentVariable("WUKONG_STUDIO_INSTALL_ROOT") is { Length: > 0 } installRoot
            ? Path.GetFullPath(installRoot)
            : @"C:\WukongROMStudio");

    public string AppRoot => Path.Combine(InstallRoot, "App");
    public string RuntimeRoot => Path.Combine(InstallRoot, "Runtime");
    public string PythonRoot => Path.Combine(RuntimeRoot, "Python");
    public string JavaRoot => Path.Combine(RuntimeRoot, "Java");
    public string ScriptsRoot => Path.Combine(RuntimeRoot, "Scripts");
    public string ContentRoot => Path.Combine(InstallRoot, "Content");
    public string DataRoot => Path.Combine(InstallRoot, "Data");
    public string JobsRoot => Path.Combine(DataRoot, "Jobs");
    public string RecipesRoot => Path.Combine(DataRoot, "Recipes");
    public string SecretsRoot => Path.Combine(DataRoot, "Secrets");
    public string WorkspaceRoot => Path.Combine(InstallRoot, "Workspace");
    public string OutputRoot => Path.Combine(InstallRoot, "ROM_BUILD_DONE");
    public string TempRoot => Path.Combine(InstallRoot, "Temp");
    public string PackagesRoot => Path.Combine(TempRoot, "Packages");
    public string DownloadsRoot => Path.Combine(TempRoot, "Downloads");
    public string ExtractionRoot => Path.Combine(TempRoot, "Extraction");
    public string LogsRoot => Path.Combine(InstallRoot, "Logs");
    public string CrashLogsRoot => Path.Combine(LogsRoot, "crash");
    public string UpdatesRoot => Path.Combine(InstallRoot, "Updates");
    public string BackupsRoot => Path.Combine(InstallRoot, "Backups");
    public string HostLogPath => Path.Combine(LogsRoot, "app-host.log");
    public string BackendLogPath => Path.Combine(LogsRoot, "backend.log");
    public string DesktopSettingsPath => Path.Combine(DataRoot, "desktop-settings.json");
    public string FirstRunPath => Path.Combine(DataRoot, "first-run.json");
    public string ContentPacksPath => Path.Combine(DataRoot, "content-packs.json");

    public void EnsureWritableDirectories()
    {
        foreach (var path in new[]
        {
            DataRoot,
            JobsRoot,
            RecipesRoot,
            SecretsRoot,
            ContentRoot,
            WorkspaceRoot,
            OutputRoot,
            TempRoot,
            PackagesRoot,
            DownloadsRoot,
            ExtractionRoot,
            LogsRoot,
            CrashLogsRoot,
            UpdatesRoot,
            BackupsRoot,
        })
        {
            Directory.CreateDirectory(path);
        }
    }

    public bool IsManagedPath(string path)
    {
        var root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(InstallRoot));
        var candidate = Path.GetFullPath(path);
        return candidate.Equals(root, StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }
}
