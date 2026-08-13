using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security;
using System.Text.Json;
using H.NotifyIcon.Core;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.Windows.AppNotifications;
using Windows.Storage.Pickers;
using WukongStudio.Core;

namespace WukongStudio.App;

public sealed partial class MainWindow : Window
{
    private const uint MonitorDefaultToNull = 0;
    private const string LegacyProjectRoot = @"C:\Android\Auto_Build_WK";
    private static readonly string LegacyTelegramEnvironmentPath =
        Path.Combine(LegacyProjectRoot, ".wkstudio", "telegram.env");
    private readonly StudioLayout _layout = StudioLayout.Default;
    private readonly CancellationTokenSource _lifetime = new();
    private readonly Dictionary<string, string> _knownJobStatuses = new(StringComparer.Ordinal);
    private readonly List<string> _selectedContentPacks = [];
    private readonly HashSet<string> _authorizedOpenPaths = new(StringComparer.OrdinalIgnoreCase);
    private readonly MenuFlyoutItem _trayJobItem = new() { Text = "Không có build đang chạy", IsEnabled = false };
    private readonly MenuFlyoutItem _trayCancelItem = new() { Text = "Hủy build hiện tại", IsEnabled = false };
    private BackendHost? _backend;
    private AppWindow? _appWindow;
    private TaskbarProgressService? _taskbarProgress;
    private DispatcherTimer? _statusTimer;
    private StudioJob? _activeJob;
    private Uri? _pendingActivationUri;
    private string? _pendingHealthToken;
    private bool _pendingRollbackNotification;
    private bool _polling;
    private bool _windowActive = true;
    private bool _allowClose;
    private bool _firstRunBusy;

    public RelayCommand RestoreCommand { get; }

    public MainWindow()
    {
        InitializeComponent();
        _authorizedOpenPaths.Add(Path.GetFullPath(_layout.OutputRoot));
        _authorizedOpenPaths.Add(Path.GetFullPath(_layout.LogsRoot));
        RestoreCommand = new RelayCommand(RestoreWindow);
        ConfigureTrayMenu();
        NativeStudio.JobsSnapshotChanged += ApplyJobsSnapshot;
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);
        SystemBackdrop = new MicaBackdrop();
        WindowRoot.ActualThemeChanged += WindowRootActualThemeChanged;
        Activated += MainWindowActivated;
        Activated += MainWindowActivityChanged;
        ImportLegacyCheckBox.Checked += (_, _) => MoveLegacyCheckBox.IsEnabled = true;
        ImportLegacyCheckBox.Unchecked += (_, _) =>
        {
            MoveLegacyCheckBox.IsChecked = false;
            MoveLegacyCheckBox.IsEnabled = false;
        };
    }

    private void ConfigureTrayMenu()
    {
        TrayIcon.LeftClickCommand = RestoreCommand;
        TrayIcon.NoLeftClickDelay = true;
        var menu = new MenuFlyout();
        var restore = new MenuFlyoutItem { Text = "Mở Wukong Studio" };
        restore.Click += RestoreFromTray;
        var openOutput = new MenuFlyoutItem { Text = "Mở thư mục ROM hoàn tất" };
        openOutput.Click += OpenOutputFromTray;
        _trayCancelItem.Click += CancelCurrentJobFromTray;
        var exit = new MenuFlyoutItem { Text = "Thoát" };
        exit.Click += ExitFromTray;
        menu.Items.Add(restore);
        menu.Items.Add(_trayJobItem);
        menu.Items.Add(openOutput);
        menu.Items.Add(_trayCancelItem);
        menu.Items.Add(new MenuFlyoutSeparator());
        menu.Items.Add(exit);
        TrayIcon.ContextFlyout = menu;
    }

    private async void MainWindowActivated(object sender, WindowActivatedEventArgs args)
    {
        Activated -= MainWindowActivated;
        ConfigureWindow();
        if (!File.Exists(_layout.FirstRunPath))
        {
            await ShowFirstRunAsync();
            return;
        }
        await InitializeStudioAsync();
    }

    private void MainWindowActivityChanged(object sender, WindowActivatedEventArgs args)
    {
        _windowActive = args.WindowActivationState != WindowActivationState.Deactivated;
        NativeStudio.SetForegroundActive(_windowActive);
        UpdateStatusPollingInterval();
    }

    private void ConfigureWindow()
    {
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(windowHandle);
        _appWindow = AppWindow.GetFromWindowId(windowId);
        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "WukongStudio.ico");
        if (File.Exists(iconPath))
        {
            _appWindow.SetIcon(iconPath);
        }
        var settings = DesktopSettings.Load(_layout);
        ApplyWindowTheme(ThemePreference(settings.Theme));
        ApplyWindowLocale(settings.Locale);
        var width = Math.Max(900, settings.WindowWidth);
        var height = Math.Max(600, settings.WindowHeight);
        _appWindow.Resize(new Windows.Graphics.SizeInt32(width, height));
        if (settings.WindowX is int x
            && settings.WindowY is int y
            && IntersectsDisplay(x, y, width, height))
        {
            _appWindow.Move(new Windows.Graphics.PointInt32(x, y));
        }
        if (settings.Maximized && _appWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.Maximize();
        }
        _appWindow.Closing += AppWindowClosing;
        _appWindow.Changed += AppWindowChanged;
        _taskbarProgress = new TaskbarProgressService(windowHandle);
        try
        {
            TrayIcon.ForceCreate();
        }
        catch (InvalidOperationException exception)
        {
            AppendHostLog($"Tray icon is unavailable: {exception.Message}");
        }
    }

    private async Task ShowFirstRunAsync()
    {
        StartupProgressRing.IsActive = false;
        StartupPanel.Visibility = Visibility.Collapsed;
        ErrorPanel.Visibility = Visibility.Collapsed;
        NativeStudio.Visibility = Visibility.Collapsed;
        FirstRunPanel.Visibility = Visibility.Visible;
        HostStatusText.Text = "Thiết lập lần đầu";
        try
        {
            _layout.EnsureWritableDirectories();
            var probe = Path.Combine(_layout.DataRoot, $"write-test-{Guid.NewGuid():N}.tmp");
            await File.WriteAllTextAsync(probe, "ok");
            File.Delete(probe);

            var drive = new DriveInfo(Path.GetPathRoot(_layout.InstallRoot)!);
            var freeGiB = drive.AvailableFreeSpace / 1024d / 1024d / 1024d;
            var legacyFound = Directory.Exists(LegacyProjectRoot);
            ImportLegacyCheckBox.IsEnabled = legacyFound;
            ImportLegacyCheckBox.IsChecked = false;
            LegacyStatusText.Text = legacyFound
                ? "Đã phát hiện project cũ. Mặc định ứng dụng sẽ sao chép và giữ nguyên source."
                : "Không phát hiện project legacy tại C:\\Android\\Auto_Build_WK.";

            var runtimeChecks = new[]
            {
                ("Python", File.Exists(Path.Combine(_layout.PythonRoot, "python.exe"))),
                ("Java", File.Exists(Path.Combine(_layout.JavaRoot, "bin", "java.exe"))),
                ("Backend", File.Exists(Path.Combine(_layout.ScriptsRoot, "studio_server.py"))),
            };
            FirstRunChecksText.Text = $"Ổ C còn trống: {freeGiB:F1} GiB\n"
                + string.Join("  ·  ", runtimeChecks.Select(item => $"{item.Item1}: {(item.Item2 ? "OK" : "thiếu")}"));
            var missingRuntime = runtimeChecks.Where(item => !item.Item2).Select(item => item.Item1).ToArray();
            FirstRunInfo.Severity = freeGiB < 20 || missingRuntime.Length > 0
                ? InfoBarSeverity.Warning
                : InfoBarSeverity.Success;
            FirstRunInfo.Title = freeGiB < 20
                ? "Dung lượng ổ C thấp"
                : missingRuntime.Length > 0
                    ? "Bộ runtime chưa đầy đủ"
                    : "Hệ thống sẵn sàng";
            FirstRunInfo.Message = missingRuntime.Length > 0
                ? "Installer/publish script cần bổ sung: " + string.Join(", ", missingRuntime)
                : "Có thể hoàn tất thiết lập và khởi động giao diện native.";
        }
        catch (Exception exception)
        {
            FirstRunInfo.Severity = InfoBarSeverity.Error;
            FirstRunInfo.Title = "Không thể ghi vào C:\\WukongROMStudio";
            FirstRunInfo.Message = exception.Message;
            CompleteFirstRunButton.IsEnabled = false;
        }
    }

    private void AppWindowChanged(AppWindow sender, AppWindowChangedEventArgs args)
    {
        if (!args.DidSizeChange || sender.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Maximized })
        {
            return;
        }
        var width = Math.Max(900, sender.Size.Width);
        var height = Math.Max(600, sender.Size.Height);
        if (width != sender.Size.Width || height != sender.Size.Height)
        {
            sender.Resize(new Windows.Graphics.SizeInt32(width, height));
        }
    }

    private async Task InitializeStudioAsync()
    {
        FirstRunPanel.Visibility = Visibility.Collapsed;
        StartupProgressRing.IsActive = true;
        StartupPanel.Visibility = Visibility.Visible;
        ErrorPanel.Visibility = Visibility.Collapsed;
        NativeStudio.Visibility = Visibility.Collapsed;
        HostStatusText.Text = "Đang khởi động...";
        try
        {
            _layout.EnsureWritableDirectories();
            new TelegramSecretStore(_layout).TryImportLegacyEnvironment(LegacyTelegramEnvironmentPath);
            _backend = new BackendHost(_layout);
            await _backend.StartAsync(_lifetime.Token);
            if (_backend.ApiClient is null)
            {
                throw new InvalidOperationException("Backend đã khởi động nhưng API client chưa sẵn sàng.");
            }
            await NativeStudio.InitializeAsync(
                this,
                _backend.ApiClient,
                _layout,
                RestartBackendAsync,
                ApplyWindowTheme,
                ApplyWindowLocale,
                _lifetime.Token);
            NativeStudio.Visibility = Visibility.Visible;
            await ApplyPendingActivationAsync();
            HostStatusText.Text = "Sẵn sàng";
            StartupProgressRing.IsActive = false;
            StartupPanel.Visibility = Visibility.Collapsed;
            StartStatusPolling();
            WritePostUpdateHealthMarker();
        }
        catch (Exception exception)
        {
            HostStatusText.Text = "Lỗi runtime";
            ErrorText.Text = exception.Message;
            StartupProgressRing.IsActive = false;
            StartupPanel.Visibility = Visibility.Collapsed;
            NativeStudio.Visibility = Visibility.Collapsed;
            ErrorPanel.Visibility = Visibility.Visible;
        }
    }

    private void AppendHostLog(string message)
    {
        try
        {
            Directory.CreateDirectory(_layout.LogsRoot);
            File.AppendAllText(
                _layout.HostLogPath,
                $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz}] {message}{Environment.NewLine}");
        }
        catch
        {
        }
    }

    private object OpenManagedPath(string path)
    {
        if (!_layout.IsManagedPath(path))
        {
            throw new InvalidOperationException("Đường dẫn nằm ngoài C:\\WukongROMStudio.");
        }
        var fullPath = Path.GetFullPath(path);
        var authorized = _authorizedOpenPaths.Any(root =>
            fullPath.Equals(root, StringComparison.OrdinalIgnoreCase)
            || fullPath.StartsWith(Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase));
        if (!authorized)
        {
            throw new InvalidOperationException("Đường dẫn chưa được backend xác nhận để mở.");
        }
        if (!File.Exists(fullPath) && !Directory.Exists(fullPath))
        {
            Directory.CreateDirectory(fullPath);
        }
        var arguments = File.Exists(fullPath) ? $"/select,\"{fullPath}\"" : $"\"{fullPath}\"";
        Process.Start(new ProcessStartInfo("explorer.exe", arguments) { UseShellExecute = true });
        return new { ok = true };
    }

    private void SaveTelegram(string token, string chatId)
    {
        if (token.Length < 20 || string.IsNullOrWhiteSpace(chatId))
        {
            throw new InvalidDataException("Telegram token hoặc chat ID không hợp lệ.");
        }
        new TelegramSecretStore(_layout).Save(new TelegramCredentials(token, chatId));
    }

    private async Task RestartBackendAsync()
    {
        if (_backend?.ApiClient is not null && (await _backend.ApiClient.GetActiveJobsAsync()).Count > 0)
        {
            throw new InvalidOperationException("Không thể restart backend khi build đang chạy.");
        }
        if (_backend is not null)
        {
            NativeStudio.Stop();
            await _backend.DisposeAsync();
        }
        _backend = new BackendHost(_layout);
        await _backend.StartAsync(_lifetime.Token);
        if (_backend.ApiClient is null)
        {
            throw new InvalidOperationException("Backend đã restart nhưng API client chưa sẵn sàng.");
        }
        await NativeStudio.InitializeAsync(
            this,
            _backend.ApiClient,
            _layout,
            RestartBackendAsync,
            ApplyWindowTheme,
            ApplyWindowLocale,
            _lifetime.Token);
        NativeStudio.Visibility = Visibility.Visible;
    }

    private void StartStatusPolling()
    {
        _statusTimer?.Stop();
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _statusTimer.Tick += PollStatus;
        _statusTimer.Start();
    }

    private void UpdateStatusPollingInterval()
    {
        if (_statusTimer is null)
        {
            return;
        }
        var interval = _windowActive || _activeJob is not null
            ? TimeSpan.FromSeconds(2)
            : TimeSpan.FromSeconds(10);
        if (_statusTimer.Interval != interval)
        {
            _statusTimer.Interval = interval;
        }
    }

    private async void PollStatus(object? sender, object e)
    {
        if (_polling
            || _backend?.ApiClient is null
            || (_windowActive && NativeStudio.Visibility == Visibility.Visible))
        {
            return;
        }
        _polling = true;
        try
        {
            var jobs = await _backend.ApiClient.GetJobsAsync(_lifetime.Token);
            ApplyJobsSnapshot(jobs);
        }
        catch (Exception exception) when (exception is HttpRequestException or JsonException)
        {
            HostStatusText.Text = "Mất kết nối backend";
            _taskbarProgress?.SetError();
        }
        finally
        {
            _polling = false;
            UpdateStatusPollingInterval();
        }
    }

    private void ApplyJobsSnapshot(IReadOnlyList<StudioJob> jobs)
    {
        foreach (var output in jobs.Select(job => job.OutputZip).Where(path => !string.IsNullOrWhiteSpace(path)))
        {
            _authorizedOpenPaths.Add(Path.GetFullPath(output!));
        }
        _activeJob = jobs.FirstOrDefault(job => job.Status is "queued" or "running" or "packaging");
        if (_activeJob is not null)
        {
            var progressText = _activeJob.Progress is int progress ? $" · {progress}%" : string.Empty;
            HostStatusText.Text = $"{_activeJob.VersionName} · {_activeJob.CurrentStep ?? _activeJob.Status}{progressText}";
            TrayIcon.ToolTipText = HostStatusText.Text;
            _trayJobItem.Text = HostStatusText.Text;
            _trayCancelItem.IsEnabled = true;
            if (_activeJob.Status == "queued")
            {
                _taskbarProgress?.SetPaused();
            }
            else if (_activeJob.Progress is int packageProgress)
            {
                _taskbarProgress?.SetValue((ulong)packageProgress, 100);
            }
            else
            {
                _taskbarProgress?.SetIndeterminate();
            }
        }
        else
        {
            HostStatusText.Text = "Sẵn sàng";
            _taskbarProgress?.Clear();
            TrayIcon.ToolTipText = "Wukong ROM Studio";
            _trayJobItem.Text = "Không có build đang chạy";
            _trayCancelItem.IsEnabled = false;
        }

        foreach (var job in jobs)
        {
            if (_knownJobStatuses.TryGetValue(job.Id, out var previous)
                && previous is not "success"
                && job.Status == "success")
            {
                var artifact = string.IsNullOrWhiteSpace(job.OutputZip) ? string.Empty : $"\n{job.OutputZip}";
                ShowBuildCompletionNotification(job, artifact);
            }
            _knownJobStatuses[job.Id] = job.Status;
        }
    }

    private void ShowBuildCompletionNotification(StudioJob job, string artifact)
    {
        var title = SecurityElement.Escape($"{job.VersionName} đã hoàn tất") ?? "Wukong ROM Studio";
        var body = SecurityElement.Escape(string.IsNullOrWhiteSpace(job.OutputZip)
            ? "ROM ZIP đã được kiểm tra thành công."
            : job.OutputZip) ?? string.Empty;
        try
        {
            if (!AppNotificationManager.IsSupported())
            {
                throw new InvalidOperationException("Windows app notifications are unavailable.");
            }
            var launch = $"wukongstudio://job/{Uri.EscapeDataString(job.Id)}";
            var xml = $"<toast launch=\"{launch}\"><visual><binding template=\"ToastGeneric\"><text>{title}</text><text>{body}</text></binding></visual></toast>";
            AppNotificationManager.Default.Show(new AppNotification(xml));
        }
        catch
        {
            TrayIcon.ShowNotification(
                "Wukong ROM Studio",
                $"{job.VersionName} đã build thành công.{artifact}",
                NotificationIcon.Info);
        }
    }

    private async void AppWindowClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        SaveWindowSettings();
        if (_allowClose)
        {
            return;
        }
        args.Cancel = true;
        var active = _backend?.ApiClient is null
            ? []
            : await _backend.ApiClient.GetActiveJobsAsync();
        if (active.Count == 0)
        {
            await ExitApplicationAsync(cancelActiveJobs: false);
            return;
        }

        var dialog = new ContentDialog
        {
            XamlRoot = Content.XamlRoot,
            Title = "Build vẫn đang chạy",
            Content = "Bạn có thể tiếp tục chạy nền, hủy build và thoát, hoặc quay lại.",
            PrimaryButtonText = "Tiếp tục chạy nền",
            SecondaryButtonText = "Hủy build và thoát",
            CloseButtonText = "Quay lại",
            DefaultButton = ContentDialogButton.Primary,
        };
        var result = await dialog.ShowAsync();
        if (result == ContentDialogResult.Primary)
        {
            _appWindow?.Hide();
        }
        else if (result == ContentDialogResult.Secondary)
        {
            await ExitApplicationAsync(cancelActiveJobs: true);
        }
    }

    private void SaveWindowSettings()
    {
        if (_appWindow is null)
        {
            return;
        }
        var current = DesktopSettings.Load(_layout);
        if (_appWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Minimized })
        {
            current.Save(_layout);
            return;
        }
        var maximized = _appWindow.Presenter is OverlappedPresenter presenter
            && presenter.State == OverlappedPresenterState.Maximized;
        (current with
        {
            WindowWidth = _appWindow.Size.Width,
            WindowHeight = _appWindow.Size.Height,
            WindowX = _appWindow.Position.X,
            WindowY = _appWindow.Position.Y,
            Maximized = maximized,
        }).Save(_layout);
    }

    private void ApplyWindowTheme(ElementTheme theme)
    {
        WindowRoot.RequestedTheme = theme;
        UpdateTitleBarTheme(WindowRoot.ActualTheme);
    }

    private void WindowRootActualThemeChanged(FrameworkElement sender, object args) =>
        UpdateTitleBarTheme(WindowRoot.ActualTheme);

    private void UpdateTitleBarTheme(ElementTheme theme)
    {
        if (_appWindow is null)
        {
            return;
        }
        var dark = theme == ElementTheme.Dark;
        _appWindow.TitleBar.ButtonForegroundColor = dark
            ? Windows.UI.Color.FromArgb(255, 238, 243, 248)
            : Windows.UI.Color.FromArgb(255, 24, 24, 24);
        _appWindow.TitleBar.ButtonHoverForegroundColor = dark
            ? Windows.UI.Color.FromArgb(255, 255, 255, 255)
            : Windows.UI.Color.FromArgb(255, 0, 0, 0);
        _appWindow.TitleBar.ButtonHoverBackgroundColor = dark
            ? Windows.UI.Color.FromArgb(255, 48, 58, 70)
            : Windows.UI.Color.FromArgb(255, 224, 224, 224);
        _appWindow.TitleBar.ButtonPressedBackgroundColor = dark
            ? Windows.UI.Color.FromArgb(255, 59, 70, 84)
            : Windows.UI.Color.FromArgb(255, 208, 208, 208);
    }

    private static ElementTheme ThemePreference(string preference) => preference switch
    {
        "dark" => ElementTheme.Dark,
        "light" => ElementTheme.Light,
        _ => ElementTheme.Default,
    };

    private void ApplyWindowLocale(string locale)
    {
        var english = string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase);
        UpdateButton.Content = english ? "Updates" : "Cập nhật";
        OpenOutputButton.Content = english ? "Open output" : "Mở output";
    }

    public void HandleActivation(Uri? uri)
    {
        RestoreWindow();
        if (uri?.Host.Equals("health", StringComparison.OrdinalIgnoreCase) == true)
        {
            _pendingHealthToken = uri.AbsolutePath.Trim('/');
            WritePostUpdateHealthMarker();
            return;
        }
        if (uri?.Host.Equals("rollback", StringComparison.OrdinalIgnoreCase) == true)
        {
            _pendingRollbackNotification = true;
            WritePostUpdateHealthMarker();
            return;
        }
        _pendingActivationUri = uri;
        _ = ApplyPendingActivationAsync();
    }

    private async Task ApplyPendingActivationAsync()
    {
        var uri = _pendingActivationUri;
        if (uri is null || _backend?.ApiClient is null)
        {
            return;
        }
        var jobId = uri.Host.Equals("job", StringComparison.OrdinalIgnoreCase)
            ? uri.AbsolutePath.Trim('/')
            : string.Empty;
        if (jobId.Length > 0)
        {
            try
            {
                await NativeStudio.SelectJobAsync(jobId);
            }
            catch (Exception exception)
            {
                AppendHostLog($"Could not activate job '{jobId}': {exception.Message}");
            }
        }
        _pendingActivationUri = null;
    }

    private void RestoreWindow()
    {
        if (_appWindow?.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Minimized } presenter)
        {
            presenter.Restore();
        }
        _appWindow?.Show();
        Activate();
    }

    private static bool IntersectsDisplay(int x, int y, int width, int height)
    {
        var rect = new NativeRect
        {
            Left = x,
            Top = y,
            Right = (int)Math.Clamp((long)x + width, int.MinValue, int.MaxValue),
            Bottom = (int)Math.Clamp((long)y + height, int.MinValue, int.MaxValue),
        };
        return MonitorFromRect(ref rect, MonitorDefaultToNull) != IntPtr.Zero;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeRect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromRect(ref NativeRect rect, uint flags);

    private async Task ExitApplicationAsync(bool cancelActiveJobs)
    {
        _allowClose = true;
        _statusTimer?.Stop();
        NativeStudio.Stop();
        _lifetime.Cancel();
        if (_backend is not null)
        {
            await _backend.StopAsync(cancelActiveJobs);
            await _backend.DisposeAsync();
        }
        TrayIcon.Dispose();
        Close();
    }

    private async void SelectContentPacksClick(object sender, RoutedEventArgs e)
    {
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.Downloads };
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        var files = await picker.PickMultipleFilesAsync();
        _selectedContentPacks.Clear();
        _selectedContentPacks.AddRange(files.Select(file => file.Path));
        SelectedPacksText.Text = _selectedContentPacks.Count == 0
            ? "Chưa chọn pack bổ sung."
            : string.Join("\n", _selectedContentPacks.Select(Path.GetFileName));
    }

    private async void CompleteFirstRunClick(object sender, RoutedEventArgs e)
    {
        if (_firstRunBusy)
        {
            return;
        }
        _firstRunBusy = true;
        CompleteFirstRunButton.IsEnabled = false;
        FirstRunProgress.Visibility = Visibility.Visible;
        try
        {
            var token = TelegramTokenBox.Password.Trim();
            var chatId = TelegramChatIdBox.Text.Trim();
            if (token.Length > 0 || chatId.Length > 0)
            {
                SaveTelegram(token, chatId);
            }

            if (ImportLegacyCheckBox.IsChecked == true)
            {
                EnsureMigrationDiskSpace();
                FirstRunProgressText.Text = "Đang nhập content từ project cũ...";
                var progress = new Progress<LegacyMigrationProgress>(item =>
                    FirstRunProgressText.Text = $"{item.Item}: {item.FilesCompleted}/{item.TotalFiles} file");
                await new LegacyMigrationService(_layout).ImportAsync(
                    LegacyProjectRoot,
                    LegacyMigrationService.DefaultItems,
                    MoveLegacyCheckBox.IsChecked == true,
                    progress,
                    _lifetime.Token);
            }

            var packService = new ContentPackService(_layout);
            foreach (var package in _selectedContentPacks)
            {
                FirstRunProgressText.Text = $"Đang kiểm tra và cài {Path.GetFileName(package)}...";
                await packService.InstallAsync(package, new Version(1, 0, 0), _lifetime.Token);
            }

            WriteFirstRunMarker();
            FirstRunProgressText.Text = "Thiết lập hoàn tất. Đang khởi động giao diện native...";
            await InitializeStudioAsync();
        }
        catch (Exception exception)
        {
            FirstRunInfo.Severity = InfoBarSeverity.Error;
            FirstRunInfo.Title = "Thiết lập chưa hoàn tất";
            FirstRunInfo.Message = exception.Message;
            FirstRunProgressText.Text = string.Empty;
        }
        finally
        {
            FirstRunProgress.Visibility = Visibility.Collapsed;
            CompleteFirstRunButton.IsEnabled = true;
            _firstRunBusy = false;
        }
    }

    private void EnsureMigrationDiskSpace()
    {
        var required = LegacyMigrationService.DefaultItems
            .Select(item => Path.Combine(LegacyProjectRoot, item.SourceName))
            .Where(Directory.Exists)
            .Sum(path => Directory.EnumerateFiles(path, "*", SearchOption.AllDirectories).Sum(file => new FileInfo(file).Length));
        var drive = new DriveInfo(Path.GetPathRoot(_layout.InstallRoot)!);
        if (drive.AvailableFreeSpace < required + 2L * 1024 * 1024 * 1024)
        {
            throw new IOException("Không đủ dung lượng để staging và xác minh dữ liệu legacy.");
        }
    }

    private void WriteFirstRunMarker()
    {
        var temporary = _layout.FirstRunPath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(new
        {
            schemaVersion = 1,
            completedAt = DateTimeOffset.UtcNow,
            studioVersion = "1.0.0",
        }));
        File.Move(temporary, _layout.FirstRunPath, overwrite: true);
    }

    private async void CheckUpdateClick(object sender, RoutedEventArgs e)
    {
        try
        {
            if (_backend?.ApiClient is not null && (await _backend.ApiClient.GetActiveJobsAsync()).Count > 0)
            {
                throw new InvalidOperationException("Không thể cập nhật khi build hoặc đóng ZIP đang chạy.");
            }

            var settings = DesktopSettings.Load(_layout);
            var urlBox = new TextBox
            {
                Header = "URL update manifest HTTPS",
                Text = settings.UpdateManifestUrl ?? string.Empty,
                MinWidth = 520,
                PlaceholderText = "https://example.com/wukong/update-manifest.json",
            };
            var dialog = new ContentDialog
            {
                XamlRoot = Content.XamlRoot,
                Title = "Kiểm tra cập nhật",
                Content = urlBox,
                PrimaryButtonText = "Kiểm tra",
                CloseButtonText = "Hủy",
                DefaultButton = ContentDialogButton.Primary,
            };
            if (await dialog.ShowAsync() != ContentDialogResult.Primary)
            {
                return;
            }
            if (!Uri.TryCreate(urlBox.Text.Trim(), UriKind.Absolute, out var manifestUri)
                || manifestUri.Scheme != Uri.UriSchemeHttps)
            {
                throw new InvalidDataException("Update manifest phải dùng URL HTTPS hợp lệ.");
            }
            (settings with { UpdateManifestUrl = manifestUri.AbsoluteUri }).Save(_layout);

            HostStatusText.Text = "Đang kiểm tra cập nhật...";
            _taskbarProgress?.SetIndeterminate();
            using var updateService = new UpdateService(_layout);
            var manifest = await updateService.GetManifestAsync(manifestUri, _lifetime.Token);
            var current = typeof(MainWindow).Assembly.GetName().Version ?? new Version(1, 0, 0);
            var available = Version.Parse(manifest.Version);
            if (available <= current)
            {
                await ShowMessageAsync("Wukong Studio đã mới nhất", $"Phiên bản hiện tại: {current.ToString(3)}");
                return;
            }

            var confirm = new ContentDialog
            {
                XamlRoot = Content.XamlRoot,
                Title = $"Cập nhật lên {manifest.Version}",
                Content = "Installer sẽ được tải và kiểm tra SHA-256. App sẽ thoát, backup App/Runtime, cài bản mới và tự rollback nếu health check thất bại.",
                PrimaryButtonText = "Tải và cập nhật",
                CloseButtonText = "Để sau",
                DefaultButton = ContentDialogButton.Primary,
            };
            if (await confirm.ShowAsync() != ContentDialogResult.Primary)
            {
                return;
            }

            HostStatusText.Text = "Đang tải bản cập nhật...";
            var installer = await updateService.DownloadAsync(manifest, _lifetime.Token);
            await LaunchUpdaterAndExitAsync(installer);
        }
        catch (Exception exception)
        {
            _taskbarProgress?.SetError();
            HostStatusText.Text = "Cập nhật thất bại";
            await ShowMessageAsync("Không thể cập nhật", exception.Message);
        }
    }

    private async Task LaunchUpdaterAndExitAsync(string installerPath)
    {
        var sourceScript = Path.Combine(_layout.ScriptsRoot, "desktop-updater.ps1");
        if (!File.Exists(sourceScript))
        {
            throw new FileNotFoundException("Desktop updater script is missing.", sourceScript);
        }
        Directory.CreateDirectory(_layout.UpdatesRoot);
        var updaterScript = Path.Combine(_layout.UpdatesRoot, "desktop-updater.ps1");
        File.Copy(sourceScript, updaterScript, overwrite: true);
        var healthToken = Convert.ToHexString(RandomNumberGenerator.GetBytes(24)).ToLowerInvariant();
        var startInfo = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = _layout.UpdatesRoot,
        };
        foreach (var argument in new[]
        {
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", updaterScript,
            "-InstallerPath", installerPath,
            "-InstallRoot", _layout.InstallRoot,
            "-ParentPid", Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "-HealthToken", healthToken,
        })
        {
            startInfo.ArgumentList.Add(argument);
        }
        if (Process.Start(startInfo) is null)
        {
            throw new InvalidOperationException("Không thể khởi động update helper.");
        }
        await ExitApplicationAsync(cancelActiveJobs: false);
    }

    private void WritePostUpdateHealthMarker()
    {
        var arguments = Environment.GetCommandLineArgs();
        var index = Array.IndexOf(arguments, "--post-update-token");
        var token = _pendingHealthToken;
        if (string.IsNullOrWhiteSpace(token) && index >= 0 && index + 1 < arguments.Length)
        {
            token = arguments[index + 1];
        }
        if (string.IsNullOrWhiteSpace(token))
        {
            if (_pendingRollbackNotification || arguments.Contains("--update-rollback", StringComparer.Ordinal))
            {
                TrayIcon.ShowNotification(
                    "Wukong ROM Studio",
                    "Bản cập nhật không qua health check. App đã rollback về phiên bản trước.",
                    NotificationIcon.Warning);
                _pendingRollbackNotification = false;
            }
            return;
        }
        if (!System.Text.RegularExpressions.Regex.IsMatch(token, "^[A-Za-z0-9_-]{16,128}$"))
        {
            return;
        }
        Directory.CreateDirectory(_layout.UpdatesRoot);
        var marker = Path.Combine(_layout.UpdatesRoot, $"health-{token}.ok");
        File.WriteAllText(marker, DateTimeOffset.UtcNow.ToString("O"));
        _pendingHealthToken = null;
    }

    private async Task ShowMessageAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = Content.XamlRoot,
            Title = title,
            Content = message,
            CloseButtonText = "Đóng",
        };
        await dialog.ShowAsync();
    }

    private void RestoreFromTray(object sender, RoutedEventArgs e) => RestoreWindow();
    private void OpenOutputFromTray(object sender, RoutedEventArgs e) => OpenManagedPath(_layout.OutputRoot);
    private async void CancelCurrentJobFromTray(object sender, RoutedEventArgs e)
    {
        if (_activeJob is not null && _backend?.ApiClient is not null)
        {
            await _backend.ApiClient.CancelJobAsync(_activeJob.Id);
        }
    }
    private async void ExitFromTray(object sender, RoutedEventArgs e) => await ExitApplicationAsync(cancelActiveJobs: true);
    private void OpenOutputClick(object sender, RoutedEventArgs e) => OpenManagedPath(_layout.OutputRoot);
    private void OpenLogsClick(object sender, RoutedEventArgs e) => OpenManagedPath(_layout.LogsRoot);
    private async void RetryClick(object sender, RoutedEventArgs e)
    {
        if (_backend is not null)
        {
            NativeStudio.Stop();
            await _backend.DisposeAsync();
        }
        await InitializeStudioAsync();
    }
    private async void ExitClick(object sender, RoutedEventArgs e) => await ExitApplicationAsync(cancelActiveJobs: true);
}
