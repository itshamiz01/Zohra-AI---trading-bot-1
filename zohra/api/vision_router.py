# ZOHRA OS — Vision API Router & Management Gateway
import logging
import base64
import os
import time
from typing import Optional

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from zohra.services.vision.screen_capture import ScreenCaptureManager
    from zohra.services.vision.ocr_engine import OCREngine
    from zohra.services.vision.chart_vision import TradingChartVision
    from zohra.services.vision.vision_memory import VisualMemoryManager

    logger = logging.getLogger("zohra.api.vision")
    router = APIRouter(prefix="/api/v1/vision", tags=["Vision Division Services"])
    
    capture_manager = ScreenCaptureManager()
    ocr_engine = OCREngine()
    chart_vision = TradingChartVision()
    memory_manager = VisualMemoryManager()

    @router.get("/capture")
    async def capture_and_analyze(monitor: int = 1):
        """
        Captures the screen, runs OCR and Trading Chart Vision,
        stores the record in Visual Memory, and returns base64 image + metadata.
        """
        try:
            # 1. Capture screen
            png_bytes, meta = capture_manager.capture_frame(monitor)
            if meta.get("error"):
                raise HTTPException(status_code=503, detail="Screen capture unavailable")
            
            # 2. Run OCR
            ocr_blocks = ocr_engine.extract_text(png_bytes)
            
            # 3. Run Chart Vision
            chart_data = chart_vision.analyze_chart(png_bytes)
            
            # 4. Save to Visual Memory
            # Save screenshot frame to disk under logs/screenshots
            os.makedirs("logs/screenshots", exist_ok=True)
            filepath = f"logs/screenshots/snap_{int(time.time())}.png"
            with open(filepath, "wb") as f:
                f.write(png_bytes)
                
            from zohra.services.vision.window_recognition import recognize_active_window
            window_title = recognize_active_window().title
            memory_manager.store_screenshot(filepath, window_title, ocr_blocks, monitor)
            
            # 5. Base64 Encode image for UI rendering
            base64_img = base64.b64encode(png_bytes).decode("utf-8")
            
            return {
                "status": "success",
                "metadata": meta,
                "ocr_blocks": ocr_blocks,
                "chart_analysis": chart_data,
                "image": f"data:image/png;base64,{base64_img}"
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Vision capture and analysis failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/search")
    async def search_vision(q: str):
        """Searches visual memory by query text."""
        try:
            results = memory_manager.search_visual_memory(q)
            return {"status": "success", "results": results}
        except Exception as e:
            logger.error(f"Vision search failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/diagnostics")
    async def run_vision_diagnostics():
        """Triggers a self-test of all vision components."""
        try:
            return {
                "status": "success",
                "diagnostics": {
                    "capture_engine": "mss" if capture_manager.mss_client else "PIL ImageGrab",
                    "ocr_engine": "ready" if ocr_engine.reader else "unavailable",
                    "capture_state": "idle",
                    "chart_analysis": "Pixel color analysis only; price levels unavailable"
                }
            }
        except Exception as e:
            logger.error(f"Vision diagnostics failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
else:
    router = None
