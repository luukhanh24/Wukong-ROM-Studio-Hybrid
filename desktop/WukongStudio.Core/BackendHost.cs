using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;

namespace WukongStudio.Core;

public sealed class BackendHost(StudioLayout layout) : IAsyncDisposable
{
    private readonly SemaphoreSlim _logLock = new(1, 1);
    private Process? _process;
    private WindowsJobObject? _jobObject;

    public Uri? BaseAddress { get; private set; }
    public string? SessionToken { get; private set; }
    public StudioApiClient? ApiClient { get; private set; }

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (_process is { HasExited: false })
        {
            return;
        }

        layout.EnsureWritableDirectories();
        var python = Path.Combine(layout.PythonRoot, "python.exe");
        var server = Path.Combine(layout.ScriptsRoot, "studio_server.py");
        if (!File.Exists(python))
        {
            throw new FileNotFoundException("Bundled Python runtime is missing.", python);
        }
        if (!File.Exists(server))
        {
            throw new FileNotFoundException("Studio backend is missing.", server);
        }

        var port = ReservePort();
        SessionToken = GenerateToken();
        BaseAddress = new Uri($"http://127.0.0.1:{port}/");
        var startInfo = new ProcessStartInfo
        {
            FileName = python,
            WorkingDirectory = layout.ScriptsRoot,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        startInfo.ArgumentList.Add(server);
        startInfo.ArgumentList.Add("--port");
        startInfo.ArgumentList.Add(port.ToString(System.Globalization.CultureInfo.InvariantCulture));
        startInfo.ArgumentList.Add("--no-browser");
        startInfo.ArgumentList.Add("--desktop-mode");
        startInfo.ArgumentList.Add("--parent-pid");
        startInfo.ArgumentList.Add(Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture));
        ConfigureEnvironment(startInfo.Environment, SessionToken);

        _process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        await AppendHostLogAsync($"Starting backend on {BaseAddress} with bundled Python {python}.", cancellationToken);
        if (!_process.Start())
        {
            throw new InvalidOperationException("Could not start the Studio backend.");
        }

        _jobObject = new WindowsJobObject();
        _jobObject.Assign(_process);
        _ = PumpLogAsync(_process.StandardOutput, layout.BackendLogPath, cancellationToken);
        _ = PumpLogAsync(_process.StandardError, layout.BackendLogPath, cancellationToken);
        ApiClient = new StudioApiClient(BaseAddress, SessionToken);
        await WaitForHealthAsync(cancellationToken);
    }

    public async Task StopAsync(bool cancelActiveJobs, CancellationToken cancellationToken = default)
    {
        if (_process is null)
        {
            return;
        }

        if (ApiClient is not null && !_process.HasExited)
        {
            try
            {
                if (cancelActiveJobs)
                {
                    foreach (var job in await ApiClient.GetActiveJobsAsync(cancellationToken))
                    {
                        await ApiClient.CancelJobAsync(job.Id, cancellationToken);
                    }
                }
                await ApiClient.ShutdownAsync(cancellationToken);
            }
            catch (HttpRequestException)
            {
            }
        }

        if (!_process.HasExited)
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            try
            {
                await _process.WaitForExitAsync(timeout.Token);
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        await AppendHostLogAsync("Backend stopped.", cancellationToken);
    }

    private void ConfigureEnvironment(IDictionary<string, string?> environment, string token)
    {
        environment["PYTHONUTF8"] = "1";
        environment["PYTHONIOENCODING"] = "utf-8";
        environment["PYTHONDONTWRITEBYTECODE"] = "1";
        environment["WUKONG_STUDIO_DESKTOP_MODE"] = "1";
        environment["WUKONG_STUDIO_SESSION_TOKEN"] = token;
        environment["WUKONG_STUDIO_INSTALL_ROOT"] = layout.InstallRoot;
        environment["WUKONG_STUDIO_APP_ROOT"] = layout.RuntimeRoot;
        environment["WUKONG_STUDIO_DATA_ROOT"] = layout.DataRoot;
        environment["WUKONG_STUDIO_CONTENT_ROOT"] = layout.ContentRoot;
        environment["WUKONG_STUDIO_WORKSPACE_ROOT"] = layout.WorkspaceRoot;
        environment["WUKONG_STUDIO_OUTPUT_ROOT"] = layout.OutputRoot;
        environment["WUKONG_STUDIO_TEMP_ROOT"] = layout.TempRoot;
        environment["WUKONG_STUDIO_LOG_ROOT"] = layout.LogsRoot;
        environment["WUKONG_STUDIO_PARENT_PID"] = Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture);
        environment["JAVA_HOME"] = layout.JavaRoot;
        environment["PATH"] = string.Join(
            Path.PathSeparator,
            Path.Combine(layout.JavaRoot, "bin"),
            Path.Combine(layout.RuntimeRoot, "Bin", "Windows", "AMD64"),
            environment.TryGetValue("PATH", out var currentPath) ? currentPath : null);

        var telegram = new TelegramSecretStore(layout).Load();
        if (telegram is not null)
        {
            environment["WUKONG_TELEGRAM_BOT_TOKEN"] = telegram.BotToken;
            environment["WUKONG_TELEGRAM_CHAT_ID"] = telegram.ChatId;
            environment["WUKONG_TELEGRAM_ADMIN_IDS"] = telegram.ChatId;
        }
        var hybrid = new HybridSecretStore(layout).Load();
        if (hybrid is not null)
        {
            environment["WUKONG_GITHUB_REPOSITORY"] = hybrid.GitHubRepository;
            environment["WUKONG_GITHUB_TOKEN"] = hybrid.GitHubToken;
            environment["WUKONG_RCLONE_CONFIG_CONTENT_B64"] = Convert.ToBase64String(
                System.Text.Encoding.UTF8.GetBytes(hybrid.RcloneConfig));
            environment["WUKONG_RCLONE_REMOTE"] = hybrid.RcloneRemote;
        }
    }

    private async Task WaitForHealthAsync(CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        while (!timeout.IsCancellationRequested)
        {
            if (_process?.HasExited == true)
            {
                throw new InvalidOperationException($"Studio backend exited with code {_process.ExitCode}.");
            }
            try
            {
                var health = await ApiClient!.GetHealthAsync(timeout.Token);
                if (health?.Status == "ready")
                {
                    return;
                }
            }
            catch (HttpRequestException)
            {
            }
            await Task.Delay(250, timeout.Token);
        }
        throw new TimeoutException("Studio backend did not become ready within 30 seconds.");
    }

    private async Task PumpLogAsync(StreamReader reader, string path, CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            string? line;
            try
            {
                line = await reader.ReadLineAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            if (line is null)
            {
                break;
            }
            await _logLock.WaitAsync(cancellationToken);
            try
            {
                await File.AppendAllTextAsync(path, line + Environment.NewLine, cancellationToken);
            }
            finally
            {
                _logLock.Release();
            }
        }
    }

    private async Task AppendHostLogAsync(string message, CancellationToken cancellationToken)
    {
        await _logLock.WaitAsync(cancellationToken);
        try
        {
            var line = $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {message}{Environment.NewLine}";
            await File.AppendAllTextAsync(layout.HostLogPath, line, cancellationToken);
        }
        finally
        {
            _logLock.Release();
        }
    }

    private static int ReservePort()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    private static string GenerateToken() => Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
        .TrimEnd('=')
        .Replace('+', '-')
        .Replace('/', '_');

    public async ValueTask DisposeAsync()
    {
        await StopAsync(cancelActiveJobs: true);
        ApiClient?.Dispose();
        _process?.Dispose();
        _jobObject?.Dispose();
        _logLock.Dispose();
    }
}
