# ZOHRA OS — Screen Capture Manager
import logging
import io
import time
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("zohra.vision.capture")

class ScreenCaptureManager:
    """
    Manages capturing desktop screen frames.
    Uses 'mss' for high-performance multi-monitor capture,
    with a fallback to PIL ImageGrab.
    """
    def __init__(self):
        self.mss_client = None
        self._init_capture()

    def _init_capture(self):
        try:
            import mss
            self.mss_client = mss.mss()
            logger.info("MSS Screen Capture initialized successfully.")
        except ImportError:
            logger.warning("MSS library not found. Falling back to PIL ImageGrab (higher latency).")
            self.mss_client = None

    def capture_frame(self, monitor_idx: int = 1) -> Tuple[bytes, Dict[str, Any]]:
        """
        Captures the current screen frame.
        Returns: Tuple[png_bytes, metadata]
        """
        start_time = time.time()
        
        try:
            if self.mss_client:
                monitors = self.mss_client.monitors
                if monitor_idx < len(monitors):
                    monitor = monitors[monitor_idx]
                else:
                    monitor = monitors[0] # Fallback to primary
                    
                sct_img = self.mss_client.grab(monitor)
                import mss.tools
                png_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                
                metadata = {
                    "width": sct_img.width,
                    "height": sct_img.height,
                    "monitor": monitor_idx,
                    "latency_ms": int((time.time() - start_time) * 1000)
                }
                return png_bytes, metadata
            else:
                # PIL Fallback
                from PIL import ImageGrab
                # ImageGrab.grab() captures the primary screen
                img = ImageGrab.grab()
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                png_bytes = img_byte_arr.getvalue()
                
                metadata = {
                    "width": img.width,
                    "height": img.height,
                    "monitor": 0,
                    "latency_ms": int((time.time() - start_time) * 1000)
                }
                return png_bytes, metadata
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            # Return a tiny 1x1 black pixel PNG as ultimate fallback
            fallback_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
            return fallback_png, {"width": 1, "height": 1, "monitor": 0, "latency_ms": 0, "error": str(e)}
            
    def close(self):
        if self.mss_client:
            self.mss_client.close()
            self.mss_client = None
