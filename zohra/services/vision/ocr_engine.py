# ZOHRA OS — OCR Engine (V7.4)
import logging
import time
from typing import List, Dict, Any, Literal

from zohra.services.vision.models import OCRBlock, OCRResult

logger = logging.getLogger("zohra.vision.ocr")


class OCREngine:
    """
    Extracts text and bounding boxes from image bytes.
    Supports EasyOCR and Tesseract, with a robust local fallback.
    """
    def __init__(self, provider: str = "local"):
        self.provider = provider.lower()
        self.reader = None
        self._init_ocr()

    def _init_ocr(self):
        if self.provider == "easyocr":
            try:
                import easyocr
                # Initialize local EasyOCR reader (English by default)
                self.reader = easyocr.Reader(['en'], gpu=True)
                logger.info("EasyOCR Engine initialized successfully (GPU enabled if available).")
            except Exception as e:
                logger.warning(f"Failed to load EasyOCR: {e}. Falling back to text extraction stub.")
                self.reader = None
        else:
            logger.info("Using local OCR text extraction stub.")
            self.reader = None

    def extract(self, image_bytes: bytes) -> OCRResult:
        """
        Processes image and returns an OCRResult with per-block confidence.
        Latency budget: ≤2s for a full-screen screenshot on reference hardware.
        """
        start_time = time.time()

        if self.reader:
            try:
                results = self.reader.readtext(image_bytes)
                blocks = []
                for bbox, text, conf in results:
                    x1, y1 = bbox[0]
                    x2, y2 = bbox[2]
                    blocks.append(OCRBlock(
                        text=text,
                        bbox=[int(x1), int(y1), int(x2), int(y2)],
                        confidence=float(conf)
                    ))
                latency = int((time.time() - start_time) * 1000)
                logger.debug(f"OCR processed in {latency}ms. Found {len(blocks)} blocks.")
                return self._assemble_result(blocks)
            except Exception as e:
                logger.error(f"EasyOCR extraction failed: {e}")

        # Tesseract is optional. Missing OCR must never invent text or balances.
        try:
            import io
            import pytesseract
            from PIL import Image
            data = pytesseract.image_to_data(Image.open(io.BytesIO(image_bytes)), output_type=pytesseract.Output.DICT)
            blocks = []
            for i, text in enumerate(data["text"]):
                if not text.strip() or float(data["conf"][i]) < 0:
                    continue
                x, y = data["left"][i], data["top"][i]
                blocks.append(OCRBlock(text=text, bbox=[x, y, x + data["width"][i], y + data["height"][i]],
                                       confidence=float(data["conf"][i]) / 100))
            return self._assemble_result(blocks)
        except (ImportError, OSError, ValueError) as exc:
            logger.warning("OCR unavailable: %s", exc)
            return self._assemble_result([])

    def extract_text(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Legacy API — returns dicts for backward compatibility."""
        result = self.extract(image_bytes)
        return [{"text": b.text, "bbox": b.bbox, "confidence": b.confidence} for b in result.text_blocks]

    @staticmethod
    def _assemble_result(blocks: List[OCRBlock]) -> OCRResult:
        full_text = "\n".join(b.text for b in blocks)
        source_conf = min(b.confidence for b in blocks) if blocks else 0.0
        return OCRResult(
            text_blocks=blocks,
            full_text=full_text,
            source_confidence=source_conf,
        )


class OCRRefiner:
    """Post-processes OCR outputs (redacting secrets)."""
    def __init__(self):
        import re
        self.secret_patterns = [
            re.compile(r'sk-[a-zA-Z0-9]{32,}', re.IGNORECASE),
            re.compile(r'gsk_[a-zA-Z0-9]{32,}', re.IGNORECASE)
        ]

    def sanitize_blocks(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for block in blocks:
            for pattern in self.secret_patterns:
                if pattern.search(block["text"]):
                    block["text"] = "[REDACTED SECRET]"
        return blocks


# ── Top-level convenience function matching V7.4 spec ──────────────────

_local_engine = None
_cloud_engine = None


def run_ocr(image_bytes: bytes, engine: Literal["local", "cloud"] = "local") -> OCRResult:
    """
    Top-level OCR function per V7.4 spec.
    Confidence per block is preserved and passed through to the AI Brain's
    hallucination mitigation (V3.13).
    """
    global _local_engine, _cloud_engine
    if engine == "cloud":
        # Cloud OCR is opt-in per V1.8; for now falls through to local
        logger.info("Cloud OCR requested — falling back to local (cloud provider not configured).")
    if _local_engine is None:
        _local_engine = OCREngine(provider="local")
    return _local_engine.extract(image_bytes)
