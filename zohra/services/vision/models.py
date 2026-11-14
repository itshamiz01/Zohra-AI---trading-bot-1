# ZOHRA OS — Vision Intelligence Data Models (V7.11)
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class OCRBlock(BaseModel):
    """A single detected text region with bounding box and confidence."""
    text: str
    bbox: List[int] = Field(description="[x1, y1, x2, y2]")
    confidence: float


class OCRResult(BaseModel):
    """Aggregated OCR output across all detected text blocks."""
    text_blocks: List[OCRBlock] = []
    full_text: str = ""
    source_confidence: float = 0.0


class UIElement(BaseModel):
    """A detected UI element (button, textbox, menu, etc.)."""
    element_type: str  # "button", "textbox", "menu", "checkbox", "label", etc.
    bbox: List[int] = Field(description="[x1, y1, x2, y2]")
    label_text: str = ""
    confidence: float = 1.0
    source: Literal["accessibility", "vision"] = "vision"


class DetectedObject(BaseModel):
    """An object detected in an image frame."""
    label: str
    bbox: List[int] = Field(description="[x1, y1, x2, y2]")
    confidence: float


class WindowContext(BaseModel):
    """Active window metadata used by the Context Manager (V3.5)."""
    handle: int = 0
    title: str = ""
    process_name: str = ""
    app_category: str = "unknown"  # "ide", "browser", "office_suite", "trading_terminal", "game", etc.


class CameraFrame(BaseModel):
    """A single camera capture with audit metadata."""
    frame_data: bytes = b""
    session_id: str = ""
    captured_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True


class StructuredVisionOutput(BaseModel):
    """
    Composite vision output assembled from all analysis pipelines.
    This is the canonical data structure published to the Event Bus
    and consumed by the AI Brain via the Context Manager (V3.5).
    """
    source: Literal["screenshot", "camera", "uploaded_file"]
    ocr_result: Optional[OCRResult] = None
    ui_elements: Optional[List[UIElement]] = None
    detected_objects: Optional[List[DetectedObject]] = None
    window_context: Optional[WindowContext] = None
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    confidence_summary: float = 0.0

    def summary(self) -> str:
        """Produces a human-readable summary for visual memory writes."""
        parts = []
        if self.ocr_result and self.ocr_result.full_text:
            parts.append(f"Text: {self.ocr_result.full_text[:200]}")
        if self.ui_elements:
            labels = [e.label_text for e in self.ui_elements if e.label_text]
            if labels:
                parts.append(f"UI elements: {', '.join(labels[:10])}")
        if self.detected_objects:
            obj_labels = [o.label for o in self.detected_objects]
            parts.append(f"Objects: {', '.join(obj_labels[:10])}")
        if self.window_context:
            parts.append(f"Window: {self.window_context.title} ({self.window_context.app_category})")
        return "; ".join(parts) if parts else "No structured observations."
