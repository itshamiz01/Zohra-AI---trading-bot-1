# ZOHRA OS — Window Recognition & App-Category Classification (V7.6)
import logging
import os

from zohra.services.vision.models import WindowContext

logger = logging.getLogger("zohra.vision.window")

# ── App-Category Classification Map ────────────────────────────────────

APP_CATEGORY_MAP = {
    # IDEs
    "code.exe": "ide", "devenv.exe": "ide", "pycharm64.exe": "ide",
    "idea64.exe": "ide", "webstorm64.exe": "ide", "sublime_text.exe": "ide",
    "notepad++.exe": "ide", "atom.exe": "ide",
    # Browsers
    "chrome.exe": "browser", "firefox.exe": "browser", "msedge.exe": "browser",
    "opera.exe": "browser", "brave.exe": "browser",
    # Office
    "winword.exe": "office_suite", "excel.exe": "office_suite",
    "powerpnt.exe": "office_suite", "outlook.exe": "office_suite",
    "onenote.exe": "office_suite",
    # Trading
    "terminal64.exe": "trading_terminal", "terminal.exe": "trading_terminal",
    "metatrader64.exe": "trading_terminal", "metatrader.exe": "trading_terminal",
    "thinkorswim.exe": "trading_terminal",
    # Communication
    "discord.exe": "communication", "slack.exe": "communication",
    "teams.exe": "communication", "telegram.exe": "communication",
    "whatsapp.exe": "communication",
    # Media
    "vlc.exe": "media", "spotify.exe": "media",
    # Terminal / Shell
    "windowsterminal.exe": "terminal", "cmd.exe": "terminal",
    "powershell.exe": "terminal", "pwsh.exe": "terminal",
    # File Manager
    "explorer.exe": "file_manager",
}


def classify_app_category(process_name: str) -> str:
    """Classifies a process name into an app category for Context Manager routing."""
    return APP_CATEGORY_MAP.get(process_name.lower(), "unknown")


def recognize_active_window() -> WindowContext:
    """
    Queries the Windows API for the foreground window handle, title, and process name.
    Used by the Context Manager (V3.5) to prioritize agent context.
    """
    handle = 0
    title = ""
    process_name = ""

    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Get foreground window handle
        hwnd = user32.GetForegroundWindow()
        handle = hwnd

        # 2. Get window title
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value

        # 3. Get process ID from window handle
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # 4. Open process and query its executable name
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        proc_handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value
        )
        if proc_handle:
            try:
                import ctypes.wintypes
                psapi = ctypes.windll.psapi
                exe_buf = ctypes.create_unicode_buffer(260)
                psapi.GetModuleFileNameExW(proc_handle, None, exe_buf, 260)
                exe_path = exe_buf.value
                process_name = os.path.basename(exe_path) if exe_path else ""
            finally:
                kernel32.CloseHandle(proc_handle)

    except Exception as e:
        logger.debug(f"Window recognition failed (expected on non-Windows): {e}")
        # An unavailable foreground window must remain unknown. Supplying a
        # development-window identity would let downstream context handling
        # mistake fabricated application state for real desktop data.
        title = ""
        process_name = ""

    app_category = classify_app_category(process_name)
    ctx = WindowContext(
        handle=handle,
        title=title,
        process_name=process_name,
        app_category=app_category,
    )
    logger.info(f"Active window: '{title}' ({process_name}) → category: {app_category}")
    return ctx
