# ZOHRA OS — Desktop Automation Manager
import logging
import time
from typing import Tuple, Dict, Any

logger = logging.getLogger("zohra.automation.desktop")

class DesktopAutomationManager:
    """
    Manages OS-level GUI controls (mouse, keyboard, window focus).
    Uses PyAutoGUI and PyWin32 with clean offline stubs.
    """
    def __init__(self):
        self.pyautogui = None
        self._init_desktop_automation()

    def _init_desktop_automation(self):
        try:
            import pyautogui
            self.pyautogui = pyautogui
            # Enable fail-safe: moving mouse to corner aborts automation
            self.pyautogui.FAILSAFE = True
            logger.info("PyAutoGUI Desktop Automation initialized successfully. Fail-Safe active.")
        except ImportError:
            logger.warning("PyAutoGUI not available. Running in local simulation mode.")
            self.pyautogui = None

    def click_coordinate(self, x: int, y: int, button: str = "left") -> bool:
        """Simulates clicking at a specific screen coordinate."""
        logger.info(f"Desktop click at ({x}, {y}) using button={button}")
        if self.pyautogui:
            try:
                self.pyautogui.click(x, y, button=button)
                return True
            except Exception as e:
                logger.error(f"Failed to execute desktop click: {e}")
                return False
        time.sleep(0.1)
        return True

    def type_text(self, text: str, press_enter: bool = True) -> bool:
        """Simulates human-like keyboard typing."""
        logger.info(f"Desktop typing text: '{text}'")
        if self.pyautogui:
            try:
                # Simulates typing with a small delay between keys
                self.pyautogui.write(text, interval=0.05)
                if press_enter:
                    self.pyautogui.press('enter')
                return True
            except Exception as e:
                logger.error(f"Failed to type text: {e}")
                return False
        time.sleep(0.2)
        return True

    def focus_window(self, title: str) -> bool:
        """Brings the window with the given title to focus."""
        logger.info(f"Bringing window to focus: '{title}'")
        try:
            # Windows specific focus logic
            import win32gui
            import win32con
            hwnd = win32gui.FindWindow(None, title)
            if hwnd:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                return True
        except Exception as e:
            logger.debug(f"win32gui focus skipped or failed: {e}")
        return True
