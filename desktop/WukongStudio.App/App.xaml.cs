using Microsoft.Windows.AppLifecycle;
using Microsoft.Windows.AppNotifications;
using Microsoft.UI.Xaml;
using System.Security.Cryptography;
using System.Text;
using Windows.ApplicationModel.Activation;
using WukongStudio.Core;

namespace WukongStudio.App;

public partial class App : Application
{
    private static readonly string InstanceKey = CreateInstanceKey();
    private MainWindow? _window;
    private AppInstance? _instance;

    public App()
    {
        InitializeComponent();
        UnhandledException += AppUnhandledException;
        TaskScheduler.UnobservedTaskException += UnobservedTaskException;
        try
        {
            if (AppNotificationManager.IsSupported())
            {
                AppNotificationManager.Default.Register();
            }
        }
        catch
        {
            // Tray notifications remain available when Windows app notifications cannot register.
        }
    }

    private static string CreateInstanceKey()
    {
        var root = StudioLayout.Default.InstallRoot.ToUpperInvariant();
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(root)));
        return $"WukongROMStudio.Main.{hash[..12]}";
    }

    private static void AppUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs args)
    {
        WriteCrashLog(args.Exception);
    }

    private static void UnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs args)
    {
        WriteCrashLog(args.Exception);
    }

    private static void WriteCrashLog(Exception exception)
    {
        try
        {
            var layout = StudioLayout.Default;
            layout.EnsureWritableDirectories();
            var path = Path.Combine(layout.CrashLogsRoot, $"crash-{DateTime.UtcNow:yyyyMMdd-HHmmssfff}.log");
            File.WriteAllText(path, exception.ToString());
        }
        catch
        {
        }
    }

    protected override async void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
    {
        var current = AppInstance.GetCurrent();
        _instance = AppInstance.FindOrRegisterForKey(InstanceKey);
        if (!_instance.IsCurrent)
        {
            await _instance.RedirectActivationToAsync(current.GetActivatedEventArgs());
            Exit();
            return;
        }

        _instance.Activated += InstanceActivated;
        _window = new MainWindow();
        _window.Activate();
        HandleActivation(current.GetActivatedEventArgs());
    }

    private void InstanceActivated(object? sender, AppActivationArguments args)
    {
        _window?.DispatcherQueue.TryEnqueue(() => HandleActivation(args));
    }

    private void HandleActivation(AppActivationArguments args)
    {
        Uri? uri = null;
        if (args.Kind == ExtendedActivationKind.Protocol && args.Data is IProtocolActivatedEventArgs protocol)
        {
            uri = protocol.Uri;
        }
        else if (args.Kind == ExtendedActivationKind.AppNotification
            && args.Data is AppNotificationActivatedEventArgs notification
            && Uri.TryCreate(notification.Argument, UriKind.Absolute, out var notificationUri))
        {
            uri = notificationUri;
        }
        else
        {
            uri = Environment.GetCommandLineArgs()
                .Skip(1)
                .Select(argument => Uri.TryCreate(argument, UriKind.Absolute, out var candidate) ? candidate : null)
                .FirstOrDefault(candidate => candidate?.Scheme.Equals("wukongstudio", StringComparison.OrdinalIgnoreCase) == true);
        }
        _window?.HandleActivation(uri);
    }
}
