"""EasyOCR wrapper — lazy-loaded singleton for text extraction from images."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_reader = None  # module-level singleton


class OCREngine:
    """Wraps EasyOCR for text detection and recognition."""

    def __init__(self):
        self._reader = None
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        import easyocr

        logger.info("Loading EasyOCR (English)…")
        self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        self._loaded = True
        logger.info("EasyOCR loaded")

    def extract_text(self, image_path: Path) -> tuple[str, float]:
        """
        Extract text from an image.

        Returns (text, avg_confidence).
        Text is all detected text joined with spaces.
        """
        self.load()
        results = self._reader.readtext(str(image_path), detail=1)

        if not results:
            return ("", 0.0)

        texts = []
        confidences = []
        for bbox, text, conf in results:
            texts.append(text.strip())
            confidences.append(conf)

        combined = " ".join(t for t in texts if t)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return (combined, round(avg_conf, 4))


def get_ocr_engine() -> OCREngine:
    global _reader
    if _reader is None:
        _reader = OCREngine()
    return _reader
