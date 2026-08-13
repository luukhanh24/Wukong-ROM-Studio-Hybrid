using System.Runtime.InteropServices;

namespace WukongStudio.Core;

public sealed class TaskbarProgressService
{
    private readonly ITaskbarList3? _taskbar;
    private readonly nint _windowHandle;

    public TaskbarProgressService(nint windowHandle)
    {
        _windowHandle = windowHandle;
        try
        {
            _taskbar = (ITaskbarList3)new TaskbarList();
            _taskbar.HrInit();
        }
        catch (Exception exception) when (exception is COMException or InvalidCastException)
        {
            _taskbar = null;
        }
    }

    public void Clear() => _taskbar?.SetProgressState(_windowHandle, TaskbarProgressState.NoProgress);
    public void SetIndeterminate() => _taskbar?.SetProgressState(_windowHandle, TaskbarProgressState.Indeterminate);
    public void SetError() => _taskbar?.SetProgressState(_windowHandle, TaskbarProgressState.Error);
    public void SetPaused() => _taskbar?.SetProgressState(_windowHandle, TaskbarProgressState.Paused);

    public void SetValue(ulong completed, ulong total)
    {
        _taskbar?.SetProgressState(_windowHandle, TaskbarProgressState.Normal);
        _taskbar?.SetProgressValue(_windowHandle, completed, Math.Max(1, total));
    }

    private enum TaskbarProgressState
    {
        NoProgress = 0,
        Indeterminate = 0x1,
        Normal = 0x2,
        Error = 0x4,
        Paused = 0x8,
    }

    [ComImport]
    [Guid("56FDF344-FD6D-11d0-958A-006097C9A090")]
    private class TaskbarList;

    [ComImport]
    [Guid("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface ITaskbarList3
    {
        void HrInit();
        void AddTab(nint window);
        void DeleteTab(nint window);
        void ActivateTab(nint window);
        void SetActiveAlt(nint window);
        void MarkFullscreenWindow(nint window, [MarshalAs(UnmanagedType.Bool)] bool fullscreen);
        void SetProgressValue(nint window, ulong completed, ulong total);
        void SetProgressState(nint window, TaskbarProgressState state);
    }
}
