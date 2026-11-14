# ZOHRA OS — Camera Capture with Privacy Controls (V7.7)
import logging
import os
import time
from datetime import datetime
from typing import Optional

from zohra.services.vision.models import CameraFrame

logger = logging.getLogger("zohra.vision.camera")

# ── Active-Capture Indicator State ──────────────────────────────────────
# Tracks which sessions currently have an active capture indicator visible.
# This is the enforcement mechanism for V1.6's "always visibly indicated" boundary.
_active_indicators: dict = {}


def show_active_capture_indicator(session_id: str):
    """
    MUST be called and rendered BEFORE any capture begins (V7.7, V1.6).
    This is not UI polish — it is a hard-ordered security boundary.
    A regression here is treated as stop-ship severity.
    """
    _active_indicators[session_id] = time.time()
    logger.info(f"🔴 CAMERA INDICATOR ON for session {session_id}")


def hide_active_capture_indicator(session_id: str):
    """Called after processing of the captured frame completes."""
    _active_indicators.pop(session_id, None)
    logger.info(f"⚪ CAMERA INDICATOR OFF for session {session_id}")


def is_indicator_active(session_id: str) -> bool:
    """Check whether the capture indicator is currently active for a session."""
    return session_id in _active_indicators


# ── Camera Device Abstraction ───────────────────────────────────────────

class CameraDevice:
    """
    Abstracts camera hardware access.
    Default mode is single-frame, not continuous stream (V7.7).
    """
    def __init__(self):
        self.cv2 = None
        self.available = False
        self.enabled = os.getenv("ZOHRA_ENABLE_CAMERA_CAPTURE", "0").lower() in {"1", "true", "yes", "on"}
        if self.enabled:
            self._init_camera()
        else:
            logger.info("Camera capture is disabled until ZOHRA_ENABLE_CAMERA_CAPTURE=1 is set.")

    def _init_camera(self):
        try:
            import cv2
            self.cv2 = cv2
            self.available = True
            logger.info("OpenCV camera backend loaded.")
        except ImportError:
            logger.warning("OpenCV not available; camera capture is unavailable.")
            self.available = False

    def capture_single_frame(self) -> Optional[bytes]:
        """Captures a single frame from the default camera device."""
        if not self.enabled:
            logger.info("Camera frame unavailable because camera capture is not enabled.")
            return None

        if self.available and self.cv2:
            try:
                cap = self.cv2.VideoCapture(0)
                try:
                    if not cap.isOpened():
                        return None
                    ret, frame = cap.read()
                finally:
                    cap.release()
                if ret:
                    _, buf = self.cv2.imencode(".png", frame)
                    return buf.tobytes()
            except Exception as e:
                logger.error(f"Camera capture failed: {e}")

        logger.info("Camera frame unavailable.")
        return None


_camera_device = CameraDevice()


# ── Public API ──────────────────────────────────────────────────────────

def capture_camera_frame(session_id: str, reason: str) -> CameraFrame:
    """
    Captures a single camera frame with full privacy-indicator enforcement.
    Hard-ordered sequence per V7.7:
      1. show indicator
      2. log security event
      3. capture single frame
      4. hide indicator
    No raw frame is persisted beyond processing (V1.8).
    """
    # 1. Indicator BEFORE capture — hard-ordered, not optional
    show_active_capture_indicator(session_id)

    # 2. Security audit log
    logger.info(
        f"SECURITY_AUDIT: camera_access | session={session_id} | "
        f"reason={reason} | timestamp={datetime.utcnow().isoformat()}"
    )

    # 3. Capture
    frame_data = _camera_device.capture_single_frame()
    if frame_data is None:
        hide_active_capture_indicator(session_id)
        raise RuntimeError("Camera capture is unavailable")

    # 4. Hide indicator after processing
    hide_active_capture_indicator(session_id)

    return CameraFrame(
        frame_data=frame_data,
        session_id=session_id,
        captured_at=datetime.utcnow(),
    )
