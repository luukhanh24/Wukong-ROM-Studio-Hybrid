using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Text;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage.Pickers;
using WukongStudio.Core;

namespace WukongStudio.App;

public sealed partial class NativeStudioView : UserControl
{
    private static readonly HashSet<string> DefaultSteps = new(StringComparer.Ordinal)
    {
        "inspect_rom",
        "extract_payload",
        "unpack_partitions",
        "debloat",
        "apply_mod",
        "sync_configs",
        "repack_partitions",
        "repack_super",
        "patch_vbmeta",
        "package_zip",
    };

    private readonly List<RomQueueEntry> _romQueue = [];
    private readonly ObservableCollection<NativeJobItem> _jobItems = [];
    private readonly ObservableCollection<NativeRomRenameItem> _romRenameItems = [];
    private readonly List<StudioDevice> _devices = [];
    private readonly ObservableCollection<StudioDevice> _deviceItems = [];
    private readonly Dictionary<string, CheckBox> _modChecks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Border> _modCards = new(StringComparer.Ordinal);
    private readonly Dictionary<string, CheckBox> _stepChecks = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TextBox> _studioVersionBoxes = new(StringComparer.Ordinal);
    private readonly List<StudioBuildRecipe> _recipes = [];
    private readonly List<string> _debloatPaths = [];
    private readonly List<string> _defaultDebloatPaths = [];
    private readonly DispatcherTimer _pollTimer = new() { Interval = TimeSpan.FromSeconds(2) };
    private readonly DispatcherTimer _logPollTimer = new() { Interval = TimeSpan.FromMilliseconds(750) };
    private readonly DispatcherTimer _logSearchTimer = new() { Interval = TimeSpan.FromMilliseconds(250) };
    private BoundedLogBuffer _logBuffer = new(100_000);
    private DesktopSettings _desktopSettings = new();
    private Window? _owner;
    private StudioApiClient? _api;
    private StudioLayout? _layout;
    private Func<Task>? _restartBackend;
    private Action<ElementTheme>? _applyHostTheme;
    private Action<string>? _applyHostLocale;
    private StudioBuildRecipeStore? _recipeStore;
    private StudioBootstrap? _bootstrap;
    private StudioRomRenamePreview? _romRenamePreview;
    private string? _selectedJobId;
    private StudioJob? _selectedJob;
    private string? _selectedOutputPath;
    private string? _logJobId;
    private string _responsiveState = string.Empty;
    private string _presentationRemainder = string.Empty;
    private string? _lastPresentedLine;
    private int _presentedLineCount;
    private int _presentedWarningCount;
    private int _presentedErrorCount;
    private long _logOffset = -1;
    private string _renderedStepSignature = string.Empty;
    private int _knownSuccessfulJobs = -1;
    private bool _busy;
    private bool _polling;
    private bool _logPolling;
    private bool _logRenderDeferred;
    private bool _logScrollPending;
    private bool _configuring;
    private bool _deviceEditorLoading;
    private bool _deviceEditorDirty;
    private bool _deviceSelectionChanging;
    private bool _syncingJobSelection;
    private bool _initialized;
    private bool _contentSyncUploadedChanges;
    private string _contentSyncVisualState = string.Empty;
    private ContentSyncProgressSnapshot? _lastContentSyncProgress;
    private ContentSyncFolderSelection? _contentSyncFolderSelection;
    private CancellationTokenSource? _contentSyncCancellation;
    private bool _uiPollingActive = true;
    private string? _selectedDeviceOriginalProductName;
    private string? _layoutSourcePath;
    private DateTimeOffset _lastMetricsRefresh = DateTimeOffset.MinValue;
    private CancellationTokenSource? _hybridSourceProbeCancellation;
    private string? _hybridProbedDevice;

    public event Action<IReadOnlyList<StudioJob>>? JobsSnapshotChanged;

    public NativeStudioView()
    {
        InitializeComponent();
        JobsList.ItemsSource = _jobItems;
        RomRenamerList.ItemsSource = _romRenameItems;
        DevicesList.ItemsSource = _deviceItems;
        StudioNavigation.SelectedItem = StudioNavigation.MenuItems[0];
        _pollTimer.Tick += PollTimerTick;
        _logPollTimer.Tick += LogPollTimerTick;
        _logSearchTimer.Tick += LogSearchTimerTick;
        ModOptionsExpander.Expanding += (_, _) => ScheduleBuildSectionLayoutUpdate();
        ModOptionsExpander.Collapsed += (_, _) => ScheduleBuildSectionLayoutUpdate();
        PipelineStepsExpander.Expanding += (_, _) => ScheduleBuildSectionLayoutUpdate();
        PipelineStepsExpander.Collapsed += (_, _) => ScheduleBuildSectionLayoutUpdate();
        ActualThemeChanged += NativeStudioActualThemeChanged;
        Unloaded += (_, _) =>
        {
            _hybridSourceProbeCancellation?.Cancel();
            _contentSyncCancellation?.Cancel();
        };
    }

    public async Task InitializeAsync(
        Window owner,
        StudioApiClient api,
        StudioLayout layout,
        Func<Task> restartBackend,
        Action<ElementTheme> applyHostTheme,
        Action<string> applyHostLocale,
        CancellationToken cancellationToken = default)
    {
        _owner = owner;
        _api = api;
        _layout = layout;
        _restartBackend = restartBackend;
        _applyHostTheme = applyHostTheme;
        _applyHostLocale = applyHostLocale;
        _recipeStore = new StudioBuildRecipeStore(layout);
        _desktopSettings = DesktopSettings.Load(layout);
        ApplyDesktopSettings(_desktopSettings);
        InstallRootText.Text = layout.InstallRoot;
        WorkspacePathText.Text = layout.WorkspaceRoot;
        OutputPathText.Text = layout.OutputRoot;
        await LoadBootstrapAsync(cancellationToken);
        LoadRecipes(_desktopSettings.LastRecipeId);
        StudioPage.UpdateLayout();
        SetViewportContentWidth(StudioContent, StudioPage.ActualWidth);
        UpdateResponsiveLayout(StudioPage.ViewportWidth);
        StudioPage.ChangeView(null, 0, null, disableAnimation: true);
        _initialized = true;
        _uiPollingActive = true;
        _pollTimer.Start();
        _logPollTimer.Start();
    }

    public void Stop()
    {
        _initialized = false;
        _pollTimer.Stop();
        _logPollTimer.Stop();
        _logSearchTimer.Stop();
    }

    public void SetForegroundActive(bool active)
    {
        if (!_initialized || _uiPollingActive == active)
        {
            return;
        }
        _uiPollingActive = active;
        if (!active)
        {
            _pollTimer.Stop();
            _logPollTimer.Stop();
            return;
        }
        _pollTimer.Start();
        _logPollTimer.Start();
        _ = RefreshAfterResumeAsync();
    }

    private async Task RefreshAfterResumeAsync()
    {
        try
        {
            await RefreshJobsAsync();
            await RefreshSelectedJobAsync();
            await RefreshSelectedJobLogAsync();
        }
        catch (Exception exception) when (exception is HttpRequestException or JsonException)
        {
            SetBackendState("Mất kết nối", ready: false);
            BackendVersionText.Text = exception.Message;
        }
    }

    private void ApplyDesktopSettings(DesktopSettings settings)
    {
        _desktopSettings = settings;
        var theme = ThemePreference(settings.Theme);
        RequestedTheme = theme;
        _applyHostTheme?.Invoke(theme);
        _applyHostLocale?.Invoke(settings.Locale);
        _logPollTimer.Interval = TimeSpan.FromMilliseconds(settings.LogPollIntervalMs);
        FollowLogButton.IsChecked = settings.AutoScrollLogs;
        StudioNavigation.IsPaneOpen = settings.NavigationPaneOpen;
        ModOptionsExpander.IsExpanded = settings.ExpandModOptions;
        PipelineStepsExpander.IsExpanded = settings.ExpandPipelineSteps;
        DefaultAutoScrollCheckBox.IsChecked = settings.AutoScrollLogs;
        NavigationExpandedCheckBox.IsChecked = settings.NavigationPaneOpen;
        ExpandModsCheckBox.IsChecked = settings.ExpandModOptions;
        ExpandPipelineCheckBox.IsChecked = settings.ExpandPipelineSteps;
        ConsoleBufferBox.Value = settings.ConsoleMaxCharacters / 1000d;
        SelectComboByTag(LogRefreshCombo, settings.LogPollIntervalMs.ToString());
        SelectComboByTag(LanguageCombo, settings.Locale);
        SelectComboByTag(ThemeCombo, settings.Theme);

        if (_logBuffer.MaxCharacters != settings.ConsoleMaxCharacters)
        {
            var snapshot = _logBuffer.Snapshot();
            _logBuffer = new BoundedLogBuffer(settings.ConsoleMaxCharacters);
            _logBuffer.Append(snapshot);
            RenderFilteredLog();
        }
        ApplyLocalization();
    }

    public async Task SelectJobAsync(string jobId)
    {
        StudioNavigation.SelectedItem = StudioNavigation.MenuItems[0];
        if (!string.Equals(_selectedJobId, jobId, StringComparison.Ordinal))
        {
            ResetLogState(jobId);
        }
        _selectedJobId = jobId;
        await RefreshJobsAsync();
        SyncSelectedJobItem();
        await RefreshSelectedJobAsync();
        await RefreshSelectedJobLogAsync();
    }

    private async Task LoadBootstrapAsync(CancellationToken cancellationToken = default)
    {
        if (_api is null)
        {
            return;
        }
        SetBusy(true);
        try
        {
            _bootstrap = await _api.GetBootstrapAsync(cancellationToken);
            var health = await _api.GetHealthAsync(cancellationToken);
            SetBackendState(health?.Status == "ready" ? "Sẵn sàng" : health?.Status ?? "Không xác định", health?.Status == "ready");
            BackendVersionText.Text = health is null ? "-" : $"Studio {health.Version} · localhost";
            PopulateConfiguration();
            PopulateCatalog();
            PopulateDiagnostics(_bootstrap.Diagnostics);
            PopulateSettings(_bootstrap.Settings);
            PopulateArtifacts(_bootstrap.Artifacts);
            ReplaceJobs(_bootstrap.Jobs);
            UpdateQueueStats(_bootstrap.Jobs);
            _knownSuccessfulJobs = _bootstrap.Jobs.Count(job => job.Status == "success");
            await EnsureJobSelectionAsync(_bootstrap.Jobs);
            ApplyLocalization();
        }
        catch (Exception exception)
        {
            ShowMessage("Không thể tải dữ liệu Studio", exception.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void PopulateConfiguration()
    {
        if (_bootstrap is null)
        {
            return;
        }
        _configuring = true;
        try
        {
            ModVersionCombo.Items.Clear();
            foreach (var version in _bootstrap.ModVersions)
            {
                ModVersionCombo.Items.Add(new ComboBoxItem { Content = version, Tag = version });
            }
            if (!string.IsNullOrWhiteSpace(_desktopSettings.LastModVersion))
            {
                SelectComboByTag(ModVersionCombo, _desktopSettings.LastModVersion);
            }
            if (ModVersionCombo.SelectedItem is null && ModVersionCombo.Items.Count > 0)
            {
                ModVersionCombo.SelectedIndex = 0;
            }
            SelectComboByTag(PresetCombo, _bootstrap.Settings.DefaultPreset);
            SelectComboByTag(DefaultPresetCombo, _bootstrap.Settings.DefaultPreset);
            NotifyTelegramCheckBox.IsChecked = _bootstrap.Settings.NotifyTelegram;
            DefaultTelegramCheckBox.IsChecked = _bootstrap.Settings.NotifyTelegram;
            _defaultDebloatPaths.Clear();
            _defaultDebloatPaths.AddRange(_bootstrap.DefaultDebloatPaths ?? []);
            _debloatPaths.Clear();
            _debloatPaths.AddRange(_bootstrap.Settings.DebloatPaths ?? _defaultDebloatPaths);
            RebuildModOptions(applyPreset: true);
            RebuildStepOptions(applyPreset: true);
            UpdateSelectedStudioVersion();
            UpdateConfigurationSummaries();
        }
        finally
        {
            _configuring = false;
        }
    }

    private void RebuildModOptions(bool applyPreset)
    {
        var previousSelections = _modChecks
            .Where(item => item.Value.IsChecked == true)
            .Select(item => item.Key)
            .ToHashSet(StringComparer.Ordinal);
        ModsPanel.Children.Clear();
        ModsPanel.ColumnDefinitions.Clear();
        ModsPanel.RowDefinitions.Clear();
        _modChecks.Clear();
        _modCards.Clear();
        if (_bootstrap is null)
        {
            return;
        }
        var version = SelectedTag(ModVersionCombo) ?? _bootstrap.ModVersions.FirstOrDefault() ?? string.Empty;
        var mods = _bootstrap.ModsByVersion.TryGetValue(version, out var versionMods)
            ? versionMods
            : _bootstrap.Mods;
        var defaults = applyPreset
            ? DefaultMods(version, SelectedPreset()).ToHashSet(StringComparer.Ordinal)
            : previousSelections;
        for (var index = 0; index < mods.Count; index++)
        {
            var mod = mods[index];
            var description = ModDescription(mod);
            var check = new CheckBox
            {
                Content = new StackPanel
                {
                    Spacing = 2,
                    MinWidth = 0,
                    Children =
                    {
                        new TextBlock
                        {
                            Text = mod.Name,
                            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                            TextTrimming = TextTrimming.CharacterEllipsis,
                            MaxLines = 1,
                        },
                        new TextBlock
                        {
                            Text = description,
                            FontSize = 10,
                            Foreground = StudioBrush(95, 107, 122),
                            TextTrimming = TextTrimming.CharacterEllipsis,
                            MaxLines = 1,
                        },
                    },
                },
                Tag = mod.Name,
                IsEnabled = mod.Ready,
                IsChecked = defaults.Contains(mod.Name, StringComparer.Ordinal),
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                VerticalAlignment = VerticalAlignment.Center,
                MinWidth = 0,
            };
            var details = new List<string>();
            if (mod.Partitions is { Count: > 0 })
            {
                details.Add("Phân vùng: " + string.Join(", ", mod.Partitions));
            }
            if (mod.SpecialActions is { Count: > 0 })
            {
                details.AddRange(mod.SpecialActions);
            }
            if (!string.IsNullOrWhiteSpace(mod.BlockedReason))
            {
                details.Add(mod.BlockedReason);
            }
            ToolTipService.SetToolTip(check, details.Count == 0 ? "MOD sẵn sàng" : string.Join("\n", details));
            check.Checked += ConfigurationOptionChanged;
            check.Unchecked += ConfigurationOptionChanged;
            _modChecks[mod.Name] = check;
            var card = new Border
            {
                Background = StudioBrush(mod.Ready ? 255 : 247, mod.Ready ? 255 : 247, mod.Ready ? 255 : 247),
                BorderBrush = StudioBrush(221, 227, 234),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(10, 8, 10, 8),
                MinHeight = 58,
                MinWidth = 0,
                Tag = mod.Name,
                Child = check,
            };
            _modCards[mod.Name] = card;
            ModsPanel.Children.Add(card);
        }
        ApplyModFilter();
        RelayoutModCards();
        UpdateConfigurationSummaries();
    }

    private void RebuildStepOptions(bool applyPreset)
    {
        var previousSelections = _stepChecks
            .Where(item => item.Value.IsChecked == true)
            .Select(item => item.Key)
            .ToHashSet(StringComparer.Ordinal);
        StepsPanel.Children.Clear();
        _stepChecks.Clear();
        if (_bootstrap is null)
        {
            return;
        }
        var preset = SelectedPreset();
        for (var index = 0; index < _bootstrap.Steps.Count; index++)
        {
            var step = _bootstrap.Steps[index];
            var selected = applyPreset
                ? preset != "custom" && DefaultSteps.Contains(step.Id)
                : previousSelections.Contains(step.Id);
            if (step.Id == "notify_telegram")
            {
                selected = NotifyTelegramCheckBox.IsChecked == true;
            }
            var check = new CheckBox
            {
                Tag = step.Id,
                IsChecked = selected,
                IsEnabled = true,
                VerticalAlignment = VerticalAlignment.Center,
            };
            ToolTipService.SetToolTip(check, step.Required ? "Bước mặc định của pipeline" : "Bước tùy chọn");
            check.Checked += ConfigurationOptionChanged;
            check.Unchecked += ConfigurationOptionChanged;
            _stepChecks[step.Id] = check;
            var row = new Grid
            {
                ColumnSpacing = 9,
                ColumnDefinitions =
                {
                    new ColumnDefinition { Width = GridLength.Auto },
                    new ColumnDefinition { Width = GridLength.Auto },
                    new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) },
                    new ColumnDefinition { Width = GridLength.Auto },
                },
            };
            row.Children.Add(check);

            var indexBadge = new Border
            {
                Background = StudioBrush(234, 243, 252),
                CornerRadius = new CornerRadius(7),
                Padding = new Thickness(7, 4, 7, 4),
                VerticalAlignment = VerticalAlignment.Center,
                Child = new TextBlock
                {
                    Text = $"{index + 1:00}",
                    Foreground = StudioBrush(11, 107, 203),
                    FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas"),
                    FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                    FontSize = 11,
                },
            };
            Grid.SetColumn(indexBadge, 1);
            row.Children.Add(indexBadge);

            var description = new StackPanel
            {
                Spacing = 1,
                Children =
                {
                    new TextBlock
                    {
                        Text = TranslateStep(step.Id, step.Label),
                        FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                        TextWrapping = TextWrapping.Wrap,
                    },
                    new TextBlock
                    {
                        Text = StepDescription(step.Id),
                        FontSize = 10,
                        Foreground = StudioBrush(95, 107, 122),
                        TextWrapping = TextWrapping.Wrap,
                    },
                },
            };
            Grid.SetColumn(description, 2);
            row.Children.Add(description);

            FrameworkElement action;
            if (step.Id == "debloat")
            {
                action = new Button
                {
                    Content = $"Chỉnh danh sách · {_debloatPaths.Count}",
                    Tag = "debloat-editor",
                    Padding = new Thickness(10, 5, 10, 5),
                    VerticalAlignment = VerticalAlignment.Center,
                };
                ((Button)action).Click += EditDebloatPathsClick;
            }
            else
            {
                action = new Border
                {
                    Background = StudioBrush(step.Required ? 237 : 246, step.Required ? 247 : 247, step.Required ? 238 : 249),
                    CornerRadius = new CornerRadius(9),
                    Padding = new Thickness(8, 3, 8, 3),
                    VerticalAlignment = VerticalAlignment.Center,
                    Child = new TextBlock
                    {
                        Text = step.Required ? "Mặc định" : "Tùy chọn",
                        Foreground = StudioBrush(step.Required ? 16 : 95, step.Required ? 124 : 107, step.Required ? 16 : 122),
                        FontSize = 10,
                        FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                    },
                };
            }
            Grid.SetColumn(action, 3);
            row.Children.Add(action);

            StepsPanel.Children.Add(new Border
            {
                Background = StudioBrush(255, 255, 255),
                BorderBrush = StudioBrush(221, 227, 234),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(9, 7, 9, 7),
                Child = row,
            });
        }
        UpdateConfigurationSummaries();
    }

    private void PopulateCatalog()
    {
        ModsCatalogPanel.Children.Clear();
        if (_bootstrap is null)
        {
            return;
        }
        UpdateDeviceCatalog(
            _bootstrap.Devices,
            _bootstrap.DeviceCatalogPath,
            _selectedDeviceOriginalProductName,
            loadEditor: !_deviceEditorDirty);
        var totalMods = _bootstrap.ModVersions.Sum(version =>
            _bootstrap.ModsByVersion.TryGetValue(version, out var values) ? values.Count : 0);
        ModCountText.Text = $"{totalMods} MOD";
        ContentSummaryText.Text = $"{_bootstrap.ModVersions.Count} phiên bản MOD · {totalMods} lựa chọn · {_bootstrap.Devices.Count} thiết bị";
        foreach (var version in _bootstrap.ModVersions)
        {
            var mods = _bootstrap.ModsByVersion.TryGetValue(version, out var values) ? values : [];
            var ready = mods.Count(mod => mod.Ready);
            ModsCatalogPanel.Children.Add(CreateInfoCard(
                version,
                $"{ready}/{mods.Count} MOD sẵn sàng",
                string.Join(", ", mods.Where(mod => mod.Ready).Select(mod => mod.Name).Take(8))));
        }
    }

    private void UpdateDeviceCatalog(
        IReadOnlyList<StudioDevice> devices,
        string? storagePath,
        string? preferredProductName,
        bool loadEditor)
    {
        _devices.Clear();
        _devices.AddRange(devices);
        DeviceCatalogPathText.Text = string.IsNullOrWhiteSpace(storagePath)
            ? "devices_sizes.json"
            : storagePath;
        DeviceCountText.Text = $"{_devices.Count} thiết bị";
        SupportedDevicesText.Text = _devices.Count.ToString();
        ApplyDeviceFilter(preferredProductName, loadEditor);
    }

    private void ApplyDeviceFilter(string? preferredProductName = null, bool loadEditor = false)
    {
        var query = DeviceSearchBox.Text.Trim();
        var filtered = _devices
            .Where(device => query.Length == 0
                || device.Name.Contains(query, StringComparison.OrdinalIgnoreCase)
                || device.ProductName.Contains(query, StringComparison.OrdinalIgnoreCase)
                || device.Soc.Contains(query, StringComparison.OrdinalIgnoreCase))
            .OrderBy(device => device.Name, StringComparer.CurrentCultureIgnoreCase)
            .ThenBy(device => device.ProductName, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        var selectedProductName = preferredProductName ?? _selectedDeviceOriginalProductName;
        var selected = filtered.FirstOrDefault(device =>
            string.Equals(device.ProductName, selectedProductName, StringComparison.OrdinalIgnoreCase));
        if (selected is null && loadEditor)
        {
            selected = filtered.FirstOrDefault();
        }

        _deviceSelectionChanging = true;
        _deviceItems.Clear();
        foreach (var device in filtered)
        {
            _deviceItems.Add(device);
        }
        DevicesList.SelectedItem = selected;
        _deviceSelectionChanging = false;
        DeviceFilteredCountText.Text = $"{filtered.Length} mục";
        DuplicateDeviceButton.IsEnabled = selected is not null;

        if (loadEditor)
        {
            LoadDeviceEditor(selected, creating: selected is null);
        }
    }

    private void LoadDeviceEditor(StudioDevice? device, bool creating)
    {
        _deviceEditorLoading = true;
        _selectedDeviceOriginalProductName = creating ? null : device?.ProductName;
        DeviceProductNameBox.Text = device?.ProductName ?? string.Empty;
        DeviceDisplayNameBox.Text = device?.Name ?? string.Empty;
        DeviceSocBox.Text = device?.Soc ?? string.Empty;
        DeviceSuperSizeBox.Text = device is null ? string.Empty : device.SuperSize.ToString();
        DeviceGroupSizeBox.Text = device is null ? string.Empty : device.GroupSize.ToString();
        DevicePartitionsBox.Text = string.Join(Environment.NewLine, device?.Partitions ?? []);
        DeviceEditorModeText.Text = creating
            ? device is null ? "Thiết bị mới" : "Bản sao chưa lưu"
            : "Đang chỉnh sửa";
        SaveDeviceButton.Content = creating ? "Thêm thiết bị" : "Lưu thiết bị";
        DeleteDeviceButton.IsEnabled = !creating && device is not null;
        DeviceEditorInfoBar.IsOpen = false;
        LayoutAnalyzerInfoBar.IsOpen = false;
        LayoutAnalyzerStatusText.Text = device is null ? "Chưa chọn thiết bị" : "Sẵn sàng phân tích";
        LayoutScoreText.Text = "--";
        LayoutSizeSummaryText.Text = device is null
            ? "Chọn thiết bị để bắt đầu."
            : $"Catalog: super {FormatBytes(device.SuperSize)} · group {FormatBytes(device.GroupSize)}";
        LayoutGroupsPanel.Children.Clear();
        LayoutRecommendationText.Text = "Chưa có dữ liệu.";
        _deviceEditorDirty = creating && device is not null;
        _deviceEditorLoading = false;
        UpdateDeviceSizeSummary();
    }

    private void DeviceSearchChanged(object sender, TextChangedEventArgs e) => ApplyDeviceFilter();

    private async void DeviceSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_deviceSelectionChanging || DevicesList.SelectedItem is not StudioDevice selected)
        {
            DuplicateDeviceButton.IsEnabled = DevicesList.SelectedItem is StudioDevice;
            return;
        }
        if (_deviceEditorDirty
            && !string.Equals(
                selected.ProductName,
                _selectedDeviceOriginalProductName,
                StringComparison.OrdinalIgnoreCase))
        {
            var discard = await ConfirmDialogAsync(
                "Bỏ thay đổi chưa lưu?",
                "Các thông số đang chỉnh sửa chưa được lưu vào danh mục thiết bị.",
                "Bỏ thay đổi");
            if (!discard)
            {
                _deviceSelectionChanging = true;
                DevicesList.SelectedItem = _deviceItems.FirstOrDefault(device =>
                    string.Equals(
                        device.ProductName,
                        _selectedDeviceOriginalProductName,
                        StringComparison.OrdinalIgnoreCase));
                _deviceSelectionChanging = false;
                return;
            }
        }
        LoadDeviceEditor(selected, creating: false);
        DuplicateDeviceButton.IsEnabled = true;
    }

    private void DeviceEditorChanged(object sender, TextChangedEventArgs e)
    {
        if (_deviceEditorLoading)
        {
            return;
        }
        _deviceEditorDirty = true;
        DeviceEditorModeText.Text = _selectedDeviceOriginalProductName is null
            ? "Chưa lưu"
            : "Đã thay đổi";
        UpdateDeviceSizeSummary();
    }

    private void UpdateDeviceSizeSummary()
    {
        if (!long.TryParse(DeviceSuperSizeBox.Text.Trim(), out var superSize)
            || !long.TryParse(DeviceGroupSizeBox.Text.Trim(), out var groupSize)
            || superSize <= 0
            || groupSize <= 0)
        {
            DeviceSizeSummaryText.Text = "Nhập SuperSize và GroupSize bằng số byte nguyên dương.";
            return;
        }
        if (groupSize > superSize)
        {
            DeviceSizeSummaryText.Text = "GroupSize đang lớn hơn SuperSize và không thể lưu.";
            return;
        }
        var aligned = superSize % 4096 == 0 && groupSize % 4096 == 0;
        DeviceSizeSummaryText.Text =
            $"Super {FormatBytes(superSize)} · Group {FormatBytes(groupSize)} · Dự phòng {FormatBytes(superSize - groupSize)}"
            + (aligned ? string.Empty : " · Chưa căn chỉnh 4 KiB");
    }

    private StudioDevice ReadDeviceEditor()
    {
        var productName = DeviceProductNameBox.Text.Trim();
        var displayName = DeviceDisplayNameBox.Text.Trim();
        var soc = DeviceSocBox.Text.Trim();
        if (productName.Length == 0 || displayName.Length == 0 || soc.Length == 0)
        {
            throw new InvalidDataException("Product name, tên hiển thị và SoC không được để trống.");
        }
        if (!long.TryParse(DeviceSuperSizeBox.Text.Trim(), out var superSize)
            || !long.TryParse(DeviceGroupSizeBox.Text.Trim(), out var groupSize))
        {
            throw new InvalidDataException("SuperSize và GroupSize phải là số nguyên theo byte.");
        }
        var partitions = DevicePartitionsBox.Text
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return new StudioDevice(displayName, productName, soc, superSize, groupSize, partitions);
    }

    private async void AnalyzeCatalogLayoutClick(object sender, RoutedEventArgs e) =>
        await RunBusyActionAsync(() => AnalyzeLayoutAsync(sourcePath: null));

    private async void BrowseLayoutSourceClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null)
        {
            return;
        }
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.ComputerFolder };
        picker.FileTypeFilter.Add(".img");
        picker.FileTypeFilter.Add(".txt");
        picker.FileTypeFilter.Add(".json");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            var authorized = await _api.AuthorizeLayoutSourceAsync(file.Path);
            _layoutSourcePath = authorized.Path ?? throw new InvalidDataException("Backend không chấp nhận nguồn layout.");
            LayoutSourceBox.Text = _layoutSourcePath;
            await AnalyzeLayoutAsync(_layoutSourcePath);
        });
    }

    private async Task AnalyzeLayoutAsync(string? sourcePath)
    {
        if (_api is null)
        {
            return;
        }
        var device = ReadDeviceEditor();
        var result = await _api.AnalyzeLayoutAsync(device, sourcePath);
        RenderLayoutAnalysis(result);
    }

    private void RenderLayoutAnalysis(JsonElement result)
    {
        var status = JsonString(result, "status");
        var score = result.TryGetProperty("score", out var scoreValue) && scoreValue.TryGetInt32(out var parsedScore)
            ? parsedScore
            : 0;
        LayoutAnalyzerStatusText.Text = status;
        LayoutScoreText.Text = $"{score}/100";
        LayoutGroupsPanel.Children.Clear();

        var configured = result.GetProperty("configured");
        var configuredSuper = JsonLong(configured, "superSize");
        var configuredGroup = JsonLong(configured, "groupSize");
        var reserve = JsonLong(configured, "reserveBytes");
        var summary = $"Catalog: super {FormatBytes(configuredSuper)} · group {FormatBytes(configuredGroup)} · reserve {FormatBytes(reserve)}";

        if (result.TryGetProperty("actual", out var actual) && actual.ValueKind == JsonValueKind.Object)
        {
            summary += $"{Environment.NewLine}Thực tế: super {FormatBytes(JsonLong(actual, "superSize"))} · group {FormatBytes(JsonLong(actual, "groupSize"))}";
            if (actual.TryGetProperty("groups", out var groups) && groups.ValueKind == JsonValueKind.Array)
            {
                foreach (var group in groups.EnumerateArray())
                {
                    var name = JsonString(group, "name");
                    var used = JsonLong(group, "usedBytes");
                    var maximum = JsonLong(group, "maximumSize");
                    var percent = group.TryGetProperty("usagePercent", out var usage) && usage.TryGetDouble(out var parsedUsage)
                        ? parsedUsage
                        : 0;
                    var row = new Grid { ColumnDefinitions = { new ColumnDefinition(), new ColumnDefinition { Width = GridLength.Auto } }, ColumnSpacing = 10 };
                    var usagePanel = new StackPanel { Spacing = 3 };
                    usagePanel.Children.Add(new TextBlock
                    {
                        Text = $"{name} · {FormatBytes(used)} / {FormatBytes(maximum)}",
                        FontSize = 11,
                    });
                    usagePanel.Children.Add(new ProgressBar
                    {
                        Minimum = 0,
                        Maximum = 100,
                        Value = Math.Clamp(percent, 0, 100),
                    });
                    row.Children.Add(usagePanel);
                    var percentage = new TextBlock
                    {
                        Text = $"{percent:0.##}%",
                        FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas"),
                        VerticalAlignment = VerticalAlignment.Bottom,
                        Margin = new Thickness(0, 0, 0, 2),
                    };
                    Grid.SetColumn(percentage, 1);
                    row.Children.Add(percentage);
                    LayoutGroupsPanel.Children.Add(row);
                }
            }
        }
        else
        {
            LayoutGroupsPanel.Children.Add(new TextBlock
            {
                Text = "Chế độ catalog-only chưa có group usage thực tế.",
                Foreground = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 95, 107, 122)),
                TextWrapping = TextWrapping.Wrap,
            });
        }
        LayoutSizeSummaryText.Text = summary;

        var notes = new List<string>();
        AppendJsonStrings(notes, result, "errors", "Lỗi: ");
        AppendJsonStrings(notes, result, "warnings", "Cảnh báo: ");
        if (result.TryGetProperty("recommendation", out var recommendation)
            && recommendation.ValueKind == JsonValueKind.Object)
        {
            notes.Add($"Group tối thiểu đề xuất: {FormatBytes(JsonLong(recommendation, "minimumGroupSize"))}");
            notes.Add($"Headroom an toàn: {FormatBytes(JsonLong(recommendation, "safetyHeadroomBytes"))}");
        }
        LayoutRecommendationText.Text = notes.Count == 0 ? "Không phát hiện chênh lệch nguy hiểm." : string.Join(Environment.NewLine, notes);
        LayoutAnalyzerInfoBar.IsOpen = notes.Count > 0;
        LayoutAnalyzerInfoBar.Title = status == "error" ? "Layout có lỗi" : "Kết quả phân tích layout";
        LayoutAnalyzerInfoBar.Message = notes.Count == 0 ? "Cấu hình phù hợp với nguồn phân tích." : string.Join(" · ", notes);
        LayoutAnalyzerInfoBar.Severity = status == "error"
            ? InfoBarSeverity.Error
            : status == "warning" ? InfoBarSeverity.Warning : InfoBarSeverity.Success;
    }

    private static void AppendJsonStrings(ICollection<string> target, JsonElement source, string property, string prefix)
    {
        if (!source.TryGetProperty(property, out var values) || values.ValueKind != JsonValueKind.Array)
        {
            return;
        }
        foreach (var value in values.EnumerateArray())
        {
            if (value.ValueKind == JsonValueKind.String && value.GetString() is { Length: > 0 } text)
            {
                target.Add(prefix + text);
            }
        }
    }

    private async Task<bool> ConfirmDialogAsync(
        string title,
        string message,
        string primaryButtonText,
        bool destructive = false)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = new TextBlock
            {
                Text = message,
                TextWrapping = TextWrapping.Wrap,
                MaxWidth = 540,
            },
            PrimaryButtonText = primaryButtonText,
            CloseButtonText = Localized("Hủy"),
            DefaultButton = destructive ? ContentDialogButton.Close : ContentDialogButton.Primary,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private async Task<bool> ConfirmDeviceMutationAsync(
        string title,
        string message,
        string primaryButtonText)
    {
        var activeCount = 0;
        if (_api is not null)
        {
            try
            {
                activeCount = (await _api.GetActiveJobsAsync()).Count;
            }
            catch (HttpRequestException)
            {
            }
        }
        if (activeCount > 0)
        {
            await ConfirmDialogAsync(
                "Không thể sửa catalog khi build đang chạy",
                $"Hiện có {activeCount} job đang chờ hoặc đang chạy. Hãy đợi queue kết thúc hoặc hủy job trước khi thay đổi cấu hình thiết bị.",
                "Đã hiểu");
            return false;
        }
        return await ConfirmDialogAsync(title, message, primaryButtonText);
    }

    private async Task<bool> ConfirmDiscardDeviceChangesAsync()
    {
        return !_deviceEditorDirty || await ConfirmDialogAsync(
            "Bỏ thay đổi chưa lưu?",
            "Form thiết bị hiện có dữ liệu chưa được lưu.",
            "Bỏ thay đổi");
    }

    private async void AddDeviceClick(object sender, RoutedEventArgs e)
    {
        if (!await ConfirmDiscardDeviceChangesAsync())
        {
            return;
        }
        _deviceSelectionChanging = true;
        DevicesList.SelectedItem = null;
        _deviceSelectionChanging = false;
        DuplicateDeviceButton.IsEnabled = false;
        LoadDeviceEditor(null, creating: true);
        DeviceProductNameBox.Focus(FocusState.Programmatic);
    }

    private async void DuplicateDeviceClick(object sender, RoutedEventArgs e)
    {
        if (DevicesList.SelectedItem is not StudioDevice selected
            || !await ConfirmDiscardDeviceChangesAsync())
        {
            return;
        }
        _deviceSelectionChanging = true;
        DevicesList.SelectedItem = null;
        _deviceSelectionChanging = false;
        DuplicateDeviceButton.IsEnabled = false;
        LoadDeviceEditor(
            selected with { ProductName = $"{selected.ProductName}_COPY" },
            creating: true);
        DeviceProductNameBox.SelectAll();
        DeviceProductNameBox.Focus(FocusState.Programmatic);
    }

    private async void CancelDeviceEditClick(object sender, RoutedEventArgs e)
    {
        if (!await ConfirmDiscardDeviceChangesAsync())
        {
            return;
        }
        var selected = _devices.FirstOrDefault(device => string.Equals(
            device.ProductName,
            _selectedDeviceOriginalProductName,
            StringComparison.OrdinalIgnoreCase));
        if (selected is null)
        {
            selected = DevicesList.SelectedItem as StudioDevice ?? _devices.FirstOrDefault();
        }
        LoadDeviceEditor(selected, creating: selected is null);
    }

    private async void RefreshDevicesClick(object sender, RoutedEventArgs e)
    {
        if (!await ConfirmDiscardDeviceChangesAsync())
        {
            return;
        }
        await RefreshDevicesAsync();
    }

    private async Task RefreshDevicesAsync()
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _bootstrap is null)
            {
                return;
            }
            var response = await _api.GetDevicesAsync();
            _bootstrap = _bootstrap with
            {
                Devices = response.Devices,
                DeviceCatalogPath = response.StoragePath,
            };
            UpdateDeviceCatalog(
                response.Devices,
                response.StoragePath,
                _selectedDeviceOriginalProductName,
                loadEditor: true);
            var totalMods = _bootstrap.ModVersions.Sum(version =>
                _bootstrap.ModsByVersion.TryGetValue(version, out var values) ? values.Count : 0);
            ContentSummaryText.Text = $"{_bootstrap.ModVersions.Count} phiên bản MOD · {totalMods} lựa chọn · {response.Devices.Count} thiết bị";
        });
    }

    private async void SaveDeviceClick(object sender, RoutedEventArgs e)
    {
        StudioDevice device;
        try
        {
            device = ReadDeviceEditor();
        }
        catch (Exception exception) when (exception is InvalidDataException or FormatException)
        {
            DeviceEditorInfoBar.Title = "Thông số chưa hợp lệ";
            DeviceEditorInfoBar.Message = exception.Message;
            DeviceEditorInfoBar.Severity = InfoBarSeverity.Error;
            DeviceEditorInfoBar.IsOpen = true;
            return;
        }

        var creating = string.IsNullOrWhiteSpace(_selectedDeviceOriginalProductName);
        var action = creating ? "thêm" : "cập nhật";
        if (!await ConfirmDeviceMutationAsync(
                creating ? "Thêm thiết bị vào danh mục?" : "Lưu thay đổi thiết bị?",
                $"Xác nhận {action} {device.ProductName} ({device.Name}).\n\nSuper: {FormatBytes(device.SuperSize)}\nGroup: {FormatBytes(device.GroupSize)}\nLogical partition bổ sung: {device.Partitions?.Count ?? 0}",
                creating ? "Thêm thiết bị" : "Lưu thay đổi"))
        {
            return;
        }

        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _bootstrap is null)
            {
                return;
            }
            var response = creating
                ? await _api.CreateDeviceAsync(device)
                : await _api.UpdateDeviceAsync(_selectedDeviceOriginalProductName!, device);
            _bootstrap = _bootstrap with
            {
                Devices = response.Devices,
                DeviceCatalogPath = response.StoragePath,
            };
            UpdateDeviceCatalog(response.Devices, response.StoragePath, device.ProductName, loadEditor: true);
            ShowMessage(
                creating ? "Đã thêm thiết bị" : "Đã cập nhật thiết bị",
                $"{device.ProductName} đã được lưu vào danh mục JSON và đã tạo bản backup.",
                InfoBarSeverity.Success);
        });
    }

    private async void DeleteDeviceClick(object sender, RoutedEventArgs e)
    {
        if (_api is null
            || _bootstrap is null
            || string.IsNullOrWhiteSpace(_selectedDeviceOriginalProductName))
        {
            return;
        }
        var productName = _selectedDeviceOriginalProductName;
        var selected = _devices.FirstOrDefault(device => string.Equals(
            device.ProductName,
            productName,
            StringComparison.OrdinalIgnoreCase));
        if (!await ConfirmDeviceMutationAsync(
                "Xóa thiết bị khỏi danh mục?",
                $"Thiết bị {productName} ({selected?.Name ?? "không rõ"}) sẽ bị xóa khỏi cấu hình build. Thao tác này không xóa ROM hoặc artifact và có thể khôi phục từ thư mục Backups.",
                "Xóa thiết bị"))
        {
            return;
        }

        await RunBusyActionAsync(async () =>
        {
            var response = await _api.DeleteDeviceAsync(productName);
            _bootstrap = _bootstrap with
            {
                Devices = response.Devices,
                DeviceCatalogPath = response.StoragePath,
            };
            UpdateDeviceCatalog(response.Devices, response.StoragePath, null, loadEditor: true);
            ShowMessage(
                "Đã xóa thiết bị",
                $"{productName} đã được xóa khỏi danh mục. Bản backup JSON vẫn được giữ lại.",
                InfoBarSeverity.Success);
        });
    }

    private void PopulateDiagnostics(JsonElement diagnostics)
    {
        DiagnosticsPanel.Children.Clear();
        OverviewHealthPanel.Children.Clear();
        var python = JsonString(diagnostics, "python");
        var java = JsonString(diagnostics, "java");
        var sevenZip = JsonString(diagnostics, "sevenZip");
        var disk = diagnostics.TryGetProperty("disk", out var diskElement) ? diskElement : default;
        var free = JsonLong(disk, "free");
        var total = JsonLong(disk, "total");
        DiskFreeText.Text = free > 0 ? $"{FormatBytes(free)} trống / {FormatBytes(total)}" : "-";
        DiagnosticsPanel.Children.Add(CreateInfoCard("Python", python, "Runtime embedded"));
        DiagnosticsPanel.Children.Add(CreateInfoCard("Java", java, "JRE embedded"));
        DiagnosticsPanel.Children.Add(CreateInfoCard("7-Zip", sevenZip, "Đóng gói ROM ZIP"));
        DiagnosticsPanel.Children.Add(CreateInfoCard("Dung lượng trống", FormatBytes(free), _layout?.WorkspaceRoot ?? string.Empty));
        var binariesOk = false;
        if (diagnostics.TryGetProperty("binaries", out var binaries))
        {
            binariesOk = JsonObjectValuesTrue(binaries);
            foreach (var item in binaries.EnumerateObject())
            {
                DiagnosticsPanel.Children.Add(CreateInfoCard(
                    item.Name,
                    item.Value.GetBoolean() ? "Sẵn sàng" : "Thiếu binary",
                    item.Value.GetBoolean() ? "Runtime\\Bin\\Windows\\AMD64" : "Build sẽ bị chặn"));
            }
        }
        var packagesOk = diagnostics.TryGetProperty("packages", out var packages)
            && JsonObjectValuesTrue(packages);
        if (packages.ValueKind == JsonValueKind.Object)
        {
            foreach (var item in packages.EnumerateObject())
            {
                DiagnosticsPanel.Children.Add(CreateInfoCard(
                    $"Python · {item.Name}",
                    item.Value.GetBoolean() ? "Đã cài" : "Thiếu package",
                    item.Value.GetBoolean() ? "Runtime embedded" : "Preflight sẽ chặn build"));
            }
        }
        var apktoolReady = diagnostics.TryGetProperty("apktool", out var apktool)
            && apktool.ValueKind == JsonValueKind.Object
            && apktool.TryGetProperty("ready", out var apktoolStatus)
            && apktoolStatus.GetBoolean();
        DiagnosticsPanel.Children.Add(CreateInfoCard(
            "apktool · MOD JAR",
            apktoolReady ? "Sẵn sàng" : "Chưa sẵn sàng",
            JsonString(apktool, "path")));
        var telegram = diagnostics.TryGetProperty("telegramConfigured", out var configured) && configured.GetBoolean();
        NotifyTelegramCheckBox.IsEnabled = telegram;
        DefaultTelegramCheckBox.IsEnabled = telegram;
        DiagnosticsPanel.Children.Add(CreateInfoCard("Telegram", telegram ? "Đã cấu hình" : "Chưa cấu hình", "Secret được bảo vệ bằng DPAPI"));
        DiagnosticsPanel.Children.Add(CreateInfoCard(
            "Chuỗi cung ứng",
            "Binary chưa ký số",
            "MD5 chỉ kiểm tra toàn vẹn, không phải chữ ký tin cậy."));
        OverviewHealthPanel.Children.Add(CreateHealthRow("Binary build", binariesOk, binariesOk ? "Sẵn sàng" : "Thiếu binary bắt buộc"));
        OverviewHealthPanel.Children.Add(CreateHealthRow("Gói Python", packagesOk, packagesOk ? "Đầy đủ dependency" : "Thiếu dependency"));
        OverviewHealthPanel.Children.Add(CreateHealthRow("apktool · MOD JAR", apktoolReady, apktoolReady ? "Sẵn sàng vá framework" : "Chưa sẵn sàng"));
        OverviewHealthPanel.Children.Add(CreateHealthRow("Telegram", telegram, telegram ? "Đã cấu hình" : "Chưa cấu hình"));
    }

    private void PopulateSettings(StudioSettings settings)
    {
        RootsBox.Text = string.Join(Environment.NewLine, settings.Roots);
        SelectComboByTag(DefaultPresetCombo, settings.DefaultPreset);
        SelectComboByTag(ZipValidationModeCombo, settings.ZipValidationMode);
        DefaultTelegramCheckBox.IsChecked = settings.NotifyTelegram;
        StageCacheToggle.IsOn = settings.StageCacheEnabled;
        StageCacheMaxBox.Value = settings.StageCacheMaxGb;
        PopulateStudioVersionSettings(settings);
        if (_bootstrap?.StageCache is not null)
        {
            RenderCacheStatus(_bootstrap.StageCache);
        }
    }

    private void PopulateStudioVersionSettings(StudioSettings settings)
    {
        StudioVersionsPanel.Children.Clear();
        _studioVersionBoxes.Clear();
        var versions = settings.StudioVersions ?? new Dictionary<string, string>();
        foreach (var modVersion in _bootstrap?.ModVersions ?? [])
        {
            var box = new TextBox
            {
                Header = modVersion,
                Text = versions.TryGetValue(modVersion, out var value) ? value : DefaultStudioVersion(modVersion),
                PlaceholderText = DefaultStudioVersion(modVersion),
            };
            _studioVersionBoxes[modVersion] = box;
            StudioVersionsPanel.Children.Add(box);
        }
        UpdateSelectedStudioVersion();
    }

    private void UpdateSelectedStudioVersion()
    {
        if (_bootstrap is null)
        {
            return;
        }
        var modVersion = SelectedTag(ModVersionCombo);
        if (string.IsNullOrWhiteSpace(modVersion))
        {
            StudioVersionBox.Text = string.Empty;
            return;
        }
        var versions = _bootstrap.Settings.StudioVersions;
        StudioVersionBox.Text = versions is not null && versions.TryGetValue(modVersion, out var value)
            ? value
            : DefaultStudioVersion(modVersion);
    }

    private static string DefaultStudioVersion(string modVersion) =>
        string.Equals(modVersion, "ColorOS_16.0.8", StringComparison.OrdinalIgnoreCase) ? "V4.1" : "V3.4";

    private static string ValidateStudioVersion(string value)
    {
        var normalized = value.Trim().ToUpperInvariant();
        if (!Regex.IsMatch(normalized, "^V[0-9]+(?:\\.[0-9]+){1,3}$", RegexOptions.CultureInvariant))
        {
            throw new InvalidDataException("Số phiên bản phải có dạng V3.4, V4.1 hoặc tương tự.");
        }
        return normalized;
    }

    private Dictionary<string, string> ReadStudioVersionSettings(bool includeSelectedEditor)
    {
        var versions = new Dictionary<string, string>(
            _bootstrap?.Settings.StudioVersions ?? new Dictionary<string, string>(),
            StringComparer.Ordinal);
        foreach (var (modVersion, box) in _studioVersionBoxes)
        {
            versions[modVersion] = ValidateStudioVersion(box.Text);
        }
        if (includeSelectedEditor && SelectedTag(ModVersionCombo) is { Length: > 0 } selected)
        {
            versions[selected] = ValidateStudioVersion(StudioVersionBox.Text);
        }
        return versions;
    }

    private async Task SaveSelectedStudioVersionAsync(bool showMessage)
    {
        if (_api is null || _bootstrap is null || SelectedTag(ModVersionCombo) is not { Length: > 0 } selected)
        {
            return;
        }
        var versions = ReadStudioVersionSettings(includeSelectedEditor: true);
        var current = _bootstrap.Settings.StudioVersions;
        if (current is not null
            && current.TryGetValue(selected, out var currentValue)
            && string.Equals(currentValue, versions[selected], StringComparison.Ordinal))
        {
            return;
        }
        var saved = await _api.SaveSettingsAsync(_bootstrap.Settings with { StudioVersions = versions });
        _bootstrap = _bootstrap with { Settings = saved };
        PopulateStudioVersionSettings(saved);
        if (showMessage)
        {
            ShowMessage("Đã lưu phiên bản", $"{selected} sẽ dùng {versions[selected]} cho tên ZIP, info.txt và build.prop.", InfoBarSeverity.Success);
        }
    }

    private async void SaveStudioVersionClick(object sender, RoutedEventArgs e) =>
        await RunBusyActionAsync(() => SaveSelectedStudioVersionAsync(showMessage: true));

    private async void StudioVersionLostFocus(object sender, RoutedEventArgs e)
    {
        try
        {
            await SaveSelectedStudioVersionAsync(showMessage: false);
        }
        catch (Exception exception) when (exception is InvalidDataException or HttpRequestException or InvalidOperationException)
        {
            ShowMessage("Không thể lưu phiên bản", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void SaveStudioVersionsClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _bootstrap is null)
            {
                return;
            }
            var versions = ReadStudioVersionSettings(includeSelectedEditor: true);
            var saved = await _api.SaveSettingsAsync(_bootstrap.Settings with { StudioVersions = versions });
            _bootstrap = _bootstrap with { Settings = saved };
            PopulateStudioVersionSettings(saved);
            ShowMessage("Đã lưu số phiên bản", "Tên ZIP, info.txt và build.prop sẽ dùng cùng cấu hình mới.", InfoBarSeverity.Success);
        });
    }

    private void RenderCacheStatus(StudioCacheStatus cache)
    {
        CacheUsageText.Text = $"{FormatBytes(cache.TotalBytes)} / {FormatBytes(cache.MaximumBytes)}";
        CacheDetailText.Text = $"{cache.EntryCount} ROM · {cache.TotalHits} lượt tái sử dụng · {cache.Root}";
        MetricCacheText.Text = $"{cache.EntryCount} / {FormatBytes(cache.TotalBytes)}";
    }

    private async Task RefreshCacheAsync()
    {
        if (_api is null)
        {
            return;
        }
        RenderCacheStatus(await _api.GetCacheAsync());
    }

    private async void SaveCacheSettingsClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _bootstrap is null)
            {
                return;
            }
            var maximumCacheGb = double.IsNaN(StageCacheMaxBox.Value)
                ? 40
                : Math.Clamp((int)Math.Round(StageCacheMaxBox.Value), 5, 500);
            var saved = await _api.SaveSettingsAsync(_bootstrap.Settings with
            {
                StageCacheEnabled = StageCacheToggle.IsOn,
                StageCacheMaxGb = maximumCacheGb,
            });
            _bootstrap = _bootstrap with { Settings = saved };
            PopulateSettings(saved);
            await RefreshCacheAsync();
            ShowMessage("Đã lưu stage cache", $"Giới hạn cache: {maximumCacheGb} GiB.", InfoBarSeverity.Success);
        });
    }

    private async void ClearCacheClick(object sender, RoutedEventArgs e)
    {
        if (_api is null || _owner is null)
        {
            return;
        }
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "Xóa stage cache?",
            Content = "Payload đã extract sẽ bị xóa. ROM nguồn, workspace và artifact không bị ảnh hưởng.",
            PrimaryButtonText = "Xóa cache",
            CloseButtonText = "Hủy",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            RenderCacheStatus(await _api.ClearCacheAsync());
            ShowMessage("Đã xóa cache", "Stage cache đã được dọn sạch.", InfoBarSeverity.Success);
        });
    }

    private void PopulateArtifacts(IReadOnlyList<StudioArtifact> artifacts)
    {
        var validArtifacts = artifacts.Count(artifact => artifact.ArtifactExists);
        ValidArtifactsText.Text = validArtifacts.ToString();
        ArtifactCountText.Text = $"{artifacts.Count} artifact · {validArtifacts} hợp lệ";
        ArtifactsPanel.Children.Clear();
        if (artifacts.Count == 0)
        {
            ArtifactsPanel.Children.Add(new TextBlock { Text = "Chưa có artifact.", Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 102, 102, 102)) });
            return;
        }
        foreach (var artifact in artifacts)
        {
            var path = artifact.OutputZip ?? string.Empty;
            var open = new Button { Content = "Mở thư mục", IsEnabled = artifact.ArtifactExists && path.Length > 0 };
            open.Click += (_, _) => OpenArtifact(path);
            var copy = new Button { Content = "Copy đường dẫn", IsEnabled = path.Length > 0 };
            copy.Click += (_, _) => CopyToClipboard(path);
            var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            actions.Children.Add(copy);
            actions.Children.Add(open);
            var size = artifact.ArtifactExists && File.Exists(path) ? new FileInfo(path).Length : 0;
            var completed = DateTimeOffset.TryParse(artifact.FinishedAt, out var finished)
                ? finished.ToLocalTime().ToString("dd/MM/yyyy HH:mm")
                : "-";
            ArtifactsPanel.Children.Add(CreateInfoCard(
                artifact.VersionName,
                artifact.ArtifactExists
                    ? $"ZIP hợp lệ · {FormatBytes(size)} · {completed}"
                    : $"{StatusText(artifact.Status)} · Artifact không tồn tại",
                path,
                actions));
        }
    }

    private async Task AddRomAsync(string path)
    {
        if (_api is null || string.IsNullOrWhiteSpace(path))
        {
            return;
        }
        try
        {
            var authorized = await _api.AuthorizeRomAsync(path.Trim());
            if (string.IsNullOrWhiteSpace(authorized.Path))
            {
                return;
            }
            await AddAuthorizedRomsAsync([authorized.Path]);
            RomPathBox.Text = string.Empty;
        }
        catch (Exception exception)
        {
            ShowMessage("Không thể thêm ROM", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async Task AddAuthorizedRomsAsync(IEnumerable<string> paths)
    {
        var entries = new List<RomQueueEntry>();
        foreach (var path in paths.Where(path => !string.IsNullOrWhiteSpace(path)))
        {
            var entry = _romQueue.FirstOrDefault(item =>
                item.Path.Equals(path, StringComparison.OrdinalIgnoreCase));
            if (entry is null)
            {
                entry = new RomQueueEntry(path);
                _romQueue.Add(entry);
            }
            entries.Add(entry);
        }
        await InspectEntriesAsync(entries);
    }

    private async Task InspectEntriesAsync(IEnumerable<RomQueueEntry> entries)
    {
        var pending = entries.Distinct().ToArray();
        if (pending.Length == 0)
        {
            return;
        }
        foreach (var entry in pending)
        {
            entry.Status = "Đang kiểm tra...";
        }
        RenderRomQueue();
        using var concurrency = new SemaphoreSlim(2);
        await Task.WhenAll(pending.Select(async entry =>
        {
            await concurrency.WaitAsync();
            try
            {
                await InspectEntryAsync(entry, render: false);
            }
            finally
            {
                concurrency.Release();
            }
        }));
        RenderRomQueue();
    }

    private async Task InspectEntryAsync(RomQueueEntry entry, bool render = true)
    {
        if (_api is null)
        {
            return;
        }
        try
        {
            var signature = InspectSignature(entry);
            if (entry.Inspect is not null && entry.InspectSignature == signature)
            {
                return;
            }
            entry.Status = "Đang kiểm tra...";
            if (render)
            {
                RenderRomQueue();
            }
            entry.Inspect = await _api.InspectRomAsync(BuildSpec(entry));
            entry.InspectSignature = signature;
            entry.Status = entry.Inspect.Ok
                ? entry.Inspect.Warnings.Count > 0 ? "Sẵn sàng · có cảnh báo" : "Sẵn sàng"
                : "Bị chặn";
        }
        catch (Exception exception)
        {
            entry.Status = "Lỗi: " + exception.Message;
            entry.Inspect = null;
            entry.InspectSignature = null;
        }
        if (render)
        {
            RenderRomQueue();
        }
    }

    private string InspectSignature(RomQueueEntry entry)
    {
        var file = new FileInfo(entry.Path);
        return JsonSerializer.Serialize(BuildSpec(entry))
            + $"|{file.Length}|{file.LastWriteTimeUtc.Ticks}";
    }

    private void RenderRomQueue()
    {
        RomQueuePanel.Children.Clear();
        if (_romQueue.Count == 0)
        {
            RomQueuePanel.Children.Add(new TextBlock
            {
                Text = "Chưa có ROM trong hàng đợi.",
                Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, 102, 102, 102)),
                HorizontalAlignment = HorizontalAlignment.Center,
                Margin = new Thickness(0, 12, 0, 12),
            });
            return;
        }
        foreach (var entry in _romQueue.ToArray())
        {
            var title = new TextBlock { Text = Path.GetFileName(entry.Path), FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
            var path = new TextBlock { Text = entry.Path, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas"), FontSize = 11, Foreground = StudioBrush(95, 107, 122), TextWrapping = TextWrapping.Wrap };
            var status = new TextBlock { Text = BuildRomStatus(entry), Foreground = StatusBrush(entry.Status), TextWrapping = TextWrapping.Wrap };
            var remove = new Button { Content = "Xóa" };
            remove.Click += (_, _) =>
            {
                _romQueue.Remove(entry);
                RenderRomQueue();
            };
            var grid = new Grid { ColumnSpacing = 12 };
            grid.ColumnDefinitions.Add(new ColumnDefinition());
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var texts = new StackPanel { Spacing = 3 };
            texts.Children.Add(title);
            texts.Children.Add(path);
            texts.Children.Add(status);
            grid.Children.Add(texts);
            Grid.SetColumn(remove, 1);
            grid.Children.Add(remove);
            RomQueuePanel.Children.Add(new Border
            {
                Background = StudioBrush(248, 248, 248),
                BorderBrush = StudioBrush(225, 225, 225),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(12),
                Child = grid,
            });
        }
    }

    private StudioBuildSpec BuildSpec(RomQueueEntry entry)
    {
        var steps = _stepChecks.Where(item => item.Value.IsChecked == true).Select(item => item.Key).ToList();
        if (NotifyTelegramCheckBox.IsChecked == true && !steps.Contains("notify_telegram", StringComparer.Ordinal))
        {
            steps.Add("notify_telegram");
        }
        return new StudioBuildSpec(
            entry.Path,
            _modChecks.Where(item => item.Value.IsChecked == true).Select(item => item.Key).ToArray(),
            SelectedTag(ModVersionCombo) ?? string.Empty,
            _debloatPaths.ToArray(),
            SelectedPreset(),
            steps,
            NotifyTelegramCheckBox.IsChecked == true);
    }

    private async Task RunPreflightAsync(bool showSuccess)
    {
        await SaveSelectedStudioVersionAsync(showMessage: false);
        if (_romQueue.Count == 0)
        {
            throw new InvalidOperationException("Hãy chọn ít nhất một ROM ZIP.");
        }
        await InspectEntriesAsync(_romQueue);
        var failed = _romQueue.Where(item => item.Inspect?.Ok != true).ToArray();
        if (failed.Length > 0)
        {
            throw new InvalidOperationException($"Preflight chặn {failed.Length} ROM. Xem lỗi ngay trong danh sách ROM.");
        }
        if (showSuccess)
        {
            ShowMessage("Preflight hoàn tất", $"{_romQueue.Count} ROM sẵn sàng đưa vào hàng đợi.", InfoBarSeverity.Success);
        }
    }

    private async Task RefreshJobsAsync()
    {
        if (_api is null)
        {
            return;
        }
        var jobs = await _api.GetJobsAsync();
        ReplaceJobs(jobs);
        UpdateQueueStats(jobs);
        JobsSnapshotChanged?.Invoke(jobs);
        var successfulJobs = jobs.Count(job => job.Status == "success");
        if (_knownSuccessfulJobs >= 0 && successfulJobs != _knownSuccessfulJobs)
        {
            PopulateArtifacts(await _api.GetArtifactsAsync());
        }
        _knownSuccessfulJobs = successfulJobs;
        await EnsureJobSelectionAsync(jobs);
    }

    private void ReplaceJobs(IReadOnlyList<StudioJob> jobs)
    {
        var selected = _selectedJobId;
        ObservableCollectionReconciler.ReconcileByKey(
            _jobItems,
            jobs,
            item => item.Id,
            job => job.Id,
            job => new NativeJobItem(job),
            (item, job) => item.Update(job));
        if (!string.IsNullOrWhiteSpace(selected))
        {
            SyncSelectedJobItem();
        }
    }

    private async Task EnsureJobSelectionAsync(IReadOnlyList<StudioJob> jobs)
    {
        var preferredJobId = JobSelectionPolicy.Choose(jobs, _selectedJobId);
        if (string.IsNullOrWhiteSpace(preferredJobId))
        {
            if (!string.IsNullOrWhiteSpace(_selectedJobId))
            {
                _selectedJobId = null;
                ResetLogState(null);
                SyncSelectedJobItem();
            }
            return;
        }
        var changed = !string.Equals(_selectedJobId, preferredJobId, StringComparison.Ordinal);
        if (changed)
        {
            ResetLogState(preferredJobId);
            _selectedJobId = preferredJobId;
        }
        SyncSelectedJobItem();
        if (changed)
        {
            await RefreshSelectedJobAsync();
            await RefreshSelectedJobLogAsync();
        }
    }

    private void SyncSelectedJobItem()
    {
        var selectedItem = _jobItems.FirstOrDefault(item => item.Id == _selectedJobId);
        if (ReferenceEquals(JobsList.SelectedItem, selectedItem))
        {
            return;
        }
        _syncingJobSelection = true;
        try
        {
            JobsList.SelectedItem = selectedItem;
        }
        finally
        {
            _syncingJobSelection = false;
        }
    }

    private void UpdateQueueStats(IReadOnlyList<StudioJob> jobs)
    {
        ActiveJobsText.Text = jobs.Count(job => job.Status is "running" or "packaging").ToString();
        QueuedJobsText.Text = jobs.Count(job => job.Status == "queued").ToString();
    }

    private async Task RefreshSelectedJobAsync()
    {
        if (_api is null || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        try
        {
            var job = await _api.GetJobAsync(_selectedJobId);
            _selectedJob = job;
            SelectedJobTitle.Text = job.VersionName;
            SelectedJobStatus.Text = BuildSelectedJobStatus(job);
            var progress = OverallProgress(job);
            SelectedJobProgress.Value = progress;
            SelectedJobProgressText.Text = $"{progress}%";
            SelectedJobElapsedText.Text = FormatDuration(BuildElapsed(job));
            SelectedJobMeta.Text = BuildJobMeta(job);
            CancelJobButton.IsEnabled = job.Status is "queued" or "running" or "packaging";
            SelectedJobErrorBar.IsOpen = !string.IsNullOrWhiteSpace(job.Error);
            SelectedJobErrorBar.Title = job.Status == "failed" ? "Build thất bại" : "Thông báo job";
            SelectedJobErrorBar.Message = job.Error ?? string.Empty;
            RenderJobSteps(job);
            if (DateTimeOffset.UtcNow - _lastMetricsRefresh >= TimeSpan.FromSeconds(4))
            {
                RenderJobMetrics(await _api.GetJobMetricsAsync(job.Id));
                _lastMetricsRefresh = DateTimeOffset.UtcNow;
            }

            var outputs = JobOutputPaths(job);
            _selectedOutputPath = outputs.FirstOrDefault(File.Exists) ?? outputs.FirstOrDefault();
            SelectedJobArtifact.Text = outputs.Count > 0
                ? string.Join(Environment.NewLine, outputs)
                : !string.IsNullOrWhiteSpace(job.Workspace)
                    ? $"Workspace: {job.Workspace}"
                    : "Chưa có artifact.";
            CopyArtifactButton.IsEnabled = outputs.Count > 0;
            OpenArtifactButton.IsEnabled = _selectedOutputPath is not null && File.Exists(_selectedOutputPath);
            OpenJobWorkspaceButton.IsEnabled = !string.IsNullOrWhiteSpace(job.Workspace) && Directory.Exists(job.Workspace);
        }
        catch (Exception exception) when (exception is HttpRequestException or InvalidOperationException)
        {
            SelectedJobStatus.Text = exception.Message;
        }
    }

    private async Task RefreshSelectedJobLogAsync()
    {
        if (_logPolling || _api is null || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        _logPolling = true;
        var jobId = _selectedJobId;
        try
        {
            if (!string.Equals(_logJobId, jobId, StringComparison.Ordinal))
            {
                ResetLogState(jobId);
            }
            var chunk = await _api.GetJobLogChunkAsync(jobId, _logOffset);
            if (string.Equals(_selectedJobId, jobId, StringComparison.Ordinal))
            {
                ApplyLogChunk(chunk);
            }
        }
        catch (InvalidOperationException)
        {
            if (_logBuffer.Length > 0)
            {
                _logBuffer.Clear();
                RenderFilteredLog();
            }
        }
        catch (HttpRequestException)
        {
            // Status polling reports backend connectivity without clearing the visible log.
        }
        finally
        {
            _logPolling = false;
        }
    }

    private void RenderFilteredLog()
    {
        var lines = CurrentPresentedLog();
        SetLogDocument(lines);
        _logRenderDeferred = false;
        _presentationRemainder = string.Empty;
        _lastPresentedLine = lines.LastOrDefault()?.Text;
    }

    private void ApplyLogChunk(StudioLogChunk chunk)
    {
        _logOffset = chunk.NextOffset;
        if (chunk.Reset)
        {
            _presentationRemainder = string.Empty;
            _lastPresentedLine = null;
        }
        var change = _logBuffer.Append(chunk.Text, chunk.Reset);
        if (chunk.Text.Length == 0)
        {
            if (chunk.Reset)
            {
                RequestLogRender();
            }
            else
            {
                RenderDeferredLogIfVisible();
            }
            return;
        }

        if (!CanRenderLog())
        {
            _logRenderDeferred = true;
            UpdateDeferredLogSummary();
            return;
        }

        var shouldScroll = false;
        if (LogSearchBox.Text.Trim().Length > 0)
        {
            ScheduleFilteredLogRender();
        }
        else if (change.RequiresFullRender)
        {
            RenderFilteredLog();
            shouldScroll = true;
        }
        else
        {
            var lines = PresentIncrementalChunk(change.AppendText);
            AppendLogDocument(lines);
            shouldScroll = lines.Count > 0;
        }
        if (shouldScroll)
        {
            ScheduleLogScroll();
        }
    }

    private void ResetLogState(string? jobId)
    {
        _logJobId = jobId;
        _logOffset = -1;
        _selectedJob = null;
        _selectedOutputPath = null;
        _renderedStepSignature = string.Empty;
        _lastMetricsRefresh = DateTimeOffset.MinValue;
        _presentationRemainder = string.Empty;
        _lastPresentedLine = null;
        _logRenderDeferred = false;
        _logBuffer.Clear();
        SetLogDocument([]);
        JobStepsPanel.Children.Clear();
        SelectedJobArtifact.Text = "Chưa có artifact.";
        CopyArtifactButton.IsEnabled = false;
        OpenArtifactButton.IsEnabled = false;
        OpenJobWorkspaceButton.IsEnabled = false;
        SelectedJobErrorBar.IsOpen = false;
        MetricMemoryText.Text = "-";
        MetricCpuText.Text = "-";
        MetricLogText.Text = "-";
        MetricDiskText.Text = "-";
        MetricCacheText.Text = "-";
    }

    private IReadOnlyList<StudioLogLine> CurrentPresentedLog() => StudioLogPresentation.Build(
        _logBuffer.Snapshot(),
        LogSearchBox.Text.Trim(),
        SelectedLogFilter(),
        TechnicalLogButton.IsChecked == true);

    private void SetLogDocument(IReadOnlyList<StudioLogLine> lines)
    {
        var text = BuildLogText(lines);
        MutateLogDocument(() =>
        {
            JobLogBox.Document.SetText(TextSetOptions.None, text);
            ApplyLogFormatting(lines, 0);
        });
        _presentedLineCount = lines.Count;
        _presentedWarningCount = lines.Count(line => line.Kind == StudioLogLineKind.Warning);
        _presentedErrorCount = lines.Count(line => line.Kind == StudioLogLineKind.Error);
        UpdateLogSummary();
    }

    private void AppendLogDocument(IReadOnlyList<StudioLogLine> lines)
    {
        if (lines.Count == 0)
        {
            return;
        }
        var text = BuildLogText(lines);
        MutateLogDocument(() =>
        {
            var range = JobLogBox.Document.GetRange(0, 0);
            range.Move(TextRangeUnit.Story, 1);
            var start = range.StartPosition;
            range.SetText(TextSetOptions.None, text);
            ApplyLogFormatting(lines, start);
        });
        _presentedLineCount += lines.Count;
        _presentedWarningCount += lines.Count(line => line.Kind == StudioLogLineKind.Warning);
        _presentedErrorCount += lines.Count(line => line.Kind == StudioLogLineKind.Error);
        UpdateLogSummary();
    }

    private IReadOnlyList<StudioLogLine> PresentIncrementalChunk(string chunk)
    {
        if (chunk.Length == 0)
        {
            return [];
        }

        var normalized = (_presentationRemainder + chunk)
            .Replace("\r\n", "\n", StringComparison.Ordinal);
        var complete = normalized.EndsWith('\n');
        var parts = normalized.Split('\n');
        _presentationRemainder = complete ? string.Empty : parts[^1];
        var count = complete ? parts.Length - 1 : Math.Max(0, parts.Length - 1);
        var result = new List<StudioLogLine>(count);
        var filter = SelectedLogFilter();
        var includeTechnical = TechnicalLogButton.IsChecked == true;
        for (var index = 0; index < count; index++)
        {
            var line = StudioLogPresentation.PresentLine(parts[index].TrimEnd('\r'), includeTechnical);
            if (line is null || !StudioLogPresentation.MatchesFilter(line, filter))
            {
                continue;
            }
            if (string.Equals(_lastPresentedLine, line.Text, StringComparison.Ordinal))
            {
                continue;
            }
            if (line.Text.Length == 0 && _lastPresentedLine is null or "")
            {
                continue;
            }
            result.Add(line);
            _lastPresentedLine = line.Text;
        }
        return result;
    }

    private static string BuildLogText(IReadOnlyList<StudioLogLine> lines) => lines.Count == 0
        ? string.Empty
        : string.Join('\r', lines.Select(line => line.Text)) + '\r';

    private void ApplyLogFormatting(IReadOnlyList<StudioLogLine> lines, int start)
    {
        if (lines.Count == 0)
        {
            return;
        }

        var position = start;
        var groupStart = start;
        var groupKind = lines[0].Kind;
        for (var index = 0; index < lines.Count; index++)
        {
            var line = lines[index];
            position += line.Text.Length + 1;
            var nextKind = index + 1 < lines.Count ? lines[index + 1].Kind : (StudioLogLineKind?)null;
            if (nextKind == groupKind)
            {
                continue;
            }

            var range = JobLogBox.Document.GetRange(groupStart, position);
            range.CharacterFormat.ForegroundColor = LogLineColor(groupKind);
            range.CharacterFormat.Bold = groupKind is StudioLogLineKind.Stage or StudioLogLineKind.Error
                ? FormatEffect.On
                : FormatEffect.Off;
            groupStart = position;
            if (nextKind is StudioLogLineKind kind)
            {
                groupKind = kind;
            }
        }
    }

    private void UpdateLogSummary()
    {
        LogSummaryText.Text = _presentedErrorCount > 0 || _presentedWarningCount > 0
            ? $"{_presentedLineCount} dòng · {_presentedWarningCount} cảnh báo · {_presentedErrorCount} lỗi"
            : $"{_presentedLineCount} dòng";
    }

    private void UpdateDeferredLogSummary()
    {
        var state = PauseLogButton.IsChecked == true ? "đang tạm dừng" : "đang đệm ngoài màn hình";
        LogSummaryText.Text = $"{_presentedLineCount} dòng · {state} · {_logBuffer.Length:N0} ký tự";
    }

    private static Windows.UI.Color LogLineColor(StudioLogLineKind kind) => kind switch
    {
        StudioLogLineKind.Stage => Windows.UI.Color.FromArgb(255, 224, 139, 255),
        StudioLogLineKind.Command => Windows.UI.Color.FromArgb(255, 79, 209, 255),
        StudioLogLineKind.Warning => Windows.UI.Color.FromArgb(255, 255, 190, 92),
        StudioLogLineKind.Error => Windows.UI.Color.FromArgb(255, 255, 111, 118),
        StudioLogLineKind.Success => Windows.UI.Color.FromArgb(255, 105, 219, 145),
        StudioLogLineKind.Technical => Windows.UI.Color.FromArgb(255, 130, 148, 171),
        _ => Windows.UI.Color.FromArgb(255, 216, 226, 240),
    };

    private void MutateLogDocument(Action mutation)
    {
        var wasReadOnly = JobLogBox.IsReadOnly;
        if (wasReadOnly)
        {
            JobLogBox.IsReadOnly = false;
        }
        try
        {
            mutation();
        }
        finally
        {
            JobLogBox.IsReadOnly = wasReadOnly;
        }
    }

    private void ScheduleFilteredLogRender(bool debounce = false)
    {
        if (debounce)
        {
            _logSearchTimer.Stop();
        }
        if (!_logSearchTimer.IsEnabled)
        {
            _logSearchTimer.Start();
        }
    }

    private bool CanRenderLog() => PauseLogButton.IsChecked != true && IsConsoleVisible();

    private void RequestLogRender(bool scroll = true)
    {
        if (!CanRenderLog())
        {
            _logRenderDeferred = true;
            UpdateDeferredLogSummary();
            return;
        }
        RenderFilteredLog();
        if (scroll)
        {
            ScheduleLogScroll();
        }
    }

    private void RenderDeferredLogIfVisible()
    {
        if (_logRenderDeferred && CanRenderLog())
        {
            RenderFilteredLog();
            ScheduleLogScroll();
        }
    }

    private void ScheduleLogScroll()
    {
        if (FollowLogButton.IsChecked != true || _logScrollPending)
        {
            return;
        }
        _logScrollPending = true;
        DispatcherQueue.TryEnqueue(() =>
        {
            _logScrollPending = false;
            if (!IsConsoleVisible())
            {
                return;
            }
            var pageOffset = StudioPage.VerticalOffset;
            var range = JobLogBox.Document.GetRange(0, 0);
            range.Move(TextRangeUnit.Story, 1);
            range.ScrollIntoView(PointOptions.None);
            StudioPage.ChangeView(null, pageOffset, null, disableAnimation: true);
        });
    }

    private bool IsConsoleVisible()
    {
        if (ConsoleCard.ActualHeight <= 0 || StudioPage.ViewportHeight <= 0)
        {
            return false;
        }
        var position = ConsoleCard
            .TransformToVisual(StudioPage)
            .TransformPoint(new Windows.Foundation.Point(0, 0));
        return position.Y < StudioPage.ViewportHeight
            && position.Y + ConsoleCard.ActualHeight > 0;
    }

    private void LogSearchTimerTick(object? sender, object e)
    {
        _logSearchTimer.Stop();
        RequestLogRender();
    }

    private async void PollTimerTick(object? sender, object e)
    {
        if (_polling || _busy)
        {
            return;
        }
        _polling = true;
        try
        {
            await RefreshJobsAsync();
            await RefreshSelectedJobAsync();
        }
        catch (Exception exception) when (exception is HttpRequestException or JsonException)
        {
            SetBackendState("Mất kết nối", ready: false);
            BackendVersionText.Text = exception.Message;
        }
        finally
        {
            _polling = false;
        }
    }

    private async void LogPollTimerTick(object? sender, object e)
    {
        if (_busy || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        if (_logOffset >= 0 && _selectedJob?.Status is "success" or "failed" or "cancelled")
        {
            return;
        }
        await RefreshSelectedJobLogAsync();
    }

    private async void BrowseRomClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null)
        {
            return;
        }
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.Downloads };
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var files = await picker.PickMultipleFilesAsync();
        try
        {
            var authorized = new List<string>();
            foreach (var file in files)
            {
                var result = await _api.AuthorizeRomAsync(file.Path);
                if (!string.IsNullOrWhiteSpace(result.Path))
                {
                    authorized.Add(result.Path);
                }
            }
            await AddAuthorizedRomsAsync(authorized);
        }
        catch (Exception exception)
        {
            ShowMessage("Không thể thêm ROM", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void BrowseFolderClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null)
        {
            return;
        }
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null)
        {
            return;
        }
        try
        {
            var result = await _api.AuthorizeRomFolderAsync(folder.Path);
            await AddAuthorizedRomsAsync(result.Roms);
        }
        catch (Exception exception)
        {
            ShowMessage("Không thể nhập folder", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void RenameRomFileClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null)
        {
            return;
        }
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.Downloads };
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }
        await RunRomRenamerActionAsync(async () =>
        {
            _romRenamePreview = await _api.PreviewRomRenameAsync(file.Path, null);
            RenderRomRenamePreview();
        });
    }

    private async void RenameRomFolderClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null)
        {
            return;
        }
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null)
        {
            return;
        }
        await RunRomRenamerActionAsync(async () =>
        {
            _romRenamePreview = await _api.PreviewRomRenameAsync(null, folder.Path);
            RenderRomRenamePreview();
        });
    }

    private async void ApplyRomRenameClick(object sender, RoutedEventArgs e)
    {
        if (_api is null || _romRenamePreview?.CanApply != true)
        {
            return;
        }
        var isEnglish = _desktopSettings.Locale == "en";
        var confirmed = await ConfirmDialogAsync(
            isEnglish ? "Rename ROM ZIP files?" : "Đổi tên các file ROM ZIP?",
            isEnglish
                ? $"{_romRenamePreview.Ready} file(s) will be renamed from metadata version_name. This does not add them to the build queue."
                : $"{_romRenamePreview.Ready} file sẽ được đổi tên theo version_name trong metadata. Tác vụ này không thêm ROM vào hàng đợi build.",
            isEnglish ? "Rename" : "Đổi tên");
        if (!confirmed)
        {
            return;
        }
        await RunRomRenamerActionAsync(async () =>
        {
            var result = await _api.ApplyRomRenameAsync(_romRenamePreview.Entries);
            _romRenamePreview = new StudioRomRenamePreview(
                result.Entries,
                result.Total,
                0,
                result.Unchanged,
                0,
                false);
            RenderRomRenamePreview();
            ShowRomRenamerMessage(
                isEnglish ? "Rename completed" : "Đổi tên hoàn tất",
                isEnglish
                    ? $"Renamed {result.Renamed} ROM ZIP file(s)."
                    : $"Đã đổi tên {result.Renamed} file ROM ZIP.",
                InfoBarSeverity.Success);
        });
    }

    private void ClearRomRenameClick(object sender, RoutedEventArgs e)
    {
        _romRenamePreview = null;
        RomRenamerInfoBar.IsOpen = false;
        RenderRomRenamePreview();
    }

    private async Task RunRomRenamerActionAsync(Func<Task> action)
    {
        if (_busy)
        {
            return;
        }
        SetBusy(true);
        RomRenamerInfoBar.IsOpen = false;
        try
        {
            await action();
        }
        catch (Exception exception)
        {
            ShowRomRenamerMessage(
                _desktopSettings.Locale == "en" ? "ROM rename failed" : "Không thể đổi tên ROM",
                exception.Message,
                InfoBarSeverity.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void RenderRomRenamePreview()
    {
        _romRenameItems.Clear();
        var preview = _romRenamePreview;
        if (preview is not null)
        {
            foreach (var entry in preview.Entries)
            {
                _romRenameItems.Add(new NativeRomRenameItem(
                    entry,
                    RomRenameStatusText(entry.Status),
                    RomRenameDetail(entry)));
            }
        }
        var total = preview?.Total ?? 0;
        RomRenamerCountText.Text = $"{total} file";
        RomRenamerEmptyState.Visibility = total == 0 ? Visibility.Visible : Visibility.Collapsed;
        RomRenamerList.Visibility = total == 0 ? Visibility.Collapsed : Visibility.Visible;
        ClearRomRenameButton.IsEnabled = !_busy && total > 0;
        ApplyRomRenameButton.IsEnabled = !_busy && preview?.CanApply == true;

        var isEnglish = _desktopSettings.Locale == "en";
        RomRenamerSummaryText.Text = preview is null
            ? isEnglish ? "No ROM selected for inspection." : "Chưa chọn ROM để kiểm tra."
            : preview.Total == 0
                ? isEnglish ? "No ZIP files were found in the selected folder." : "Không tìm thấy file ZIP trong folder đã chọn."
                : isEnglish
                    ? $"{preview.Ready} ready · {preview.Unchanged} unchanged · {preview.Errors} error(s)"
                    : $"{preview.Ready} sẵn sàng · {preview.Unchanged} không đổi · {preview.Errors} lỗi";
    }

    private string RomRenameStatusText(string status) => _desktopSettings.Locale == "en"
        ? status switch
        {
            "ready" => "Ready",
            "unchanged" => "Unchanged",
            "renamed" => "Renamed",
            "error" => "Error",
            _ => status,
        }
        : status switch
        {
            "ready" => "Sẵn sàng",
            "unchanged" => "Không đổi",
            "renamed" => "Đã đổi tên",
            "error" => "Lỗi",
            _ => status,
        };

    private string RomRenameDetail(StudioRomRenameEntry entry)
    {
        var detail = entry.Error ?? entry.Warning;
        if (!string.IsNullOrWhiteSpace(detail))
        {
            return _desktopSettings.Locale == "en" ? detail : TranslateRomRenameError(detail);
        }
        return $"version_name: {entry.VersionName ?? "-"}";
    }

    private static string TranslateRomRenameError(string message)
    {
        if (message.StartsWith("Missing META-INF", StringComparison.Ordinal))
        {
            return "ZIP thiếu META-INF/com/android/metadata";
        }
        if (message.StartsWith("Target ZIP already exists:", StringComparison.Ordinal))
        {
            return message.Replace("Target ZIP already exists:", "File đích đã tồn tại:", StringComparison.Ordinal);
        }
        return message switch
        {
            "ROM is not a valid ZIP file" => "ROM không phải file ZIP hợp lệ",
            "ROM metadata does not contain version_name" => "Metadata không có version_name",
            "ROM metadata version_name contains an unsafe path component" => "version_name chứa thành phần đường dẫn không an toàn",
            "ROM metadata version_name is reserved by Windows" => "version_name là tên dành riêng của Windows",
            "Multiple ROM ZIP files resolve to the same target filename" => "Nhiều ROM tạo ra cùng một tên file đích",
            "version_name was normalized for a safe Windows filename" => "version_name đã được chuẩn hóa thành tên file Windows an toàn",
            _ => message,
        };
    }

    private void ShowRomRenamerMessage(string title, string message, InfoBarSeverity severity)
    {
        RomRenamerInfoBar.Title = title;
        RomRenamerInfoBar.Message = message;
        RomRenamerInfoBar.Severity = severity;
        RomRenamerInfoBar.IsOpen = true;
    }

    private async void AddRomPathClick(object sender, RoutedEventArgs e) => await AddRomAsync(RomPathBox.Text);

    private async void PreflightClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () => await RunPreflightAsync(showSuccess: true));
    }

    private async void StartBuildClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null)
            {
                return;
            }
            await RunPreflightAsync(showSuccess: false);
            var response = await _api.CreateJobsAsync(_romQueue.Select(BuildSpec).ToArray());
            _romQueue.Clear();
            RenderRomQueue();
            await RefreshJobsAsync();
            var first = response.Jobs.FirstOrDefault();
            if (first is not null)
            {
                await SelectJobAsync(first.Id);
                ConsoleCard.StartBringIntoView(new BringIntoViewOptions
                {
                    AnimationDesired = true,
                    VerticalAlignmentRatio = 0.05,
                });
            }
            ShowMessage("Đã thêm vào hàng đợi", $"Đã tạo {response.Jobs.Count} job build.", InfoBarSeverity.Success);
        });
    }

    private async void RefreshJobsClick(object sender, RoutedEventArgs e) => await RunBusyActionAsync(RefreshJobsAsync);

    private async void JobSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_syncingJobSelection)
        {
            return;
        }
        if (JobsList.SelectedItem is not NativeJobItem item)
        {
            return;
        }
        if (!string.Equals(_selectedJobId, item.Id, StringComparison.Ordinal))
        {
            ResetLogState(item.Id);
            _selectedJobId = item.Id;
        }
        await RefreshSelectedJobAsync();
        await RefreshSelectedJobLogAsync();
    }

    private async void CancelJobClick(object sender, RoutedEventArgs e)
    {
        if (_api is null || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            await _api.CancelJobAsync(_selectedJobId);
            await RefreshJobsAsync();
            await RefreshSelectedJobAsync();
            await RefreshSelectedJobLogAsync();
        });
    }

    private void CopyLogClick(object sender, RoutedEventArgs e) =>
        CopyToClipboard(string.Join(Environment.NewLine, CurrentPresentedLog().Select(line => line.Text)));

    private void LogSearchChanged(object sender, TextChangedEventArgs e) => ScheduleFilteredLogRender(debounce: true);

    private void LogLevelChanged(object sender, SelectionChangedEventArgs e)
    {
        if (JobLogBox is not null)
        {
            RequestLogRender();
        }
    }

    private void TechnicalLogChanged(object sender, RoutedEventArgs e)
    {
        RequestLogRender();
    }

    private void PauseLogChanged(object sender, RoutedEventArgs e)
    {
        if (PauseLogButton.IsChecked == true)
        {
            _logRenderDeferred = true;
            UpdateDeferredLogSummary();
            return;
        }
        RenderDeferredLogIfVisible();
    }

    private void WrapLogChanged(object sender, RoutedEventArgs e)
    {
        JobLogBox.TextWrapping = WrapLogButton.IsChecked == true
            ? TextWrapping.Wrap
            : TextWrapping.NoWrap;
    }

    private void ClearLogClick(object sender, RoutedEventArgs e)
    {
        _logBuffer.Clear();
        _presentationRemainder = string.Empty;
        _lastPresentedLine = null;
        _logRenderDeferred = false;
        SetLogDocument([]);
    }

    private async void DownloadLogClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.Downloads,
            SuggestedFileName = SafeFileName((_selectedJob?.VersionName ?? _selectedJobId) + ".log"),
        };
        picker.FileTypeChoices.Add("Log Wukong Studio", [".log"]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSaveFileAsync();
        if (file is null)
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            await _api.DownloadJobLogAsync(_selectedJobId, file.Path);
            ShowMessage("Đã tải log", file.Path, InfoBarSeverity.Success);
        });
    }

    private async void DownloadDiagnosticsBundleClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _api is null || string.IsNullOrWhiteSpace(_selectedJobId))
        {
            return;
        }
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.Downloads,
            SuggestedFileName = SafeFileName((_selectedJob?.VersionName ?? _selectedJobId) + "-diagnostics"),
        };
        picker.FileTypeChoices.Add("Wukong diagnostics ZIP", [".zip"]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSaveFileAsync();
        if (file is null)
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            await _api.DownloadDiagnosticsBundleAsync(_selectedJobId, file.Path);
            ShowMessage("Đã xuất gói chẩn đoán", file.Path, InfoBarSeverity.Success);
        });
    }

    private void RenderJobMetrics(StudioJobMetrics metrics)
    {
        MetricMemoryText.Text = metrics.Process.Available
            ? FormatBytes(metrics.Process.WorkingSetBytes)
            : "N/A";
        MetricCpuText.Text = metrics.Process.Available
            ? FormatDuration(TimeSpan.FromSeconds(metrics.Process.CpuTimeSeconds))
            : "N/A";
        MetricLogText.Text = FormatBytes(metrics.LogBytes);
        MetricDiskText.Text = FormatBytes(metrics.DiskFreeBytes);
        MetricCacheText.Text = $"{metrics.StageCache.EntryCount} / {FormatBytes(metrics.StageCache.TotalBytes)}";
    }

    private void CopyArtifactClick(object sender, RoutedEventArgs e)
    {
        if (_selectedJob is not null)
        {
            CopyToClipboard(string.Join(Environment.NewLine, JobOutputPaths(_selectedJob)));
        }
    }

    private void OpenSelectedArtifactClick(object sender, RoutedEventArgs e)
    {
        if (_selectedOutputPath is not null)
        {
            OpenArtifact(_selectedOutputPath);
        }
    }

    private void OpenSelectedWorkspaceClick(object sender, RoutedEventArgs e) =>
        OpenDirectory(_selectedJob?.Workspace);

    private async void RefreshArtifactsClick(object sender, RoutedEventArgs e)
    {
        await RefreshArtifactsAsync();
    }

    private async void RefreshDiagnosticsClick(object sender, RoutedEventArgs e)
    {
        await RefreshDiagnosticsAsync();
    }

    private async void AddRootFolderClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null)
        {
            return;
        }
        var picker = new FolderPicker();
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null)
        {
            return;
        }
        var roots = RootsBox.Text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
        if (!roots.Contains(folder.Path, StringComparer.OrdinalIgnoreCase))
        {
            roots.Add(folder.Path);
            RootsBox.Text = string.Join(Environment.NewLine, roots);
        }
    }

    private async void SaveSettingsClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _bootstrap is null)
            {
                return;
            }
            var roots = RootsBox.Text.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            var maximumCacheGb = double.IsNaN(StageCacheMaxBox.Value)
                ? 40
                : (int)Math.Round(StageCacheMaxBox.Value);
            var settings = _bootstrap.Settings with
            {
                Roots = roots,
                Locale = SelectedTag(LanguageCombo) ?? _desktopSettings.Locale,
                Theme = SelectedTag(ThemeCombo) ?? _desktopSettings.Theme,
                DefaultPreset = SelectedTag(DefaultPresetCombo) ?? "lite",
                NotifyTelegram = DefaultTelegramCheckBox.IsChecked == true,
                DebloatPaths = _debloatPaths.ToArray(),
                StageCacheEnabled = StageCacheToggle.IsOn,
                StageCacheMaxGb = Math.Clamp(maximumCacheGb, 5, 500),
                StudioVersions = ReadStudioVersionSettings(includeSelectedEditor: true),
                ZipValidationMode = SelectedTag(ZipValidationModeCombo) ?? "fast",
            };
            var saved = await _api.SaveSettingsAsync(settings);
            _bootstrap = _bootstrap with { Settings = saved };
            PopulateSettings(saved);
            await RefreshCacheAsync();
            ShowMessage("Đã lưu cài đặt", "Cấu hình backend đã được cập nhật.", InfoBarSeverity.Success);
        });
    }

    private async void ConfigureTelegramClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _layout is null || _restartBackend is null)
            {
                return;
            }
            var token = TelegramTokenBox.Password.Trim();
            var chatId = TelegramChatIdBox.Text.Trim();
            if (token.Length < 20 || chatId.Length == 0)
            {
                throw new InvalidDataException("Telegram bot token hoặc chat ID không hợp lệ.");
            }
            if ((await _api.GetActiveJobsAsync()).Count > 0)
            {
                throw new InvalidOperationException("Không thể đổi Telegram khi build đang chạy hoặc đang đóng ZIP.");
            }
            new TelegramSecretStore(_layout).Save(new TelegramCredentials(token, chatId));
            TelegramTokenBox.Password = string.Empty;
            await _restartBackend();
            ShowMessage("Đã cập nhật Telegram", "Credential đã được mã hóa và backend đã khởi động lại.", InfoBarSeverity.Success);
        });
    }

    private async void ConfigureHybridSecretsClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null || _layout is null || _restartBackend is null) return;
            var repository = HybridRepositoryBox.Text.Trim();
            var token = HybridGitHubTokenBox.Password.Trim();
            var rcloneConfig = HybridRcloneConfigBox.Text.Trim();
            if (!repository.Contains('/') || token.Length < 20 || !rcloneConfig.Contains("[wukong-gdrive]"))
            {
                throw new InvalidDataException("Repository, GitHub token hoặc rclone.conf không hợp lệ.");
            }
            new HybridSecretStore(_layout).Save(
                new HybridCredentials(repository, token, rcloneConfig));
            HybridGitHubTokenBox.Password = string.Empty;
            HybridRcloneConfigBox.Text = string.Empty;
            await _restartBackend();
            ShowMessage(
                "Đã cập nhật Hybrid Cloud",
                "Credential đã được mã hóa; backend đã khởi động lại.",
                InfoBarSeverity.Success);
        });
    }

    private void SaveDesktopSettingsClick(object sender, RoutedEventArgs e)
    {
        if (_layout is null)
        {
            return;
        }
        var bufferThousands = double.IsNaN(ConsoleBufferBox.Value) ? 100d : ConsoleBufferBox.Value;
        var interval = int.TryParse(SelectedTag(LogRefreshCombo), out var selectedInterval)
            ? selectedInterval
            : 750;
        var settings = DesktopSettings.Load(_layout) with
        {
            ConsoleMaxCharacters = (int)Math.Round(bufferThousands * 1000),
            LogPollIntervalMs = interval,
            AutoScrollLogs = DefaultAutoScrollCheckBox.IsChecked == true,
            NavigationPaneOpen = NavigationExpandedCheckBox.IsChecked == true,
            ExpandModOptions = ExpandModsCheckBox.IsChecked == true,
            ExpandPipelineSteps = ExpandPipelineCheckBox.IsChecked == true,
            LastModVersion = SelectedTag(ModVersionCombo),
            Locale = SelectedTag(LanguageCombo) ?? "vi",
            Theme = SelectedTag(ThemeCombo) ?? "light",
            LastRecipeId = SelectedTag(RecipeCombo),
        };
        settings.Save(_layout);
        ApplyDesktopSettings(DesktopSettings.Load(_layout));
        ShowMessage("Đã lưu giao diện", "Tùy chọn menu, console và panel build đã được cập nhật.", InfoBarSeverity.Success);
    }

    private void LanguageChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_initialized || _configuring || _layout is null)
        {
            return;
        }
        _desktopSettings = _desktopSettings with { Locale = SelectedTag(LanguageCombo) ?? "vi" };
        _desktopSettings.Save(_layout);
        _applyHostLocale?.Invoke(_desktopSettings.Locale);
        ApplyLocalization();
        if (_bootstrap is not null)
        {
            _configuring = true;
            RebuildStepOptions(applyPreset: false);
            _configuring = false;
        }
        _renderedStepSignature = string.Empty;
        if (_selectedJob is not null)
        {
            RenderJobSteps(_selectedJob);
            SelectedJobStatus.Text = BuildSelectedJobStatus(_selectedJob);
        }
    }

    private void ThemeChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_initialized || _configuring || _layout is null)
        {
            return;
        }
        _desktopSettings = _desktopSettings with { Theme = SelectedTag(ThemeCombo) ?? "system" };
        _desktopSettings.Save(_layout);
        var theme = ThemePreference(_desktopSettings.Theme);
        RequestedTheme = theme;
        _applyHostTheme?.Invoke(theme);
        RefreshThemeVisuals();
    }

    private void NativeStudioActualThemeChanged(FrameworkElement sender, object args)
    {
        if (!_initialized || _desktopSettings.Theme != "system")
        {
            return;
        }
        RefreshThemeVisuals();
    }

    private void RefreshThemeVisuals()
    {
        if (_bootstrap is not null)
        {
            RebuildModOptions(applyPreset: false);
            RebuildStepOptions(applyPreset: false);
            PopulateCatalog();
            PopulateDiagnostics(_bootstrap.Diagnostics);
            PopulateArtifacts(_bootstrap.Artifacts);
            RenderRomQueue();
        }
        _renderedStepSignature = string.Empty;
        if (_selectedJob is not null)
        {
            RenderJobSteps(_selectedJob);
        }
    }

    private void ApplyLocalization()
    {
        LocalizeVisualTree(RootLayout);
        RenderRomRenamePreview();
        RefreshContentSyncLocalization();
    }

    private void LocalizeVisualTree(DependencyObject element)
    {
        switch (element)
        {
            case TextBlock text:
                text.Text = Localized(text.Text);
                break;
            case TextBox textBox:
                textBox.Header = LocalizedObject(textBox.Header);
                textBox.PlaceholderText = Localized(textBox.PlaceholderText);
                break;
            case PasswordBox passwordBox:
                passwordBox.Header = LocalizedObject(passwordBox.Header);
                passwordBox.PlaceholderText = Localized(passwordBox.PlaceholderText);
                break;
            case NumberBox numberBox:
                numberBox.Header = LocalizedObject(numberBox.Header);
                break;
            case ComboBox comboBox:
                comboBox.Header = LocalizedObject(comboBox.Header);
                break;
            case ToggleSwitch toggle:
                toggle.Header = LocalizedObject(toggle.Header);
                toggle.OnContent = LocalizedObject(toggle.OnContent);
                toggle.OffContent = LocalizedObject(toggle.OffContent);
                break;
            case AppBarButton appBarButton:
                appBarButton.Label = Localized(appBarButton.Label);
                break;
            case AppBarToggleButton appBarToggleButton:
                appBarToggleButton.Label = Localized(appBarToggleButton.Label);
                break;
            case ContentControl contentControl when contentControl.Content is string content:
                contentControl.Content = Localized(content);
                break;
        }
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(element); index++)
        {
            LocalizeVisualTree(VisualTreeHelper.GetChild(element, index));
        }
    }

    private object? LocalizedObject(object? value) => value is string text ? Localized(text) : value;

    private string Localized(string text)
    {
        foreach (var (vietnamese, english) in UiTranslations)
        {
            if (string.Equals(text, vietnamese, StringComparison.Ordinal)
                || string.Equals(text, english, StringComparison.Ordinal))
            {
                return _desktopSettings.Locale == "en" ? english : vietnamese;
            }
        }
        return text;
    }

    private static readonly IReadOnlyDictionary<string, string> UiTranslations =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["Bảng điều khiển"] = "Dashboard",
            ["Bản build"] = "Builds",
            ["Đổi tên ROM"] = "Rename ROM",
            ["Danh mục"] = "Catalog",
            ["Chẩn đoán"] = "Diagnostics",
            ["Cài đặt"] = "Settings",
            ["Trung tâm điều khiển"] = "Control center",
            ["Làm mới tất cả"] = "Refresh all",
            ["Mở ROM hoàn tất"] = "Open completed ROMs",
            ["Đọc version_name trong metadata, xem trước và xác nhận trước khi đổi tên ZIP."] = "Read metadata version_name, preview changes and confirm before renaming ZIP files.",
            ["Chọn nguồn"] = "Select source",
            ["Chọn một ROM ZIP hoặc một folder. Tool chỉ xử lý các file .zip nằm trực tiếp trong folder."] = "Select one ROM ZIP or one folder. The tool only processes direct .zip children of the folder.",
            ["Chọn ROM ZIP"] = "Select ROM ZIP",
            ["Chọn folder"] = "Select folder",
            ["Xóa danh sách"] = "Clear list",
            ["Xem trước thay đổi"] = "Preview changes",
            ["Chưa chọn ROM để kiểm tra."] = "No ROM selected for inspection.",
            ["Chưa có bản xem trước"] = "No preview yet",
            ["Chọn ROM ZIP hoặc folder để đọc version_name."] = "Select a ROM ZIP or folder to read version_name.",
            ["TÊN HIỆN TẠI"] = "CURRENT NAME",
            ["TÊN MỚI"] = "NEW NAME",
            ["Không ghi đè file đã tồn tại. Mọi file phải hợp lệ trước khi batch được đổi tên."] = "Existing files are never overwritten. Every file must be valid before the batch is renamed.",
            ["Xác nhận đổi tên"] = "Confirm rename",
            ["Hủy"] = "Cancel",
            ["ROM đầu vào"] = "Input ROMs",
            ["Duyệt ROM ZIP"] = "Browse ROM ZIP",
            ["Nhập folder"] = "Import folder",
            ["Thêm đường dẫn"] = "Add path",
            ["Chưa có ROM trong hàng đợi."] = "No ROM in the queue.",
            ["Cấu hình bản build"] = "Build configuration",
            ["Nền MOD"] = "MOD platform",
            ["Biến thể build"] = "Build variant",
            ["Phiên bản Studio"] = "Studio version",
            ["Thông báo Telegram khi hoàn thành từng bản"] = "Notify Telegram after each variant completes",
            ["Recipe đã lưu"] = "Saved recipe",
            ["Tên recipe"] = "Recipe name",
            ["Áp dụng"] = "Apply",
            ["Mới"] = "New",
            ["Lưu"] = "Save",
            ["So sánh"] = "Compare",
            ["Khóa"] = "Lock",
            ["Mở khóa"] = "Unlock",
            ["Xóa"] = "Delete",
            ["Tùy chọn MOD"] = "MOD options",
            ["Tìm MOD..."] = "Search MODs...",
            ["Chọn tất cả"] = "Select all",
            ["Bỏ chọn"] = "Clear",
            ["Pipeline build"] = "Build pipeline",
            ["Theo preset"] = "From preset",
            ["Kiểm tra trước"] = "Preflight",
            ["Bắt đầu build"] = "Start build",
            ["Job gần đây"] = "Recent jobs",
            ["Làm mới"] = "Refresh",
            ["Hủy job"] = "Cancel job",
            ["Sao chép"] = "Copy",
            ["Mở"] = "Open",
            ["Tự cuộn"] = "Auto-scroll",
            ["Tạm dừng"] = "Pause",
            ["Xuống dòng"] = "Wrap",
            ["Log kỹ thuật"] = "Technical log",
            ["Tải log gốc"] = "Download raw log",
            ["Gói chẩn đoán"] = "Diagnostics bundle",
            ["Xóa hiển thị"] = "Clear view",
            ["Thêm thiết bị"] = "Add device",
            ["Partition Layout Analyzer"] = "Partition Layout Analyzer",
            ["Chỉ kiểm tra catalog"] = "Analyze catalog only",
            ["Chọn nguồn và phân tích"] = "Choose source and analyze",
            ["Ngôn ngữ"] = "Language",
            ["Chế độ giao diện"] = "Appearance",
            ["Tiếng Việt"] = "Vietnamese",
            ["Theo hệ thống"] = "System default",
            ["Sáng"] = "Light",
            ["Tối"] = "Dark",
            ["Lưu tùy chọn Windows"] = "Save Windows preferences",
            ["Bật cache extract payload"] = "Enable payload extraction cache",
            ["Dung lượng tối đa (GiB)"] = "Maximum size (GiB)",
            ["Xóa cache"] = "Clear cache",
            ["Lưu cache"] = "Save cache",
            ["Lưu số phiên bản"] = "Save version numbers",
            ["Hậu kiểm ZIP"] = "ZIP validation",
            ["Nhanh (khuyến nghị)"] = "Fast (recommended)",
            ["CRC toàn phần"] = "Full CRC",
            ["Chế độ nhanh vẫn kiểm tra image bắt buộc, manifest và cấu trúc super.img; CRC toàn phần đọc lại toàn bộ ZIP."] = "Fast mode still checks required images, the manifest and super.img structure; Full CRC reads the entire ZIP again.",
            ["Mở output"] = "Open output",
            ["Mở workspace"] = "Open workspace",
            ["Mở log"] = "Open logs",
            ["Khởi động lại backend"] = "Restart backend",
            ["Nguồn ROM thông minh"] = "Smart ROM source",
            ["Dán URL trực tiếp, link OPlus downloadCheck, Daniel Springer hoặc Drive"] = "Paste a direct URL, OPlus downloadCheck link, Daniel Springer page, or Drive path",
            ["Phân tích"] = "Analyze",
            ["Thông tin tự nhận diện"] = "Auto-detected information",
            ["Nhà cung cấp · thiết bị · phiên bản · loại OTA"] = "Provider · device · version · OTA type",
            ["Dung lượng tự nhận diện (byte)"] = "Auto-detected size (bytes)",
            ["Đang nhận diện ROM…"] = "Identifying ROM…",
            ["Chỉ đọc header và metadata ZIP, không tải toàn bộ ROM."] = "Only ZIP headers and metadata are read; the full ROM is not downloaded.",
            ["Đã nhận diện ROM"] = "ROM identified",
            ["Đã nhận diện nguồn"] = "Source identified",
            ["Không thể phân tích ROM"] = "Unable to analyze ROM",
            ["Đã nhận diện nguồn Drive"] = "Drive source identified",
            ["Nguồn local"] = "Local source",
            ["Nguồn local hoặc Drive"] = "Local or Drive source",
            ["Phân tích sâu tự động hiện áp dụng cho URL HTTP/HTTPS."] = "Automatic deep analysis currently applies to HTTP/HTTPS URLs.",
            ["không rõ dung lượng"] = "unknown size",
            ["Metadata sẽ được kiểm tra khi job preflight tải nguồn riêng tư."] = "Metadata will be checked when preflight fetches the private source.",
            ["File local sẽ được kiểm tra quyền truy cập và checksum trước khi build."] = "The local file will be checked for access and checksum before building.",
            ["Đồng bộ nội dung đa nền tảng"] = "Cross-platform content sync",
            ["Content là nguồn chuẩn duy nhất. Chọn một thư mục để tạo lại toàn bộ content-pack tương ứng và thay thế binary trên Drive. Công bố manifest GitHub là bước riêng."] = "Content is the single source of truth. Choose a folder to rebuild its complete content pack and replace the Drive binary. Publishing the GitHub manifest is a separate step.",
            ["Chọn thư mục trong Content; Content\\STARK chứa WK_Manager và com."] = "Choose a folder inside Content; Content\\STARK contains WK_Manager and com.",
            ["Đồng bộ binary lên Drive"] = "Sync binaries to Drive",
            ["Chọn thư mục và thay thế trên Drive"] = "Choose folder and replace on Drive",
            ["Công bố manifest lên GitHub"] = "Publish manifest to GitHub",
            ["Không thể chọn thư mục này"] = "This folder cannot be selected",
            ["Chỉ chọn thư mục được quản lý bên trong Content."] = "Choose a managed folder inside Content only.",
            ["Thay thế content-pack trên Drive?"] = "Replace the content pack on Drive?",
            ["Thư mục đã chọn"] = "Selected folder",
            ["Content-pack sẽ bị thay thế toàn bộ"] = "Content pack that will be fully replaced",
            ["Phạm vi được đóng gói"] = "Packaged scope",
            ["Archive hiện tại trên Drive sẽ bị ghi đè trong khi upload, sau đó mới được xác minh. Nếu xác minh thất bại, Drive có thể đã chứa archive mới nhưng index cục bộ vẫn giữ bản đã xác minh trước đó."] = "The current Drive archive is overwritten during upload and verified afterward. If verification fails, Drive may already contain the new archive, while the local index retains the previously verified version.",
            ["Thay thế trên Drive"] = "Replace on Drive",
            ["Hủy upload"] = "Cancel upload",
            ["Đã hủy đồng bộ"] = "Sync canceled",
            ["Upload đã dừng; index cục bộ không thay đổi."] = "Upload stopped; the local index was not changed.",
            ["Không thể hoàn thành tác vụ"] = "Unable to complete the operation",
            ["Xem log kỹ thuật bên dưới để biết chi tiết và thử lại."] = "Review the technical log below for details, then try again.",
            ["Sẽ thay thế pack"] = "Will replace pack",
            ["Chưa đồng bộ trong phiên này."] = "Not synced in this session.",
            ["Đang chuẩn bị đồng bộ"] = "Preparing sync",
            ["Đang kiểm tra nội dung thay đổi…"] = "Checking changed content…",
            ["Đang tính dung lượng…"] = "Calculating size…",
            ["Tốc độ — · ETA —"] = "Speed — · ETA —",
            ["Tiến độ đồng bộ content-pack"] = "Content-pack sync progress",
            ["Đang đóng gói content-pack"] = "Packaging content pack",
            ["Đang tạo archive nén…"] = "Creating compressed archive…",
            ["Chuẩn bị upload"] = "Preparing upload",
            ["Đang upload lên Google Drive"] = "Uploading to Google Drive",
            ["Đang đo tốc độ…"] = "Measuring speed…",
            ["Đang tính ETA…"] = "Calculating ETA…",
            ["Còn lại"] = "Remaining",
            ["Gói"] = "Pack",
            ["Gói 1/1"] = "Pack 1/1",
            ["Đang xác minh dung lượng và checksum trên Drive"] = "Verifying size and checksum on Drive",
            ["Đang tải xuống để kiểm tra toàn vẹn"] = "Downloading for integrity verification",
            ["Đang đối chiếu dữ liệu…"] = "Comparing data…",
            ["Content-pack đã xác minh"] = "Content pack verified",
            ["Sẵn sàng cho pack tiếp theo"] = "Ready for the next pack",
            ["Đang công bố manifest"] = "Publishing manifest",
            ["Đang kiểm tra checksum và catalog…"] = "Checking checksums and catalog…",
            ["Đang cập nhật catalog GitHub…"] = "Updating the GitHub catalog…",
            ["Không có pack thay đổi; đang kiểm tra manifest hiện tại…"] = "No changed packs; checking the current manifest…",
            ["Binary trên Drive đã xác minh"] = "Drive binaries verified",
            ["Đã bỏ qua upload Drive"] = "Drive upload skipped",
            ["Không đổi"] = "Unchanged",
            ["Đồng bộ hoàn tất"] = "Sync complete",
            ["Manifest GitHub đã được công bố"] = "GitHub manifest published",
            ["Drive đã nhận và xác minh dữ liệu mới"] = "Drive received and verified the new data",
            ["Không có content-pack thay đổi; manifest hiện tại đã xác minh"] = "No content packs changed; the current manifest is verified",
            ["Checksum đã xác minh"] = "Checksum verified",
            ["Đồng bộ thất bại"] = "Sync failed",
            ["Lỗi"] = "Failed",
            ["Xem log chi tiết bên dưới để xử lý"] = "Review the detailed log below to recover",
            ["Không có content-pack thay đổi"] = "No content packs changed",
            ["Đã đồng bộ content-pack"] = "Content packs synced",
            ["Binary và manifest đã được công bố liền mạch; Actions và Telegram đã sẵn sàng."] = "Binaries and manifest are published; Actions and Telegram are ready.",
            ["Đã bỏ qua upload Drive và xác minh manifest hiện tại."] = "Drive upload was skipped and the current manifest was verified.",
            ["Drive không cần upload binary mới"] = "Drive does not need a new binary upload",
            ["0 B cần upload"] = "0 B to upload",
            ["Sẵn sàng công bố manifest GitHub"] = "Ready to publish the GitHub manifest",
            ["giây"] = "sec",
            ["phút"] = "min",
            ["giờ"] = "hr",
            ["Đang đồng bộ Drive, xác minh checksum và công bố manifest GitHub…"] = "Syncing Drive, verifying checksums, and publishing the GitHub manifest…",
            ["Đang thay thế content-pack trên Drive và xác minh checksum…"] = "Replacing the content pack on Drive and verifying its checksum…",
            ["Thư mục đã chọn đã thay thế content-pack trên Drive; checksum đã xác minh. Hãy công bố manifest khi sẵn sàng."] = "The selected folder replaced its Drive content pack and the checksum was verified. Publish the manifest when ready.",
            ["Đã thay thế content-pack"] = "Content pack replaced",
            ["Binary mới đã sẵn sàng; công bố manifest để Actions và Telegram sử dụng."] = "The new binary is ready; publish the manifest for Actions and Telegram to use it.",
            ["Đồng bộ content-pack thất bại — xem lỗi chi tiết bên dưới."] = "Content-pack sync failed — review the details below.",
            ["Đang kiểm tra archive và công bố manifest lên GitHub…"] = "Checking archives and publishing the manifest to GitHub…",
            ["Manifest GitHub đã cập nhật; Actions và Telegram sẽ dùng catalog mới."] = "The GitHub manifest is updated; Actions and Telegram will use the new catalog.",
            ["Công bố manifest thất bại — xem lỗi chi tiết bên dưới."] = "Manifest publishing failed — review the details below.",
        };

    private async void NavigationSelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        var tag = (args.SelectedItemContainer as NavigationViewItem)?.Tag?.ToString() ?? "studio";
        StudioPage.Visibility = tag == "studio" ? Visibility.Visible : Visibility.Collapsed;
        ArtifactsPage.Visibility = tag == "artifacts" ? Visibility.Visible : Visibility.Collapsed;
        HybridPage.Visibility = tag == "hybrid" ? Visibility.Visible : Visibility.Collapsed;
        RomRenamerPage.Visibility = tag == "rom-renamer" ? Visibility.Visible : Visibility.Collapsed;
        CatalogPage.Visibility = tag == "catalog" ? Visibility.Visible : Visibility.Collapsed;
        DiagnosticsPage.Visibility = tag == "diagnostics" ? Visibility.Visible : Visibility.Collapsed;
        SettingsPage.Visibility = tag == "settings" ? Visibility.Visible : Visibility.Collapsed;
        var selectedPage = tag switch
        {
            "artifacts" => ArtifactsPage,
            "hybrid" => HybridPage,
            "rom-renamer" => RomRenamerPage,
            "catalog" => CatalogPage,
            "diagnostics" => DiagnosticsPage,
            "settings" => SettingsPage,
            _ => StudioPage,
        };
        selectedPage.ChangeView(null, 0, null, disableAnimation: true);
        if (tag == "artifacts")
        {
            await RefreshArtifactsAsync();
        }
        else if (tag == "catalog" && !_deviceEditorDirty)
        {
            await RefreshDevicesAsync();
        }
        else if (tag == "diagnostics")
        {
            await RefreshDiagnosticsAsync();
        }
        else if (tag == "settings")
        {
            await RefreshCacheAsync();
        }
        ApplyLocalization();
    }

    private HybridBuildRecipe BuildHybridRecipe()
    {
        static string SelectedTag(ComboBox combo) =>
            (combo.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? string.Empty;
        var source = HybridSourceBox.Text.Trim();
        var checksum = HybridChecksumBox.Text.Trim();
        var device = HybridDeviceBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(source) || string.IsNullOrWhiteSpace(device))
        {
            throw new InvalidOperationException("Hãy nhập mã thiết bị và nguồn ROM.");
        }
        var mods = HybridModsBox.Text
            .Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        return new HybridBuildRecipe(
            1,
            SelectedTag(HybridTaskCombo),
            device,
            new HybridSourceSpec(
                SelectedTag(HybridSourceKindCombo),
                source,
                string.IsNullOrWhiteSpace(checksum) ? null : checksum,
                long.TryParse(HybridSourceSizeBox.Text, out var sourceSize) && sourceSize > 0 ? sourceSize : null),
            new HybridBuildOptions(
                SelectedTag(HybridPresetCombo),
                mods,
                HybridModVersionBox.Text.Trim(),
                Package: true),
            new HybridExecutionOptions(SelectedTag(HybridExecutionCombo)),
            new HybridStorageOptions("wukong-gdrive", HybridPublishCheckBox.IsChecked == true));
    }

    private async void ChooseHybridSourceClick(object sender, RoutedEventArgs e)
    {
        if (_api is null) return;
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.Downloads };
        picker.FileTypeFilter.Add(".zip");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSingleFileAsync();
        if (file is null) return;
        var authorized = await _api.AuthorizeRomAsync(file.Path);
        HybridSourceKindCombo.SelectedIndex = 0;
        HybridSourceBox.Text = authorized.Path ?? file.Path;
    }

    private async void HybridSourceTextChanged(object sender, TextChangedEventArgs e)
    {
        _hybridSourceProbeCancellation?.Cancel();
        _hybridSourceProbeCancellation?.Dispose();
        _hybridSourceProbeCancellation = new CancellationTokenSource();
        var token = _hybridSourceProbeCancellation.Token;
        var value = HybridSourceBox.Text.Trim();
        HybridSourceDetailsBox.Text = string.Empty;
        HybridSourceSizeBox.Text = string.Empty;
        if (!string.IsNullOrWhiteSpace(_hybridProbedDevice)
            && HybridDeviceBox.Text.Trim() == _hybridProbedDevice)
        {
            HybridDeviceBox.Text = string.Empty;
        }
        _hybridProbedDevice = null;
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri)
            || uri.Scheme is not ("http" or "https"))
        {
            var isWindowsPath = Regex.IsMatch(value, @"^(?:[A-Za-z]:[\\/]|\\\\)");
            var isRclone = !isWindowsPath
                && Regex.IsMatch(value, @"^[A-Za-z0-9][A-Za-z0-9_.-]*:(?!//).+");
            HybridSourceKindCombo.SelectedIndex = isRclone ? 2 : 0;
            HybridSourceProbeInfo.IsOpen = !string.IsNullOrWhiteSpace(value);
            HybridSourceProbeInfo.Severity = InfoBarSeverity.Informational;
            HybridSourceProbeInfo.Title = Localized(isRclone ? "Đã nhận diện nguồn Drive" : "Nguồn local");
            HybridSourceProbeInfo.Message = Localized(isRclone
                ? "Metadata sẽ được kiểm tra khi job preflight tải nguồn riêng tư."
                : "File local sẽ được kiểm tra quyền truy cập và checksum trước khi build.");
            return;
        }
        HybridSourceKindCombo.SelectedIndex = 1;
        try
        {
            await Task.Delay(650, token);
            await ProbeHybridSourceAsync(token);
        }
        catch (OperationCanceledException)
        {
        }
    }

    private async void ProbeHybridSourceClick(object sender, RoutedEventArgs e)
    {
        _hybridSourceProbeCancellation?.Cancel();
        _hybridSourceProbeCancellation?.Dispose();
        _hybridSourceProbeCancellation = new CancellationTokenSource();
        await ProbeHybridSourceAsync(_hybridSourceProbeCancellation.Token);
    }

    private async Task ProbeHybridSourceAsync(CancellationToken cancellationToken)
    {
        if (_api is null) return;
        var source = HybridSourceBox.Text.Trim();
        if (!Uri.TryCreate(source, UriKind.Absolute, out var uri)
            || uri.Scheme is not ("http" or "https"))
        {
            HybridSourceProbeInfo.IsOpen = true;
            HybridSourceProbeInfo.Severity = InfoBarSeverity.Informational;
            HybridSourceProbeInfo.Title = Localized("Nguồn local hoặc Drive");
            HybridSourceProbeInfo.Message = Localized("Phân tích sâu tự động hiện áp dụng cho URL HTTP/HTTPS.");
            return;
        }
        HybridSourceProbeInfo.IsOpen = true;
        HybridSourceProbeInfo.Severity = InfoBarSeverity.Informational;
        HybridSourceProbeInfo.Title = Localized("Đang nhận diện ROM…");
        HybridSourceProbeInfo.Message = Localized("Chỉ đọc header và metadata ZIP, không tải toàn bộ ROM.");
        try
        {
            var result = await _api.ProbeHybridSourceAsync(source, cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (!string.Equals(HybridSourceBox.Text.Trim(), source, StringComparison.Ordinal))
            {
                return;
            }
            HybridSourceDetailsBox.Text = string.Join(" · ", new[]
            {
                result.Provider,
                result.ProductName ?? result.Device,
                result.Version,
                result.OtaType,
                result.SecurityPatch,
            }.Where(value => !string.IsNullOrWhiteSpace(value)));
            HybridSourceSizeBox.Text = result.SizeBytes?.ToString() ?? string.Empty;
            var detectedDevice = result.ProductName ?? result.Device;
            var catalogAcceptsDevice = _devices.Count == 0
                || _devices.Any(device => string.Equals(
                    device.ProductName,
                    detectedDevice,
                    StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrWhiteSpace(detectedDevice) && catalogAcceptsDevice)
            {
                HybridDeviceBox.Text = detectedDevice;
                _hybridProbedDevice = detectedDevice;
            }
            HybridSourceProbeInfo.Severity = result.DeepInspected
                ? InfoBarSeverity.Success
                : InfoBarSeverity.Warning;
            HybridSourceProbeInfo.Title = Localized(result.DeepInspected ? "Đã nhận diện ROM" : "Đã nhận diện nguồn");
            HybridSourceProbeInfo.Message = result.Warning
                ?? $"{result.Filename} · {(result.SizeBytes is long size ? FormatBytes(size) : Localized("không rõ dung lượng"))}";
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception exception)
        {
            HybridSourceProbeInfo.Severity = InfoBarSeverity.Error;
            HybridSourceProbeInfo.Title = Localized("Không thể phân tích ROM");
            HybridSourceProbeInfo.Message = exception.Message;
        }
    }

    private async void ValidateHybridRecipeClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null) return;
            var result = await _api.ValidateHybridRecipeAsync(BuildHybridRecipe());
            HybridResultBox.Text = JsonSerializer.Serialize(
                result,
                new JsonSerializerOptions { WriteIndented = true });
            ShowMessage("Recipe hợp lệ", $"Runner: {result.Runner.Runner}", InfoBarSeverity.Success);
        });
    }

    private async void CreateHybridJobClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null) return;
            var job = await _api.CreateHybridJobAsync(BuildHybridRecipe());
            HybridResultBox.Text = JsonSerializer.Serialize(
                job,
                new JsonSerializerOptions { WriteIndented = true });
            ShowMessage("Đã tạo job hybrid", $"{job.JobId} · {job.Runner}", InfoBarSeverity.Success);
            HybridJobIdBox.Text = job.JobId;
            await RefreshHybridJobsAsync();
        });
    }

    private async Task RefreshHybridJobsAsync()
    {
        if (_api is null) return;
        var jobs = await _api.GetHybridJobsAsync();
        HybridJobsList.Items.Clear();
        foreach (var job in jobs)
        {
            HybridJobsList.Items.Add(new ListViewItem
            {
                Tag = job.JobId,
                Content = $"{job.JobId}  ·  {job.Status}  ·  {job.Stage ?? "-"}  ·  {job.Runner}"
            });
        }
    }

    private async void RefreshHybridJobsClick(object sender, RoutedEventArgs e) =>
        await RunBusyActionAsync(RefreshHybridJobsAsync);

    private void HybridJobSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (HybridJobsList.SelectedItem is ListViewItem item && item.Tag is string jobId)
        {
            HybridJobIdBox.Text = jobId;
        }
    }

    private async void InspectHybridJobClick(object sender, RoutedEventArgs e) =>
        await RunHybridJobActionAsync("inspect");

    private async void CancelHybridJobClick(object sender, RoutedEventArgs e) =>
        await RunHybridJobActionAsync("cancel");

    private async void ResumeHybridJobClick(object sender, RoutedEventArgs e) =>
        await RunHybridJobActionAsync("resume");

    private async Task RunHybridJobActionAsync(string action)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null) return;
            var jobId = HybridJobIdBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(jobId)) throw new InvalidOperationException("Hãy chọn job.");
            var job = action switch
            {
                "cancel" => await _api.CancelHybridJobAsync(jobId),
                "resume" => await _api.ResumeHybridJobAsync(jobId),
                _ => await _api.GetHybridJobAsync(jobId),
            };
            if (action == "resume") HybridJobIdBox.Text = job.JobId;
            HybridResultBox.Text = JsonSerializer.Serialize(job, new JsonSerializerOptions { WriteIndented = true });
            await RefreshHybridJobsAsync();
        });
    }

    private async void ShowHybridSourcesClick(object sender, RoutedEventArgs e) =>
        await ShowHybridCloudAsync("sources");

    private async void ShowHybridArtifactsClick(object sender, RoutedEventArgs e) =>
        await ShowHybridCloudAsync("artifacts");

    private async Task ShowHybridCloudAsync(string category)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null) return;
            HybridResultBox.Text = (await _api.GetHybridCloudLibraryAsync(category)).GetRawText();
        });
    }

    private async void ShowHybridDiagnosticsClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is null) return;
            HybridResultBox.Text = (await _api.GetHybridDiagnosticsAsync()).GetRawText();
        });
    }

    private async void SyncContentToDriveClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _layout is null)
        {
            return;
        }
        var picker = new FolderPicker { SuggestedStartLocation = PickerLocationId.ComputerFolder };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is null)
        {
            return;
        }
        try
        {
            _contentSyncFolderSelection = ContentSyncFolderResolver.Resolve(_layout.InstallRoot, folder.Path);
            RenderContentSyncSelection();
        }
        catch (Exception exception)
        {
            HybridResultBox.Text = exception.Message;
            ShowMessage(
                Localized("Không thể chọn thư mục này"),
                Localized("Chỉ chọn thư mục được quản lý bên trong Content."),
                InfoBarSeverity.Error);
            return;
        }
        var selection = _contentSyncFolderSelection!;
        var confirmed = await ConfirmDialogAsync(
            Localized("Thay thế content-pack trên Drive?"),
            $"{Localized("Thư mục đã chọn")}:\n{selection.SelectedFolder}\n\n" +
            $"{Localized("Content-pack sẽ bị thay thế toàn bộ")}:\n{selection.PackId}\n\n" +
            $"{Localized("Phạm vi được đóng gói")}:\n{selection.PackRoot}\n\n" +
            Localized("Archive hiện tại trên Drive sẽ bị ghi đè trong khi upload, sau đó mới được xác minh. Nếu xác minh thất bại, Drive có thể đã chứa archive mới nhưng index cục bộ vẫn giữ bản đã xác minh trước đó."),
            Localized("Thay thế trên Drive"),
            destructive: true);
        if (!confirmed)
        {
            return;
        }
        _contentSyncCancellation = new CancellationTokenSource();
        await RunBusyActionAsync(async () =>
        {
            BeginContentSyncProgress();
            ContentSyncStatusText.Text = Localized("Đang thay thế content-pack trên Drive và xác minh checksum…");
            try
            {
                var driveOutput = await RunPlatformContentSyncAsync("drive", selection.SelectedFolder, _contentSyncCancellation.Token);
                HybridResultBox.Text = driveOutput;
                ContentSyncStatusText.Text = Localized("Thư mục đã chọn đã thay thế content-pack trên Drive; checksum đã xác minh. Hãy công bố manifest khi sẵn sàng.");
                CompleteContentSyncProgress();
                ShowMessage(
                    Localized("Đã thay thế content-pack"),
                    $"{selection.PackId} · {Localized("Binary mới đã sẵn sàng; công bố manifest để Actions và Telegram sử dụng.")}",
                    InfoBarSeverity.Success);
            }
            catch (OperationCanceledException)
            {
                ContentSyncStatusText.Text = Localized("Upload đã dừng; index cục bộ không thay đổi.");
                HybridResultBox.Text = Localized("Đã hủy đồng bộ");
                CancelContentSyncProgress();
                throw;
            }
            catch (Exception exception)
            {
                ContentSyncStatusText.Text = Localized("Đồng bộ content-pack thất bại — xem lỗi chi tiết bên dưới.");
                HybridResultBox.Text = exception.Message;
                FailContentSyncProgress();
                throw;
            }
        });
        _contentSyncCancellation.Dispose();
        _contentSyncCancellation = null;
    }

    private async void PublishContentManifestClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(async () =>
        {
            BeginContentSyncProgress(manifestOnly: true);
            ContentSyncStatusText.Text = Localized("Đang kiểm tra archive và công bố manifest lên GitHub…");
            try
            {
                var output = await RunPlatformContentSyncAsync("github");
                HybridResultBox.Text = output;
                ContentSyncStatusText.Text = Localized("Manifest GitHub đã cập nhật; Actions và Telegram sẽ dùng catalog mới.");
                CompleteContentSyncProgress(manifestOnly: true);
                ShowMessage(
                    "Đã công bố manifest",
                    "GitHub Actions và catalog Telegram đã nhận mốc content-pack mới.",
                    InfoBarSeverity.Success);
            }
            catch (Exception exception)
            {
                ContentSyncStatusText.Text = Localized("Công bố manifest thất bại — xem lỗi chi tiết bên dưới.");
                HybridResultBox.Text = exception.Message;
                FailContentSyncProgress();
                throw;
            }
        });
    }

    private async Task<string> RunPlatformContentSyncAsync(
        string target,
        string? selectedFolder = null,
        CancellationToken cancellationToken = default)
    {
        if (_layout is null)
        {
            throw new InvalidOperationException("Studio layout chưa sẵn sàng.");
        }
        var credentials = new HybridSecretStore(_layout).Load()
            ?? throw new InvalidOperationException("Hãy lưu GitHub token và rclone.conf trong Thiết đặt trước.");
        var python = Path.Combine(_layout.PythonRoot, "python.exe");
        var script = Path.Combine(_layout.ScriptsRoot, "tools", "sync_platform_content.py");
        var templateIndex = Path.Combine(_layout.ScriptsRoot, "content-packs", "index.json");
        var syncDataRoot = Path.Combine(_layout.DataRoot, "ContentSync");
        var index = Path.Combine(syncDataRoot, "index.json");
        var runId = Guid.NewGuid().ToString("N");
        if (!File.Exists(python) || !File.Exists(script) || !File.Exists(templateIndex))
        {
            throw new FileNotFoundException("Runtime đồng bộ content-pack chưa được cài đầy đủ. Hãy build/cài lại Wukong ROM Studio.");
        }
        Directory.CreateDirectory(syncDataRoot);
        if (!File.Exists(index))
        {
            File.Copy(templateIndex, index);
        }
        Directory.CreateDirectory(_layout.SecretsRoot);
        var rcloneConfig = Path.Combine(_layout.SecretsRoot, $".content-sync-{Guid.NewGuid():N}.conf");
        try
        {
            await File.WriteAllTextAsync(rcloneConfig, credentials.RcloneConfig, new UTF8Encoding(false));
            File.SetAttributes(rcloneConfig, FileAttributes.Hidden | FileAttributes.Temporary);
            var startInfo = new System.Diagnostics.ProcessStartInfo
            {
                FileName = python,
                WorkingDirectory = _layout.ScriptsRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            startInfo.ArgumentList.Add("-m");
            startInfo.ArgumentList.Add("tools.sync_platform_content");
            startInfo.ArgumentList.Add("--install-root");
            startInfo.ArgumentList.Add(_layout.InstallRoot);
            startInfo.ArgumentList.Add("--index");
            startInfo.ArgumentList.Add(index);
            startInfo.ArgumentList.Add("--baseline-index");
            startInfo.ArgumentList.Add(templateIndex);
            startInfo.ArgumentList.Add("--remote");
            startInfo.ArgumentList.Add($"{credentials.RcloneRemote.TrimEnd(':')}:WukongROM/content-packs");
            startInfo.ArgumentList.Add("--target");
            startInfo.ArgumentList.Add(target);
            startInfo.ArgumentList.Add("--run-id");
            startInfo.ArgumentList.Add(runId);
            if (!string.IsNullOrWhiteSpace(selectedFolder))
            {
                startInfo.ArgumentList.Add("--folder");
                startInfo.ArgumentList.Add(selectedFolder);
            }
            startInfo.ArgumentList.Add("--repository");
            startInfo.ArgumentList.Add(credentials.GitHubRepository);
            if (target == "drive")
            {
                startInfo.ArgumentList.Add("--rclone-config");
                startInfo.ArgumentList.Add(rcloneConfig);
                if (string.IsNullOrWhiteSpace(selectedFolder))
                {
                    startInfo.ArgumentList.Add("--migrate-shared");
                }
            }
            startInfo.Environment["PYTHONUTF8"] = "1";
            startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
            startInfo.Environment["WUKONG_GITHUB_REPOSITORY"] = credentials.GitHubRepository;
            startInfo.Environment["WUKONG_GITHUB_TOKEN"] = credentials.GitHubToken;
            startInfo.Environment["PATH"] = string.Join(
                Path.PathSeparator,
                Path.Combine(_layout.RuntimeRoot, "Bin", "Windows", "AMD64"),
                Environment.GetEnvironmentVariable("PATH"));
            using var process = new System.Diagnostics.Process { StartInfo = startInfo };
            if (!process.Start())
            {
                throw new InvalidOperationException("Không thể khởi động tác vụ đồng bộ content-pack.");
            }
            using var cancellationRegistration = cancellationToken.Register(
                () => TryTerminateContentSyncProcess(process));
            try
            {
                var errorTask = process.StandardError.ReadToEndAsync();
                var output = new StringBuilder();
                while (await process.StandardOutput.ReadLineAsync(cancellationToken) is { } line)
                {
                    output.AppendLine(line);
                    if (target == "drive" && ContentSyncProgressProtocol.TryParse(line, out var progress))
                    {
                        RenderContentSyncProgress(progress!);
                    }
                    else if (target == "drive"
                        && ContentSyncProgressProtocol.TryReadChangedPackCount(line, out var changedPackCount))
                    {
                        _contentSyncUploadedChanges = changedPackCount > 0;
                        if (changedPackCount == 0)
                        {
                            ShowContentSyncNoChanges();
                        }
                    }
                }
                await process.WaitForExitAsync(cancellationToken);
                var error = await errorTask;
                if (process.ExitCode != 0)
                {
                    throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? output.ToString() : error);
                }
                return output.ToString().Trim();
            }
            catch (OperationCanceledException)
            {
                if (!TryTerminateContentSyncProcess(process))
                {
                    throw new InvalidOperationException(
                        "Không thể dừng tiến trình đồng bộ. Hãy đóng Studio trước khi xóa file tạm.");
                }
                await process.WaitForExitAsync();
                CleanupContentSyncRunArtifacts(syncDataRoot, index, runId);
                throw;
            }
        }
        finally
        {
            if (File.Exists(rcloneConfig))
            {
                File.SetAttributes(rcloneConfig, FileAttributes.Normal);
                File.Delete(rcloneConfig);
            }
        }
    }

    private static bool TryTerminateContentSyncProcess(System.Diagnostics.Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
            return true;
        }
        catch (InvalidOperationException)
        {
            return process.HasExited;
        }
        catch (Win32Exception)
        {
            return false;
        }
        catch (NotSupportedException)
        {
            return false;
        }
        catch (AggregateException)
        {
            return false;
        }
    }

    private static void CleanupContentSyncRunArtifacts(string syncDataRoot, string index, string runId)
    {
        TryDeleteContentSyncArtifact(Path.Combine(syncDataRoot, $".{Path.GetFileName(index)}.{runId}.working"));
        var archiveRoot = Path.Combine(syncDataRoot, "archives");
        if (!Directory.Exists(archiveRoot))
        {
            return;
        }
        foreach (var artifact in Directory.EnumerateFiles(
            archiveRoot,
            $"*.{runId}.tar*",
            SearchOption.TopDirectoryOnly))
        {
            TryDeleteContentSyncArtifact(artifact);
        }
    }

    private static void TryDeleteContentSyncArtifact(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (IOException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private void RenderContentSyncSelection()
    {
        ContentSyncSelectionText.Text = _contentSyncFolderSelection is null
            ? Localized("Chọn thư mục trong Content; Content\\STARK chứa WK_Manager và com.")
            : $"{Localized("Sẽ thay thế pack")} {_contentSyncFolderSelection.PackId} · {_contentSyncFolderSelection.PackRoot}";
    }

    private void BeginContentSyncProgress(bool manifestOnly = false)
    {
        _contentSyncVisualState = manifestOnly ? "manifest" : "preparing";
        _contentSyncUploadedChanges = false;
        _lastContentSyncProgress = null;
        ContentSyncProgressPanel.Visibility = Visibility.Visible;
        CancelContentSyncButton.Content = Localized("Hủy upload");
        CancelContentSyncButton.IsEnabled = !manifestOnly;
        CancelContentSyncButton.Visibility = manifestOnly ? Visibility.Collapsed : Visibility.Visible;
        ContentSyncPhaseText.Foreground = null;
        ContentSyncPercentText.Foreground = (Brush)Resources["PrimaryBrush"];
        ContentSyncPhaseText.Text = manifestOnly
            ? Localized("Đang công bố manifest")
            : Localized("Đang chuẩn bị đồng bộ");
        ContentSyncPackText.Text = manifestOnly
            ? Localized("Đang kiểm tra checksum và catalog…")
            : _contentSyncFolderSelection is null
                ? Localized("Đang kiểm tra nội dung thay đổi…")
                : $"{Localized("Gói 1/1")} · {_contentSyncFolderSelection.PackId}";
        ContentSyncPercentText.Text = "—";
        ContentSyncProgressBar.Value = 0;
        ContentSyncProgressBar.IsIndeterminate = true;
        ContentSyncBytesText.Text = Localized("Đang tính dung lượng…");
        ContentSyncSpeedText.Text = Localized("Tốc độ — · ETA —");
        AutomationProperties.SetName(
            ContentSyncProgressBar,
            Localized("Tiến độ đồng bộ content-pack"));
    }

    private void RenderContentSyncProgress(ContentSyncProgressSnapshot progress)
    {
        _contentSyncVisualState = "progress";
        _contentSyncUploadedChanges = true;
        _lastContentSyncProgress = progress;
        ContentSyncProgressPanel.Visibility = Visibility.Visible;
        ContentSyncPackText.Text = ContentSyncPackLabel(progress);

        switch (progress.Phase)
        {
            case "archive":
                ContentSyncPhaseText.Text = Localized("Đang đóng gói content-pack");
                ContentSyncPercentText.Text = "—";
                ContentSyncProgressBar.IsIndeterminate = true;
                ContentSyncBytesText.Text = Localized("Đang tạo archive nén…");
                ContentSyncSpeedText.Text = Localized("Chuẩn bị upload");
                break;
            case "upload":
                ContentSyncPhaseText.Text = Localized("Đang upload lên Google Drive");
                ContentSyncProgressBar.IsIndeterminate = false;
                ContentSyncProgressBar.Value = progress.Percent;
                ContentSyncPercentText.Text = $"{progress.Percent:0.#}%";
                ContentSyncBytesText.Text = $"{FormatTransferBytes(progress.Bytes)} / {FormatTransferBytes(progress.TotalBytes)}";
                var speed = progress.SpeedBytesPerSecond > 0
                    ? $"{FormatTransferBytes(progress.SpeedBytesPerSecond)}/s"
                    : Localized("Đang đo tốc độ…");
                var eta = progress.EtaSeconds is double etaSeconds
                    ? $"{Localized("Còn lại")} {FormatTransferDuration(etaSeconds)}"
                    : Localized("Đang tính ETA…");
                ContentSyncSpeedText.Text = $"{speed} · {eta}";
                break;
            case "verify-remote":
                ShowContentSyncVerification(progress, Localized("Đang xác minh dung lượng và checksum trên Drive"));
                break;
            case "verify-download":
                ShowContentSyncVerification(progress, Localized("Đang tải xuống để kiểm tra toàn vẹn"));
                break;
            case "complete":
                ContentSyncPhaseText.Text = Localized("Content-pack đã xác minh");
                ContentSyncProgressBar.IsIndeterminate = false;
                ContentSyncProgressBar.Value = 100;
                ContentSyncPercentText.Text = "100%";
                ContentSyncBytesText.Text = FormatTransferBytes(progress.TotalBytes);
                ContentSyncSpeedText.Text = Localized("Sẵn sàng cho pack tiếp theo");
                break;
        }
    }

    private void ShowContentSyncVerification(ContentSyncProgressSnapshot progress, string phase)
    {
        ContentSyncPhaseText.Text = phase;
        ContentSyncProgressBar.IsIndeterminate = true;
        ContentSyncProgressBar.Value = 100;
        ContentSyncPercentText.Text = "100%";
        ContentSyncBytesText.Text = FormatTransferBytes(progress.TotalBytes);
        ContentSyncSpeedText.Text = Localized("Đang đối chiếu dữ liệu…");
    }

    private void ShowContentSyncPublishing()
    {
        _contentSyncVisualState = "publishing";
        _lastContentSyncProgress = null;
        ContentSyncPhaseText.Text = Localized("Đang công bố manifest");
        ContentSyncPackText.Text = _contentSyncUploadedChanges
            ? Localized("Đang cập nhật catalog GitHub…")
            : Localized("Không có pack thay đổi; đang kiểm tra manifest hiện tại…");
        ContentSyncProgressBar.IsIndeterminate = true;
        ContentSyncPercentText.Text = _contentSyncUploadedChanges ? "100%" : Localized("Không đổi");
        ContentSyncSpeedText.Text = _contentSyncUploadedChanges
            ? Localized("Binary trên Drive đã xác minh")
            : Localized("Đã bỏ qua upload Drive");
    }

    private void CompleteContentSyncProgress(bool manifestOnly = false)
    {
        _contentSyncVisualState = manifestOnly ? "manifest-complete" : "complete";
        _lastContentSyncProgress = null;
        ContentSyncPhaseText.Text = Localized("Đồng bộ hoàn tất");
        ContentSyncPackText.Text = manifestOnly
            ? Localized("Manifest GitHub đã được công bố")
            : _contentSyncUploadedChanges
                ? Localized("Drive đã nhận và xác minh dữ liệu mới")
                : Localized("Không có content-pack thay đổi; manifest hiện tại đã xác minh");
        ContentSyncProgressBar.IsIndeterminate = false;
        ContentSyncProgressBar.Value = 100;
        ContentSyncPercentText.Text = !manifestOnly && !_contentSyncUploadedChanges
            ? Localized("Không đổi")
            : "100%";
        ContentSyncSpeedText.Text = !manifestOnly && !_contentSyncUploadedChanges
            ? Localized("Đã bỏ qua upload Drive")
            : Localized("Checksum đã xác minh");
        CancelContentSyncButton.Visibility = Visibility.Collapsed;
    }

    private void FailContentSyncProgress()
    {
        _contentSyncVisualState = "failed";
        if (_lastContentSyncProgress is not null)
        {
            ContentSyncPackText.Text = ContentSyncPackLabel(_lastContentSyncProgress);
        }
        ContentSyncPhaseText.Text = Localized("Đồng bộ thất bại");
        ContentSyncPhaseText.Foreground = (Brush)Resources["ErrorBrush"];
        ContentSyncProgressBar.IsIndeterminate = false;
        ContentSyncProgressBar.Value = 0;
        ContentSyncPercentText.Text = Localized("Lỗi");
        ContentSyncPercentText.Foreground = (Brush)Resources["ErrorBrush"];
        ContentSyncSpeedText.Text = Localized("Xem log chi tiết bên dưới để xử lý");
        CancelContentSyncButton.Visibility = Visibility.Collapsed;
    }

    private void CancelContentSyncClick(object sender, RoutedEventArgs e)
    {
        CancelContentSyncButton.IsEnabled = false;
        _contentSyncCancellation?.Cancel();
    }

    private void CancelContentSyncProgress()
    {
        _contentSyncVisualState = "canceled";
        ContentSyncPhaseText.Text = Localized("Đã hủy đồng bộ");
        ContentSyncPhaseText.Foreground = (Brush)Resources["MutedBrush"];
        ContentSyncProgressBar.IsIndeterminate = false;
        ContentSyncPercentText.Text = "—";
        ContentSyncPercentText.Foreground = (Brush)Resources["MutedBrush"];
        ContentSyncSpeedText.Text = Localized("Upload đã dừng; index cục bộ không thay đổi.");
        CancelContentSyncButton.Visibility = Visibility.Collapsed;
    }

    private string ContentSyncPackLabel(ContentSyncProgressSnapshot progress)
    {
        var position = progress.PackCount > 1
            ? $"{Localized("Gói")} {progress.PackIndex}/{progress.PackCount}"
            : Localized("Gói 1/1");
        return $"{position} · {progress.PackId}";
    }

    private void ShowContentSyncNoChanges()
    {
        _contentSyncVisualState = "no-changes";
        _lastContentSyncProgress = null;
        ContentSyncProgressPanel.Visibility = Visibility.Visible;
        ContentSyncPhaseText.Text = Localized("Không có content-pack thay đổi");
        ContentSyncPackText.Text = Localized("Drive không cần upload binary mới");
        ContentSyncProgressBar.IsIndeterminate = false;
        ContentSyncProgressBar.Value = 100;
        ContentSyncPercentText.Text = Localized("Không đổi");
        ContentSyncBytesText.Text = Localized("0 B cần upload");
        ContentSyncSpeedText.Text = Localized("Sẵn sàng công bố manifest GitHub");
        CancelContentSyncButton.Visibility = Visibility.Collapsed;
    }

    private void RefreshContentSyncLocalization()
    {
        RenderContentSyncSelection();
        if (ContentSyncProgressPanel.Visibility != Visibility.Visible)
        {
            return;
        }
        AutomationProperties.SetName(
            ContentSyncProgressBar,
            Localized("Tiến độ đồng bộ content-pack"));
        switch (_contentSyncVisualState)
        {
            case "preparing": BeginContentSyncProgress(); break;
            case "manifest": BeginContentSyncProgress(manifestOnly: true); break;
            case "progress" when _lastContentSyncProgress is not null:
                RenderContentSyncProgress(_lastContentSyncProgress);
                break;
            case "no-changes": ShowContentSyncNoChanges(); break;
            case "publishing": ShowContentSyncPublishing(); break;
            case "complete": CompleteContentSyncProgress(); break;
            case "manifest-complete": CompleteContentSyncProgress(manifestOnly: true); break;
            case "failed": FailContentSyncProgress(); break;
            case "canceled": CancelContentSyncProgress(); break;
        }
    }

    private static string FormatTransferBytes(double value) =>
        value <= 0 ? "0 B" : FormatBytes((long)value);

    private string FormatTransferDuration(double seconds)
    {
        if (seconds < 60)
        {
            return $"{Math.Max(1, (int)Math.Ceiling(seconds))} {Localized("giây")}";
        }
        if (seconds < 3600)
        {
            return $"{Math.Ceiling(seconds / 60):0} {Localized("phút")}";
        }
        return $"{Math.Floor(seconds / 3600):0} {Localized("giờ")} {Math.Ceiling(seconds % 3600 / 60):0} {Localized("phút")}";
    }

    private async Task RefreshArtifactsAsync()
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is not null)
            {
                PopulateArtifacts(await _api.GetArtifactsAsync());
            }
        });
    }

    private async Task RefreshDiagnosticsAsync()
    {
        await RunBusyActionAsync(async () =>
        {
            if (_api is not null)
            {
                PopulateDiagnostics(await _api.GetDiagnosticsAsync());
            }
        });
    }

    private void ModVersionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_configuring || _bootstrap is null || ModVersionCombo.SelectedItem is null)
        {
            return;
        }
        _configuring = true;
        RebuildModOptions(applyPreset: true);
        UpdateSelectedStudioVersion();
        _configuring = false;
        InvalidatePreflight();
        if (_layout is not null)
        {
            _desktopSettings = _desktopSettings with { LastModVersion = SelectedTag(ModVersionCombo) };
            _desktopSettings.Save(_layout);
        }
    }

    private void PresetChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_configuring || _bootstrap is null || PresetCombo.SelectedItem is null)
        {
            return;
        }
        _configuring = true;
        if (SelectedPreset() != "custom")
        {
            RebuildModOptions(applyPreset: true);
            RebuildStepOptions(applyPreset: true);
        }
        _configuring = false;
        InvalidatePreflight();
    }

    private void ConfigurationOptionChanged(object sender, RoutedEventArgs e)
    {
        if (_configuring || _bootstrap is null)
        {
            return;
        }
        _configuring = true;
        SelectComboByTag(PresetCombo, "custom");
        _configuring = false;
        UpdateConfigurationSummaries();
        InvalidatePreflight();
    }

    private void StudioPageSizeChanged(object sender, SizeChangedEventArgs e)
    {
        SetViewportContentWidth(StudioContent, e.NewSize.Width);
        UpdateResponsiveLayout(e.NewSize.Width);
    }

    private void SecondaryPageSizeChanged(object sender, SizeChangedEventArgs e)
    {
        if (ReferenceEquals(sender, ArtifactsPage))
        {
            SetViewportContentWidth(ArtifactsContent, e.NewSize.Width);
        }
        else if (ReferenceEquals(sender, RomRenamerPage))
        {
            SetViewportContentWidth(RomRenamerContent, e.NewSize.Width);
        }
        else if (ReferenceEquals(sender, CatalogPage))
        {
            SetViewportContentWidth(CatalogContent, e.NewSize.Width);
        }
        else if (ReferenceEquals(sender, DiagnosticsPage))
        {
            SetViewportContentWidth(DiagnosticsContent, e.NewSize.Width);
        }
        else if (ReferenceEquals(sender, SettingsPage))
        {
            SetViewportContentWidth(SettingsContent, e.NewSize.Width);
        }
        UpdateResponsiveLayout(e.NewSize.Width);
    }

    private static void SetViewportContentWidth(FrameworkElement content, double viewportWidth)
    {
        if (viewportWidth <= 0)
        {
            return;
        }
        var targetWidth = Math.Min(content.MaxWidth, viewportWidth);
        if (double.IsNaN(content.Width) || Math.Abs(content.Width - targetWidth) >= 0.5)
        {
            content.Width = targetWidth;
        }
    }

    private void StudioPageViewChanged(object? sender, ScrollViewerViewChangedEventArgs e)
    {
        if (!e.IsIntermediate)
        {
            RenderDeferredLogIfVisible();
        }
    }

    private void UpdateResponsiveLayout(double contentWidth)
    {
        var nextState = contentWidth >= 1280
            ? "WideLayout"
            : contentWidth >= 840
                ? "MediumLayout"
                : "NarrowLayout";
        if (string.Equals(nextState, _responsiveState, StringComparison.Ordinal))
        {
            return;
        }
        if (VisualStateManager.GoToState(this, nextState, useTransitions: false))
        {
            _responsiveState = nextState;
            UpdateBuildSectionsLayout();
            RelayoutModCards();
        }
    }

    private void ScheduleBuildSectionLayoutUpdate()
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            UpdateBuildSectionsLayout();
            RelayoutModCards();
        });
    }

    private void UpdateBuildSectionsLayout()
    {
        var sideBySide = string.Equals(_responsiveState, "WideLayout", StringComparison.Ordinal)
            && ModOptionsExpander.IsExpanded
            && PipelineStepsExpander.IsExpanded;
        BuildPipelineColumn.Width = sideBySide
            ? new GridLength(0.92, GridUnitType.Star)
            : new GridLength(0);
        Grid.SetRow(BuildPipelineCard, sideBySide ? 0 : 1);
        Grid.SetColumn(BuildPipelineCard, sideBySide ? 1 : 0);
        BuildSectionsGrid.RowSpacing = sideBySide ? 0 : 12;
    }

    private void ModsPanelSizeChanged(object sender, SizeChangedEventArgs e) => RelayoutModCards(e.NewSize.Width);

    private void ModSearchChanged(object sender, TextChangedEventArgs e)
    {
        ApplyModFilter();
        RelayoutModCards();
    }

    private void ApplyModFilter()
    {
        var query = ModSearchBox.Text.Trim();
        foreach (var (name, card) in _modCards)
        {
            card.Visibility = query.Length == 0 || name.Contains(query, StringComparison.OrdinalIgnoreCase)
                ? Visibility.Visible
                : Visibility.Collapsed;
        }
    }

    private void RelayoutModCards(double? availableWidth = null)
    {
        var width = availableWidth.GetValueOrDefault(ModsPanel.ActualWidth);
        var columns = width switch
        {
            >= 1080 => 4,
            >= 760 => 3,
            >= 430 => 2,
            _ => 1,
        };
        ModsPanel.ColumnDefinitions.Clear();
        ModsPanel.RowDefinitions.Clear();
        for (var index = 0; index < columns; index++)
        {
            ModsPanel.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        }

        var visibleCards = _modCards.Values
            .Where(card => card.Visibility == Visibility.Visible)
            .ToArray();
        var rows = (int)Math.Ceiling(visibleCards.Length / (double)columns);
        for (var index = 0; index < rows; index++)
        {
            ModsPanel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        }
        for (var index = 0; index < visibleCards.Length; index++)
        {
            Grid.SetRow(visibleCards[index], index / columns);
            Grid.SetColumn(visibleCards[index], index % columns);
        }
    }

    private void SelectAllModsClick(object sender, RoutedEventArgs e) => SetAllMods(selected: true);

    private void ClearModsClick(object sender, RoutedEventArgs e) => SetAllMods(selected: false);

    private void SetAllMods(bool selected)
    {
        if (_bootstrap is null)
        {
            return;
        }
        _configuring = true;
        foreach (var check in _modChecks.Values.Where(check => check.IsEnabled))
        {
            check.IsChecked = selected;
        }
        SelectComboByTag(PresetCombo, "custom");
        _configuring = false;
        UpdateConfigurationSummaries();
        InvalidatePreflight();
    }

    private void SelectAllStepsClick(object sender, RoutedEventArgs e) => SetAllSteps(_ => true);

    private void ClearStepsClick(object sender, RoutedEventArgs e) => SetAllSteps(_ => false);

    private void ResetStepsToPresetClick(object sender, RoutedEventArgs e)
    {
        var preset = SelectedPreset();
        if (preset == "custom")
        {
            preset = _bootstrap?.Settings.DefaultPreset ?? "lite";
        }
        SetAllSteps(stepId => DefaultSteps.Contains(stepId) || stepId == "notify_telegram" && NotifyTelegramCheckBox.IsChecked == true);
        ShowMessage("Đã khôi phục pipeline", $"Các bước đã được đưa về cấu hình {PresetDisplayName(preset)}.", InfoBarSeverity.Informational);
    }

    private void SetAllSteps(Func<string, bool> selector)
    {
        if (_bootstrap is null)
        {
            return;
        }
        _configuring = true;
        foreach (var (stepId, check) in _stepChecks)
        {
            check.IsChecked = selector(stepId);
        }
        if (_stepChecks.TryGetValue("notify_telegram", out var notifyStep))
        {
            NotifyTelegramCheckBox.IsChecked = notifyStep.IsChecked == true;
        }
        SelectComboByTag(PresetCombo, "custom");
        _configuring = false;
        UpdateConfigurationSummaries();
        InvalidatePreflight();
    }

    private async void ExportBuildProfileClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _bootstrap is null)
        {
            return;
        }
        var selectedRecipe = SelectedRecipe();
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = SafeFileName(selectedRecipe?.Name
                ?? $"Wukong-{SelectedTag(ModVersionCombo)}-{SelectedPreset()}-profile"),
        };
        picker.FileTypeChoices.Add("Wukong build profile", [".json"]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSaveFileAsync();
        if (file is null)
        {
            return;
        }

        await RunBusyActionAsync(async () =>
        {
            if (selectedRecipe is not null && _recipeStore is not null)
            {
                _recipeStore.Export(selectedRecipe.Id, file.Path);
            }
            else
            {
                var profile = CaptureBuildProfile(Path.GetFileNameWithoutExtension(file.Name));
                await File.WriteAllTextAsync(file.Path, profile.ToJson(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
            }
            ShowMessage("Đã xuất build profile", file.Path, InfoBarSeverity.Success);
        });
    }

    private async void ImportBuildProfileClick(object sender, RoutedEventArgs e)
    {
        if (_owner is null || _bootstrap is null)
        {
            return;
        }
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.DocumentsLibrary };
        picker.FileTypeFilter.Add(".json");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(_owner));
        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }

        await RunBusyActionAsync(async () =>
        {
            var recipe = _recipeStore?.Import(file.Path);
            var profile = recipe?.Profile ?? StudioBuildProfile.Parse(await File.ReadAllTextAsync(file.Path));
            var (unknownMods, unknownSteps) = ApplyBuildProfile(profile);
            if (recipe is not null)
            {
                LoadRecipes(recipe.Id);
            }
            var ignored = unknownMods + unknownSteps;
            ShowMessage(
                ignored == 0 ? "Đã nhập build profile" : "Đã nhập profile với cảnh báo",
                ignored == 0
                    ? $"Đã áp dụng {profile.ModNames.Count} MOD và {profile.EnabledSteps.Count} bước."
                    : $"Đã bỏ qua {unknownMods} MOD và {unknownSteps} bước không còn tồn tại.",
                ignored == 0 ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        });
    }

    private StudioBuildProfile CaptureBuildProfile(string name) => StudioBuildProfile.Create(
        name,
        SelectedTag(ModVersionCombo) ?? string.Empty,
        SelectedPreset(),
        _modChecks.Where(item => item.Value.IsChecked == true).Select(item => item.Key),
        _debloatPaths,
        _stepChecks.Where(item => item.Value.IsChecked == true).Select(item => item.Key),
        NotifyTelegramCheckBox.IsChecked == true);

    private (int UnknownMods, int UnknownSteps) ApplyBuildProfile(StudioBuildProfile profile)
    {
        var versionExists = ModVersionCombo.Items
            .OfType<ComboBoxItem>()
            .Any(item => string.Equals(item.Tag?.ToString(), profile.ModVersion, StringComparison.Ordinal));
        if (!versionExists)
        {
            throw new InvalidDataException($"Phiên bản MOD không tồn tại: {profile.ModVersion}");
        }

        _configuring = true;
        try
        {
            SelectComboByTag(ModVersionCombo, profile.ModVersion);
            SelectComboByTag(PresetCombo, profile.Preset);
            if (PresetCombo.SelectedItem is null)
            {
                SelectComboByTag(PresetCombo, "custom");
            }
            RebuildModOptions(applyPreset: true);
            RebuildStepOptions(applyPreset: true);

            var requestedMods = profile.ModNames.ToHashSet(StringComparer.Ordinal);
            foreach (var (name, check) in _modChecks)
            {
                check.IsChecked = check.IsEnabled && requestedMods.Contains(name);
            }
            var requestedSteps = profile.EnabledSteps.ToHashSet(StringComparer.Ordinal);
            foreach (var (stepId, check) in _stepChecks)
            {
                check.IsChecked = requestedSteps.Contains(stepId);
            }
            _debloatPaths.Clear();
            _debloatPaths.AddRange(profile.DebloatPaths);
            NotifyTelegramCheckBox.IsChecked = profile.NotifyTelegram && NotifyTelegramCheckBox.IsEnabled;
            if (_stepChecks.TryGetValue("notify_telegram", out var notifyStep))
            {
                notifyStep.IsChecked = NotifyTelegramCheckBox.IsChecked == true;
            }
        }
        finally
        {
            _configuring = false;
        }

        ApplyModFilter();
        RelayoutModCards();
        RebuildStepOptions(applyPreset: false);
        UpdateSelectedStudioVersion();
        UpdateConfigurationSummaries();
        InvalidatePreflight();
        ApplyLocalization();
        return (
            profile.ModNames.Count(name => !_modChecks.ContainsKey(name)),
            profile.EnabledSteps.Count(step => !_stepChecks.ContainsKey(step)));
    }

    private void LoadRecipes(string? preferredId = null)
    {
        if (_recipeStore is null)
        {
            return;
        }
        var selectedId = preferredId ?? SelectedTag(RecipeCombo);
        _recipes.Clear();
        _recipes.AddRange(_recipeStore.List());
        _configuring = true;
        try
        {
            RecipeCombo.Items.Clear();
            foreach (var recipe in _recipes)
            {
                RecipeCombo.Items.Add(new ComboBoxItem
                {
                    Content = recipe.Locked ? $"{recipe.Name} · khóa" : recipe.Name,
                    Tag = recipe.Id,
                });
            }
            if (!string.IsNullOrWhiteSpace(selectedId))
            {
                SelectComboByTag(RecipeCombo, selectedId);
            }
        }
        finally
        {
            _configuring = false;
        }
        UpdateRecipeState();
    }

    private StudioBuildRecipe? SelectedRecipe() => SelectedTag(RecipeCombo) is { Length: > 0 } id
        ? _recipes.FirstOrDefault(recipe => recipe.Id == id)
        : null;

    private void RecipeSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_configuring)
        {
            return;
        }
        var recipe = SelectedRecipe();
        RecipeNameBox.Text = recipe?.Name ?? string.Empty;
        UpdateRecipeState();
        if (_layout is not null)
        {
            _desktopSettings = _desktopSettings with { LastRecipeId = recipe?.Id };
            _desktopSettings.Save(_layout);
        }
    }

    private void UpdateRecipeState()
    {
        var recipe = SelectedRecipe();
        RecipeStateText.Text = recipe is null
            ? "Chưa chọn recipe"
            : recipe.Locked ? "Đã khóa · chỉ đọc" : "Có thể chỉnh sửa";
        LockRecipeButton.Label = recipe?.Locked == true ? "Mở khóa" : "Khóa";
    }

    private void NewRecipeClick(object sender, RoutedEventArgs e)
    {
        _configuring = true;
        RecipeCombo.SelectedItem = null;
        _configuring = false;
        RecipeNameBox.Text = string.Empty;
        UpdateRecipeState();
        RecipeNameBox.Focus(FocusState.Programmatic);
    }

    private async void ApplyRecipeClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(() =>
        {
            var recipe = SelectedRecipe() ?? throw new InvalidOperationException("Hãy chọn một recipe.");
            ApplyBuildProfile(recipe.Profile);
            ShowMessage("Đã áp dụng recipe", recipe.Name, InfoBarSeverity.Success);
            return Task.CompletedTask;
        });
    }

    private async void SaveRecipeClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(() =>
        {
            if (_recipeStore is null)
            {
                return Task.CompletedTask;
            }
            var existing = SelectedRecipe();
            var name = string.IsNullOrWhiteSpace(RecipeNameBox.Text)
                ? existing?.Name ?? "Wukong build recipe"
                : RecipeNameBox.Text.Trim();
            var saved = _recipeStore.Save(name, CaptureBuildProfile(name), existing?.Id);
            LoadRecipes(saved.Id);
            ShowMessage("Đã lưu recipe", saved.Name, InfoBarSeverity.Success);
            return Task.CompletedTask;
        });
    }

    private async void ToggleRecipeLockClick(object sender, RoutedEventArgs e)
    {
        await RunBusyActionAsync(() =>
        {
            if (_recipeStore is null)
            {
                return Task.CompletedTask;
            }
            var recipe = SelectedRecipe() ?? throw new InvalidOperationException("Hãy chọn một recipe.");
            var updated = _recipeStore.SetLocked(recipe.Id, !recipe.Locked);
            LoadRecipes(updated.Id);
            return Task.CompletedTask;
        });
    }

    private async void DeleteRecipeClick(object sender, RoutedEventArgs e)
    {
        var recipe = SelectedRecipe();
        if (recipe is null || _recipeStore is null)
        {
            return;
        }
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "Xóa build recipe?",
            Content = recipe.Name,
            PrimaryButtonText = "Xóa",
            CloseButtonText = "Hủy",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }
        await RunBusyActionAsync(() =>
        {
            _recipeStore.Delete(recipe.Id);
            LoadRecipes();
            RecipeNameBox.Text = string.Empty;
            return Task.CompletedTask;
        });
    }

    private async void CompareRecipeClick(object sender, RoutedEventArgs e)
    {
        var recipe = SelectedRecipe();
        if (recipe is null)
        {
            ShowMessage("Chưa chọn recipe", "Hãy chọn recipe cần so sánh.", InfoBarSeverity.Warning);
            return;
        }
        var current = CaptureBuildProfile("Current");
        var differences = CompareProfiles(recipe.Profile, current);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"So sánh · {recipe.Name}",
            Content = new ScrollViewer
            {
                MaxHeight = 480,
                Content = new TextBlock
                {
                    Text = differences.Count == 0 ? "Cấu hình hiện tại giống recipe." : string.Join(Environment.NewLine, differences),
                    TextWrapping = TextWrapping.Wrap,
                    FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas"),
                },
            },
            CloseButtonText = "Đóng",
        };
        await dialog.ShowAsync();
    }

    private static IReadOnlyList<string> CompareProfiles(StudioBuildProfile saved, StudioBuildProfile current)
    {
        var differences = new List<string>();
        if (saved.ModVersion != current.ModVersion) differences.Add($"Nền MOD: {saved.ModVersion} -> {current.ModVersion}");
        if (saved.Preset != current.Preset) differences.Add($"Biến thể: {saved.Preset} -> {current.Preset}");
        AddSetDifference(differences, "MOD", saved.ModNames, current.ModNames);
        AddSetDifference(differences, "Pipeline", saved.EnabledSteps, current.EnabledSteps);
        AddSetDifference(differences, "Debloat", saved.DebloatPaths, current.DebloatPaths);
        if (saved.NotifyTelegram != current.NotifyTelegram) differences.Add($"Telegram: {saved.NotifyTelegram} -> {current.NotifyTelegram}");
        return differences;
    }

    private static void AddSetDifference(
        ICollection<string> output,
        string label,
        IReadOnlyList<string> saved,
        IReadOnlyList<string> current)
    {
        var added = current.Except(saved, StringComparer.OrdinalIgnoreCase).ToArray();
        var removed = saved.Except(current, StringComparer.OrdinalIgnoreCase).ToArray();
        if (added.Length > 0) output.Add($"{label} thêm: {string.Join(", ", added)}");
        if (removed.Length > 0) output.Add($"{label} bỏ: {string.Join(", ", removed)}");
    }

    private void NotifyTelegramChanged(object sender, RoutedEventArgs e)
    {
        if (_configuring || _bootstrap is null)
        {
            return;
        }
        _configuring = true;
        if (_stepChecks.TryGetValue("notify_telegram", out var notifyStep))
        {
            notifyStep.IsChecked = NotifyTelegramCheckBox.IsChecked == true;
        }
        SelectComboByTag(PresetCombo, "custom");
        _configuring = false;
        UpdateConfigurationSummaries();
        InvalidatePreflight();
    }

    private async void EditDebloatPathsClick(object sender, RoutedEventArgs e)
    {
        if (_api is null || _bootstrap is null)
        {
            return;
        }

        DebloatPathsBox.Text = string.Join(Environment.NewLine, _debloatPaths);
        UpdateDebloatEditorCount();
        DebloatDialog.XamlRoot = XamlRoot;
        var result = await DebloatDialog.ShowAsync();
        if (result == ContentDialogResult.None)
        {
            return;
        }

        var paths = result == ContentDialogResult.Secondary
            ? _defaultDebloatPaths.ToArray()
            : ParseDebloatPaths(DebloatPathsBox.Text);
        await RunBusyActionAsync(async () =>
        {
            var saved = await _api.SaveSettingsAsync(_bootstrap.Settings with { DebloatPaths = paths });
            _bootstrap = _bootstrap with { Settings = saved };
            _debloatPaths.Clear();
            _debloatPaths.AddRange(saved.DebloatPaths ?? _defaultDebloatPaths);
            PopulateSettings(saved);
            _configuring = true;
            SelectComboByTag(PresetCombo, "custom");
            RebuildStepOptions(applyPreset: false);
            _configuring = false;
            UpdateConfigurationSummaries();
            InvalidatePreflight();
            ShowMessage(
                "Đã cập nhật bước 04",
                $"Danh sách hiện có {_debloatPaths.Count} đường dẫn và đã được lưu cho lần mở app tiếp theo.",
                InfoBarSeverity.Success);
        });
    }

    private void DebloatPathsChanged(object sender, TextChangedEventArgs e) => UpdateDebloatEditorCount();

    private void UpdateDebloatEditorCount()
    {
        DebloatEditorCountText.Text = $"{ParseDebloatPaths(DebloatPathsBox.Text).Count} đường dẫn";
    }

    private static IReadOnlyList<string> ParseDebloatPaths(string text) => text
        .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .ToArray();

    private void UpdateConfigurationSummaries()
    {
        ModSelectionSummaryText.Text = $"{_modChecks.Count(item => item.Value.IsChecked == true)} / {_modChecks.Count} đã chọn";
        StepSelectionSummaryText.Text = $"{_stepChecks.Count(item => item.Value.IsChecked == true)} / {_stepChecks.Count} bước";
    }

    private void InvalidatePreflight()
    {
        foreach (var entry in _romQueue)
        {
            entry.Inspect = null;
            entry.InspectSignature = null;
            entry.Status = "Cần chạy lại preflight";
        }
        RenderRomQueue();
    }

    private async Task RunBusyActionAsync(Func<Task> action)
    {
        if (_busy)
        {
            return;
        }
        SetBusy(true);
        try
        {
            await action();
        }
        catch (OperationCanceledException)
        {
            ShowMessage(Localized("Đã hủy đồng bộ"), Localized("Upload đã dừng; index cục bộ không thay đổi."), InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            if (HybridPage.Visibility == Visibility.Visible)
            {
                HybridResultBox.Text = exception.Message;
            }
            ShowMessage(
                Localized("Không thể hoàn thành tác vụ"),
                Localized("Xem log kỹ thuật bên dưới để biết chi tiết và thử lại."),
                InfoBarSeverity.Error);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void SetBusy(bool value)
    {
        _busy = value;
        BrowseRomButton.IsEnabled = !value;
        BrowseFolderButton.IsEnabled = !value;
        AddRomPathButton.IsEnabled = !value;
        PreflightButton.IsEnabled = !value;
        StartBuildButton.IsEnabled = !value;
        SyncContentDriveButton.IsEnabled = !value;
        PublishContentManifestButton.IsEnabled = !value;
        CancelContentSyncButton.IsEnabled = value;
        RenameRomFileButton.IsEnabled = !value;
        RenameRomFolderButton.IsEnabled = !value;
        ClearRomRenameButton.IsEnabled = !value && (_romRenamePreview?.Total ?? 0) > 0;
        ApplyRomRenameButton.IsEnabled = !value && _romRenamePreview?.CanApply == true;
        RomRenamerBusyRing.IsActive = value;
        RomRenamerBusyRing.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        BuildBusyRing.IsActive = value;
        BuildBusyRing.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ShowMessage(string title, string message, InfoBarSeverity severity)
    {
        NativeMessageBar.Title = title;
        NativeMessageBar.Message = message;
        NativeMessageBar.Severity = severity;
        NativeMessageBar.IsOpen = true;
    }

    private void SetBackendState(string text, bool ready)
    {
        BackendStateText.Text = text;
        BackendStateText.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(
            ready ? Windows.UI.Color.FromArgb(255, 16, 124, 16) : Windows.UI.Color.FromArgb(255, 196, 43, 28));
        BackendStateBadge.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(
            ready ? Windows.UI.Color.FromArgb(255, 232, 244, 234) : Windows.UI.Color.FromArgb(255, 253, 235, 233));
    }

    private IReadOnlyList<string> DefaultMods(string version, string preset)
    {
        if (_bootstrap is null || preset == "custom")
        {
            return [];
        }
        if (_bootstrap.PresetDefaultsByVersion.TryGetValue(version, out var byPreset)
            && byPreset.TryGetValue(preset, out var versionDefaults))
        {
            return versionDefaults;
        }
        return _bootstrap.PresetDefaults.TryGetValue(preset, out var defaults) ? defaults : [];
    }

    private static string ModDescription(StudioMod mod)
    {
        if (!mod.Ready)
        {
            return string.IsNullOrWhiteSpace(mod.BlockedReason) ? "MOD chưa sẵn sàng" : mod.BlockedReason;
        }
        var details = new List<string>();
        if (mod.Partitions is { Count: > 0 })
        {
            details.Add($"{mod.Partitions.Count} phân vùng");
        }
        if (mod.SpecialActions is { Count: > 0 })
        {
            details.Add($"{mod.SpecialActions.Count} tác vụ riêng");
        }
        return details.Count == 0 ? "Sẵn sàng áp dụng" : string.Join(" · ", details);
    }

    private string StepDescription(string stepId) => _desktopSettings.Locale == "en"
        ? stepId switch
        {
            "inspect_rom" => "Read metadata, identify the device and validate the ZIP.",
            "extract_payload" => "Extract partition images from the source payload.bin.",
            "unpack_partitions" => "Unpack partitions that are allowed to be modified.",
            "debloat" => "Delete the exact paths in the configured debloat list.",
            "apply_mod" => "Apply MODs and hooks for the selected platform.",
            "sync_configs" => "Synchronize permissions, fs_config and SELinux/file_contexts.",
            "repack_partitions" => "Repack every modified partition.",
            "repack_super" => "Build super.img from stock and repacked images.",
            "patch_vbmeta" => "Patch vbmeta using the current AVB configuration.",
            "patch_vendor_boot" => "Optional vendor_boot.img task.",
            "package_zip" => "Create the ZIP, manifest and run the final validator.",
            "notify_telegram" => "Send a separate notification for each completed variant.",
            _ => "ROM build pipeline task.",
        }
        : stepId switch
        {
            "inspect_rom" => "Đọc metadata, nhận diện thiết bị và kiểm tra ZIP.",
            "extract_payload" => "Trích xuất image từ payload.bin của ROM nguồn.",
            "unpack_partitions" => "Giải nén các phân vùng được phép chỉnh sửa.",
            "debloat" => "Xóa chính xác các đường dẫn trong danh sách cấu hình.",
            "apply_mod" => "Áp dụng MOD và hook tương ứng với phiên bản đã chọn.",
            "sync_configs" => "Đồng bộ quyền, fs_config và SELinux/file_contexts.",
            "repack_partitions" => "Đóng gói lại các phân vùng đã thay đổi.",
            "repack_super" => "Tạo super.img từ image gốc và image đã repack.",
            "patch_vbmeta" => "Vá vbmeta theo cấu hình AVB hiện tại.",
            "patch_vendor_boot" => "Tác vụ tùy chọn cho vendor_boot.img.",
            "package_zip" => "Đóng ZIP, tạo manifest và chạy final validator.",
            "notify_telegram" => "Gửi thông báo riêng ngay khi từng bản hoàn thành.",
            _ => "Tác vụ trong pipeline build ROM.",
        };

    private Microsoft.UI.Xaml.Media.SolidColorBrush StudioBrush(int red, int green, int blue)
    {
        if (ActualTheme == ElementTheme.Dark)
        {
            if (red >= 245 && green >= 245 && blue >= 245)
            {
                (red, green, blue) = (29, 37, 48);
            }
            else if (red >= 220 && green >= 220 && blue >= 220)
            {
                (red, green, blue) = (43, 55, 69);
            }
            else if (red is >= 85 and <= 110 && green is >= 95 and <= 125 && blue is >= 110 and <= 145)
            {
                (red, green, blue) = (168, 180, 195);
            }
            else if (red <= 20 && green is >= 90 and <= 130 && blue >= 170)
            {
                (red, green, blue) = (103, 184, 255);
            }
            else if (red == 16 && green == 124 && blue == 16)
            {
                (red, green, blue) = (105, 219, 145);
            }
            else if (red == 196 && green == 43 && blue == 28)
            {
                (red, green, blue) = (255, 111, 118);
            }
        }
        return new(Windows.UI.Color.FromArgb(255, (byte)red, (byte)green, (byte)blue));
    }

    private static ElementTheme ThemePreference(string preference) => preference switch
    {
        "dark" => ElementTheme.Dark,
        "light" => ElementTheme.Light,
        _ => ElementTheme.Default,
    };

    private string SelectedPreset() => SelectedTag(PresetCombo) ?? "lite";

    private static string PresetDisplayName(string preset) => preset switch
    {
        "lite" => "Lite",
        "resume" => "Plus",
        "both" => "Lite + Plus",
        _ => "Custom",
    };

    private StudioLogFilter SelectedLogFilter() => SelectedTag(LogLevelCombo) switch
    {
        "important" => StudioLogFilter.Important,
        "warnings" => StudioLogFilter.WarningsAndErrors,
        "errors" => StudioLogFilter.Errors,
        _ => StudioLogFilter.All,
    };

    private static string? SelectedTag(ComboBox combo) => (combo.SelectedItem as ComboBoxItem)?.Tag?.ToString();

    private static void SelectComboByTag(ComboBox combo, string tag)
    {
        combo.SelectedItem = combo.Items
            .OfType<ComboBoxItem>()
            .FirstOrDefault(item => string.Equals(item.Tag?.ToString(), tag, StringComparison.Ordinal));
    }

    private Border CreateInfoCard(string title, string status, string detail, FrameworkElement? action = null)
    {
        var grid = new Grid { ColumnSpacing = 12 };
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        if (action is not null)
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        }
        var text = new StackPanel { Spacing = 3 };
        text.Children.Add(new TextBlock { Text = title, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        text.Children.Add(new TextBlock { Text = status, Foreground = StudioBrush(0, 103, 192), TextWrapping = TextWrapping.Wrap });
        text.Children.Add(new TextBlock { Text = detail, Foreground = StudioBrush(95, 107, 122), FontSize = 12, TextWrapping = TextWrapping.Wrap });
        grid.Children.Add(text);
        if (action is not null)
        {
            Grid.SetColumn(action, 1);
            grid.Children.Add(action);
        }
        return new Border
        {
            Background = StudioBrush(255, 255, 255),
            BorderBrush = StudioBrush(225, 225, 225),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(14),
            Child = grid,
        };
    }

    private FrameworkElement CreateHealthRow(string name, bool ready, string detail)
    {
        var accent = ready
            ? Windows.UI.Color.FromArgb(255, 16, 124, 16)
            : Windows.UI.Color.FromArgb(255, 196, 43, 28);
        var grid = new Grid { ColumnSpacing = 10 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition());
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var indicator = new Microsoft.UI.Xaml.Shapes.Ellipse
        {
            Width = 8,
            Height = 8,
            Fill = StudioBrush(accent.R, accent.G, accent.B),
            VerticalAlignment = VerticalAlignment.Center,
        };
        var text = new StackPanel { Spacing = 1 };
        text.Children.Add(new TextBlock { Text = name, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
        text.Children.Add(new TextBlock
        {
            Text = detail,
            Foreground = StudioBrush(95, 107, 122),
            FontSize = 11,
        });
        var badge = new Border
        {
            Background = StudioBrush(ready ? 232 : 253, ready ? 244 : 235, ready ? 234 : 233),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(8, 4, 8, 4),
            VerticalAlignment = VerticalAlignment.Center,
            Child = new TextBlock
            {
                Text = ready ? "OK" : "Cần xử lý",
                Foreground = StudioBrush(accent.R, accent.G, accent.B),
                FontSize = 11,
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            },
        };
        Grid.SetColumn(text, 1);
        Grid.SetColumn(badge, 2);
        grid.Children.Add(indicator);
        grid.Children.Add(text);
        grid.Children.Add(badge);
        return grid;
    }

    private void OpenArtifact(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            return;
        }
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"/select,\"{path}\"") { UseShellExecute = true });
    }

    private void OpenOutputClick(object sender, RoutedEventArgs e) => OpenDirectory(_layout?.OutputRoot);
    private void OpenWorkspaceClick(object sender, RoutedEventArgs e) => OpenDirectory(_layout?.WorkspaceRoot);
    private void OpenLogsClick(object sender, RoutedEventArgs e) => OpenDirectory(_layout?.LogsRoot);

    private async void RefreshDashboardClick(object sender, RoutedEventArgs e) => await LoadBootstrapAsync();

    private async void RestartBackendClick(object sender, RoutedEventArgs e)
    {
        if (_restartBackend is null)
        {
            return;
        }
        await RunBusyActionAsync(async () =>
        {
            await _restartBackend();
            ShowMessage("Backend đã khởi động lại", "Runtime và API localhost đã sẵn sàng.", InfoBarSeverity.Success);
        });
    }

    private static void OpenDirectory(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return;
        }
        Directory.CreateDirectory(path);
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("explorer.exe", $"\"{path}\"") { UseShellExecute = true });
    }

    private static void CopyToClipboard(string text)
    {
        var package = new DataPackage();
        package.SetText(text ?? string.Empty);
        Clipboard.SetContent(package);
    }

    private static string SafeFileName(string value)
    {
        var invalid = Path.GetInvalidFileNameChars().ToHashSet();
        return string.Concat(value.Select(character => invalid.Contains(character) ? '_' : character));
    }

    private void RenderJobSteps(StudioJob job)
    {
        var steps = job.Steps ?? [];
        var signature = job.CurrentStep + "|" + string.Join('|', steps.Select(step =>
            $"{step.Id}:{step.Status}:{StepDuration(step):0.###}:{StepCacheState(step)}:{StepProgressMessage(step)}"));
        if (string.Equals(_renderedStepSignature, signature, StringComparison.Ordinal))
        {
            return;
        }
        _renderedStepSignature = signature;
        JobStepsPanel.Children.Clear();
        if (steps.Count == 0)
        {
            JobStepsPanel.Children.Add(new TextBlock { Text = "Job chưa có timeline.", Foreground = StatusBrush("pending") });
            return;
        }

        for (var index = 0; index < steps.Count; index++)
        {
            var step = steps[index];
            var active = string.Equals(job.CurrentStep, step.Id, StringComparison.Ordinal);
            var colors = StepColors(step.Status);
            var text = new StackPanel { Spacing = 2 };
            text.Children.Add(new TextBlock
            {
                Text = $"{index + 1:00} · {StatusText(step.Status)}",
                Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(colors.Foreground),
                FontSize = 10,
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            });
            text.Children.Add(new TextBlock
            {
                Text = TranslateStep(step.Id, step.Id),
                FontSize = 11,
                FontWeight = active ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal,
                TextWrapping = TextWrapping.Wrap,
                MaxWidth = 132,
            });
            var detail = StepDetailText(step);
            if (detail.Length > 0)
            {
                text.Children.Add(new TextBlock
                {
                    Text = detail,
                    FontSize = 10,
                    Foreground = new SolidColorBrush(colors.Foreground),
                    FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Consolas"),
                });
            }
            JobStepsPanel.Children.Add(new Border
            {
                MinWidth = 126,
                MaxWidth = 150,
                MinHeight = 68,
                Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(colors.Background),
                BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(active ? colors.Foreground : colors.Border),
                BorderThickness = new Thickness(active ? 2 : 1),
                CornerRadius = new CornerRadius(9),
                Padding = new Thickness(10, 7, 10, 7),
                Child = text,
            });
        }
    }

    private static double StepDuration(StudioJobStep step) =>
        StepDetailNumber(step, "durationSeconds");

    private static double StepDetailNumber(StudioJobStep step, string propertyName) =>
        step.Details is JsonElement details
        && details.ValueKind == JsonValueKind.Object
        && details.TryGetProperty(propertyName, out var value)
        && value.TryGetDouble(out var number)
            ? number
            : 0;

    private static string FormatStepSeconds(double seconds) =>
        seconds >= 60 ? $"{seconds / 60:0.0}m" : $"{seconds:0.0}s";

    private static string StepCacheState(StudioJobStep step) =>
        step.Details is JsonElement details
        && details.ValueKind == JsonValueKind.Object
        && details.TryGetProperty("cacheHit", out var value)
        && value.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? value.GetBoolean() ? "hit" : "miss"
            : string.Empty;

    private string StepDetailText(StudioJobStep step)
    {
        var parts = new List<string>();
        var duration = StepDuration(step);
        if (duration > 0)
        {
            if (string.Equals(step.Id, "package_zip", StringComparison.Ordinal))
            {
                var staging = StepDetailNumber(step, "stagingSeconds");
                var compression = StepDetailNumber(step, "compressionSeconds");
                var validation = StepDetailNumber(step, "validationSeconds");
                parts.Add($"{(_desktopSettings.Locale == "en" ? "Total" : "Tổng")} {FormatStepSeconds(duration)}");
                if (staging > 0)
                {
                    parts.Add($"{(_desktopSettings.Locale == "en" ? "Staging" : "Chuẩn bị")} {FormatStepSeconds(staging)}");
                }
                if (compression > 0)
                {
                    parts.Add($"{(_desktopSettings.Locale == "en" ? "Compress" : "Nén")} {FormatStepSeconds(compression)}");
                }
                parts.Add($"{(_desktopSettings.Locale == "en" ? "Validate" : "Hậu kiểm")} {FormatStepSeconds(validation)}");
            }
            else
            {
                parts.Add(FormatStepSeconds(duration));
            }
        }
        var cache = StepCacheState(step);
        if (cache.Length > 0)
        {
            parts.Add(cache == "hit" ? "CACHE HIT" : "CACHE MISS");
        }
        if (step.Details is JsonElement details
            && details.ValueKind == JsonValueKind.Object
            && details.TryGetProperty("phase", out var phase)
            && phase.ValueKind == JsonValueKind.String
            && phase.GetString() is { Length: > 0 } phaseName)
        {
            parts.Add(phaseName);
        }
        var progressMessage = StepProgressMessage(step);
        if (progressMessage.Length > 0)
        {
            parts.Add(LocalizeProgressMessage(progressMessage));
        }
        return string.Join(" · ", parts);
    }

    private static string StepProgressMessage(StudioJobStep step) =>
        step.Details is JsonElement details
        && details.ValueKind == JsonValueKind.Object
        && details.TryGetProperty("progressMessage", out var message)
        && message.ValueKind == JsonValueKind.String
            ? message.GetString() ?? string.Empty
            : string.Empty;

    private string BuildSelectedJobStatus(StudioJob job)
    {
        var status = $"{StatusText(job.Status)} · {TranslateStep(job.CurrentStep, job.CurrentStep)}";
        return string.IsNullOrWhiteSpace(job.ProgressMessage)
            ? status
            : $"{status} · {LocalizeProgressMessage(job.ProgressMessage)}";
    }

    private string LocalizeProgressMessage(string message) => _desktopSettings.Locale == "en"
        ? message switch
        {
            "Đang xác thực nhanh ZIP" => "Running fast ZIP validation",
            "Đang kiểm tra CRC toàn phần" => "Running full CRC validation",
            "Hậu kiểm ZIP đã đạt" => "ZIP validation passed",
            "ZIP đã xác thực" => "ZIP validated",
            "ZIP 100% · chuẩn bị hậu kiểm" => "ZIP 100% · preparing validation",
            _ when message.StartsWith("Đang đóng gói ZIP", StringComparison.Ordinal) => message.Replace("Đang đóng gói ZIP", "Packaging ZIP", StringComparison.Ordinal),
            _ => message,
        }
        : message;

    private (Windows.UI.Color Background, Windows.UI.Color Border, Windows.UI.Color Foreground) StepColors(string status)
    {
        if (_desktopSettings.Theme == "dark")
        {
            return status switch
            {
                "success" => (Windows.UI.Color.FromArgb(255, 26, 55, 43), Windows.UI.Color.FromArgb(255, 57, 105, 80), Windows.UI.Color.FromArgb(255, 105, 219, 145)),
                "running" or "packaging" => (Windows.UI.Color.FromArgb(255, 25, 48, 70), Windows.UI.Color.FromArgb(255, 56, 103, 148), Windows.UI.Color.FromArgb(255, 103, 184, 255)),
                "failed" or "cancelled" => (Windows.UI.Color.FromArgb(255, 66, 35, 39), Windows.UI.Color.FromArgb(255, 125, 60, 68), Windows.UI.Color.FromArgb(255, 255, 111, 118)),
                "skipped" => (Windows.UI.Color.FromArgb(255, 65, 52, 28), Windows.UI.Color.FromArgb(255, 127, 100, 45), Windows.UI.Color.FromArgb(255, 255, 190, 92)),
                _ => (Windows.UI.Color.FromArgb(255, 31, 40, 51), Windows.UI.Color.FromArgb(255, 53, 66, 83), Windows.UI.Color.FromArgb(255, 168, 180, 195)),
            };
        }
        return status switch
        {
            "success" => (Windows.UI.Color.FromArgb(255, 232, 244, 234), Windows.UI.Color.FromArgb(255, 177, 219, 183), Windows.UI.Color.FromArgb(255, 16, 124, 16)),
            "running" or "packaging" => (Windows.UI.Color.FromArgb(255, 234, 243, 252), Windows.UI.Color.FromArgb(255, 172, 207, 240), Windows.UI.Color.FromArgb(255, 0, 103, 192)),
            "failed" or "cancelled" => (Windows.UI.Color.FromArgb(255, 253, 235, 233), Windows.UI.Color.FromArgb(255, 239, 185, 180), Windows.UI.Color.FromArgb(255, 196, 43, 28)),
            "skipped" => (Windows.UI.Color.FromArgb(255, 255, 244, 206), Windows.UI.Color.FromArgb(255, 232, 202, 118), Windows.UI.Color.FromArgb(255, 138, 90, 0)),
            _ => (Windows.UI.Color.FromArgb(255, 247, 249, 251), Windows.UI.Color.FromArgb(255, 221, 227, 234), Windows.UI.Color.FromArgb(255, 95, 107, 122)),
        };
    }

    private static int OverallProgress(StudioJob job)
    {
        if (job.Status == "success")
        {
            return 100;
        }
        var steps = job.Steps ?? [];
        if (steps.Count == 0 || job.Status == "queued")
        {
            return 0;
        }
        var completed = steps.Count(step => step.Status is "success" or "skipped");
        var partial = 0d;
        var active = steps.FirstOrDefault(step => step.Id == job.CurrentStep)
            ?? steps.FirstOrDefault(step => step.Status == "running");
        if (active?.Details is JsonElement details
            && details.ValueKind == JsonValueKind.Object
            && details.TryGetProperty("progress", out var progress)
            && progress.TryGetDouble(out var value))
        {
            partial = Math.Clamp(value, 0, 100) / 100d;
        }
        return (int)Math.Round(Math.Clamp((completed + partial) * 100d / steps.Count, 0, 100));
    }

    private static TimeSpan BuildElapsed(StudioJob job)
    {
        if (!DateTimeOffset.TryParse(job.StartedAt, out var started))
        {
            return TimeSpan.Zero;
        }
        var end = DateTimeOffset.TryParse(job.FinishedAt, out var finished) ? finished : DateTimeOffset.UtcNow;
        return end > started ? end - started : TimeSpan.Zero;
    }

    private static string FormatDuration(TimeSpan duration) =>
        $"{(int)duration.TotalHours:00}:{duration.Minutes:00}:{duration.Seconds:00}";

    private static string BuildJobMeta(StudioJob job)
    {
        var id = job.Id.Length > 12 ? job.Id[..12] : job.Id;
        var created = DateTimeOffset.TryParse(job.CreatedAt, out var date)
            ? date.ToLocalTime().ToString("dd/MM/yyyy HH:mm:ss")
            : "-";
        return $"ID {id} · Tạo {created} · {job.Steps?.Count ?? 0} bước";
    }

    private static IReadOnlyList<string> JobOutputPaths(StudioJob job)
    {
        var outputs = new List<string>();
        if (!string.IsNullOrWhiteSpace(job.OutputZip))
        {
            outputs.Add(job.OutputZip);
        }
        var package = job.Steps?.FirstOrDefault(step => step.Id == "package_zip");
        if (package?.Details is JsonElement details
            && details.ValueKind == JsonValueKind.Object
            && details.TryGetProperty("outputZips", out var values)
            && values.ValueKind == JsonValueKind.Array)
        {
            outputs.AddRange(values.EnumerateArray()
                .Where(value => value.ValueKind == JsonValueKind.String)
                .Select(value => value.GetString())
                .Where(value => !string.IsNullOrWhiteSpace(value))!);
        }
        return outputs.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private static string BuildRomStatus(RomQueueEntry entry)
    {
        if (entry.Inspect is null)
        {
            return entry.Status;
        }
        var metadata = entry.Inspect.Metadata;
        var device = entry.Inspect.Device;
        var version = JsonString(metadata, "version_name");
        var product = JsonString(metadata, "product_name");
        var deviceName = JsonString(device, "name");
        var messages = entry.Inspect.Ok
            ? string.Join(" · ", entry.Inspect.Warnings)
            : string.Join(" · ", entry.Inspect.Errors);
        return $"{entry.Status} · {version} · {product} · {deviceName}{(messages.Length > 0 ? "\n" + messages : string.Empty)}";
    }

    private Microsoft.UI.Xaml.Media.Brush StatusBrush(string status)
    {
        var color = status.Contains("Lỗi", StringComparison.OrdinalIgnoreCase)
            || status.Contains("chặn", StringComparison.OrdinalIgnoreCase)
            ? Windows.UI.Color.FromArgb(255, 196, 43, 28)
            : status.Contains("Sẵn sàng", StringComparison.OrdinalIgnoreCase)
                ? Windows.UI.Color.FromArgb(255, 16, 124, 16)
                : Windows.UI.Color.FromArgb(255, 102, 102, 102);
        return StudioBrush(color.R, color.G, color.B);
    }

    private string StatusText(string status) => _desktopSettings.Locale == "en"
        ? status switch
        {
            "queued" => "Queued",
            "running" => "Building",
            "packaging" => "Packaging ZIP",
            "success" => "Completed",
            "failed" => "Failed",
            "cancelled" => "Cancelled",
            "pending" => "Pending",
            "skipped" => "Skipped",
            _ => status,
        }
        : status switch
        {
            "queued" => "Đang chờ",
            "running" => "Đang build",
            "packaging" => "Đang đóng ZIP",
            "success" => "Hoàn tất",
            "failed" => "Thất bại",
            "cancelled" => "Đã hủy",
            "pending" => "Chờ",
            "skipped" => "Bỏ qua",
            _ => status,
        };

    private string TranslateStep(string? id, string? fallback) => _desktopSettings.Locale == "en"
        ? id switch
        {
            "inspect_rom" => "Inspect ROM",
            "extract_payload" => "Extract payload",
            "unpack_partitions" => "Unpack partitions",
            "debloat" => "Remove unnecessary apps",
            "apply_mod" => "Apply MODs",
            "sync_configs" => "Sync fs_config and SELinux",
            "repack_partitions" => "Repack partitions",
            "repack_super" => "Build super.img",
            "patch_vbmeta" => "Patch vbmeta",
            "patch_vendor_boot" => "Patch vendor_boot",
            "package_zip" => "Package ROM ZIP",
            "notify_telegram" => "Telegram notification",
            null or "" => fallback ?? "-",
            _ => fallback ?? id,
        }
        : id switch
        {
            "inspect_rom" => "Phân tích ROM",
            "extract_payload" => "Giải nén payload",
            "unpack_partitions" => "Giải nén phân vùng",
            "debloat" => "Xóa ứng dụng không cần thiết",
            "apply_mod" => "Áp dụng MOD",
            "sync_configs" => "Đồng bộ fs_config và SELinux",
            "repack_partitions" => "Đóng gói phân vùng",
            "repack_super" => "Đóng gói super.img",
            "patch_vbmeta" => "Vá vbmeta",
            "patch_vendor_boot" => "Vá vendor_boot",
            "package_zip" => "Đóng gói ROM ZIP",
            "notify_telegram" => "Thông báo Telegram",
            null or "" => fallback ?? "-",
            _ => fallback ?? id,
        };

    private static string JsonString(JsonElement element, string name)
    {
        if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out var value))
        {
            return "-";
        }
        return value.ValueKind == JsonValueKind.String ? value.GetString() ?? "-" : value.ToString();
    }

    private static long JsonLong(JsonElement element, string name)
    {
        return element.ValueKind == JsonValueKind.Object
            && element.TryGetProperty(name, out var value)
            && value.TryGetInt64(out var result)
            ? result
            : 0;
    }

    private static bool JsonObjectValuesTrue(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return false;
        }
        var values = element.EnumerateObject().ToArray();
        return values.Length > 0 && values.All(item => item.Value.ValueKind == JsonValueKind.True);
    }

    private static string FormatBytes(long value)
    {
        if (value <= 0)
        {
            return "-";
        }
        string[] units = ["B", "KiB", "MiB", "GiB", "TiB"];
        var amount = (double)value;
        var unit = 0;
        while (amount >= 1024 && unit < units.Length - 1)
        {
            amount /= 1024;
            unit++;
        }
        return $"{amount:0.##} {units[unit]}";
    }

    private sealed class RomQueueEntry(string path)
    {
        public string Path { get; } = path;
        public string Status { get; set; } = "Chờ preflight";
        public StudioInspectResult? Inspect { get; set; }
        public string? InspectSignature { get; set; }
    }
}

public sealed class NativeRomRenameItem(
    StudioRomRenameEntry entry,
    string statusText,
    string detail)
{
    public string SourceName { get; } = entry.SourceName;
    public string TargetName { get; } = entry.TargetName ?? "-";
    public string StatusText { get; } = statusText;
    public string Detail { get; } = detail;
}

public sealed class NativeJobItem : INotifyPropertyChanged
{
    private string _versionName;
    private string _statusLine;
    private string _detailLine;

    public NativeJobItem(StudioJob job)
    {
        Id = job.Id;
        _versionName = job.VersionName;
        _statusLine = BuildStatusLine(job);
        _detailLine = BuildDetailLine(job);
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string Id { get; }
    public string VersionName => _versionName;
    public string StatusLine => _statusLine;
    public string DetailLine => _detailLine;

    public void Update(StudioJob job)
    {
        if (!string.Equals(_versionName, job.VersionName, StringComparison.Ordinal))
        {
            _versionName = job.VersionName;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(VersionName)));
        }
        var statusLine = BuildStatusLine(job);
        if (!string.Equals(_statusLine, statusLine, StringComparison.Ordinal))
        {
            _statusLine = statusLine;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(StatusLine)));
        }
        var detailLine = BuildDetailLine(job);
        if (!string.Equals(_detailLine, detailLine, StringComparison.Ordinal))
        {
            _detailLine = detailLine;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(DetailLine)));
        }
    }

    private static string BuildStatusLine(StudioJob job) =>
        $"{StatusLabel(job.Status)} · {StepLabel(job.CurrentStep)}";

    private static string BuildDetailLine(StudioJob job)
    {
        var created = DateTimeOffset.TryParse(job.CreatedAt, out var date)
            ? date.ToLocalTime().ToString("dd/MM HH:mm")
            : "-";
        var steps = job.Steps ?? [];
        var completed = steps.Count(step => step.Status is "success" or "skipped");
        var progress = job.Status == "success" || steps.Count > 0 && completed == steps.Count
            ? 100
            : steps.Count == 0 ? 0 : (int)Math.Round(completed * 100d / steps.Count);
        return $"{created} · {progress}% · {steps.Count} bước";
    }

    private static string StatusLabel(string status) => status switch
    {
        "queued" => "Đang chờ",
        "running" => "Đang build",
        "packaging" => "Đang đóng ZIP",
        "success" => "Hoàn tất",
        "failed" => "Thất bại",
        "cancelled" => "Đã hủy",
        _ => status,
    };

    private static string StepLabel(string? step) => step switch
    {
        "inspect_rom" => "Phân tích ROM",
        "extract_payload" => "Giải nén payload",
        "unpack_partitions" => "Giải nén phân vùng",
        "debloat" => "Xóa ứng dụng",
        "apply_mod" => "Áp dụng MOD",
        "sync_configs" => "Đồng bộ cấu hình",
        "repack_partitions" => "Đóng gói phân vùng",
        "repack_super" => "Đóng gói super.img",
        "patch_vbmeta" => "Vá vbmeta",
        "package_zip" => "Đóng gói ZIP",
        "notify_telegram" => "Thông báo Telegram",
        null or "" => "-",
        _ => step.Replace('_', ' '),
    };
}
