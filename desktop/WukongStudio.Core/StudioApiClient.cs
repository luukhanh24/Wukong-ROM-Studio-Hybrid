using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace WukongStudio.Core;

public sealed record StudioHealth(
    string Status,
    string Version,
    bool DesktopMode,
    string InstallRoot,
    bool ContentReady);

public sealed record StudioJob(
    string Id,
    string VersionName,
    string Status,
    string? CurrentStep,
    string? OutputZip,
    IReadOnlyList<StudioJobStep>? Steps,
    string? CreatedAt = null,
    string? StartedAt = null,
    string? FinishedAt = null,
    string? Error = null,
    string? Workspace = null)
{
    public int? Progress
    {
        get
        {
            var package = Steps?.FirstOrDefault(step => step.Id == "package_zip");
            if (package?.Details is not JsonElement details
                || !details.TryGetProperty("progress", out var progress)
                || !progress.TryGetInt32(out var value))
            {
                return null;
            }
            return Math.Clamp(value, 0, 100);
        }
    }

    public string? ProgressMessage
    {
        get
        {
            var active = Steps?.FirstOrDefault(step => step.Id == CurrentStep)
                ?? Steps?.FirstOrDefault(step => step.Status == "running");
            if (active?.Details is not JsonElement details
                || details.ValueKind != JsonValueKind.Object
                || !details.TryGetProperty("progressMessage", out var message)
                || message.ValueKind != JsonValueKind.String)
            {
                return null;
            }
            return message.GetString();
        }
    }
}

public sealed record StudioJobStep(string Id, string Status, JsonElement? Details);
public sealed record StudioJobsResponse(IReadOnlyList<StudioJob> Jobs);
public sealed record StudioStepDefinition(string Id, string Label, bool Required);
public sealed record StudioMod(
    string Name,
    string Version,
    bool Valid,
    bool Ready,
    string? BlockedReason,
    IReadOnlyList<string>? Partitions,
    bool PatchOnly,
    IReadOnlyList<string>? SpecialActions);
public sealed record StudioDevice(
    string Name,
    [property: JsonPropertyName("product_name")]
    string ProductName,
    string Soc,
    long SuperSize,
    long GroupSize,
    IReadOnlyList<string>? Partitions);
public sealed record StudioSettings(
    IReadOnlyList<string> Roots,
    string Locale,
    string Theme,
    string DefaultPreset,
    bool NotifyTelegram,
    IReadOnlyList<string>? DebloatPaths,
    bool StageCacheEnabled = true,
    int StageCacheMaxGb = 40,
    IReadOnlyDictionary<string, string>? StudioVersions = null,
    string ZipValidationMode = "fast");
public sealed record StudioArtifact(
    string Id,
    string VersionName,
    string Status,
    string? OutputZip,
    bool ArtifactExists,
    string? CreatedAt,
    string? FinishedAt);
public sealed record StudioBootstrap(
    string Name,
    StudioSettings Settings,
    IReadOnlyList<StudioDevice> Devices,
    IReadOnlyList<string> ModVersions,
    IReadOnlyDictionary<string, IReadOnlyList<StudioMod>> ModsByVersion,
    IReadOnlyList<StudioMod> Mods,
    IReadOnlyDictionary<string, IReadOnlyDictionary<string, IReadOnlyList<string>>> PresetDefaultsByVersion,
    IReadOnlyDictionary<string, IReadOnlyList<string>> PresetDefaults,
    IReadOnlyList<StudioJob> Jobs,
    IReadOnlyList<StudioArtifact> Artifacts,
    IReadOnlyList<StudioStepDefinition> Steps,
    JsonElement Diagnostics,
    IReadOnlyList<string>? DefaultDebloatPaths = null,
    string? DeviceCatalogPath = null,
    StudioCacheStatus? StageCache = null);
public sealed record StudioBuildSpec(
    string RomPath,
    IReadOnlyList<string> ModNames,
    string ModVersion,
    IReadOnlyList<string>? DebloatPaths,
    string Preset,
    IReadOnlyList<string> EnabledSteps,
    bool NotifyTelegram,
    string? ResumeFromJobId = null);
public sealed record StudioInspectResult(
    bool Ok,
    IReadOnlyList<string> Errors,
    IReadOnlyList<string> Warnings,
    JsonElement Metadata,
    JsonElement Device,
    long Size,
    string? ModVersion);
public sealed record StudioAuthorizeRomResponse(string? Path);
public sealed record StudioAuthorizeFolderResponse(string? Folder, IReadOnlyList<string> Roms);
public sealed record StudioRomRenameEntry(
    string SourcePath,
    string SourceName,
    string? VersionName,
    string? TargetPath,
    string? TargetName,
    string Status,
    string? Warning,
    string? Error);
public sealed record StudioRomRenamePreview(
    IReadOnlyList<StudioRomRenameEntry> Entries,
    int Total,
    int Ready,
    int Unchanged,
    int Errors,
    bool CanApply);
public sealed record StudioRomRenameResult(
    IReadOnlyList<StudioRomRenameEntry> Entries,
    int Total,
    int Renamed,
    int Unchanged);
public sealed record StudioJobCreateResponse(IReadOnlyList<StudioJob> Jobs);
public sealed record StudioArtifactsResponse(IReadOnlyList<StudioArtifact> Artifacts);
public sealed record StudioDevicesResponse(IReadOnlyList<StudioDevice> Devices, string StoragePath);
public sealed record StudioLogChunk(string Text, long NextOffset, bool Reset);
public sealed record StudioAuthorizeLayoutResponse(string? Path);
public sealed record StudioCacheEntry(
    string Key,
    string? VersionName,
    string? RomName,
    long Bytes,
    int Files,
    int Hits,
    string? CreatedAt,
    string? LastUsedAt);
public sealed record StudioCacheStatus(
    bool Enabled,
    string Root,
    long MaximumBytes,
    long TotalBytes,
    int EntryCount,
    int TotalHits,
    IReadOnlyList<StudioCacheEntry> Entries);
public sealed record StudioProcessMetrics(
    bool Available,
    long WorkingSetBytes = 0,
    long PrivateBytes = 0,
    double CpuTimeSeconds = 0);
public sealed record StudioStepMetrics(
    string Id,
    string Status,
    double DurationSeconds,
    bool? CacheHit,
    string? Phase);
public sealed record StudioJobMetrics(
    string JobId,
    string Status,
    int? Pid,
    StudioProcessMetrics Process,
    long LogBytes,
    long ArtifactBytes,
    long DiskFreeBytes,
    long DiskTotalBytes,
    IReadOnlyList<StudioStepMetrics> Steps,
    StudioCacheStatus StageCache,
    string CapturedAt);

public sealed record HybridSourceSpec(
    string Kind,
    string Uri,
    string? Sha256 = null,
    long? SizeBytes = null);
public sealed record HybridBuildOptions(
    string Preset,
    IReadOnlyList<string> Mods,
    string ModVersion,
    bool Package = true,
    IReadOnlyList<string>? EnabledSteps = null,
    IReadOnlyList<string>? DebloatPaths = null,
    bool NotifyTelegram = false);
public sealed record HybridExecutionOptions(string Target, long? EstimatedWorkspaceBytes = null);
public sealed record HybridStorageOptions(string Remote = "wukong-gdrive", bool PublishArtifact = true);
public sealed record HybridBuildRecipe(
    int SchemaVersion,
    string Task,
    string Device,
    HybridSourceSpec Source,
    HybridBuildOptions Build,
    HybridExecutionOptions Execution,
    HybridStorageOptions Storage);
public sealed record HybridIdentity(string Channel, string Subject, string Role);
public sealed record HybridArtifact(
    string Name,
    string Uri,
    string Sha256,
    long SizeBytes,
    string? PublicUrl = null);
public sealed record HybridJobManifest(
    [property: JsonPropertyName("job_id")] string JobId,
    HybridIdentity Owner,
    [property: JsonPropertyName("recipe_digest")] string RecipeDigest,
    string Status,
    string? Stage,
    double Progress,
    string? Runner,
    string? Checkpoint,
    [property: JsonPropertyName("checkpoint_at")] string? CheckpointAt,
    IReadOnlyList<HybridArtifact> Artifacts,
    string? Error,
    [property: JsonPropertyName("created_at")] string CreatedAt,
    [property: JsonPropertyName("updated_at")] string UpdatedAt,
    [property: JsonPropertyName("finished_at")] string? FinishedAt);
public sealed record HybridJobsResponse(IReadOnlyList<HybridJobManifest> Jobs);
public sealed record HybridRunnerDecision(
    string Kind,
    string Runner,
    IReadOnlyList<string> Labels,
    string Reason);
public sealed record HybridRecipeValidation(
    bool Ok,
    HybridBuildRecipe Recipe,
    string RecipeDigest,
    HybridRunnerDecision Runner);

public sealed class StudioApiClient : IDisposable
{
    private readonly HttpClient _client;

    public StudioApiClient(Uri baseAddress, string token)
    {
        _client = new HttpClient { BaseAddress = baseAddress, Timeout = TimeSpan.FromMinutes(5) };
        _client.DefaultRequestHeaders.Add("X-Studio-Token", token);
    }

    public Task<StudioHealth?> GetHealthAsync(CancellationToken cancellationToken = default) =>
        _client.GetFromJsonAsync<StudioHealth>("api/health", cancellationToken);

    public async Task<IReadOnlyList<StudioJob>> GetJobsAsync(CancellationToken cancellationToken = default)
    {
        return (await _client.GetFromJsonAsync<StudioJobsResponse>("api/jobs", cancellationToken))?.Jobs
            ?? [];
    }

    public async Task<IReadOnlyList<StudioJob>> GetActiveJobsAsync(CancellationToken cancellationToken = default)
    {
        var jobs = await GetJobsAsync(cancellationToken);
        return jobs.Where(job => job.Status is "queued" or "running" or "packaging").ToArray();
    }

    public async Task CancelJobAsync(string jobId, CancellationToken cancellationToken = default)
    {
        using var response = await _client.PostAsync($"api/jobs/{Uri.EscapeDataString(jobId)}/cancel", null, cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public Task<StudioBootstrap> GetBootstrapAsync(CancellationToken cancellationToken = default) =>
        GetAsync<StudioBootstrap>("api/bootstrap", cancellationToken);

    public Task<StudioDevicesResponse> GetDevicesAsync(CancellationToken cancellationToken = default) =>
        GetAsync<StudioDevicesResponse>("api/devices", cancellationToken);

    public Task<StudioDevicesResponse> CreateDeviceAsync(
        StudioDevice device,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioDevicesResponse>("api/devices", device, cancellationToken);

    public Task<StudioDevicesResponse> UpdateDeviceAsync(
        string originalProductName,
        StudioDevice device,
        CancellationToken cancellationToken = default) =>
        PutAsync<StudioDevicesResponse>(
            $"api/devices/{Uri.EscapeDataString(originalProductName)}",
            device,
            cancellationToken);

    public async Task<StudioDevicesResponse> DeleteDeviceAsync(
        string productName,
        CancellationToken cancellationToken = default)
    {
        using var response = await _client.DeleteAsync(
            $"api/devices/{Uri.EscapeDataString(productName)}",
            cancellationToken);
        return await ReadJsonAsync<StudioDevicesResponse>(response, cancellationToken);
    }

    public Task<StudioAuthorizeRomResponse> AuthorizeRomAsync(
        string romPath,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioAuthorizeRomResponse>(
            "api/fs/authorize-rom",
            new { romPath },
            cancellationToken);

    public Task<StudioAuthorizeFolderResponse> AuthorizeRomFolderAsync(
        string folderPath,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioAuthorizeFolderResponse>(
            "api/fs/authorize-rom-folder",
            new { folderPath },
            cancellationToken);

    public Task<StudioRomRenamePreview> PreviewRomRenameAsync(
        string? romPath,
        string? folderPath,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioRomRenamePreview>(
            "api/tools/rom-renamer/preview",
            new { romPath, folderPath },
            cancellationToken);

    public Task<StudioRomRenameResult> ApplyRomRenameAsync(
        IReadOnlyList<StudioRomRenameEntry> entries,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioRomRenameResult>(
            "api/tools/rom-renamer/apply",
            new { entries },
            cancellationToken);

    public Task<StudioAuthorizeLayoutResponse> AuthorizeLayoutSourceAsync(
        string path,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioAuthorizeLayoutResponse>(
            "api/fs/authorize-layout-source",
            new { path },
            cancellationToken);

    public Task<JsonElement> AnalyzeLayoutAsync(
        StudioDevice device,
        string? sourcePath,
        CancellationToken cancellationToken = default) =>
        PostAsync<JsonElement>(
            "api/layout/analyze",
            new { device, sourcePath },
            cancellationToken);

    public Task<StudioInspectResult> InspectRomAsync(
        StudioBuildSpec spec,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioInspectResult>("api/roms/inspect", spec, cancellationToken);

    public Task<HybridRecipeValidation> ValidateHybridRecipeAsync(
        HybridBuildRecipe recipe,
        CancellationToken cancellationToken = default) =>
        PostAsync<HybridRecipeValidation>("api/v1/recipes/validate", recipe, cancellationToken);

    public Task<HybridJobManifest> CreateHybridJobAsync(
        HybridBuildRecipe recipe,
        CancellationToken cancellationToken = default) =>
        PostAsync<HybridJobManifest>("api/v1/jobs", recipe, cancellationToken);

    public Task<HybridJobManifest> GetHybridJobAsync(
        string jobId,
        CancellationToken cancellationToken = default) =>
        GetAsync<HybridJobManifest>($"api/v1/jobs/{Uri.EscapeDataString(jobId)}", cancellationToken);

    public async Task<IReadOnlyList<HybridJobManifest>> GetHybridJobsAsync(
        CancellationToken cancellationToken = default) =>
        (await GetAsync<HybridJobsResponse>("api/v1/jobs", cancellationToken)).Jobs;

    public Task<JsonElement> GetHybridCatalogAsync(CancellationToken cancellationToken = default) =>
        GetAsync<JsonElement>("api/v1/catalog", cancellationToken);

    public Task<JsonElement> GetHybridDiagnosticsAsync(CancellationToken cancellationToken = default) =>
        GetAsync<JsonElement>("api/v1/diagnostics", cancellationToken);

    public Task<JsonElement> GetHybridCloudLibraryAsync(
        string category = "artifacts",
        CancellationToken cancellationToken = default) =>
        GetAsync<JsonElement>(
            $"api/v1/cloud/library?category={Uri.EscapeDataString(category)}",
            cancellationToken);

    public Task<HybridJobManifest> CancelHybridJobAsync(
        string jobId,
        CancellationToken cancellationToken = default) =>
        PostAsync<HybridJobManifest>(
            $"api/v1/jobs/{Uri.EscapeDataString(jobId)}/cancel",
            new { },
            cancellationToken);

    public Task<HybridJobManifest> ResumeHybridJobAsync(
        string jobId,
        CancellationToken cancellationToken = default) =>
        PostAsync<HybridJobManifest>(
            $"api/v1/jobs/{Uri.EscapeDataString(jobId)}/resume",
            new { },
            cancellationToken);

    public Task<StudioJobCreateResponse> CreateJobsAsync(
        IReadOnlyList<StudioBuildSpec> specs,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioJobCreateResponse>("api/jobs", new { specs }, cancellationToken);

    public Task<StudioJob> GetJobAsync(string jobId, CancellationToken cancellationToken = default) =>
        GetAsync<StudioJob>($"api/jobs/{Uri.EscapeDataString(jobId)}", cancellationToken);

    public async Task<string> GetJobLogAsync(string jobId, CancellationToken cancellationToken = default)
    {
        using var response = await _client.GetAsync(
            $"api/jobs/{Uri.EscapeDataString(jobId)}/log",
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await response.Content.ReadAsStringAsync(cancellationToken);
    }

    public async Task<StudioLogChunk> GetJobLogChunkAsync(
        string jobId,
        long offset,
        int limit = 16384,
        CancellationToken cancellationToken = default)
    {
        using var response = await _client.GetAsync(
            $"api/jobs/{Uri.EscapeDataString(jobId)}/log?offset={offset}&limit={Math.Clamp(limit, 1, 262144)}&follow=1",
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        var text = await response.Content.ReadAsStringAsync(cancellationToken);
        var nextOffset = response.Headers.TryGetValues("X-Log-Next-Offset", out var offsetValues)
            && long.TryParse(offsetValues.FirstOrDefault(), out var parsedOffset)
                ? parsedOffset
                : offset;
        var reset = response.Headers.TryGetValues("X-Log-Reset", out var resetValues)
            && resetValues.FirstOrDefault() == "1";
        return new StudioLogChunk(text, nextOffset, reset);
    }

    public async Task DownloadJobLogAsync(
        string jobId,
        string destinationPath,
        CancellationToken cancellationToken = default)
    {
        using var response = await _client.GetAsync(
            $"api/jobs/{Uri.EscapeDataString(jobId)}/log",
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var destination = new FileStream(
            destinationPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            65536,
            useAsync: true);
        await source.CopyToAsync(destination, cancellationToken);
    }

    public Task<StudioJobMetrics> GetJobMetricsAsync(
        string jobId,
        CancellationToken cancellationToken = default) =>
        GetAsync<StudioJobMetrics>($"api/jobs/{Uri.EscapeDataString(jobId)}/metrics", cancellationToken);

    public async Task DownloadDiagnosticsBundleAsync(
        string jobId,
        string destinationPath,
        CancellationToken cancellationToken = default)
    {
        using var response = await _client.GetAsync(
            $"api/jobs/{Uri.EscapeDataString(jobId)}/diagnostics-bundle",
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        await using var source = await response.Content.ReadAsStreamAsync(cancellationToken);
        await using var destination = new FileStream(
            destinationPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            65536,
            useAsync: true);
        await source.CopyToAsync(destination, cancellationToken);
    }

    public async Task<IReadOnlyList<StudioArtifact>> GetArtifactsAsync(
        CancellationToken cancellationToken = default)
    {
        return (await GetAsync<StudioArtifactsResponse>("api/artifacts", cancellationToken)).Artifacts;
    }

    public Task<JsonElement> GetDiagnosticsAsync(CancellationToken cancellationToken = default) =>
        GetAsync<JsonElement>("api/diagnostics", cancellationToken);

    public Task<StudioCacheStatus> GetCacheAsync(CancellationToken cancellationToken = default) =>
        GetAsync<StudioCacheStatus>("api/cache", cancellationToken);

    public Task<StudioCacheStatus> ClearCacheAsync(CancellationToken cancellationToken = default) =>
        PostAsync<StudioCacheStatus>("api/cache/clear", new { }, cancellationToken);

    public Task<StudioSettings> GetSettingsAsync(CancellationToken cancellationToken = default) =>
        GetAsync<StudioSettings>("api/settings", cancellationToken);

    public Task<StudioSettings> SaveSettingsAsync(
        StudioSettings settings,
        CancellationToken cancellationToken = default) =>
        PostAsync<StudioSettings>("api/settings", settings, cancellationToken);

    public async Task<bool> ShutdownAsync(CancellationToken cancellationToken = default)
    {
        using var response = await _client.PostAsync("api/shutdown", null, cancellationToken);
        return response.IsSuccessStatusCode;
    }

    private async Task<T> GetAsync<T>(string path, CancellationToken cancellationToken)
    {
        using var response = await _client.GetAsync(path, cancellationToken);
        return await ReadJsonAsync<T>(response, cancellationToken);
    }

    private async Task<T> PostAsync<T>(string path, object payload, CancellationToken cancellationToken)
    {
        using var response = await _client.PostAsJsonAsync(path, payload, JsonOptions, cancellationToken);
        return await ReadJsonAsync<T>(response, cancellationToken);
    }

    private async Task<T> PutAsync<T>(string path, object payload, CancellationToken cancellationToken)
    {
        using var response = await _client.PutAsJsonAsync(path, payload, JsonOptions, cancellationToken);
        return await ReadJsonAsync<T>(response, cancellationToken);
    }

    private static async Task<T> ReadJsonAsync<T>(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        await EnsureSuccessAsync(response, cancellationToken);
        return await response.Content.ReadFromJsonAsync<T>(JsonOptions, cancellationToken)
            ?? throw new InvalidDataException("Studio API returned an empty response.");
    }

    private static async Task EnsureSuccessAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }
        var content = await response.Content.ReadAsStringAsync(cancellationToken);
        try
        {
            using var document = JsonDocument.Parse(content);
            if (document.RootElement.TryGetProperty("error", out var error))
            {
                throw new InvalidOperationException(error.GetString() ?? response.ReasonPhrase);
            }
        }
        catch (JsonException)
        {
        }
        throw new HttpRequestException(
            string.IsNullOrWhiteSpace(content) ? response.ReasonPhrase : content,
            null,
            response.StatusCode);
    }

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public void Dispose() => _client.Dispose();
}
