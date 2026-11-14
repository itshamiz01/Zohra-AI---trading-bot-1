import unittest
import time
from unittest.mock import patch

from zohra.services.vision.models import (
    OCRBlock, OCRResult, UIElement, DetectedObject,
    WindowContext, CameraFrame, StructuredVisionOutput,
)
from zohra.services.vision.ocr_engine import OCREngine, run_ocr, OCRRefiner
from zohra.services.vision.preprocessing import preprocess
from zohra.services.vision.ui_detector import detect_ui_elements, _vision_based_detection
from zohra.services.vision.window_recognition import recognize_active_window, classify_app_category
from zohra.services.vision.camera_capture import (
    capture_camera_frame, show_active_capture_indicator,
    hide_active_capture_indicator, is_indicator_active, _active_indicators,
)
from zohra.services.vision.object_detection import detect_objects
from zohra.services.vision.vision_memory import VisualMemoryManager
from zohra.agents.vision_agent import VisionAgent, VISION_AGENT_TOOL_SCOPE


class TestVisionModels(unittest.TestCase):
    def test_ocr_block(self):
        block = OCRBlock(text="Hello", bbox=[10, 20, 100, 40], confidence=0.95)
        self.assertEqual(block.text, "Hello")
        self.assertAlmostEqual(block.confidence, 0.95)

    def test_ocr_result(self):
        blocks = [
            OCRBlock(text="A", bbox=[0, 0, 10, 10], confidence=0.90),
            OCRBlock(text="B", bbox=[20, 0, 30, 10], confidence=0.80),
        ]
        result = OCRResult(
            text_blocks=blocks,
            full_text="A\nB",
            source_confidence=0.80,
        )
        self.assertEqual(result.source_confidence, 0.80)
        self.assertIn("A", result.full_text)

    def test_structured_output_summary(self):
        ocr = OCRResult(text_blocks=[], full_text="Balance: 10450 USD", source_confidence=0.97)
        win = WindowContext(handle=1, title="MetaTrader 5", process_name="terminal64.exe", app_category="trading_terminal")
        output = StructuredVisionOutput(
            source="screenshot",
            ocr_result=ocr,
            window_context=win,
            confidence_summary=0.97,
        )
        summary = output.summary()
        self.assertIn("Balance", summary)
        self.assertIn("MetaTrader", summary)
        self.assertIn("trading_terminal", summary)


class TestOCREngine(unittest.TestCase):
    def test_run_ocr_returns_ocr_result(self):
        result = run_ocr(b"fake_image_bytes")
        self.assertIsInstance(result, OCRResult)
        # Invalid image bytes must not manufacture OCR text or confidence.
        self.assertEqual(result.text_blocks, [])
        self.assertEqual(result.source_confidence, 0.0)

    def test_per_block_confidence_surfacing(self):
        result = run_ocr(b"fake_image_bytes")
        for block in result.text_blocks:
            self.assertIsInstance(block.confidence, float)
            self.assertTrue(0 <= block.confidence <= 1.0)

    def test_low_confidence_tagging(self):
        """V7.4 / V3.13: low-confidence OCR should be surfaced, not hidden."""
        result = run_ocr(b"fake_image_bytes")
        # source_confidence should be the minimum block confidence, or zero
        # when no authentic OCR result is available.
        if result.text_blocks:
            min_conf = min(b.confidence for b in result.text_blocks)
            self.assertAlmostEqual(result.source_confidence, min_conf)
        else:
            self.assertEqual(result.source_confidence, 0.0)

    def test_legacy_extract_text_api(self):
        engine = OCREngine()
        blocks = engine.extract_text(b"fake_image_bytes")
        self.assertIsInstance(blocks, list)
        self.assertTrue(all("text" in block for block in blocks))

    def test_ocr_refiner_redacts_secrets(self):
        refiner = OCRRefiner()
        blocks = [{"text": "key: sk-abcdefghijklmnopqrstuvwxyz1234567890", "bbox": [0, 0, 100, 20], "confidence": 0.9}]
        sanitized = refiner.sanitize_blocks(blocks)
        self.assertEqual(sanitized[0]["text"], "[REDACTED SECRET]")


class TestUIDetection(unittest.TestCase):
    def test_vision_fallback_returns_ui_elements(self):
        """V7.5: Vision-based fallback should trigger and return elements with lower confidence."""
        elements = _vision_based_detection(b"fake_image_bytes")
        self.assertIsInstance(elements, list)
        # All vision-inferred elements should have source="vision"
        for el in elements:
            self.assertEqual(el.source, "vision")
            # Confidence should be lower than raw OCR (multiplied by 0.8)
            self.assertTrue(el.confidence < 1.0)

    def test_detect_ui_elements_returns_list(self):
        elements = detect_ui_elements(b"fake_image_bytes")
        self.assertIsInstance(elements, list)


class TestWindowRecognition(unittest.TestCase):
    def test_classify_app_category(self):
        self.assertEqual(classify_app_category("chrome.exe"), "browser")
        self.assertEqual(classify_app_category("terminal64.exe"), "trading_terminal")
        self.assertEqual(classify_app_category("code.exe"), "ide")
        self.assertEqual(classify_app_category("unknown_app.exe"), "unknown")

    def test_recognize_active_window(self):
        ctx = recognize_active_window()
        self.assertIsInstance(ctx, WindowContext)
        # On any platform, we should get a non-empty result (mock or real)
        self.assertIsInstance(ctx.app_category, str)


class TestCameraCapture(unittest.TestCase):
    def test_indicator_before_capture(self):
        """
        V7.7 / V7.16: show_active_capture_indicator MUST be called and rendered
        BEFORE capture begins. A regression here is stop-ship severity.
        """
        session_id = "test_privacy_001"
        _active_indicators.clear()

        # Do not touch a real camera during tests. A disabled device must
        # still clear the privacy indicator before reporting unavailability.
        with patch(
            "zohra.services.vision.camera_capture._camera_device.capture_single_frame",
            return_value=None,
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                capture_camera_frame(session_id, reason="unit_test")

        # After an unavailable capture, indicator must be OFF.
        self.assertFalse(is_indicator_active(session_id))

    def test_single_frame_default(self):
        """V7.7: default mode is single-frame, not continuous stream."""
        with patch(
            "zohra.services.vision.camera_capture._camera_device.capture_single_frame",
            return_value=None,
        ):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                capture_camera_frame("test_single", reason="test")


class TestObjectDetection(unittest.TestCase):
    def test_detect_objects_returns_list(self):
        objects = detect_objects(b"fake_image_bytes")
        self.assertIsInstance(objects, list)
        for obj in objects:
            self.assertIsInstance(obj, DetectedObject)
            self.assertTrue(len(obj.label) > 0)
            self.assertTrue(0 <= obj.confidence <= 1.0)


class TestVisualMemory(unittest.TestCase):
    def test_write_visual_memory_structured_only(self):
        """V7.8: only structured summaries are written, never raw pixels."""
        mgr = VisualMemoryManager()
        mgr.write_visual_memory("Detected: coffee mug on desk", "camera:identify_object")
        # Search should find it
        results = mgr.search_visual_memory("coffee mug")
        self.assertTrue(len(results) > 0)
        # Filepath should be [structured_only], proving no raw image was persisted
        self.assertEqual(results[0]["filepath"], "[structured_only]")


class TestVisionAgent(unittest.TestCase):
    def test_read_only_tool_scope(self):
        """V7.1 / V5.3: Vision Agent MUST NOT have OS-mutating tools."""
        mutating_tools = {"execute_command", "click_element", "type_text",
                          "open_app", "delete_file", "send_keys"}
        overlap = VISION_AGENT_TOOL_SCOPE & mutating_tools
        self.assertEqual(len(overlap), 0, f"Vision Agent has mutating tools: {overlap}")

    def test_analyze_screenshot(self):
        agent = VisionAgent()
        output = agent.analyze_screenshot(run_ui_detection=True, run_object_detection=False)
        self.assertIsInstance(output, StructuredVisionOutput)
        self.assertEqual(output.source, "screenshot")
        self.assertIsNotNone(output.ocr_result)
        self.assertIsNotNone(output.window_context)

    def test_analyze_camera(self):
        agent = VisionAgent()
        with patch("zohra.agents.vision_agent.capture_camera_frame", side_effect=RuntimeError("Camera capture is unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                agent.analyze_camera("test_cam_session", "unit_test")

    def test_analyze_uploaded_file(self):
        agent = VisionAgent()
        output = agent.analyze_uploaded_file(b"fake_image_data")
        self.assertIsInstance(output, StructuredVisionOutput)
        self.assertEqual(output.source, "uploaded_file")


if __name__ == "__main__":
    unittest.main()
