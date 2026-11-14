# ZOHRA OS — Vision Preprocessing Pipeline (V7.3)
import logging
import io

logger = logging.getLogger("zohra.vision.preprocessing")


def preprocess(image_bytes: bytes, max_dimension: int = 1920) -> bytes:
    """
    Preprocesses raw image bytes: resize to bounded dimension, convert to RGB,
    normalize to PNG for downstream analysis.
    Returns processed PNG bytes.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed (strip alpha, handle grayscale)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if either dimension exceeds max
        w, h = img.size
        if w > max_dimension or h > max_dimension:
            scale = max_dimension / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.debug(f"Resized image from {w}x{h} to {new_w}x{new_h}")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        logger.warning("PIL not available — returning raw bytes without preprocessing.")
        return image_bytes
    except Exception as e:
        logger.error(f"Preprocessing failed: {e} — returning raw bytes.")
        return image_bytes
