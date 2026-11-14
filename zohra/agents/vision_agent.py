# ZOHRA OS — Vision Agent (V7.1, V5.3 — Read-Only by Construction)
import logging
import time
from datetime import datetime
from typing import Optional

from zohra.services.vision.models import (
    StructuredVisionOutput, OCRResult, WindowContext,
)
from zohra.services.vision.preprocessing import preprocess
from zohra.services.vision.ocr_engine import run_ocr
from zohra.services.vision.ui_detector import detect_ui_elements
from zohra.services.vision.window_recognition import recognize_active_window
from zohra.services.vision.object_detection import detect_objects
from zohra.services.vision.camera_capture import capture_camera_frame
from zohra.services.vision.screen_capture import ScreenCaptureManager
from zohra.services.vision.vision_memory import VisualMemoryManager
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.agents.vision")

# Read-only tool scope — NO OS-mutating capabilities (V5.3, V5.10, V7.1)
VISION_AGENT_TOOL_SCOPE = frozenset([
    "capture_screenshot",
    "capture_camera_frame",
    "run_ocr",
    "detect_ui_elements",
    "detect_objects",
    "recognize_active_window",
    # NO: "execute_command", "click_element", "type_text", "open_app", etc.
])


class VisionAgent:
    """
    Read-only Vision Agent (V7.1).
    Orchestrates: preprocess → route → analyse → assemble StructuredVisionOutput
                  → publish to Event Bus → write visual memory.

    Cannot itself trigger OS actions — it only produces structured observations
    that other agents (Automation Agent V8) act on.
    """
    def __init__(self):
        self.screen_capture = ScreenCaptureManager()
        self.visual_memory = VisualMemoryManager()
        self.tool_scope = VISION_AGENT_TOOL_SCOPE
        logger.info("Vision Agent initialized (read-only construction).")

    def analyze_screenshot(
        self,
        run_ui_detection: bool = True,
        run_object_detection: bool = False,
    ) -> StructuredVisionOutput:
        """
        Full screenshot analysis pipeline (V7.9):
        capture → preprocess → OCR → UI detection → window recognition
        → assemble structured output → publish → write memory.
        """
        start = time.time()

        # 1. Capture
        png_bytes, meta = self.screen_capture.capture_frame()

        # 2. Preprocess
        processed = preprocess(png_bytes)

        # 3. Window Recognition
        window_ctx = recognize_active_window()

        # 4. OCR
        ocr_result = run_ocr(processed)

        # 5. UI Element Detection (optional)
        ui_elements = None
        if run_ui_detection:
            ui_elements = detect_ui_elements(processed)

        # 6. Object Detection (optional)
        detected_objects = None
        if run_object_detection:
            detected_objects = detect_objects(processed)

        # 7. Assemble
        output = StructuredVisionOutput(
            source="screenshot",
            ocr_result=ocr_result,
            ui_elements=ui_elements,
            detected_objects=detected_objects,
            window_context=window_ctx,
            captured_at=datetime.utcnow(),
            confidence_summary=ocr_result.source_confidence if ocr_result else 0.0,
        )

        latency_ms = int((time.time() - start) * 1000)
        logger.info(f"Screenshot analysis completed in {latency_ms}ms")

        # 8. Write visual memory (structured only — never raw pixels)
        self.visual_memory.write_visual_memory(output.summary(), "screenshot")

        return output

    def analyze_camera(self, session_id: str, reason: str) -> StructuredVisionOutput:
        """
        Camera single-frame analysis pipeline (V7.7):
        indicator → capture → preprocess → OCR → object detection
        → assemble → publish → write memory.
        """
        # Capture with full privacy enforcement (indicator shown before capture)
        frame = capture_camera_frame(session_id, reason)

        # Preprocess
        processed = preprocess(frame.frame_data)

        # OCR
        ocr_result = run_ocr(processed)

        # Object Detection
        detected_objects = detect_objects(processed)

        # Assemble
        output = StructuredVisionOutput(
            source="camera",
            ocr_result=ocr_result,
            detected_objects=detected_objects,
            captured_at=frame.captured_at,
            confidence_summary=ocr_result.source_confidence if ocr_result else 0.0,
        )

        # Write visual memory (structured only)
        self.visual_memory.write_visual_memory(output.summary(), f"camera:{reason}")

        return output

    def analyze_uploaded_file(self, image_bytes: bytes) -> StructuredVisionOutput:
        """Analyzes an uploaded image file through the standard pipeline."""
        processed = preprocess(image_bytes)
        ocr_result = run_ocr(processed)
        detected_objects = detect_objects(processed)

        output = StructuredVisionOutput(
            source="uploaded_file",
            ocr_result=ocr_result,
            detected_objects=detected_objects,
            captured_at=datetime.utcnow(),
            confidence_summary=ocr_result.source_confidence if ocr_result else 0.0,
        )

        self.visual_memory.write_visual_memory(output.summary(), "uploaded_file")
        return output
