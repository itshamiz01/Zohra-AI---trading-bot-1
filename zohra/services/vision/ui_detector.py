# ZOHRA OS — UI Element Detector (V7.5)
import logging
from typing import List

from zohra.services.vision.models import UIElement, OCRBlock
from zohra.services.vision.ocr_engine import run_ocr

logger = logging.getLogger("zohra.vision.ui_detector")


# ── Accessibility API (Primary — V7.5) ─────────────────────────────────

def _read_accessibility_tree() -> List[UIElement]:
    """
    Reads the Windows UI Automation accessibility tree for the foreground window.
    Primary method — structurally more reliable (exact element identity).
    """
    try:
        import ctypes
        import ctypes.wintypes

        # Get foreground window handle
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return []

        # Attempt to use pywinauto or uiautomation for tree reading
        try:
            import uiautomation as auto
            control = auto.ControlFromHandle(hwnd)
            if not control:
                return []

            elements = []
            for child in control.GetChildren():
                etype = child.ControlTypeName or "unknown"
                name = child.Name or ""
                rect = child.BoundingRectangle
                bbox = [rect.left, rect.top, rect.right, rect.bottom]
                elements.append(UIElement(
                    element_type=etype.lower(),
                    bbox=bbox,
                    label_text=name,
                    confidence=1.0,
                    source="accessibility",
                ))
            logger.info(f"Accessibility tree read: {len(elements)} elements found.")
            return elements
        except ImportError:
            logger.debug("uiautomation library not available.")
            return []
    except Exception as e:
        logger.debug(f"Accessibility API read failed: {e}")
        return []


# ── Vision-Based Fallback (V7.5) ───────────────────────────────────────

def _match_ocr_text_to_bounding_box(
    element_bbox: List[int], text_blocks: List[OCRBlock]
) -> str:
    """Matches OCR text blocks that overlap a UI element bounding box."""
    ex1, ey1, ex2, ey2 = element_bbox
    for block in text_blocks:
        bx1, by1, bx2, by2 = block.bbox
        # Check overlap
        if bx1 < ex2 and bx2 > ex1 and by1 < ey2 and by2 > ey1:
            return block.text
    return ""


def _vision_based_detection(image_bytes: bytes) -> List[UIElement]:
    """
    Fallback: infers UI elements from pixel analysis + OCR label matching.
    Used when the target app doesn't expose a usable accessibility tree.
    Tagged with lower confidence per V7.5.
    """
    ocr_result = run_ocr(image_bytes)

    elements = []
    # Heuristic: each OCR block with certain keywords is treated as a UI element
    button_keywords = {"ok", "cancel", "save", "submit", "buy", "sell", "close",
                       "open", "apply", "yes", "no", "delete", "confirm", "next",
                       "back", "login", "sign in", "sign up"}
    for block in ocr_result.text_blocks:
        text_lower = block.text.strip().lower()
        if text_lower in button_keywords or len(text_lower) <= 15:
            etype = "button" if text_lower in button_keywords else "label"
            elements.append(UIElement(
                element_type=etype,
                bbox=block.bbox,
                label_text=block.text,
                confidence=block.confidence * 0.8,  # Lower confidence for vision-inferred
                source="vision",
            ))

    logger.info(f"Vision-based UI detection fallback: {len(elements)} elements inferred.")
    return elements


# ── Public API ──────────────────────────────────────────────────────────

def detect_ui_elements(screenshot_bytes: bytes) -> List[UIElement]:
    """
    Detects UI elements using accessibility API first, falling back to
    vision-based detection if the tree is empty or unavailable.
    """
    elements = _read_accessibility_tree()
    if elements:
        return elements

    # Fallback
    logger.info("Accessibility tree empty/unavailable — using vision-based fallback.")
    return _vision_based_detection(screenshot_bytes)
